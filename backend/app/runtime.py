import json
import os
from pathlib import Path

_dll_directory = None


def database_port() -> int:
    runtime_file = Path(__file__).resolve().parents[2] / '.runtime.local.json'
    runtime = json.loads(runtime_file.read_text(encoding='utf-8-sig')) if runtime_file.exists() else {}
    port = runtime.get('database_port', 15432)
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError('DB 포트는 1024~65535 범위의 정수여야 합니다.')
    if port in (runtime.get('frontend_port', 15173), runtime.get('backend_port', 18080)):
        raise ValueError('DB 포트는 화면·API 포트와 서로 달라야 합니다.')
    return port


def configure_libpq() -> None:
    global _dll_directory
    runtime_file = Path(__file__).resolve().parents[2] / '.runtime.local.json'
    if not runtime_file.exists():
        return
    runtime = json.loads(runtime_file.read_text(encoding='utf-8-sig'))
    binary_directory = runtime.get('postgresql_bin')
    if binary_directory and Path(binary_directory).is_dir():
        os.environ.setdefault('PSYCOPG_IMPL', 'python')
        if binary_directory not in os.environ.get('PATH', '').split(os.pathsep):
            os.environ['PATH'] = binary_directory + os.pathsep + os.environ.get('PATH', '')
        if os.name == 'nt' and _dll_directory is None:
            _dll_directory = os.add_dll_directory(binary_directory)
