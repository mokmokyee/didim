# DiDim

고등학생과 대학생을 위한 장학금·공모전 탐색 서비스입니다.

DiDim은 Flask나 24시간 실행되는 Python 서버를 사용하지 않습니다. 정적 화면은 Firebase Hosting에서 항상 제공하고, 로그인과 데이터 저장은 Firebase Authentication·Cloud Firestore가 처리합니다. Python 수집기는 GitHub Actions에서 6시간마다 실행된 뒤 종료됩니다.

## 서비스 주소

- 운영 사이트: <https://didim-5576e.web.app>
- Firebase 프로젝트: `didim-5576e`

## 운영 방식

```text
사용자 브라우저
  ├─ Firebase Hosting: HTML, CSS, JavaScript 제공
  ├─ Firebase Authentication: Google 로그인
  └─ Cloud Firestore: 공고, 회원정보, 저장목록, 조회 기록

GitHub Actions
  ├─ main Push: Hosting과 Firestore 규칙 자동 배포
  └─ 6시간마다: Python 수집기 실행 → Gemini 분류 → Firestore 갱신
```

사이트는 Firebase Hosting에서 계속 접속할 수 있습니다. Python 프로그램이 24시간 실행되는 구조가 아니므로 별도의 Flask 서버나 Cloud Run이 필요하지 않습니다.

## 주요 기능

- Google 로그인 및 회원 프로필 저장
- 장학금·공모전 목록, 검색, 필터, 정렬
- 관심 분야와 사용자 정보를 이용한 브라우저 기반 추천
- 프로그램 저장 및 모집 상태별 저장목록
- 로그인 사용자별 조회 기록
- 외부 공고 정기 수집 및 Gemini 기반 분류

## 폴더 구조

```text
DiDim/
├─ public/                         # Firebase Hosting 배포 파일
│  ├─ assets/
│  ├─ css/
│  ├─ data/opportunities.json      # Firestore 장애·초기 상태용 백업 데이터
│  ├─ js/api.js                    # Firebase Auth·Firestore 직접 연동
│  ├─ js/firebase-config.js        # 공개 가능한 Firebase 웹 설정
│  └─ *.html
├─ collector/                      # 예약 실행되는 Python 수집기
│  ├─ data/                        # 분류 체계, 수집 주소, 초기 공고 데이터
│  ├─ services/                    # 수집, Gemini, Firestore 게시 로직
│  └─ main.py
├─ tests/
├─ .github/workflows/
│  ├─ deploy-hosting.yml           # main Push 시 사이트 배포
│  └─ update-opportunities.yml     # 6시간마다 공고 갱신
├─ firebase.json
├─ firestore.rules
├─ firestore.indexes.json
└─ requirements.txt
```

## Firestore 데이터 구조

```text
catalog/opportunities
catalog_chunks/{generationChunk}
opportunities/{opportunityId}
opportunity_views/{opportunityId_uid}
users/{uid}
users/{uid}/saved_opportunities/{opportunityId}
crawl_runs/{runId}
crawl_locks/opportunities
gemini_usage/{kstDate}
```

- `opportunities`, `catalog`, `catalog_chunks`: 누구나 읽을 수 있지만 브라우저에서 수정할 수 없습니다.
- `users/{uid}`와 저장목록: 로그인한 본인만 읽고 수정할 수 있습니다.
- 공고 갱신과 집계: Firebase Admin SDK를 사용하는 GitHub Actions만 수행합니다.
- 자세한 접근 제어는 `firestore.rules`에 정의되어 있습니다.

## 로컬 화면 확인

```powershell
cd C:\Users\mokse\Desktop\DiDim
.\.venv\Scripts\python.exe -m http.server 8000 --directory public
```

브라우저에서 <http://127.0.0.1:8000>을 엽니다. 로컬 화면도 실제 Firebase Authentication과 Firestore를 사용합니다.

## 로컬 수집기 실행

1. `.env.example`을 참고해 루트에 `.env`를 만듭니다.
2. Firebase 서비스 계정 JSON은 저장소에 커밋하지 않습니다.
3. 필요한 Python 패키지를 설치합니다.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

포함된 공고 데이터만 Firestore에 게시:

```powershell
.\.venv\Scripts\python.exe -m collector.main --seed-only
```

외부 사이트를 수집하고 Gemini로 분류한 뒤 게시:

```powershell
.\.venv\Scripts\python.exe -m collector.main
```

## GitHub 최초 연결

1. 빈 비공개 GitHub 저장소를 생성합니다.
2. 저장소의 `Settings > Secrets and variables > Actions`로 이동합니다.
3. 다음 Repository secrets를 등록합니다.

```text
FIREBASE_SERVICE_ACCOUNT_JSON
GEMINI_API_KEY
```

4. 필요한 경우 다음 Repository variable을 등록합니다.

```text
GEMINI_MODEL=gemini-3.1-flash-lite
```

5. 로컬 저장소의 기본 브랜치를 `main`으로 설정하고 Push합니다.

`FIREBASE_SERVICE_ACCOUNT_JSON`에는 서비스 계정 JSON 파일의 전체 내용을 저장합니다. JSON 파일 자체, `.env`, Gemini API 키는 Git에 포함하지 않습니다.

## 자동화

### 사이트 배포

`.github/workflows/deploy-hosting.yml`은 `main` 브랜치가 Push될 때 다음 항목을 배포합니다.

- Firebase Hosting 정적 파일
- Firestore Security Rules
- Firestore 인덱스

### 공고 갱신

`.github/workflows/update-opportunities.yml`은 UTC 기준 `17 */6 * * *` 일정으로 하루 네 번 실행됩니다.

1. 장학금·공모전 출처 수집
2. 변경된 공고 Gemini 분류
3. 조회수와 저장 수 집계
4. Firestore 공고 및 공개 카탈로그 갱신

GitHub Actions의 `Run workflow`에서 `seed_only`를 선택하면 외부 사이트를 수집하지 않고 포함된 초기 데이터만 게시할 수 있습니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
node --check public\js\api.js
node --check public\js\firebase-config.js
node --check public\js\main.js
```

## 수동 배포

```powershell
npm ci --ignore-scripts
npm run firebase:deploy
```

## 보안 주의사항

- `public/js/firebase-config.js`의 Firebase 웹 설정은 브라우저용 공개 설정입니다.
- Firebase 서비스 계정 JSON과 Gemini API 키는 비밀정보입니다.
- 비밀정보는 GitHub Secrets 또는 로컬 `.env`에만 저장합니다.
- 서비스 계정 JSON, `.env`, SQLite 파일은 `.gitignore`에서 제외합니다.
- Firestore 접근 권한은 웹 API 키가 아니라 Authentication과 Security Rules로 통제합니다.
