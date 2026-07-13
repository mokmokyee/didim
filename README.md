# DiDim

고등학생과 대학생을 위한 장학금·공모전 탐색 서비스입니다.

DiDim은 Flask나 24시간 실행되는 Python 서버를 사용하지 않습니다. 정적 화면은 Firebase Hosting에서 항상 제공하고, 로그인과 데이터 저장은 Firebase Authentication·Cloud Firestore가 처리합니다. 미등록 검색어는 브라우저가 Gemini Developer API에 직접 매핑을 요청합니다. Python 수집기는 GitHub Actions에서 6시간마다 실행된 뒤 종료됩니다.

## 서비스 주소

- 운영 사이트: <https://didim-5576e.web.app>
- Firebase 프로젝트: `didim-5576e`

## 운영 방식

```text
사용자 브라우저
  ├─ Firebase Hosting: HTML, CSS, JavaScript 제공
  ├─ Firebase Authentication: Google 로그인
  ├─ Cloud Firestore: 공고, 회원정보, 저장목록, 조회 기록
  └─ Gemini Developer API: 미등록 검색어만 표준 키워드로 매핑

GitHub Actions
  ├─ main Push: Hosting과 Firestore 규칙 자동 배포
  └─ 6시간마다: Python 수집기 실행 → Gemini 분류 → Firestore 갱신
```

이 구조는 Gemini Developer API 무료 등급과 Firebase Spark 플랜에서 사용할 수 있습니다. 배포 과정에서 GitHub Secret의 기존 `GEMINI_API_KEY`를 런타임 설정 파일로 생성하므로 키가 Git 저장소에는 커밋되지 않습니다. 단, 정적 웹사이트가 Gemini를 직접 호출하므로 배포된 키는 브라우저 개발자 도구에서 확인할 수 있습니다.

## 주요 기능

- Google 로그인 및 회원 프로필 저장
- 검색 버튼 기반 의미 검색, 필터, 정렬
- 표준 키워드 검색은 상위 분야로 확장하고, 미등록 검색어만 Gemini로 표준 키워드에 매핑
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
│  ├─ data/search_taxonomy.json    # 배포용 표준 검색 키워드
│  ├─ js/api.js                    # Auth·Firestore·Gemini REST API 연동
│  ├─ js/search-resolver.js        # 표준 키워드 직접 판정과 응답 검증
│  ├─ js/firebase-config.js        # 공개 Firebase 설정
│  ├─ js/gemini-runtime-config.example.js # 배포 생성 파일 형식 예시
│  └─ *.html
├─ collector/                      # 예약 실행되는 Python 수집기
│  ├─ data/                        # 분류 체계, 수집 주소, 초기 공고 데이터
│  ├─ services/                    # 수집, Gemini, Firestore 게시 로직
│  └─ main.py
├─ scripts/
│  ├─ sync-search-taxonomy.mjs     # 수집기와 브라우저 검색 분류표 동기화
│  └─ write-gemini-runtime-config.mjs # Secret에서 브라우저 설정 생성
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
npm ci --ignore-scripts
npm run gemini-runtime:write
npm run firebase:serve
```

`gemini-runtime:write`는 루트 `.env`의 `GEMINI_API_KEY`를 읽어 Git에서 제외되는 `public/js/gemini-runtime-config.js`를 만듭니다. 브라우저에서 Emulator가 안내하는 Hosting 주소를 엽니다.

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

## 브라우저 Gemini 검색 설정

검색과 정기 수집은 같은 `GEMINI_API_KEY`를 사용합니다. GitHub 저장소의 `Settings > Secrets and variables > Actions`에 등록된 키를 배포 워크플로가 읽어 `public/js/gemini-runtime-config.js`를 생성한 뒤 Hosting에 올립니다. 이 생성 파일은 `.gitignore`에 포함되어 소스 저장소에는 올라가지 않습니다.

같은 키를 GitHub Actions와 브라우저가 함께 사용하므로 HTTP 리퍼러 제한을 걸면 리퍼러가 없는 GitHub Actions 수집기가 실패합니다. 따라서 이 구성에서 가능한 보호는 다음과 같습니다.

1. Google Cloud API 키 설정에서 키의 API 제한을 `Generative Language API`로 한정합니다.
2. Gemini API 사용량 할당량을 부스 규모에 맞게 낮추고 사용량을 확인합니다.
3. 검색어를 100자로 제한하고, 같은 브라우저의 동일 검색어는 캐시하여 중복 호출을 줄입니다.
4. Gemini 응답은 최대 12개의 표준 키워드만 허용하는 JSON 스키마와 브라우저 검증을 모두 통과해야 사용합니다.

Firebase App Check는 Firebase AI Logic 프록시를 사용할 때 적용할 수 있는 보호이므로, Gemini REST API를 직접 호출하는 현재 방식에는 적용되지 않습니다.

## 자동화

### 사이트 배포

`.github/workflows/deploy-hosting.yml`은 `main` 브랜치가 Push될 때 다음 항목을 배포합니다.

- GitHub Secret에서 브라우저용 Gemini 런타임 설정 생성
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
npm run search-taxonomy:check
node --test tests\search-resolver.test.js
node --check public\js\api.js
node --check public\js\search-resolver.js
node --check public\js\firebase-config.js
node --check scripts\write-gemini-runtime-config.mjs
node --check public\js\main.js
```

## 수동 배포

```powershell
npm ci --ignore-scripts
npm run gemini-runtime:write
npm run firebase:deploy
```

## 보안 주의사항

- `public/js/firebase-config.js`의 Firebase 웹 설정은 브라우저용 공개 설정입니다.
- Firebase 서비스 계정 JSON과 Gemini API 키는 비밀정보입니다.
- Gemini 키의 원본은 GitHub Secrets 또는 로컬 `.env`에만 저장하며 Git에는 커밋하지 않습니다.
- 배포된 `gemini-runtime-config.js`의 키는 브라우저에서 노출됩니다. 클라이언트 암호화는 브라우저가 복호화해야 하므로 실질적인 보호가 되지 않습니다.
- 기존 키 하나를 브라우저와 GitHub Actions가 공유하므로 HTTP 리퍼러 제한은 사용할 수 없습니다. API 제한과 할당량을 반드시 적용합니다.
- Gemini가 반환한 값은 표준 키워드 목록으로 다시 검증합니다.
- 서비스 계정 JSON, `.env`, 생성된 Gemini 런타임 설정, SQLite 파일은 `.gitignore`에서 제외합니다.
- Firestore 접근 권한은 웹 API 키가 아니라 Authentication과 Security Rules로 통제합니다.
