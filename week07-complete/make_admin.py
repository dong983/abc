"""
관리자 계정 만들기 — 한 번만 실행.
    python make_admin.py 내아이디
"""
import sqlite3
import sys

if len(sys.argv) < 2:
    print("사용법: python make_admin.py 아이디")
    raise SystemExit(1)

username = sys.argv[1]
conn = sqlite3.connect("bbs.db")
cursor = conn.execute("UPDATE users SET role = 'admin' WHERE username = ?", (username,))
conn.commit()

if cursor.rowcount == 0:
    print(f"'{username}' 계정을 찾을 수 없습니다. 먼저 회원가입하세요.")
else:
    print(f"'{username}' → admin 완료. 로그아웃 후 다시 로그인하면 적용됩니다.")