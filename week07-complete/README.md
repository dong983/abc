# 나만의 BBS (v1) — 회원가입 · 로그인 · 권한

Flask + SQLite 게시판(v0)에 회원가입·로그인·로그아웃과 본인 글만 수정/삭제할 수 있는
권한 검사를 더한 버전입니다.

## 무엇인가요

목록·상세·작성·수정·삭제 + 회원가입·로그인·로그아웃 + 본인 글만 수정/삭제를 갖춘
게시판입니다. 비밀번호는 해시로 저장하고, 세션으로 로그인 상태를 기억합니다. 핵심 기능은
AI 없이 직접 작성했습니다.

## 왜 만들었나요

지난주 BBS는 누구나 글을 쓰고 아무 글이나 고칠 수 있었습니다. "누가 썼는지"와 "누가
고칠 수 있는지"를 코드로 정하고 싶어서 회원·권한 기능을 추가했습니다.

## 어떻게 열어보나요

```
pip install flask
python app.py
```

`http://localhost:5001` 접속.

## 폴더 구조

```
├── app.py
├── templates/
│   ├── list.html / detail.html / new.html / edit.html
│   └── signup.html / login.html
└── notes/
    ├── session-auth.md
    └── why-auth.md
```

## 다음에 할 일

- [ ] 상단 네비 `base.html`로 공통화 (도전 과제)
- [ ] 공공데이터 API 대시보드 추가 (Week8)
