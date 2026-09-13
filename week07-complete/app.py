import os
import sqlite3
from pathlib import Path

from flask import Flask, request, render_template, redirect, url_for, session
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash

from opendata import fetch_air_quality

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
socketio = SocketIO(app)

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "bbs.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            user_id INTEGER,
            is_notice INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (post_id) REFERENCES posts(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    # 8주차까지 없던 컬럼을 이어쓰는 DB에 추가 (한 번만 실행됨)
    for statement in [
        "ALTER TABLE posts ADD COLUMN user_id INTEGER",
        "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'",
        "ALTER TABLE posts ADD COLUMN is_notice INTEGER NOT NULL DEFAULT 0",
    ]:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def get_post_or_404(post_id):
    conn = get_db()
    post = conn.execute(
        "SELECT posts.*, users.username FROM posts "
        "LEFT JOIN users ON posts.user_id = users.id "
        "WHERE posts.id = ?", (post_id,)
    ).fetchone()
    conn.close()
    return post


def require_owner(post):
    """수정 전용: 본인 글만 (관리자도 예외 없음)"""
    if post is None:
        return "글 없음", 404
    if post["user_id"] != session.get("user_id"):
        return "권한 없음", 403
    return None


def require_owner_or_admin(post):
    """삭제 전용: 본인 글이거나 관리자면 허용"""
    if post is None:
        return "글 없음", 404
    is_owner = post["user_id"] == session.get("user_id")
    is_admin = session.get("role") == "admin"
    if not (is_owner or is_admin):
        return "권한 없음", 403
    return None


def require_admin():
    if session.get("role") != "admin":
        return "관리자만 가능합니다", 403
    return None


# ===== 6주차: 목록 (7주차: 작성자 JOIN, 9주차: 검색 + 공지 정렬) =====
@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    conn = get_db()

    if q:
        keyword = f"%{q}%"
        posts = conn.execute("""
            SELECT posts.*, users.username
            FROM posts
            LEFT JOIN users ON posts.user_id = users.id
            WHERE posts.title LIKE ? OR posts.content LIKE ?
            ORDER BY posts.is_notice DESC, posts.id DESC
        """, (keyword, keyword)).fetchall()
    else:
        posts = conn.execute("""
            SELECT posts.*, users.username
            FROM posts
            LEFT JOIN users ON posts.user_id = users.id
            ORDER BY posts.is_notice DESC, posts.id DESC
        """).fetchall()

    conn.close()
    return render_template("list.html", posts=posts, q=q)


# ===== 6주차: 상세 (9주차: 댓글 목록 함께 조회) =====
@app.route("/posts/<int:post_id>")
def detail(post_id):
    post = get_post_or_404(post_id)
    if post is None:
        return "글 없음", 404

    conn = get_db()
    comments = conn.execute("""
        SELECT comments.*, users.username
        FROM comments
        LEFT JOIN users ON comments.user_id = users.id
        WHERE comments.post_id = ?
        ORDER BY comments.id ASC
    """, (post_id,)).fetchall()
    conn.close()

    return render_template("detail.html", post=post, comments=comments)


# ===== 6주차: 작성 (7주차: 로그인 필수 + user_id 저장) =====
@app.route("/new")
def new_form():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("new.html")


@app.route("/posts", methods=["POST"])
def create_post():
    if "user_id" not in session:
        return redirect(url_for("login"))

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()

    if not title or not content:
        return redirect(url_for("new_form"))

    conn = get_db()
    conn.execute(
        "INSERT INTO posts (title, content, user_id) VALUES (?, ?, ?)",
        (title, content, session["user_id"])
    )
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


# ===== 6주차: 수정 (7주차: 본인 글만) =====
@app.route("/posts/<int:post_id>/edit")
def edit_form(post_id):
    post = get_post_or_404(post_id)
    err = require_owner(post)
    if err:
        return err
    return render_template("edit.html", post=post)


@app.route("/posts/<int:post_id>/edit", methods=["POST"])
def update_post(post_id):
    post = get_post_or_404(post_id)
    err = require_owner(post)
    if err:
        return err

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()

    conn = get_db()
    conn.execute(
        "UPDATE posts SET title = ?, content = ? WHERE id = ?",
        (title, content, post_id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("detail", post_id=post_id))


# ===== 6주차: 삭제 (7주차: 본인 글만 -> 9주차: 본인 또는 관리자) =====
@app.route("/posts/<int:post_id>/delete", methods=["POST"])
def delete_post(post_id):
    post = get_post_or_404(post_id)
    err = require_owner_or_admin(post)
    if err:
        return err

    conn = get_db()
    conn.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
    conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


# ===== 9주차: 댓글 =====
@app.route("/posts/<int:post_id>/comments", methods=["POST"])
def create_comment(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    content = request.form.get("content", "").strip()
    if not content:
        return redirect(url_for("detail", post_id=post_id))

    conn = get_db()
    conn.execute(
        "INSERT INTO comments (post_id, user_id, content) VALUES (?, ?, ?)",
        (post_id, session["user_id"], content)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("detail", post_id=post_id))


@app.route("/comments/<int:comment_id>/delete", methods=["POST"])
def delete_comment(comment_id):
    conn = get_db()
    comment = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if comment is None:
        conn.close()
        return "댓글 없음", 404

    is_owner = comment["user_id"] == session.get("user_id")
    is_admin = session.get("role") == "admin"
    if not (is_owner or is_admin):
        conn.close()
        return "권한 없음", 403

    conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("detail", post_id=comment["post_id"]))


# ===== 9주차: 관리자 전용 - 공지 고정/해제 =====
@app.route("/posts/<int:post_id>/notice", methods=["POST"])
def toggle_notice(post_id):
    err = require_admin()
    if err:
        return err

    conn = get_db()
    conn.execute("UPDATE posts SET is_notice = 1 - is_notice WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("detail", post_id=post_id))


# ===== 7주차: 회원가입 · 로그인 · 로그아웃 (9주차: role 세션 저장) =====
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            return render_template("signup.html", error="아이디와 비밀번호를 입력하세요.")

        password_hash = generate_password_hash(password)
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template("signup.html", error="이미 사용 중인 아이디입니다.")
        conn.close()
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("index"))

        return render_template("login.html", error="아이디 또는 비밀번호가 틀립니다.")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


# ===== 8주차: 공공데이터 대시보드 =====
@app.route("/dashboard")
def dashboard():
    sido = request.args.get("sido", "인천")
    rows, source = fetch_air_quality(sido)
    return render_template("dashboard.html", rows=rows, sido=sido, source=source)


# ===== 9주차: 실시간 채팅 (AI 도전 과제로 만든 것) =====
@app.route("/chat")
def chat():
    if "user_id" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    messages = conn.execute(
        "SELECT * FROM chat_messages ORDER BY id DESC LIMIT 30"
    ).fetchall()
    conn.close()
    return render_template("chat.html", messages=list(reversed(messages)))


@socketio.on("send_message")
def handle_send_message(data):
    if "user_id" not in session:
        return
    username = session.get("username", "익명")
    content = (data.get("content") or "").strip()
    if not content:
        return

    conn = get_db()
    conn.execute(
        "INSERT INTO chat_messages (username, content) VALUES (?, ?)",
        (username, content)
    )
    conn.commit()
    conn.close()

    emit("new_message", {"username": username, "content": content}, broadcast=True)


if __name__ == "__main__":
    create_tables()
    socketio.run(app, debug=True, port=5001, allow_unsafe_werkzeug=True)