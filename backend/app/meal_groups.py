from collections import defaultdict

from sqlalchemy import select

from app.personal_contracts import MealResponse
from app.personal_models import MealEntry
from app.planner_models import MealPlan, PlanOperation
from app.planner_service import sum_nutrition
from fastapi import HTTPException


LABELS = {'breakfast': '아침', 'lunch': '점심', 'dinner': '저녁', 'snack': '간식'}


def meal_groups(session, owner, cancelled, limit, offset):
    conditions = [MealEntry.owner_key == owner,
        MealEntry.cancelled_at.is_not(None) if cancelled else MealEntry.cancelled_at.is_(None)]
    metadata = session.execute(select(MealEntry.id, MealEntry.eaten_at,
        MealEntry.payload['record_group_id'].as_string().label('group_id'),
        MealEntry.payload['plan_id'].as_string().label('plan_id'),
        MealEntry.payload['meal_key'].as_string().label('meal_key')).where(*conditions)).all()
    legacy_ids = {row.id for row in metadata if not row.group_id}
    links = {}
    if legacy_ids:
        operations = session.execute(select(PlanOperation.id, PlanOperation.plan_id,
            PlanOperation.payload['records'], PlanOperation.payload['plan']['meals'])
            .join(MealPlan, MealPlan.id == PlanOperation.plan_id)
            .where(MealPlan.owner_key == owner, PlanOperation.payload.has_key('records')))
        for operation_id, plan_id, records, planned_meals in operations:
            ids = {record['id'] for record in records or []}
            if not ids & legacy_ids:
                continue
            key = next((record.get('meal_key') for record in records if record.get('meal_key')), None)
            if key is None:
                key = next((meal['key'] for meal in planned_meals or []
                    if any(record['id'] in ids for record in meal.get('records', []))), None)
            for record_id in ids & legacy_ids:
                links[record_id] = ('legacy:' + operation_id, plan_id, key)

    groups = defaultdict(list)
    contexts = {}
    for row in metadata:
        group_id, plan_id, key = links.get(row.id, (
            'record:' + row.group_id if row.group_id else 'meal:' + row.id, row.plan_id, row.meal_key))
        groups[group_id].append(row)
        contexts[group_id] = (plan_id, key)
    ordered = sorted(groups, key=lambda key: (max(row.eaten_at for row in groups[key]), key), reverse=True)
    selected = ordered[offset:offset + limit]
    ids = [row.id for group_id in selected for row in groups[group_id]]
    entries = {row.id: row for row in session.scalars(select(MealEntry).where(*conditions, MealEntry.id.in_(ids)))} if ids else {}
    items = []
    for group_id in selected:
        if any(row.id not in entries for row in groups[group_id]):
            raise HTTPException(409, '기록 상태가 바뀌었어요. 기록을 다시 불러와 주세요.')
        plan_id, key = contexts[group_id]
        members = []
        for metadata_row in sorted(groups[group_id], key=lambda row: (row.eaten_at, row.id)):
            row = entries[metadata_row.id]
            payload = {name: value for name, value in row.payload.items() if name != 'portion_reference'}
            members.append(MealResponse.model_validate({**payload, 'version': row.version,
                'cancelled_at': row.cancelled_at, 'plan_id': plan_id, 'meal_key': key}).model_dump(mode='json'))
        nutrients, missing = sum_nutrition(members)
        items.append({'id': group_id, 'plan_id': plan_id, 'meal_key': key,
            'label': LABELS.get(key, '연결된 식사' if plan_id else '직접 남긴 식사'),
            'eaten_at': min(row.eaten_at for row in groups[group_id]),
            'skipped_foods': members[0]['skipped_foods'], 'items': members,
            'nutrients': nutrients, 'missing_nutrients': missing})
    return {'items': items, 'total': len(ordered), 'total_entries': len(metadata)}
