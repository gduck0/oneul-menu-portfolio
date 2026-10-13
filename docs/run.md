# 로컬 실행

프로젝트 폴더에서 PowerShell을 열고 아래 명령을 실행합니다.

```powershell
.\scripts\Start-Dev.ps1
.\scripts\Status-Dev.ps1
.\scripts\Stop-Dev.ps1
```

시작 명령은 서버를 백그라운드에서 실행합니다. 로그와 프로세스 정보는 Git에서 제외된 `.local/`에 저장됩니다. 중지 명령은 이 프로젝트가 시작한 프로세스만 대상으로 합니다. 시작 명령을 다시 실행하면 기존 서버의 응답을 확인합니다.

- 화면: `http://127.0.0.1:15173`
- API 상태: `http://127.0.0.1:18080/api/health`
- API 문서: `http://127.0.0.1:18080/docs`

현재 주소는 서버를 실행하는 컴퓨터에서만 열립니다. 다른 기기에서 서비스 화면을 여는 접속 경로는 별도로 구성해야 합니다.

여러 로컬 체크아웃을 함께 실행할 때는 Git에서 제외된 `.runtime.local.json`에 `frontend_port`, `backend_port`를 지정합니다. 예를 들어 화면 15176, API 18082를 사용할 수 있습니다. 두 포트는 서로 다른 1024~65535 범위의 정수여야 합니다. 시작·상태·중지 명령과 API 프록시가 해당 설정을 사용하며 실제 주소는 시작 명령이 출력합니다. 실행 중인 서버의 포트를 바꿀 때는 먼저 이 체크아웃의 중지 명령을 실행합니다.

## 의존성 재설치

Python 3.13, Node.js 24, pnpm 11.25 환경에서 검증했습니다. 표준 설치 환경에서는 `python`, `node`, `pnpm`이 명령 경로에 있어야 합니다. 로컬 실행 파일의 경로를 별도로 지정할 때는 Git에서 제외된 `.runtime.local.json`에 `node`, `pnpm` 경로를 설정할 수 있습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.lock
Push-Location frontend
pnpm install --frozen-lockfile
pnpm build
Pop-Location
```

백엔드는 프로젝트 전용 `.venv`를 사용합니다. 설치 버전은 `backend/requirements.lock`, 프론트 버전은 `frontend/pnpm-lock.yaml`에 고정합니다.

현재는 초기 화면과 API 상태 확인만 제공합니다. 음식 검색·추천·DB·모델 연결은 후속 구현 범위입니다.

## 확인한 실행 결과

- 독립 가상환경 설치 후 `pip check` 통과
- TypeScript 검사와 Vite 프로덕션 빌드 통과
- 데스크톱 1440px, 모바일 390px·320px에서 화면 표시와 가로 넘침 검사 통과
- 브라우저 실행 오류·콘솔 오류 없음
- 프론트 `/api/health`를 통한 백엔드 응답 확인
- 미존재 API 경로의 404 응답과 OpenAPI 문서 확인
- 중복 시작, 서버 중지 후 포트 해제, 재시작 확인

DB 저장·추천 결과·로컬 모델 동작은 아직 검증하지 않았습니다.
