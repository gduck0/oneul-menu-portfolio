from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import get_engine
from app.food_models import Food, NutritionSnapshot
from app.food_source import convert_row
from app.main import app
from app.session_dependency import get_session


@pytest.fixture
def catalog_client(test_engine):
    fixture = json.loads((Path(__file__).parent / 'fixtures/nutrition-reference.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(json.dumps(fixture['rows'], ensure_ascii=False, sort_keys=True).encode()).hexdigest() == fixture['rows_sha256']
    snapshot_id = hashlib.sha256(uuid4().bytes).hexdigest()
    with test_engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
            try:
                session.execute(update(NutritionSnapshot).values(active=False))
                session.add(NutritionSnapshot(id=snapshot_id, source_url=fixture['source_page'],
                    retrieved_at=datetime(2026, 10, 19, tzinfo=timezone.utc), row_count=20,
                    active=True, manifest={'test_subset': True}))
                session.flush()
                rows = list(fixture['rows'])
                base = deepcopy(rows[0])
                synthetic = [
                    ('TEST-RICE-A', '시험 밥', '100g', None),
                    ('TEST-RICE-B', '시험 밥', '100ml', None),
                    ('TEST-RICE-C', '시험 밥', '100g', '시험 업체'),
                    ('TEST-ALIAS', '돈가스_시험', '100g', None),
                    ('TEST-UNICODE', 'ＳＯＵＰ 시험', '100g', None),
                    ('TEST-PERCENT', '시험%표기', '100g', None),
                    ('TEST-UNDERSCORE', '시험_표기', '100g', None),
                    ('TEST-SLASH', '시험/표기', '100g', None),
                    ('TEST-BASIS', '시험 기준량', '250g', None),
                    ('TEST-ZERO', '시험 영양값', '100g', None),
                    ('TEST-EMPTY', '시험 결측', '100g', None),
                ]
                for code, name, basis, company in synthetic:
                    row = {**base, 'FOOD_CD': code, 'FOOD_NM': name, 'NUT_CON_SRTR_QUA': basis, 'COMPANY_NM': company}
                    if code == 'TEST-ZERO':
                        row.update(ENERC='1.005', PROT='0', FATCE='', CHOCDF='10.55')
                    if code == 'TEST-EMPTY':
                        row.update(ENERC='', PROT='', FATCE='', CHOCDF='')
                    rows.append(row)
                ids = {}
                originals = {}
                for row in rows:
                    data = convert_row(row, snapshot_id)
                    session.add(Food(**data))
                    ids[row['FOOD_CD']] = data['id']
                    originals[data['id']] = deepcopy(data)
                session.flush()
                app.dependency_overrides[get_session] = lambda: session
                with TestClient(app) as client:
                    yield client, session, ids, originals
            finally:
                app.dependency_overrides.clear()
        transaction.rollback()


def test_search_preserves_codes_units_and_stable_pages(catalog_client):
    client, _, ids, _ = catalog_client
    response = client.get('/api/foods', params={'q': '시 험 밥'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['total'] == 3 and result['requires_confirmation'] is True
    assert result['items'][0]['id'] == ids['TEST-RICE-A']
    assert {item['basis_unit'] for item in result['items']} == {'g', 'mL'}
    pages = [client.get('/api/foods', params={'q': '시험 밥', 'limit': 1, 'offset': index}).json()['items'][0] for index in range(3)]
    assert [item['id'] for item in pages] == [item['id'] for item in result['items']]
    beyond = client.get('/api/foods', params={'q': '시험 밥', 'limit': 1, 'offset': 3}).json()
    assert beyond['total'] == 3 and beyond['items'] == []


@pytest.mark.parametrize(('query', 'code'), [('돈까스', 'TEST-ALIAS'), ('ｓｏｕｐ 시험', 'TEST-UNICODE'),
    ('시험%', 'TEST-PERCENT'), ('시험_', 'TEST-UNDERSCORE'), ('시험/', 'TEST-SLASH')])
def test_normalization_aliases_and_literal_wildcards(catalog_client, query, code):
    client, _, ids, _ = catalog_client
    items = client.get('/api/foods', params={'q': query}).json()['items']
    assert ids[code] in {item['id'] for item in items}
    if query.startswith('시험'):
        assert [item['id'] for item in items] == [ids[code]]


def test_empty_search_is_not_an_error(catalog_client):
    client, _, _, _ = catalog_client
    result = client.get('/api/foods', params={'q': '자료에없는음식xyz'}).json()
    assert result['items'] == [] and result['total'] == 0 and result['requires_confirmation'] is False


@pytest.mark.parametrize('params', [{}, {'q': ''}, {'q': '  \t '}, {'q': '밥' * 81},
    {'q': '밥', 'limit': 0}, {'q': '밥', 'limit': 51}, {'q': '밥', 'offset': -1}, {'q': '밥', 'offset': 10001}])
def test_invalid_search_is_rejected(catalog_client, params):
    assert catalog_client[0].get('/api/foods', params=params).status_code == 422


def test_detail_preserves_original_source_without_mutation(catalog_client):
    client, session, ids, originals = catalog_client
    food_id = ids['TEST-RICE-A']
    before = deepcopy(session.get(Food, food_id).raw)
    result = client.get('/api/foods/' + food_id).json()
    row = originals[food_id]
    assert result['name'] == row['name'] and result['source_weight'] == row['source_weight']
    assert Decimal(result['basis_amount']) == row['basis_amount']
    assert result['source']['food_code'] == row['food_code']
    assert result['source']['snapshot_id'] == row['snapshot_id']
    assert result['source']['reference_date'] == row['reference_date']
    assert result['source']['production_date'] == row['production_date']
    assert result['source']['provider'] == row['provider']
    assert datetime.fromisoformat(result['source']['retrieved_at'].replace('Z', '+00:00')) == datetime(2026, 10, 19, tzinfo=timezone.utc)
    assert result['source']['url'].startswith('https://www.data.go.kr/')
    assert 'raw' not in result and 'normalized_name' not in result
    assert session.get(Food, food_id).raw == before and not session.dirty


def test_inactive_version_is_excluded_from_search_but_still_resolvable(catalog_client):
    client, session, _, originals = catalog_client
    snapshot_id = hashlib.sha256(uuid4().bytes).hexdigest()
    session.add(NutritionSnapshot(id=snapshot_id, source_url='https://example.test/preserved-source',
        retrieved_at=datetime(2025, 1, 1, tzinfo=timezone.utc), row_count=1, active=False, manifest={}))
    session.flush()
    row = deepcopy(next(iter(originals.values()))['raw'])
    row.update(FOOD_CD='TEST-OLD', FOOD_NM='시험 옛 음식')
    data = convert_row(row, snapshot_id)
    session.add(Food(**data)); session.flush()
    assert client.get('/api/foods', params={'q': '시험 옛 음식'}).json()['total'] == 0
    detail = client.get('/api/foods/' + data['id']).json()
    assert detail['source']['snapshot_id'] == snapshot_id
    assert detail['source']['url'] == 'https://example.test/preserved-source'
    result = client.get('/api/foods/' + data['id'] + '/nutrition', params={'amount': '100', 'unit': data['basis_unit']})
    assert result.status_code == 200
    assert result.json()['food'] == detail


@pytest.mark.parametrize('amount', ['0.001', '125', '200.123', '10000'])
def test_portion_uses_source_basis_and_decimal_math(catalog_client, amount):
    client, _, ids, originals = catalog_client
    food_id = ids['TEST-BASIS']; original = originals[food_id]
    result = client.get('/api/foods/' + food_id + '/nutrition', params={'amount': amount, 'unit': 'g'})
    assert result.status_code == 200, result.text
    data = result.json()
    for field in ('energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g'):
        expected = original[field]
        if expected is None:
            assert data['nutrients'][field] is None
        else:
            calculated = (expected * Decimal(amount) / Decimal('250')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            assert Decimal(data['nutrients'][field]) == calculated
    assert Decimal(data['portion']['amount']) == Decimal(amount)
    assert data['food'] == client.get('/api/foods/' + food_id).json()


def test_rounding_zero_and_missing_values_are_distinct(catalog_client):
    client, _, ids, _ = catalog_client
    data = client.get('/api/foods/' + ids['TEST-ZERO'] + '/nutrition', params={'amount': '100', 'unit': 'g'}).json()
    assert data['nutrients'] == {'energy_kcal': '1.01', 'protein_g': '0.00', 'fat_g': None, 'carbohydrate_g': '10.55'}
    assert data['missing_nutrients'] == ['fat_g']
    empty = client.get('/api/foods/' + ids['TEST-EMPTY'] + '/nutrition', params={'amount': '50', 'unit': 'g'}).json()
    assert all(value is None for value in empty['nutrients'].values())
    assert len(empty['missing_nutrients']) == 4


def test_volume_calculation_and_cross_unit_rejection(catalog_client):
    client, _, ids, originals = catalog_client
    food_id = ids['TEST-RICE-B']
    result = client.get('/api/foods/' + food_id + '/nutrition', params={'amount': '150', 'unit': 'mL'})
    assert result.status_code == 200
    assert Decimal(result.json()['nutrients']['energy_kcal']) == (originals[food_id]['energy_kcal'] * Decimal('1.5')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    assert client.get('/api/foods/' + food_id + '/nutrition', params={'amount': '150', 'unit': 'g'}).status_code == 422
    assert client.get('/api/foods/' + ids['TEST-RICE-A'] + '/nutrition', params={'amount': '150', 'unit': 'mL'}).status_code == 422


@pytest.mark.parametrize('amount', ['0', '-1', '10000.001', '0.0001', 'NaN', 'Infinity', '-Infinity', 'abc'])
def test_invalid_amount_is_rejected(catalog_client, amount):
    client, _, ids, _ = catalog_client
    assert client.get('/api/foods/' + ids['TEST-ZERO'] + '/nutrition', params={'amount': amount, 'unit': 'g'}).status_code == 422


def test_unknown_id_invalid_id_and_unit_are_rejected(catalog_client):
    client, _, ids, _ = catalog_client
    assert client.get('/api/foods/' + '0' * 64).status_code == 404
    assert client.get('/api/foods/' + '0' * 64 + '/nutrition', params={'amount': '100', 'unit': 'g'}).status_code == 404
    assert client.get('/api/foods/not-an-id').status_code == 422
    assert client.get('/api/foods/' + ids['TEST-ZERO'] + '/nutrition', params={'amount': '100', 'unit': 'cup'}).status_code == 422
    assert client.post('/api/foods', json={}).status_code == 405


def test_database_failure_is_503_without_connection_details():
    class UnavailableEngine:
        def connect(self):
            raise OperationalError('SELECT private-query', {}, Exception('private-connection-detail'))

    app.dependency_overrides[get_engine] = lambda: UnavailableEngine()
    try:
        with TestClient(app) as client:
            result = client.get('/api/foods', params={'q': '밥'})
            assert result.status_code == 503
            assert 'private-connection-detail' not in result.text and 'private-query' not in result.text
            assert client.get('/api/health').status_code == 200
    finally:
        app.dependency_overrides.clear()
