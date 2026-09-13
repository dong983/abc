# 세션·권한 흐름 (예시)

```
[회원가입] username, password 입력
    → password_hash = generate_password_hash(password)
    → INSERT INTO users (username, password_hash)

[로그인] username, password 입력
    → DB에서 username으로 user 조회
    → check_password_hash(user.password_hash, password)
    → 맞으면 session["user_id"], session["username"] 저장

[글쓰기] "user_id" not in session? → /login으로 리다이렉트
    → INSERT INTO posts (..., user_id = session["user_id"])

[수정/삭제] post.user_id == session.get("user_id") ?
    → 아니면 403 "권한 없음"
    → 화면에서도 버튼을 숨기지만, 라우트 안에서도 반드시 검사
```

# 오늘 막혔던 점

- `session.clear()`를 안 하고 로그아웃만 만들었더니 이전 `user_id`가 남아있던 적이 있었다.
- 템플릿에서 버튼만 숨기고 라우트 검사를 빼먹었더니 URL 직접 입력으로 남의 글이 수정됐다.

# 다음에 하고 싶은 것

- 댓글에도 같은 소유권 검사 패턴을 적용해보고 싶다.
