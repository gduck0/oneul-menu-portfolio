from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog_import import import_catalog
from app.food_models import Food, NutritionSnapshot
from app.food_source import CatalogSource, convert_row, load_source, number


@pytest.fixture
def reference():
    return json.loads((Path(__file__).parent / 'fixtures/nutrition-reference.json').read_text(encoding='utf-8'))


@pytest.fixture
def source_factory(tmp_path, reference):
    count = 0

    def write(rows=None):
        nonlocal count
        directory = tmp_path / str(count)
        count += 1
        directory.mkdir()
        rows = deepcopy(reference['rows'] if rows is None else rows)
        for page in range(1, 6):
            page_rows = rows[page - 1::5]
            raw = json.dumps(page_rows, ensure_ascii=False).encode()
            (directory / f'page-{page}.json').write_bytes(raw)
            manifest = {'page': page, 'rows': len(page_rows), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'source_page': reference['source_page'], 'retrieved_at_utc': '2026-10-13T00:00:00+00:00'}
            (directory / f'page-{page}.manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return directory

    return write


@pytest.fixture
def session(test_engine):
    with test_engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
            yield session
        transaction.rollback()


@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity', 'unknown'])
def test_invalid_nutrient_is_rejected(value):
    with pytest.raises(ValueError):
        number(value)


@pytest.mark.parametrize('basis', ['1회', '100oz', '0g', '-1g'])
def test_unsupported_basis_is_rejected(reference, basis):
    row = deepcopy(reference['rows'][0])
    row['NUT_CON_SRTR_QUA'] = basis
    with pytest.raises(ValueError):
        convert_row(row, 'a' * 64)


def test_source_values_and_missing_values_are_preserved(reference):
    for row in reference['rows']:
        converted = convert_row(row, 'a' * 64)
        assert converted['raw'] == row
        assert converted['food_code'] == row['FOOD_CD']
        assert converted['provider'] == row['SRC_NM']
        assert converted['reference_date'] == row['CRTR_YMD']
        assert converted['source_weight'] == (row.get('FOOD_SIZE') or None)
    row = deepcopy(reference['rows'][0])
    row.update(ENERC='0', PROT='', FATCE=None, CHOCDF='1.25')
    converted = convert_row(row, 'a' * 64)
    assert converted['energy_kcal'] == Decimal('0')
    assert converted['protein_g'] is None and converted['fat_g'] is None
    assert converted['carbohydrate_g'] == Decimal('1.25')
    assert number('0.12345000') == Decimal('0.12345')
    assert number('999999999.99999') == Decimal('999999999.99999')


def test_volume_basis_stays_separate_from_weight(reference):
    row = next(row for row in reference['rows'] if 'ml' in row['NUT_CON_SRTR_QUA'].lower())
    converted = convert_row(row, 'a' * 64)
    assert converted['basis_amount'] == Decimal('100') and converted['basis_unit'] == 'mL'
    assert converted['source_weight'] == (row.get('FOOD_SIZE') or None)


@pytest.mark.parametrize('value', ['0.123456', '1000000000'])
def test_values_that_cannot_be_stored_exactly_are_rejected(value):
    with pytest.raises(ValueError):
        number(value)


def test_small_weight_basis_is_not_rounded_to_zero(reference):
    row = deepcopy(reference['rows'][0])
    row['NUT_CON_SRTR_QUA'] = '0.000001g'
    with pytest.raises(ValueError):
        convert_row(row, 'a' * 64)


def test_manifest_filename_must_match_page_number(source_factory):
    directory = source_factory()
    (directory / 'page-1.manifest.json').rename(directory / 'page-9.manifest.json')
    with pytest.raises(ValueError):
        load_source(directory)


def test_file_tampering_is_rejected_before_import(source_factory):
    directory = source_factory()
    with (directory / 'page-1.json').open('ab') as file:
        file.write(b' ')
    with pytest.raises(ValueError, match='지문'):
        load_source(directory)


def test_missing_page_is_rejected(source_factory):
    directory = source_factory()
    (directory / 'page-5.manifest.json').unlink()
    with pytest.raises(ValueError, match='5개'):
        load_source(directory)


def test_incorrect_row_count_is_rejected(source_factory):
    directory = source_factory()
    path = directory / 'page-1.manifest.json'
    manifest = json.loads(path.read_text())
    manifest['rows'] += 1
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='행 수'):
        load_source(directory)


def test_duplicate_food_code_is_rejected(source_factory, reference):
    rows = deepcopy(reference['rows'])
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError, match='중복'):
        load_source(source_factory(rows))


def test_non_food_rows_are_excluded(source_factory, reference):
    rows = deepcopy(reference['rows'])
    extra = {**rows[0], 'DATA_CD': 'P', 'FOOD_CD': 'TEST-PRODUCT'}
    source = load_source(source_factory(rows + [extra]))
    assert len(source.rows) == len(rows)
    assert all(row['food_code'] != 'TEST-PRODUCT' for row in source.rows)


def test_empty_food_source_is_rejected(source_factory, reference):
    rows = [{**row, 'DATA_CD': 'P'} for row in reference['rows']]
    with pytest.raises(ValueError, match='음식 자료가 없습니다'):
        load_source(source_factory(rows))


def test_reimport_does_not_duplicate_foods(session, source_factory):
    source = load_source(source_factory())
    with session.begin():
        first = import_catalog(session, source)
    with session.begin():
        second = import_catalog(session, source)
        count = session.scalar(select(func.count()).select_from(Food).where(Food.snapshot_id == source.snapshot_id))
        assert first.row_count == second.row_count == count == 9
        assert not first.already_imported and second.already_imported


def test_new_version_keeps_previous_food_and_only_one_active_version(session, source_factory, reference):
    first = load_source(source_factory())
    rows = deepcopy(reference['rows'])
    rows[0]['ENERC'] = '123.45'
    second = load_source(source_factory(rows))
    with session.begin():
        import_catalog(session, first)
    with session.begin():
        import_catalog(session, second)
        previous = session.get(Food, first.rows[0]['id'])
        current = session.get(Food, second.rows[0]['id'])
        assert previous.raw == reference['rows'][0]
        assert previous.energy_kcal != current.energy_kcal == Decimal('123.45')
        assert previous.id != current.id and previous.food_code == current.food_code
        assert session.scalar(select(func.count()).select_from(NutritionSnapshot).where(NutritionSnapshot.active.is_(True))) == 1
        assert not session.get(NutritionSnapshot, first.snapshot_id).active
    with pytest.raises(ValueError, match='과거 버전'):
        with session.begin():
            import_catalog(session, first)


def test_insert_failure_rolls_back_version_switch_and_new_rows(session, source_factory, reference):
    first = load_source(source_factory())
    with session.begin():
        import_catalog(session, first)
    rows = deepcopy(reference['rows'])
    rows[0]['ENERC'] = '123.45'
    second = load_source(source_factory(rows))
    broken = deepcopy(second.rows)
    broken[-1]['energy_kcal'] = Decimal('-1')
    with pytest.raises(IntegrityError):
        with session.begin():
            import_catalog(session, CatalogSource(second.snapshot_id, second.manifests, broken))
    with session.begin():
        assert session.get(NutritionSnapshot, first.snapshot_id).active
        assert session.get(NutritionSnapshot, second.snapshot_id) is None
        assert session.scalar(select(func.count()).select_from(Food).where(Food.snapshot_id == second.snapshot_id)) == 0


def test_partial_existing_snapshot_is_not_accepted_as_success(session, source_factory):
    source = load_source(source_factory())
    with session.begin():
        import_catalog(session, source)
        session.delete(session.get(Food, source.rows[0]['id']))
    with pytest.raises(ValueError, match=' 음식 수'):
        with session.begin():
            import_catalog(session, source)
