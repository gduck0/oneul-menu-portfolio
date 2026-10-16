from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import unicodedata


def number(value) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('원본 영양 값이 숫자가 아닙니다.') from None
    if not result.is_finite() or result < 0:
        raise ValueError('원본 영양 값은 유한한 음이 아닌 값이어야 합니다.')
    if result > Decimal('999999999.99999') or result != result.quantize(Decimal('0.00001')):
        raise ValueError('원본 숫자를 현재 저장 형식으로 손실 없이 저장할 수 없습니다.')
    return result


def convert_row(row: dict, snapshot_id: str) -> dict:
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(g|ml|mL)', row['NUT_CON_SRTR_QUA'])
    if not match:
        raise ValueError('지원되지 않는 원본 기준량입니다.')
    basis_amount = number(match[1])
    if basis_amount is None or basis_amount <= 0:
        raise ValueError('지원되지 않는 원본 기준량입니다.')
    if not row['FOOD_CD'].strip() or not row['FOOD_NM'].strip():
        raise ValueError('음식 코드와 이름이 필요합니다.')
    company = row.get('COMPANY_NM')
    return {
        'id': hashlib.sha256((snapshot_id + ':' + row['FOOD_CD']).encode()).hexdigest(),
        'snapshot_id': snapshot_id, 'food_code': row['FOOD_CD'], 'name': row['FOOD_NM'],
        'normalized_name': re.sub(r'\s+', '', unicodedata.normalize('NFKC', row['FOOD_NM'])).casefold(),
        'category': None, 'company': None if company in ('', None, '해당없음') else company,
        'basis_amount': basis_amount, 'basis_unit': 'g' if match[2] == 'g' else 'mL',
        'energy_kcal': number(row.get('ENERC')), 'protein_g': number(row.get('PROT')),
        'fat_g': number(row.get('FATCE')), 'carbohydrate_g': number(row.get('CHOCDF')),
        'provider': row['SRC_NM'], 'reference_date': row['CRTR_YMD'],
        'production_date': row.get('CRT_YMD') or None, 'source_weight': row.get('FOOD_SIZE') or None,
        'raw': row,
    }


@dataclass(frozen=True)
class CatalogSource:
    snapshot_id: str
    manifests: list[dict]
    rows: list[dict]


def load_source(directory: Path) -> CatalogSource:
    manifests, rows = [], []
    for manifest_path in sorted(directory.glob('page-*.manifest.json')):
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        page = manifest['page']
        if type(page) is not int or page not in range(1, 6):
            raise ValueError('원본 페이지 번호가 올바르지 않습니다.')
        if manifest_path.name != f'page-{page}.manifest.json':
            raise ValueError('수집 기록의 파일명과 페이지 번호가 일치하지 않습니다.')
        raw = (directory / f'page-{page}.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest['sha256']:
            raise ValueError('공식 원본 지문이 수집 기록과 다릅니다.')
        page_rows = json.loads(raw)
        if not isinstance(page_rows, list) or len(page_rows) != manifest['rows']:
            raise ValueError('공식 원본 행 수가 수집 기록과 다릅니다.')
        manifests.append(manifest)
        rows.extend(page_rows)
    if len(manifests) != 5 or sorted(item['page'] for item in manifests) != [1, 2, 3, 4, 5]:
        raise ValueError('다운로드한 원본 5개 페이지와 수집 기록이 필요합니다.')
    snapshot_id = hashlib.sha256(''.join(item['sha256'] for item in manifests).encode()).hexdigest()
    food_rows = [row for row in rows if row.get('DATA_CD') == 'D']
    if not food_rows:
        raise ValueError('가져올 음식 자료가 없습니다.')
    if len({row['FOOD_CD'] for row in food_rows}) != len(food_rows):
        raise ValueError('중복 식품코드가 있어 가져오기를 중단합니다.')
    return CatalogSource(snapshot_id, manifests, [convert_row(row, snapshot_id) for row in food_rows])
