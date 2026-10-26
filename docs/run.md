# 로컬 실행

목표와 취향에 맞춰 하루 식단을 계획하는 서비스를 준비하고 있다. 현재 저장소에서 실행할 수 있는 범위는 다음과 같다.

| 구분 | 현재 범위 |
| --- | --- |
| 음식 API | 이름 검색, 상세 조회, 분량별 영양 계산 |
| 계정 API | 가입·로그인·로그아웃·본인 확인 |
| 설정 API | 계정/체험 설정 조회·저장 |
| 식단 API | 메뉴 조회, 하루 추천·조회, 끼니/구성 음식 변경, 분량 조절, 고정·되돌리기 |
| 화면 | 초기 안내 화면. 검색·로그인·설정 화면은 아직 연결하지 않음 |
| 이후 범위 | 실제 식사 기록·평가·이관, 서비스 화면 연결 |

식단 추천·변경은 서버에 연결됐으며, 실제 식사 기록·평가·이관은 공용 테이블만 준비한 상태다. API 계약은 [음식 자료](food-data.md), [계정과 설정](accounts-settings.md), [식단 추천·변경](planner.md)을 참고한다.

## 처음 준비

Windows PowerShell에서 진행한다. Python 3.13, Node.js 24, pnpm 11.25 환경에서 검증했다. Python·Node.js·pnpm은 미리 설치하며 기본적으로 PATH에서 찾는다.

프로젝트 폴더에서 의존성을 설치한다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.lock
Push-Location frontend
pnpm install --frozen-lockfile
pnpm build
Pop-Location
```

설치 버전은 `backend/requirements.lock`, `frontend/pnpm-lock.yaml`에 고정한다. 이미 구성한 환경은 다시 생성할 필요가 없다.

로컬 설정이 없을 때만 예시 파일을 복사한다.

```powershell
if (-not (Test-Path -LiteralPath .runtime.local.json)) {
    Copy-Item -LiteralPath .runtime.example.json -Destination .runtime.local.json
}
```

`.runtime.local.json`의 `postgresql_bin`을 실제 PostgreSQL `pgsql/bin` 절대 경로로 바꾼다. 예시 경로는 설치 위치가 아니다. PostgreSQL 바이너리 준비는 [DB 안내](database.md)를 따른다.

`node`, `pnpm`은 생략하거나 null·빈 문자열로 두면 PATH의 `node`, `pnpm.cmd`에서 각각 찾는다. PATH에 없는 경우 실제 실행 파일의 절대 경로를 지정한다. 명시한 경로가 없거나 디렉터리이면 중단하며 다른 실행 파일로 자동 대체하지 않는다. 설정 파일과 비밀값은 Git에 넣지 않는다.

Node는 화면 실행에 필요하다. pnpm은 의존성 설치·빌드에 필요하며, 이미 설치된 화면을 시작할 때 pnpm 미발견만으로 중단하지 않는다. 설정에 pnpm 경로를 직접 적었다면 그 경로의 오류는 그대로 알린다.

기존 데이터 디렉터리나 환경 파일을 지우지 않고 개발·테스트 DB를 준비한다.

```powershell
.\scripts\Setup-Database.ps1
.\scripts\Migrate-Database.ps1 -Target dev
.\scripts\Migrate-Database.ps1 -Target test
.\scripts\Test-Backend.ps1
```

전체 음식 원본이 없어도 자동 테스트는 저장소의 표본과 트랜잭션 내부 시험 자료를 사용한다. 음식이 없는 개발 DB에서 검색 결과가 비어 있는 것은 정상이다. 실제 음식 검색을 사용하려면 [자료 준비 절차](food-data.md)를 따른다. 준비 상태 API 성공은 전체 음식 자료나 추천 기능의 준비 완료를 뜻하지 않는다.

## 시작·확인·중지

```powershell
.\scripts\Start-Dev.ps1
.\scripts\Status-Dev.ps1
.\scripts\Stop-Dev.ps1
```

시작 명령은 서버를 백그라운드에서 실행한다. 로그와 프로세스 정보는 `.local/`에 저장하며 Git에서 제외한다. 중지 명령은 이 체크아웃에서 시작한 프로세스만 대상으로 한다. 다시 시작하면 기존 서버 응답을 확인한다.

- 기본 화면: `http://127.0.0.1:15173`
- API 상태: `http://127.0.0.1:18080/api/health`
- DB 준비 상태: `http://127.0.0.1:18080/api/ready`
- API 문서: `http://127.0.0.1:18080/docs`

주소는 실행하는 컴퓨터에서만 열린다. `.runtime.local.json`의 `frontend_port`, `backend_port`, `database_port`로 다른 체크아웃과 충돌하지 않는 포트를 설정한다. 실제 주소는 시작 명령이 출력한다. 실행 중인 포트를 바꾸려면 해당 체크아웃의 중지 절차를 먼저 따른다. 기존 DB를 새로 만들거나 다른 체크아웃의 프로세스를 중지해 해결하지 않는다.

## 검증 범위

계정·설정 기반 반영 시 백엔드 101개와 TypeScript·Vite 빌드, 실제 HTTP 8항목을 확인했다. HTTP 검사에는 계정·체험 설정 분리, 입력 실패 시 보존, 서버 재시작과 재로그인이 포함된다. 개발·테스트의 기존 음식/출처 내용이 유지되는 것도 확인했다.

위 수치는 해당 코드 반영 때의 실행 결과다. 새 컴퓨터에서 재실행하면 그 환경의 결과를 따로 확인해야 한다. 초기 안내 화면은 이전에 1440/390/320px에서 확인했으며 서비스 화면 전체나 최신 모바일 기능을 검증한 결과가 아니다. 새 빈 DB의 전체 준비·다운로드부터 설치까지의 전 과정을 새 컴퓨터에서 확인한 것으로 확대하지 않는다. Starlette/httpx 관련 폐기 예고 경고 1건이 남아 있다.

식단 API 연결에서는 16개 추천·변경 사례와 기존 검사를 합친 백엔드 117개, 실제 HTTP 8항목을 확인했다. 새 빈 개발 DB의 마이그레이션과 보관 음식 백업에서 복원한 테스트 DB의 업그레이드를 나눠 검사했다. 설치 파일 다운로드·서비스 화면·다른 물리 기기 사용성을 새로 검증한 결과는 아니다.
