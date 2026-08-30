from flask import Flask, request, redirect, url_for, render_template, session
from werkzeug.security import generate_password_hash, check_password_hash
import os
app =  Flask(__name__)
app.security_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

import sqlite3
from pathlib import Path

DATEBASE = Path(__file__).resolve().parent / 'bbs.db'

def get_db():
    conn = sqlite3.connect(DATEBASE)
    conn.row_factory = sqlite3.Row
    return conn

def create_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    try:
        conn.execute("ALTER TABLE posts ADD COLUMN user_id INTEGER")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

@app.route('/')
def index():
    conn = get_db()
    posts = conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('list.html', posts=posts)

@app.route("/posts/<int:post_id>")
def detail(post_id):
    conn = get_db()
    post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)
    ).fetchone()
    conn.close()
    return render_template('detail.html', post=post)

@app.route("/new")
def new_from():
    return render_template("new.html")

@app.route("/posts", methods=["POST"])
def create_post():
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()

    conn = get_db()
    conn.execute("INSERT INTO posts (title, content) VALUES (?, ?)", (title, content))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)
        try:
            conn = get_db()
            conn.execute("""
            INSERT INTO user (username, password_hash) VALUES (?, ?)
            """,
            (username, hashed_pw)
            )
            conn.commit()
            conn.close()
            return redirect('/login')
        except:
            return '이미 존재하는 아이디입니다.'
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        user = conn.execute("""SELECT * FROM users WHERE username = ?
        """,
        (username)
        ).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            return redirect('/')
        return '아이디 또는 비밀번호가 틀렸습니다.'
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect('/')

@app.route("/new", methods=["GET", "POST"])
def new():
    if 'user_id' not in session:
        return redirect("/login")

    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        user_id = session["user_id"]
        conn = get_db()
        conn.execute("""
        INSERT INTO posts (title, content, user_id) VALUES (?, ?, ?)
        """,
        (title, content, user_id)
        )
        conn.commit()
        conn.close()
        return redirect("/")
    
    return render_template("new.html")

@app.route("/posts/<int:post_id>/edit")
def edit_form(post_id):
    conn = get_db()
    post = conn.execute(
    "SELECT * FROM posts WHERE id = ?", (post_id, )
    ).fetchone()
    conn.close()
    return render_template("edit.html", post=post)

@app.route("/posts/<int:post_id>/edit", methods=["POST"])
def update_post(post_id):
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()

    conn = get_db()
    conn.execute("UPDATE posts SET title = ?, content = ? WHERE id = ?",
    (title, content, post_id, )
    )
    conn.commit()
    conn.close()
    return redirect(url_for("detail", post_id=post_id))

@app.route("/posts/<int:post_id>/delete", methods=["POST"])
def delete_post(post_id):
    conn = get_db()
    conn.execute("DELETE FROM posts WHERE id = ?", (post_id, ))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

if __name__ == '__main__':
    create_table()
    app.run(debug=True, port=5001)
