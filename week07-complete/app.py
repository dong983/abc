import base64
import os
import uuid
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
import os
import sqlite3
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, session
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from opendata import fetch_air_quality
import openai
from openai import OpenAI
import neis

load_dotenv()

client = OpenAI()
MODEL = os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini"

SYSTEM_PROMPT = (
    "너는 학교생활 도우미 '반장'이야. "
    "오직 제공된 공지와 데이터에 근거해서만 답변해. "
    "공지에 명시되지 않은 날짜, 장소, 준비물은 절대로 추측하지 말고 '확인 필요'라고 표시해."
)

CHAT_PROMPT = (
    "너는 학교생활 도우미 '반장'이야. 친절하고 간결하게 답해. "
    "사용자가 대화 중에 알려준 공지·일정·준비물은 기억해서 답에 사용해. "
    "대화에 없는 날짜, 장소, 준비물은 절대로 추측하지 말고 '확인 필요'라고 표시해."
)

IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
MAX_HISTORY = 20
user_chats: dict[str, list[dict]] = {}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
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



class AIError(Exception):
    """사용자 화면 표시용 AI 에러 클래스"""

def ask(user_input, instructions=SYSTEM_PROMPT) -> str:
    try:
        response = client.responses.create(
            model=MODEL,
            instructions=instructions,
            input=user_input,
            temperature=0.2,
        )
    except openai.AuthenticationError:
        raise AIError("API 키가 올바르지 않아요. OPENAI_API_KEY 환경 변수를 확인하세요.")
    except openai.RateLimitError:
        raise AIError("요청이 너무 많거나 사용 한도를 넘었어요. 잠시 뒤에 다시 시도하세요.")
    except openai.OpenAIError as e:
        raise AIError(f"AI 호출 중 오류가 났어요. ({type(e).__name__})")
    return response.output_text

def get_user_key() -> str:
    if "user_key" not in session:
        session["user_key"] = str(uuid.uuid4())
    return session["user_key"]

def chat_with_history(user_key: str, message: str) -> str:
    history = user_chats.setdefault(user_key, [])
    history.append({"role": "user", "content": message})
    try:
        reply = ask(history, instructions=CHAT_PROMPT)
    except AIError:
        history.pop()
        raise
    history.append({"role": "assistant", "content": reply})
    del history[:-MAX_HISTORY]
    return reply

def brief_meal(school_name: str, meal: dict) -> str:
    allergy_table = ", ".join(f"{n}.{name}" for n, name in neis.ALLERGY_CODES.items())
    prompt = (
        f"아래는 나이스(NEIS) 공식 API에서 가져온 {school_name}의 오늘 {meal['meal_name']} 원문이야.\n"
        "이 원문에만 근거해서 답하고, 원문에 없는 메뉴·수치는 지어내지 말고 '확인 필요'라고 써.\n"
        f"[알레르기 번호표] {allergy_table}\n"
        f"[메뉴 원문]\n{meal['menu']}\n"
        f"[칼로리] {meal['calorie'] or '정보 없음'}\n"
        f"[영양정보]\n{meal['nutrition'] or '정보 없음'}\n\n"
        "1) 오늘 급식을 1~2문장으로 요약해줘.\n"
        "2) 메뉴 뒤 괄호 숫자는 알레르기 번호야. 번호표로 풀이해서 주의할 메뉴를 알려줘.\n"
        "3) 칼로리·영양정보가 있으면 짧게 해설해줘.\n"
        "마크다운 기호(#, *, **)는 쓰지 말고 일반 문장과 줄바꿈으로만 써."
    )
    return ask(prompt)

def summarize_notice(notice: str) -> str:
    prompt = (
        "아래 공지를 [일정 / 할 일 / 준비물] 순서로 간결하게 정리해줘.\n"
        "공지에 없는 항목은 '확인 필요'라고 써. 마크다운 기호는 쓰지 마.\n"
        f"공지: {notice}"
    )
    return ask(prompt)

def analyze_image(file_storage) -> str:
    ext = os.path.splitext(file_storage.filename or "")[1].lower()
    mime = IMAGE_MIME.get(ext)
    if mime is None:
        raise AIError("JPG 또는 PNG 사진만 올릴 수 있어요.")

    image_b64 = base64.b64encode(file_storage.read()).decode("ascii")
    prompt = (
        "이 시간표/안내문 사진을 분석해 줘. "
        "1) 전체 일정이나 시간표 목록을 텍스트로 표기하고, "
        "2) 챙겨야 할 준비물을 요약해 줘. "
        "글자가 흐려 식별할 수 없는 부분은 '확인 필요'라고 표시하고, 사진에 없는 내용은 절대 지어내지 마. "
        "마크다운 기호는 쓰지 마."
    )
    message = [{
        "role": "user",
        "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:{mime};base64,{image_b64}"},
        ],
    }]
    return ask(message)

@app.route("/chatbot", methods=["GET", "POST"])
def chatbot():
    user_key = get_user_key()
    view = {
        "school_name": "", "meal_school": None, "meal": None, "ai_meal": None,
        "notice_text": "", "summary": None, "image_result": None, "errors": {},
    }

    if request.method == "POST":
        action = request.form.get("action")

        if action == "meal":
            view["school_name"] = request.form.get("school_name", "").strip()
            school = neis.get_school_code(view["school_name"]) if view["school_name"] else None
            if school is None:
                view["errors"]["meal"] = "학교를 찾지 못했어요. 정확한 학교 이름(예: 경기고등학교)을 입력하세요."
            else:
                office_code, school_code, school_full_name = school
                view["meal_school"] = school_full_name
                view["meal"] = neis.get_today_meal(office_code, school_code)
                if view["meal"] is None:
                    view["errors"]["meal"] = "오늘 급식 정보가 등록되지 않았습니다. (주말·방학·휴업일일 수 있어요)"
                else:
                    try:
                        view["ai_meal"] = brief_meal(school_full_name, view["meal"])
                    except AIError as e:
                        view["errors"]["ai_meal"] = str(e)

        elif action == "notice":
            view["notice_text"] = request.form.get("notice_text", "").strip()
            if not view["notice_text"]:
                view["errors"]["notice"] = "공지 내용을 입력하세요."
            else:
                try:
                    view["summary"] = summarize_notice(view["notice_text"])
                except AIError as e:
                    view["errors"]["notice"] = str(e)

        elif action == "image":
            photo = request.files.get("photo")
            if photo is None or photo.filename == "":
                view["errors"]["image"] = "사진 파일을 선택하세요."
            else:
                try:
                    view["image_result"] = analyze_image(photo)
                except AIError as e:
                    view["errors"]["image"] = str(e)

    return render_template("index.html", history=user_chats.get(user_key, []), **view)

@app.route("/chatbot/chat", methods=["POST"])
def chatbot_chat():
    user_key = get_user_key()
    message = request.form.get("message", "").strip()

    if not message:
        return jsonify({"reply": "질문을 입력하세요."}), 400
    if message == "초기화":
        user_chats.pop(user_key, None)
        return jsonify({"reply": "[시스템] 대화 문맥이 초기화되었습니다."})

    try:
        return jsonify({"reply": chat_with_history(user_key, message)})
    except AIError as e:
        return jsonify({"reply": str(e)}), 502

@app.errorhandler(413)
def too_large(_):
    return "사진 용량이 너무 커요(5MB 이하). 뒤로 가서 작은 사진을 올려주세요.", 413

### 이게 항상 맨 밑에 있어야함
### 이게 항상 맨 밑에 있어야함
### 이게 항상 맨 밑에 있어야함
### 이게 항상 맨 밑에 있어야함
if __name__ == "__main__":
    create_tables()
    socketio.run(app, debug=True, port=5001, allow_unsafe_werkzeug=True)
### 이게 항상 맨 밑에 있어야함
### 이게 항상 맨 밑에 있어야함
### 이게 항상 맨 밑에 있어야함
### 이게 항상 맨 밑에 있어야함
