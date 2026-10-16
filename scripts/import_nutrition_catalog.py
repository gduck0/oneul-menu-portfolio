import argparse
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / 'backend'))

from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.catalog_import import import_catalog
from app.food_source import load_source
from app.settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description='보존한 공식 음식 자료를 지정한 DB에 가져옵니다.')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', choices=['dev', 'test'], required=True)
    args = parser.parse_args()
    engine = None
    try:
        source = load_source(args.source)
        filename, key, mode = ('.env', 'DATABASE_URL', 'development') if args.target == 'dev' else ('.env.test', 'TEST_DATABASE_URL', 'test')
        url = dotenv_values(PROJECT / filename).get(key)
        if not url:
            raise ValueError('대상 DB의 연결 설정이 필요합니다.')
        settings = Settings(app_env=mode, database_url=url, _env_file=None)
        engine = create_engine(settings.database_url.get_secret_value(), connect_args={'connect_timeout': 3}, hide_parameters=True)
        with Session(engine) as session, session.begin():
            result = import_catalog(session, source)
        print('CATALOG_ALREADY_IMPORTED' if result.already_imported else 'CATALOG_IMPORTED', result.row_count, result.snapshot_id)
        return 0
    except (OSError, ValueError, KeyError, TypeError, SQLAlchemyError):
        print('자료 가져오기에 실패했습니다. 원본 파일과 대상 DB 설정을 확인하세요.', file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
