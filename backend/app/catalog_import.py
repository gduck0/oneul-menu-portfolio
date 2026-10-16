from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.orm import Session

from app.food_models import Food, NutritionSnapshot
from app.food_source import CatalogSource


@dataclass(frozen=True)
class ImportResult:
    snapshot_id: str
    row_count: int
    already_imported: bool


def import_catalog(session: Session, source: CatalogSource) -> ImportResult:
    # 활성 버전 교체와 중복 확인을 하나의 트랜잭션 안에서 처리한다.
    session.execute(text('SELECT pg_advisory_xact_lock(21987, 1)'))
    existing = session.get(NutritionSnapshot, source.snapshot_id)
    if existing is not None:
        actual = session.scalar(select(func.count()).select_from(Food).where(Food.snapshot_id == source.snapshot_id))
        if actual != existing.row_count or actual != len(source.rows):
            raise ValueError('기존 스냅샷의 음식 수가 기록과 다릅니다.')
        if not existing.active:
            raise ValueError('과거 버전을 자동으로 다시 활성화하지 않습니다.')
        return ImportResult(source.snapshot_id, actual, True)
    session.execute(update(NutritionSnapshot).where(NutritionSnapshot.active.is_(True)).values(active=False))
    session.add(NutritionSnapshot(
        id=source.snapshot_id, source_url=source.manifests[0]['source_page'],
        retrieved_at=max(datetime.fromisoformat(item['retrieved_at_utc']) for item in source.manifests),
        row_count=len(source.rows), active=True,
        manifest={'pages': source.manifests, 'source_row_count': sum(item['rows'] for item in source.manifests),
                  'policy': '음식 D만 가져옴. 원재료·가공식품 제외.'},
    ))
    session.flush()
    for offset in range(0, len(source.rows), 500):
        session.execute(insert(Food), source.rows[offset:offset + 500])
    return ImportResult(source.snapshot_id, len(source.rows), False)
