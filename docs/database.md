# 프로젝트 전용 PostgreSQL

PostgreSQL 18.6 Windows 바이너리를 프로젝트 내부에서 실행한다. 시스템 서비스로 등록하지 않으며 다른 프로젝트의 DB를 사용하지 않는다.

| 구분 | 설정 |
| --- | --- |
| 접속 | `127.0.0.1:15432` 기본값, `.runtime.local.json`의 `database_port`로 변경 |
| 개발 | DB `oneul_menu_dev`, 계정 `oneul_dev` |
| 테스트 | DB `oneul_menu_test`, 계정 `oneul_test` |
| 서비스 스키마 | `app` |
| 데이터 파일 | `.local/postgresql/data/` |
| 관리용 비밀값 | `.local/postgresql/credentials.json` |
| 개발 연결 설정 | `.env` |
| 테스트 연결 설정 | `.env.test`의 `TEST_DATABASE_URL` |

비밀값·DB 파일·로그·실행 파일은 Git에 포함하지 않는다. 관리 계정은 로컬 초기화·실행 관리에만 사용하고 서비스와 자동 테스트는 각자의 계정을 사용한다.

## 새 컴퓨터에서 준비

1. [PostgreSQL 공식 Windows 안내](https://www.postgresql.org/download/windows/)가 연결하는 [EDB 바이너리 배포](https://www.enterprisedb.com/download-postgresql-binaries)에서 Windows x86-64 ZIP을 내려받는다. 검증한 파일은 `postgresql-18.6-5-windows-x64-binaries.zip`이다.
2. ZIP의 `pgsql/bin`, `pgsql/lib`, `pgsql/share`를 `.local/postgresql/runtime/pgsql/` 아래에 보관한다.
3. 기존 로컬 바이너리가 있으면 읽기 전용으로 재사용할 수 있다. 데이터 디렉터리와 비밀값은 반드시 이 체크아웃에서 새로 생성한다.
4. 로컬 설정이 없으면 `.runtime.example.json`을 `.runtime.local.json`으로 복사하고 `postgresql_bin`을 실제 `pgsql/bin` 절대 경로로 바꾼다. 예시의 `C:/tools/...`는 설치 위치가 아니므로 그대로 사용하지 않는다. 기존 설정은 덮어쓰지 않는다. `node`, `pnpm`을 생략하거나 null·빈 문자열로 두면 각각 PATH에서 찾고, 명시한 잘못된 경로는 오류로 처리한다. 다른 체크아웃과 동시 실행할 때는 `database_port`를 충돌하지 않는 포트로 지정한다. 화면·API 포트와 기존 유효한 실행 경로는 유지한다. 실행 중인 DB의 포트 변경은 지원하지 않으며 기존 비밀 설정과 다른 포트는 거부한다.
5. 가상환경에 `backend/requirements.lock`을 설치하고 다음 명령을 실행한다. 비밀번호·연결 파일은 로컬에서 생성된다. `.env.example`은 설정 형식의 참고용이다.

```powershell
.\scripts\Setup-Database.ps1
.\scripts\Migrate-Database.ps1 -Target dev
.\scripts\Migrate-Database.ps1 -Target test
.\scripts\Start-Dev.ps1
```

초기화는 기존 DB를 삭제하거나 비밀번호·환경 파일을 덮어쓰지 않는다. 불완전한 데이터 디렉터리 또는 예상과 다른 DB 소유자가 발견되면 중단한다. `0001_app_schema` 위에 `0002_food_catalog`로 음식·출처 버전 테이블을 추가한다. `0003`~`0006`은 계정·개인 설정과 이후 기능의 공용 저장 구조를 추가한다. 현재 연결된 기능과 저장 구조의 구분은 [계정·설정 안내](accounts-settings.md), 자료 가져오기는 [음식 자료 안내](food-data.md)를 따른다.

Windows에서는 공식 PostgreSQL의 `libpq`를 사용하는 Psycopg Python 구현으로 검증했다. 라이브러리 경로는 프로젝트 프로세스 안에서만 설정하며 운영체제 보안 정책을 변경하지 않는다.

## 실행·중지·검증

`Start-Dev.ps1`, `Status-Dev.ps1`, `Stop-Dev.ps1`은 프론트·백엔드·프로젝트 DB를 함께 관리한다. DB만 관리할 때는 `Start-Database.ps1`, `Status-Database.ps1`, `Stop-Database.ps1`을 사용한다. 마이그레이션은 시작 명령이 자동 적용하지 않으므로 스키마 변경 후 대상 DB를 명시해서 실행한다.

- `/api/health`: 백엔드 프로세스 응답 여부
- `/api/ready`: 실제 DB 접속과 서비스 스키마 확인. DB 중단·스키마 미준비 시 503

테스트는 `.env.test`를 명시적으로 읽고 개발 설정으로 대체하지 않는다. DB 이름·계정·호스트·포트를 검증하며 PostgreSQL 접속 규칙과 권한도 서로 다른 DB의 접속을 거부한다. 두 계정 모두 슈퍼유저·DB 생성·역할 생성·복제 권한이 없다.

```powershell
.\scripts\Test-Backend.ps1
```

DB 격리 단계에서 확인한 범위(당시 결과):

- 자동 검증 12개 통과: 잘못된 테스트 대상 차단, 실제 저장·롤백, 테스트 계정의 개발 DB 접속 거부, 권한 제한, 준비 상태 정상·실패 응답
- 개발 계정의 테스트 DB 접속도 거부
- 개발 확인 데이터를 포함한 테이블 내용의 지문이 테스트와 DB 재시작 전후 동일
- 검증용 임시 테이블은 확인 후 정리
- 실제 DB 중단 시 `/api/health` 200, 프론트 경유 `/api/ready` 503, 재시작 후 `/api/ready` 200
- 초기화·마이그레이션 재실행 성공, `pip check` 통과

Starlette의 `httpx` 사용 폐기 예고 경고 1건이 발생했다. 현재 검증은 통과하며 후속 테스트 환경 갱신 시 호환성을 확인한다.

이후 음식 조회·계정·설정 기반까지 반영한 시점에는 백엔드 101개와 개발·테스트 업그레이드/재실행, 모델과 실제 스키마의 일치를 확인했다. 개발·테스트 각각 기존 음식 17,732행과 출처 1행을 보존한 업그레이드 검사다. 이 검사는 새 빈 DB에서 처음부터 설치한 검사와 구분한다.

식단 추천·변경 API 연결 시에는 별도로 만든 클러스터에서 새 빈 개발 DB의 0001~0006 마이그레이션과 음식 백업을 복원한 테스트 DB의 0002~0006 업그레이드/재실행을 확인했다. 검사 후 기존 음식과 업무 테이블의 내용이 같았고 검사 계정·계획은 정리됐다. 실제 기록·평가·이관 API와 서비스 화면은 아직 연결하지 않았다.
