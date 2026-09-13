# BBS 업그레이드 · 회원가입·로그인·권한 (교사 참고 · 완성 예시)

**수업안:** [../../../weeks/week07-bbs-auth.md](../../../weeks/week07-bbs-auth.md)

학생용 starter는 [../../week07/](../../week07/) 입니다.
이 폴더는 **조교·교사 참고용**입니다. 수업 중(회원·권한을 직접 작성하는 동안)에는 학생에게 통째로 배포하지 않습니다. 단, **수업 종료 직전** 시간 내에 못 끝낸 학생에게는 다음 주(8주차 대시보드)를 같은 출발선에서 시작할 수 있도록 **따라잡기용으로 전달해도 됩니다** — 자세한 기준은 [weeks/week07-bbs-auth.md](../../../weeks/week07-bbs-auth.md)의 "진행 팁"을 참고하세요.

## 이 예시에 대해

[week06-complete](../week06-complete/)의 BBS(v0)를 그대로 이어받아, 수업안 2~5장(🟢 회원가입·
로그인·로그아웃·작성자 연결·본인 글만 수정/삭제, AI 없이 직접)의 참고 코드를 담았습니다.
`bbs.db`는 실행 시 자동 생성되므로 포함하지 않습니다.

> 이 폴더는 이전에 있던 구(舊) 7주차(디자인 패턴·React) 완성본을 대체합니다. 그 예시는
> [week07-design-patterns-complete/](../week07-design-patterns-complete/)에 보관되어 있습니다.
> [week08-complete](../week08-complete/)는 이 폴더(v1)에 공공데이터 대시보드(v2)를 더한
> 다음 단계입니다.

**중요:** 2~5장(회원가입·로그인·작성자 연결·권한 검사)은 학생이 AI 없이 직접 타이핑하는
구간입니다 — 수업 중 이 `app.py`를 통째로 복사해 주지 않습니다.

## 파일

```
week07-complete/
├── ABOUT.md               ← 이 안내 (교사용)
├── README.md              ← 완성된 프로젝트 README 예시
├── app.py                 ← Flask 서버 (CRUD + 회원가입·로그인·권한)
├── templates/
│   ├── list.html          ← 작성자 표시 + 로그인 상태 nav
│   ├── detail.html        ← 본인 글만 수정/삭제 버튼
│   ├── new.html
│   ├── edit.html
│   ├── signup.html        ← 신규
│   └── login.html         ← 신규
└── notes/
    ├── session-auth.md    ← 세션·권한 흐름 예시
    └── why-auth.md        ← 왜 회원 기능을 넣었는가 예시
```

## 실행 방법 (시연용)

```
pip install flask
python app.py
```

`http://localhost:5001` 접속 → 회원가입 → 로그인 → 글쓰기 → 로그아웃 흐름과, 다른 계정으로
로그인해 남의 글 URL에 `/edit`을 직접 입력했을 때 403(또는 로그인 페이지)이 뜨는지 확인.

## 확인 포인트

- app.py: `password`가 아니라 `password_hash`만 DB에 저장되는가?
- app.py: 화면에서 버튼을 숨기는 것과 별개로, `require_owner`로 **라우트 안에서도** 권한을 검사하는가?
- SQL: 값 전달에 전부 `?` 파라미터를 쓰고 있는가?
- notes/session-auth.md: 로그인 → session 저장 → 글쓰기/수정 시 검사 흐름이 학생 눈높이로 구체적인가?
- 학생 결과물에서 2~5장이 **AI 프롬프트 없이** 완성됐는지 (6장 도전 과제만 AI 사용 대상)
