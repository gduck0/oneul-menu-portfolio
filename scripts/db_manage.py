"""프로젝트 전용 로컬 PostgreSQL 관리."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / 'backend'))
from app.runtime import configure_libpq, database_port

configure_libpq()
import psycopg
from psycopg import sql

DB_ROOT = PROJECT / '.local/postgresql'
DATA = DB_ROOT / 'data'
CREDENTIALS = DB_ROOT / 'credentials.json'
PORT = database_port()
TARGETS = {
    'dev': ('oneul_menu_dev', 'oneul_dev'),
    'test': ('oneul_menu_test', 'oneul_test'),
}


def executable(name: str) -> str:
    runtime = json.loads((PROJECT / '.runtime.local.json').read_text(encoding='utf-8-sig'))
    location = Path(runtime['postgresql_bin']) / f'{name}.exe'
    if not location.is_file():
        raise RuntimeError('PostgreSQL 실행 파일을 먼저 준비하세요.')
    return str(location)


def credentials() -> dict:
    settings = json.loads(CREDENTIALS.read_text(encoding='utf-8'))
    if settings['port'] != PORT:
        raise RuntimeError('기존 DB 포트와 설정이 다릅니다. 기존 데이터·비밀값을 변경하지 않습니다.')
    return settings


def run_pg(name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    output_file = DB_ROOT / 'tool-output.log'
    with output_file.open('wb') as output:
        process = subprocess.run([executable(name), *map(str, args)], stdout=output, stderr=subprocess.STDOUT, timeout=90)
    process.stdout = output_file.read_bytes()
    process.stderr = b''
    if check and process.returncode != 0:
        (DB_ROOT / 'tool-last-error.log').write_bytes(process.stdout + process.stderr)
        raise RuntimeError(f'{name} 실행 실패. .local/postgresql/server.log를 확인하세요.')
    return process


def connect(target: str = 'admin', database: str | None = None):
    settings = credentials()
    if target == 'admin':
        account, default_db = 'oneul_admin', 'postgres'
    else:
        default_db, account = TARGETS[target]
    return psycopg.connect(
        host='127.0.0.1', port=PORT, dbname=database or default_db,
        user=account, password=settings['passwords'][target], connect_timeout=3,
        autocommit=True,
    )


def verify_cluster() -> None:
    with connect() as connection:
        directory = connection.execute('SHOW data_directory').fetchone()[0]
        if Path(directory).resolve() != DATA.resolve():
            raise RuntimeError('예상한 프로젝트 데이터 디렉터리와 다릅니다.')


def is_running() -> bool:
    return run_pg('pg_ctl', '-D', DATA, 'status', check=False).returncode == 0


def start() -> None:
    if not (DATA / 'PG_VERSION').is_file():
        raise RuntimeError('DB를 먼저 초기화하세요: Setup-Database.ps1')
    if not is_running():
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', PORT))
        run_pg('pg_ctl', '-D', DATA, '-l', DB_ROOT / 'server.log', '-w', '-t', '30', 'start')
    verify_cluster()
    print(f'POSTGRES_RUNNING 127.0.0.1:{PORT}')


def setup() -> None:
    DB_ROOT.mkdir(parents=True, exist_ok=True)
    if not CREDENTIALS.exists():
        if DATA.exists() or (PROJECT / '.env').exists() or (PROJECT / '.env.test').exists():
            raise RuntimeError('기존 데이터 또는 환경 파일이 있어 초기화를 중단했습니다.')
        settings = {'port': PORT, 'passwords': {key: secrets.token_hex(24) for key in ['admin', 'dev', 'test']}}
        CREDENTIALS.write_text(json.dumps(settings, indent=2), encoding='utf-8')
    settings = credentials()
    if not (DATA / 'PG_VERSION').exists():
        if DATA.exists() and any(DATA.iterdir()):
            raise RuntimeError('미완료 데이터 디렉터리를 덮어쓰지 않습니다.')
        password_file = DB_ROOT / 'initdb-password.tmp'
        try:
            password_file.write_text(settings['passwords']['admin'] + '\n', encoding='utf-8')
            run_pg('initdb', '-D', DATA, '-U', 'oneul_admin', '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C', f'--pwfile={password_file}')
        finally:
            password_file.unlink(missing_ok=True)
        with (DATA / 'postgresql.conf').open('a', encoding='utf-8') as config:
            config.write(f"\nlisten_addresses = '127.0.0.1'\nport = {PORT}\npassword_encryption = 'scram-sha-256'\nshared_buffers = '128MB'\n")
        (DATA / 'pg_hba.conf').write_text(
            'host all oneul_admin 127.0.0.1/32 scram-sha-256\n'
            'host oneul_menu_dev oneul_dev 127.0.0.1/32 scram-sha-256\n'
            'host oneul_menu_test oneul_test 127.0.0.1/32 scram-sha-256\n'
            'host all all 127.0.0.1/32 reject\n', encoding='utf-8',
        )
    start()
    with connect() as admin:
        for target, (database, account) in TARGETS.items():
            existing_role = admin.execute('SELECT oid FROM pg_roles WHERE rolname = %s', (account,)).fetchone()
            if existing_role is None:
                admin.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}').format(sql.Identifier(account), sql.Literal(settings['passwords'][target])))
            existing_db = admin.execute('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s', (database,)).fetchone()
            if existing_db is None:
                admin.execute(sql.SQL('CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING {}').format(sql.Identifier(database), sql.Identifier(account), sql.Literal('UTF8')))
            elif existing_db[0] != account:
                raise RuntimeError('DB 소유자가 예상과 다릅니다. 기존 DB를 변경하지 않습니다.')
            admin.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(database)))
            admin.execute(sql.SQL('GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}').format(sql.Identifier(database), sql.Identifier(account)))
            with connect(database=database) as database_admin:
                database_admin.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
    for target, (database, account) in TARGETS.items():
        filename = '.env' if target == 'dev' else '.env.test'
        env_file = PROJECT / filename
        if not env_file.exists():
            key = 'DATABASE_URL' if target == 'dev' else 'TEST_DATABASE_URL'
            value = f'postgresql+psycopg://{account}:{settings["passwords"][target]}@127.0.0.1:{PORT}/{database}'
            prefix = 'APP_ENV=development\n' if target == 'dev' else ''
            env_file.write_text(prefix + key + '=' + value + '\n', encoding='utf-8')
    print('DATABASES_CREATED dev/test; credentials excluded from Git')


def stop() -> None:
    if is_running():
        verify_cluster()
        run_pg('pg_ctl', '-D', DATA, '-m', 'fast', '-w', '-t', '30', 'stop')
    print('POSTGRES_STOPPED')


def migrate(target: str) -> None:
    start()
    settings = credentials()
    database, account = TARGETS[target]
    environment = os.environ.copy()
    environment['APP_ENV'] = 'development' if target == 'dev' else 'test'
    environment['DATABASE_URL'] = f'postgresql+psycopg://{account}:{settings["passwords"][target]}@127.0.0.1:{PORT}/{database}'
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=PROJECT / 'backend', env=environment, capture_output=True)
    if result.returncode != 0:
        (DB_ROOT / 'migration-last-error.log').write_bytes(result.stdout + result.stderr)
        raise RuntimeError(f'{target} 마이그레이션에 실패했습니다. 연결 설정과 스키마를 확인하세요.')
    print(f'MIGRATION_OK {target}')


def status() -> None:
    verify_cluster()
    with connect() as admin:
        print('POSTGRES_VERSION', admin.execute('SHOW server_version').fetchone()[0])
    for target in TARGETS:
        with connect(target) as connection:
            print('DATABASE_OK', target, connection.execute('SELECT current_database()').fetchone()[0])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['setup', 'start', 'stop', 'status', 'migrate'])
    parser.add_argument('--target', choices=['dev', 'test'], default='dev')
    args = parser.parse_args()
    try:
        if args.action == 'migrate':
            migrate(args.target)
        else:
            globals()[args.action]()
    except Exception as error:
        (DB_ROOT / 'operation-last-error.log').write_text(str(error), encoding='utf-8')
        print(f'DATABASE_OPERATION_FAILED ({type(error).__name__}). 연결 설정·권한·로컬 DB 로그를 확인하세요.', file=sys.stderr)
        sys.exit(1)
