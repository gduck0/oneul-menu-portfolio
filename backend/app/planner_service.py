from copy import deepcopy
from collections import Counter
from functools import lru_cache
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
import itertools
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from app.food_catalog import NUTRIENT_FIELDS, normalize_name, summarize
from app.food_models import Food, NutritionSnapshot
from app.planner_contracts import MealConstraints, PlanRequest

ZERO = Decimal('0')
LABELS = {'breakfast': '아침', 'lunch': '점심', 'dinner': '저녁', 'snack': '간식'}
LAYOUTS = {
    2: [('lunch', 0.45), ('dinner', 0.55)],
    3: [('breakfast', 0.25), ('lunch', 0.35), ('dinner', 0.4)],
    4: [('breakfast', 0.23), ('lunch', 0.30), ('dinner', 0.35), ('snack', 0.12)],
}
DIVERSITY_REPEAT_COST = 0.15
# 이름과 재료 예시에 명시된 묶음만 사용한다. 전체 성분·알레르기 분류가 아니다.
INGREDIENT_GROUPS = {
    '달걀': ('달걀', '계란'),
    '두부': ('두부', '유부'),
    '닭고기': ('닭', '치킨'),
    '소고기': ('소고기', '쇠고기', '소불고기'),
    '돼지고기': ('돼지', '돈육', '돈가스', '돈까스', '햄'),
    '생선': ('참치', '고등어', '삼치', '갈치', '연어', '가자미', '멸치', '꽁치', '북어'),
    '해산물': ('새우', '오징어', '낙지', '주꾸미', '전복', '바지락', '게살'),
}


def ingredient_groups(items):
    groups = set()
    for item in items:
        if not item.get('menu_id') or item.get('role') not in ['main', 'protein', 'soup', 'side']:
            continue
        value = normalize_name(item['name'] + ' ' + ' '.join(item.get('ingredients', [])))
        groups.update(
            group
            for group, aliases in INGREDIENT_GROUPS.items()
            if any(alias in value for alias in aliases)
        )
    return groups


def diversity_cost(items, counts):
    return DIVERSITY_REPEAT_COST * sum(counts.get(group, 0) for group in ingredient_groups(items))


@lru_cache
def recommendation_families():
    families = {}
    for menu in menu_definitions()['menus']:
        if menu['role'] not in ['main', 'protein', 'side']:
            continue
        if menu['role'] == 'protein':
            family = (
                ','.join(sorted(ingredient_groups([menu]))) or menu['source_name'].split('_')[0]
            )
        else:
            family = menu['source_name'].split('_')[0]
        families[menu['menu_id']] = menu['role'] + ':' + normalize_name(family)
    return families


def composition_signature(items):
    families = recommendation_families()
    return tuple(
        sorted({families[item['menu_id']] for item in items if item.get('menu_id') in families})
    )


@lru_cache
def day_family_catalog():
    # 등록 메뉴의 음식 형태를 묶는다. 같은 재료·쌀·국/반찬 전체를 한 계열로 보지 않는다.
    aliases = {
        '충무김밥': '김밥',
        '계란덮밥': '덮밥',
        **dict.fromkeys(
            [
                '채소죽',
                '전복죽',
                '닭죽',
                '소고기버섯죽',
                '참치죽',
                '게살죽',
                '팥죽',
                '흑임자죽',
                '쌀죽(흰죽)',
                '잣죽',
            ],
            '죽',
        ),
    }
    return {
        menu['menu_id']: menu['role']
        + ':'
        + normalize_name(
            aliases.get(menu['source_name'].split('_')[0], menu['source_name'].split('_')[0])
        )
        for menu in menu_definitions()['menus']
        if menu['role'] in ['main', 'protein', 'side']
    }


def day_menu_families(items):
    families = day_family_catalog()
    return {families[item['menu_id']] for item in items if item.get('menu_id') in families}


def day_family_counts(meals):
    return Counter(family for meal in meals for family in day_menu_families(meal['items']))


def history_cost(items, recent_meals):
    # 최근 노출은 취향 감점이 아니다. 조건이 좁으면 같은 메뉴도 다시 선택한다.
    ids = {
        item['menu_id']
        for item in items
        if item.get('role') in ['main', 'protein', 'side'] and item.get('menu_id')
    }
    families = set(composition_signature(items))
    cost = 0
    for index, meal in enumerate((recent_meals or [])[:5]):
        previous = {
            item['menu_id']
            for item in meal['items']
            if item.get('role') in ['main', 'protein', 'side'] and item.get('menu_id')
        }
        related = set(composition_signature(meal['items']))
        cost += (0.18 * bool(ids & previous) + 0.22 * bool(families & related)) * (0.7**index)
    return min(0.36, cost)


def diverse_shortlist(options, limit, signature):
    # 분량만 다른 상위 후보가 탐색 폭을 모두 차지하지 않게 한다.
    selected = options[: min(4, limit)]
    groups = {tuple(sorted(day_menu_families(option['items']))) for option in selected}
    for option in options[len(selected) :]:
        group = tuple(sorted(day_menu_families(option['items'])))
        if group not in groups:
            selected.append(option)
            groups.add(group)
        if len(selected) >= limit:
            break
    seen = {signature(option) for option in selected}
    for option in options:
        key = signature(option)
        if key not in seen and len(selected) < limit:
            selected.append(option)
            seen.add(key)
    return sorted(selected, key=lambda option: option['cost'])


def protein_pool(menus, limit):
    selected = menus[: limit // 2]
    groups = {tuple(sorted(ingredient_groups([menu]))) for menu in selected}
    for menu in menus[len(selected) :]:
        group = tuple(sorted(ingredient_groups([menu])))
        if group not in groups:
            selected.append(menu)
            groups.add(group)
        if len(selected) >= limit:
            break
    ids = {menu['menu_id'] for menu in selected}
    for menu in menus:
        if menu['menu_id'] not in ids and len(selected) < limit:
            selected.append(menu)
            ids.add(menu['menu_id'])
    return selected


@lru_cache
def menu_definitions():
    return json.loads(
        (Path(__file__).parent / 'data/planner-menus.json').read_text(encoding='utf-8')
    )


def menu_catalog(session):
    definitions = menu_definitions()
    codes = {code for menu in definitions['menus'] for code in menu['source_food_codes']}
    rows = session.execute(
        select(Food, NutritionSnapshot)
        .join(NutritionSnapshot)
        .where(NutritionSnapshot.active.is_(True), Food.food_code.in_(codes))
    ).all()
    by_code = {food.food_code: (food, snapshot) for food, snapshot in rows}
    menus = []
    for spec in definitions['menus']:
        sources = [by_code[code] for code in spec['source_food_codes'] if code in by_code]
        selected = by_code.get(spec['source_selected_code'])
        if selected is None or len(sources) != len(spec['source_food_codes']):
            continue
        if any(
            food.basis_unit != 'g' or any(getattr(food, field) is None for field in NUTRIENT_FIELDS)
            for food, _ in sources
        ):
            continue
        values = {
            field: (
                Decimal(
                    str(
                        median(
                            [getattr(food, field) * 100 / food.basis_amount for food, _ in sources]
                        )
                    )
                )
                if spec['nutrition_method'] == 'median'
                else getattr(selected[0], field) * 100 / selected[0].basis_amount
            ).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            for field in NUTRIENT_FIELDS
        }
        item = {
            **spec,
            'nutrients': {field: str(value) for field, value in values.items()},
            'food': summarize(*selected).model_dump(mode='json'),
            'nutrition_note': '일반 메뉴 참고값',
            'catalog_version': definitions['version'],
        }
        menus.append(item)
    return menus


def prepared_side(menu, constraints):
    return constraints.prepared_sides and menu['role'] in ['staple', 'vegetable']


def preparation_minutes(menu, constraints):
    return (
        5
        if prepared_side(menu, constraints) or (constraints.no_cook and menu['ready_to_eat'])
        else menu['minutes']
    )


def calculate_item(menu, amount, constraints=None):
    amount = Decimal(str(amount))
    nutrients = {
        field: str(
            (Decimal(menu['nutrients'][field]) * amount / 100).quantize(
                Decimal('.01'), rounding=ROUND_HALF_UP
            )
        )
        for field in NUTRIENT_FIELDS
    }
    item = {
        'item_id': menu['menu_id'],
        'menu_id': menu['menu_id'],
        'name': menu['name'],
        'amount_g': str(amount),
        'nutrients': nutrients,
        'reference_nutrients': deepcopy(menu['nutrients']),
        'food': menu['food'],
        'nutrition_method': menu['nutrition_method'],
        'nutrition_note': menu['nutrition_note'],
        'role': menu['role'],
        'preparation': menu['preparation'],
        'tools': menu['tools'],
        'minutes': menu['minutes'],
        'ingredients': menu['ingredients'],
        'ingredients_complete': False,
        'preparation_status': menu['preparation_status'],
        'min_g': menu['min_g'],
        'max_g': menu['max_g'],
        'prepared': False,
    }
    item.update(reference_portion_g=menu['portion_g'], ready_to_eat=menu['ready_to_eat'])
    if constraints and (prepared_side(menu, constraints) or constraints.no_cook):
        item.update(
            minutes=preparation_minutes(menu, constraints),
            prepared=True,
            preparation='이미 준비한 음식의 먹을 양을 덜어 준비해요. 필요한 데우기와 차림은 참고로 약 5분을 잡았어요.',
            tools=['준비된 음식'],
        )
    return item


def manual_item(menus, menu_id, custom_name, amount):
    if menu_id:
        menu = next((menu for menu in menus if menu['menu_id'] == menu_id), None)
        if menu is None:
            raise HTTPException(404, '식단용 메뉴를 찾지 못했어요.')
        item = calculate_item(menu, amount or menu['portion_g'])
        item.update(minutes=None, prepared=False)
        return item
    return {
        'item_id': 'custom-' + str(uuid4()),
        'menu_id': None,
        'name': custom_name,
        'amount_g': str(amount) if amount is not None else None,
        'nutrients': {field: None for field in NUTRIENT_FIELDS},
        'food': None,
        'nutrition_method': 'unknown',
        'nutrition_note': '직접 입력 · 영양 자료 없음',
        'role': 'custom',
        'preparation': None,
        'tools': [],
        'minutes': None,
        'ingredients': [],
        'ingredients_complete': False,
        'preparation_status': 'unknown',
        'min_g': None,
        'max_g': None,
        'prepared': False,
    }


def sum_nutrition(items):
    values = {
        field: (
            str(
                sum(
                    (
                        Decimal(item['nutrients'][field])
                        for item in items
                        if item['nutrients'][field] is not None
                    ),
                    ZERO,
                ).quantize(Decimal('.01'))
            )
            if any(item['nutrients'][field] is not None for item in items)
            else None
        )
        for field in NUTRIENT_FIELDS
    }
    missing = [
        field
        for field in NUTRIENT_FIELDS
        if any(item['nutrients'][field] is None for item in items)
    ]
    return values, missing


def totals(meals):
    values, missing = sum_nutrition([item for meal in meals for item in meal['items']])
    if any(not meal['items'] for meal in meals):
        missing = list(NUTRIENT_FIELDS)
    return values, missing


def name_matches(menu, names):
    value = normalize_name(
        menu['name'] + ' ' + menu['source_name'] + ' ' + ' '.join(menu['ingredients'])
    )
    groups = {normalize_name(group) for group in ingredient_groups([menu])}
    return any(
        normalize_name(name) in value or normalize_name(name) in groups
        for name in names
        if normalize_name(name)
    )


def exclusion_conflicts(menu, names):
    # 수동 선택을 막지 않고 자동 추천과 동일한 제외 기준을 안내한다.
    return list(dict.fromkeys(name.strip() for name in names if name_matches(menu, [name])))


def allowed(menu, slot, constraints, settings):
    if LABELS[slot] not in menu['meal_slots']:
        return False
    if name_matches(menu, constraints.avoided_foods + settings.avoided_foods):
        return False
    prepared = prepared_side(menu, constraints)
    if constraints.no_cook and not (menu['ready_to_eat'] or prepared):
        return False
    mode = menu['preparation_mode']
    required = {
        'pan': 'pan',
        'pot': 'pot',
        'steam': 'steam',
        'blanch': 'pot',
        'heat': 'stone',
        'rice': 'rice',
        'grill': 'grill',
    }.get(mode)
    if (
        constraints.tools
        and required
        and required not in constraints.tools
        and not menu['ready_to_eat']
        and not prepared
    ):
        if not (required == 'steam' and 'pot' in constraints.tools):
            return False
    minutes = preparation_minutes(menu, constraints)
    return constraints.max_minutes is None or minutes <= constraints.max_minutes


def taste_cost(menu, settings, scores):
    cost = 0
    if name_matches(menu, settings.favorite_foods):
        cost -= 0.05
    if name_matches(menu, settings.frequent_foods):
        cost -= 0.02
    if settings.goal == 'similarity' and name_matches(
        menu, settings.favorite_foods + settings.frequent_foods
    ):
        cost -= 0.08
    cost -= float(scores.get(menu['source_selected_code'], ZERO))
    return cost


def meal_options(
    menus,
    slot,
    target,
    constraints,
    settings,
    scores,
    skip_ids=None,
    protein_target=None,
    recent_meals=None,
):
    skip_ids = skip_ids or set()
    valid = [menu for menu in menus if allowed(menu, slot, constraints, settings)]

    def rank(menu):
        return taste_cost(menu, settings, scores), menu['menu_id']

    by_role = {
        role: sorted([menu for menu in valid if menu['role'] == role], key=rank)
        for role in ['main', 'staple', 'protein', 'vegetable', 'soup', 'side']
    }
    bundles = [([menu], scale) for menu in by_role['main'] for scale in [0.8, 1, 1.15]]
    if slot == 'snack':
        bundles = [([menu], scale) for menu in valid for scale in [0.8, 1, 1.15]]
        for first, second in itertools.combinations(valid, 2):
            if {first.get('snack_group'), second.get('snack_group')} == {'egg', 'tuber'}:
                bundles.extend([([first, second], scale) for scale in [0.8, 1, 1.15]])
    else:
        for staple, protein, vegetable in itertools.product(
            by_role['staple'][:4], protein_pool(by_role['protein'], 10), by_role['vegetable'][:6]
        ):
            bundles.extend([([staple, protein, vegetable], scale) for scale in [0.8, 1, 1.1]])
        if by_role['soup']:
            for staple, protein, soup in itertools.product(
                by_role['staple'][:3], protein_pool(by_role['protein'], 6), by_role['soup'][:4]
            ):
                bundles.append(([staple, protein, soup], 1))
    references = {tuple(menu['menu_id'] for menu in bundle): bundle for bundle, _ in bundles}
    for bundle in references.values():
        reference_energy = sum(
            float(menu['nutrients']['energy_kcal']) * menu['portion_g'] / 100 for menu in bundle
        )
        if reference_energy > 0:
            bundles.append((bundle, target / reference_energy))
    options = []
    seen = set()
    for bundle, scale in bundles:
        if skip_ids and {menu['menu_id'] for menu in bundle} == skip_ids:
            continue
        minutes = sum(preparation_minutes(menu, constraints) for menu in bundle)
        if constraints.max_minutes and minutes > constraints.max_minutes:
            continue
        items = []
        for menu in bundle:
            amount = min(
                menu['max_g'], max(menu['min_g'], round(menu['portion_g'] * scale / 5) * 5)
            )
            items.append(calculate_item(menu, amount, constraints))
        signature = tuple((item['menu_id'], item['amount_g']) for item in items)
        if signature in seen:
            continue
        seen.add(signature)
        nutrients, _ = sum_nutrition(items)
        energy = float(nutrients['energy_kcal'])
        if energy > max(target * 1.2, 180):
            continue
        cost = (
            abs(energy - target) / max(target, 1)
            + sum(taste_cost(menu, settings, scores) for menu in bundle)
            + history_cost(items, recent_meals)
        )
        if settings.goal == 'protein':
            cost -= min(0.12, float(nutrients['protein_g']) / max(energy, 1) * 1.2)
        if protein_target:
            cost += (
                abs(float(nutrients['protein_g']) - protein_target)
                / protein_target
                * (0.75 if settings.goal == 'protein' else 0.25)
            )
        options.append(
            {
                'items': items,
                'nutrients': nutrients,
                'minutes': minutes,
                'cost': cost,
                'energy': energy,
            }
        )
    options.sort(
        key=lambda option: (option['cost'], tuple(item['menu_id'] for item in option['items']))
    )
    return diverse_shortlist(
        options, 24, lambda option: tuple(item['menu_id'] for item in option['items'])
    )


def update_summary(payload):
    values, missing = totals(payload['meals'])
    payload['nutrients'] = values
    payload['missing_nutrients'] = missing
    targets = {
        'energy_kcal': 'energy_target',
        'protein_g': 'protein_target',
        'carbohydrate_g': 'carbohydrate_target',
        'fat_g': 'fat_target',
    }
    payload['target_difference'] = {
        field: (
            None
            if field in missing or payload['settings'].get(target) is None
            else str(
                (Decimal(values[field]) - Decimal(str(payload['settings'][target]))).quantize(
                    Decimal('.01')
                )
            )
        )
        for field, target in targets.items()
    }
    notes = []
    if missing:
        notes.append(
            '직접 입력하거나 비어 있는 끼니가 있어 확인 가능한 영양만 합산했어요. 하루 목표 충족 여부는 확정할 수 없어요.'
        )
    if any(meal['status'] == 'empty' for meal in payload['meals']):
        notes.append(
            '조건에 맞는 메뉴가 없는 끼니가 있어요. 제외 음식·기구·시간 중 원하는 조건을 조절해 주세요.'
        )
    groups = {}
    for meal in payload['meals']:
        for group in ingredient_groups(meal['items']):
            groups[group] = groups.get(group, 0) + 1
    repeated = [group for group in INGREDIENT_GROUPS if groups.get(group, 0) > 1]
    if repeated:
        notes.append(
            '이름·재료 예시에서 '
            + ', '.join(repeated)
            + ' 묶음이 여러 끼니에 반복돼요. 목표·조건·고정한 메뉴를 함께 고려한 결과이며 직접 바꿀 수 있어요.'
        )
    repeated_families = sorted(
        family.split(':', 1)[1]
        for family, count in day_family_counts(payload['meals']).items()
        if count > 1
    )
    if repeated_families:
        notes.append(
            '하루에 '
            + ', '.join(dict.fromkeys(repeated_families))
            + ' 계열이 겹쳐요. 직접 정한 메뉴·준비 조건과 후보 범위를 함께 고려한 결과예요. 원하면 다른 메뉴를 직접 골라도 좋아요.'
        )
    diff = payload['target_difference']['energy_kcal']
    if diff is not None and abs(Decimal(diff)) > Decimal(
        str(payload['settings']['energy_target'])
    ) * Decimal('.1'):
        direction = '낮아요' if Decimal(diff) < 0 else '높아요'
        notes.append(
            f"입력한 하루 목표보다 약 {abs(Decimal(diff)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)}kcal {direction}. 메뉴별 추천 분량 범위와 직접 정한 메뉴·양, 준비 조건에 따라 차이가 날 수 있어요."
        )
    for field in ['protein_g', 'carbohydrate_g', 'fat_g']:
        delta = payload['target_difference'][field]
        target = payload['settings'].get(targets[field])
        if (
            delta is not None
            and target
            and abs(Decimal(delta)) > Decimal(str(target)) * Decimal('.2')
        ):
            notes.append(
                '설정한 탄단지 목표와 차이가 있어요. 목표는 선택 기준이며 모든 조건을 동시에 맞추는 것을 보장하지 않아요.'
            )
            break
    payload['notes'] = notes
    return payload


def meal_reason(
    option,
    target,
    constraints,
    menus,
    settings,
    scores,
    slot=None,
    recent_meals=None,
    other_families=None,
):
    if not option['items']:
        return '현재 준비 조건에 맞는 메뉴가 없어요. 조건을 바꾸거나 내 메뉴를 입력해 주세요.'
    reasons = []
    if slot == 'snack':
        reasons.append('간식으로 구분한 메뉴에서 골랐어요.')
    if recent_meals:
        reasons.append(
            '최근 추천과의 메뉴 반복도 함께 살펴봤어요. 조건에 따라 같은 메뉴가 다시 나올 수 있어요.'
        )
    if constraints.no_cook:
        reasons.append('완제품이나 이미 준비한 음식을 사용해 조리 없이 먹을 수 있어요.')
    prepared = [
        item['name']
        for item in option['items']
        if item.get('prepared') and item['role'] in ['staple', 'vegetable']
    ]
    if prepared:
        reasons.append('이미 만든 밥·반찬을 사용하고 차림 시간을 계산했어요.')
    if constraints.max_minutes:
        reasons.append(
            f"참고 준비 {option['minutes']}분으로 {constraints.max_minutes}분 조건 안에서 골랐어요."
        )
    delta = round(option['energy'] - target)
    reasons.append(
        '이 끼니의 참고 열량 기준에 가까워요.'
        if abs(delta) <= target * 0.1
        else f"이 끼니 기준보다 참고 열량이 약 {abs(delta)}kcal {'많아요' if delta>0 else '적어요'}."
    )
    selected = [
        menu for menu in menus if menu['menu_id'] in {item['menu_id'] for item in option['items']}
    ]
    if any(
        name_matches(menu, settings.favorite_foods + settings.frequent_foods) for menu in selected
    ):
        reasons.append('저장한 선호·평소 음식과 맞는 메뉴를 포함했어요.')
    if any(scores.get(menu['source_selected_code'], ZERO) > 0 for menu in selected):
        reasons.append('이전에 남긴 만족 평가도 선택에 참고했어요.')
    if settings.goal == 'protein':
        reasons.append('단백질을 우선하는 선택 기준을 적용했어요.')
    if ingredient_groups(option['items']):
        reasons.append('다른 끼니와의 재료 반복도 함께 고려했어요.')
    if other_families is not None and day_menu_families(option['items']):
        reasons.append(
            '직접 정한 메뉴·준비 조건과 후보 범위를 고려해 같은 메뉴 계열의 반복을 허용했어요.'
            if day_menu_families(option['items']) & other_families
            else '다른 끼니와 같은 메뉴 계열이 겹치지 않게 골랐어요.'
        )
    return ' '.join(reasons)


def build_meals(data: PlanRequest, menus, settings, scores, recent_meals=None):
    recent_meals = recent_meals or {}
    layout = LAYOUTS[data.meal_count]
    choices = []
    for slot, share in layout:
        constraints = data.constraints.get(slot, MealConstraints())
        target = float(data.energy_target) * share
        fixed = data.fixed_meals.get(slot)
        if fixed:
            item = manual_item(menus, fixed.menu_id, fixed.custom_name, fixed.amount_g)
            nutrients, _ = sum_nutrition([item])
            options = [
                {
                    'items': [item],
                    'nutrients': nutrients,
                    'minutes': None,
                    'cost': 0,
                    'energy': float(nutrients['energy_kcal'] or 0),
                }
            ]
        else:
            options = meal_options(
                menus,
                slot,
                target,
                constraints,
                settings,
                scores,
                protein_target=float(data.protein_target) * share if data.protein_target else None,
                recent_meals=recent_meals.get(slot),
            )
        choices.append((slot, share, constraints, options))
    reserved = day_family_counts(
        [
            option
            for slot, _, _, options in choices
            if slot in data.fixed_meals
            for option in options
        ]
    )
    beam = [([], 0, set(), {}, reserved, 0)]
    for choice_index, (slot, share, constraints, options) in enumerate(choices):
        next_beam = []
        remaining_families = [
            {frozenset(day_menu_families(option['items'])) for option in future_options}
            for future_slot, _, _, future_options in choices[choice_index + 1 :]
            if future_slot not in data.fixed_meals and future_options
        ]
        if not options:
            options = [
                {
                    'items': [],
                    'nutrients': {field: None for field in NUTRIENT_FIELDS},
                    'minutes': None,
                    'cost': 2,
                    'energy': 0,
                }
            ]
        for chosen, cost, used, groups, families, family_repeats in beam:
            for option in options:
                ids = {item['menu_id'] for item in option['items']}
                repeat = len(used & ids) * 0.4
                counts = dict(groups)
                for group in ingredient_groups(option['items']):
                    counts[group] = counts.get(group, 0) + 1
                next_families = dict(families)
                additional_repeats = 0
                if slot not in data.fixed_meals:
                    for family in day_menu_families(option['items']):
                        additional_repeats += families.get(family, 0)
                        next_families[family] = next_families.get(family, 0) + 1
                next_beam.append(
                    (
                        chosen + [(slot, share, constraints, option)],
                        cost + option['cost'] + repeat + diversity_cost(option['items'], groups),
                        used | ids,
                        counts,
                        next_families,
                        family_repeats + additional_repeats,
                    )
                )

        def partial_cost(row):
            share_so_far = sum(part[1] for part in row[0])
            cost = row[1] * 0.4
            for field, goal in [
                ('energy_kcal', data.energy_target),
                ('protein_g', data.protein_target),
                ('carbohydrate_g', data.carbohydrate_target),
                ('fat_g', data.fat_target),
            ]:
                if not goal or any(part[3]['nutrients'][field] is None for part in row[0]):
                    continue
                value = sum(float(part[3]['nutrients'][field]) for part in row[0])
                target = float(goal) * share_so_far
                weight = (
                    (2 if settings.goal == 'energy' else 1)
                    if field == 'energy_kcal'
                    else (0.75 if field == 'protein_g' and settings.goal == 'protein' else 0.25)
                )
                cost += abs(value - target) / target * weight
            return cost

        def projected_repeats(row):
            # 뒤쪽 고정 메뉴는 예약했고, 후보가 제한된 뒤쪽 자동 추천도 미리 확인한다.
            return row[5] + sum(
                min(sum(row[4].get(family, 0) for family in families) for families in candidates)
                for candidates in remaining_families
            )

        next_beam.sort(key=lambda row: (projected_repeats(row), partial_cost(row)))
        beam = next_beam[:48]

    def day_cost(row):
        nutrients = {
            field: sum(float(part[3]['nutrients'][field] or 0) for part in row[0])
            for field in NUTRIENT_FIELDS
        }
        missing = {
            field
            for part in row[0]
            for field in NUTRIENT_FIELDS
            if part[3]['nutrients'][field] is None
        }
        cost = row[1] * 0.4
        if 'energy_kcal' not in missing:
            cost += (
                abs(nutrients['energy_kcal'] - float(data.energy_target))
                / float(data.energy_target)
                * (2 if settings.goal == 'energy' else 1)
            )
        for field, target in [
            ('protein_g', data.protein_target),
            ('carbohydrate_g', data.carbohydrate_target),
            ('fat_g', data.fat_target),
        ]:
            if target and field not in missing:
                cost += (
                    abs(nutrients[field] - float(target))
                    / float(target)
                    * (0.75 if field == 'protein_g' and settings.goal == 'protein' else 0.25)
                )
        return cost

    best = min(beam, key=lambda row: (row[5], day_cost(row)))[0]
    result = []
    for slot, share, constraints, option in best:
        others = set().union(
            *(
                day_menu_families(other['items'])
                for other_slot, _, _, other in best
                if other_slot != slot
            )
        )
        reason = (
            '직접 정한 끼니를 고정했어요. 다른 끼니를 바꿔도 메뉴와 양을 유지해요.'
            if slot in data.fixed_meals
            else meal_reason(
                option,
                float(data.energy_target) * share,
                constraints,
                menus,
                settings,
                scores,
                slot,
                recent_meals.get(slot),
                others,
            )
        )
        result.append(
            {
                'key': slot,
                'label': LABELS[slot],
                'locked': slot in data.fixed_meals,
                'consumed': False,
                'status': 'ready' if option['items'] else 'empty',
                'items': option['items'],
                'nutrients': option['nutrients'],
                'minutes': option['minutes'],
                'constraints': constraints.model_dump(mode='json'),
                'energy_reference': str(round(float(data.energy_target) * share, 2)),
                'reason': reason,
            }
        )
    return result


def replace_meal(payload, key, menus, settings, scores, new_constraints=None, recent_meals=None):
    meal = next((meal for meal in payload['meals'] if meal['key'] == key), None)
    if meal is None:
        raise HTTPException(404, '이 계획의 끼니를 찾지 못했어요.')
    if meal['locked']:
        raise HTTPException(409, '고정한 끼니예요. 고정을 해제한 뒤 바꿔 주세요.')
    constraints = MealConstraints.model_validate(new_constraints or meal['constraints'])
    target = float(meal['energy_reference'])
    used = {
        item['menu_id']
        for other in payload['meals']
        if other['key'] != key
        for item in other['items']
        if item['menu_id']
    }
    previous = {item['menu_id'] for item in meal['items'] if item['menu_id']}
    protein_target = payload['settings'].get('protein_target')
    options = meal_options(
        menus,
        key,
        target,
        constraints,
        settings,
        scores,
        previous,
        protein_target=(
            float(protein_target) * target / float(payload['settings']['energy_target'])
            if protein_target
            else None
        ),
        recent_meals=recent_meals,
    )
    others = [item for other in payload['meals'] if other['key'] != key for item in other['items']]
    families = day_family_counts([other for other in payload['meals'] if other['key'] != key])
    groups = {}
    for other in payload['meals']:
        if other['key'] != key:
            for group in ingredient_groups(other['items']):
                groups[group] = groups.get(group, 0) + 1
    other_values, missing = sum_nutrition(others)

    def score(option):
        cost = (
            option['cost']
            + sum(item['menu_id'] in used for item in option['items']) * 0.4
            + diversity_cost(option['items'], groups)
        )
        if not missing:
            cost += (
                abs(
                    float(other_values['energy_kcal'])
                    + option['energy']
                    - float(payload['settings']['energy_target'])
                )
                / float(payload['settings']['energy_target'])
                * 0.8
            )
        return cost

    if not options:
        meal['reason'] = (
            '다른 메뉴를 찾지 못해 현재 끼니를 유지했어요. 조건을 조절해 다시 찾아보세요.'
        )
        return payload
    option = min(
        options,
        key=lambda option: (
            sum(families.get(family, 0) for family in day_menu_families(option['items'])),
            score(option),
        ),
    )
    meal.update(
        items=option['items'],
        nutrients=option['nutrients'],
        minutes=option['minutes'],
        constraints=constraints.model_dump(mode='json'),
        status='ready',
        reason='다른 끼니는 유지했어요. '
        + meal_reason(
            option, target, constraints, menus, settings, scores, key, recent_meals, set(families)
        ),
    )
    return update_summary(payload)


def grouped_food_search(session, query, limit, offset):
    from app.food_catalog import ALIASES
    from sqlalchemy import or_

    query_key = normalize_name(query)
    if not query_key:
        raise HTTPException(422, '음식 이름을 입력해 주세요.')
    terms = ALIASES.get(query_key, (query_key,))
    terms = tuple(
        set(terms)
        | {
            spec['source_name']
            for spec in menu_definitions()['menus']
            if any(normalize_name(alias) == query_key for alias in spec['aliases'])
        }
    )
    conditions = or_(
        *(Food.normalized_name.contains(normalize_name(term), autoescape=True) for term in terms)
    )
    rows = session.execute(
        select(Food, NutritionSnapshot)
        .join(NutritionSnapshot)
        .where(NutritionSnapshot.active.is_(True), conditions)
    ).all()
    groups = {}
    display_names = {
        normalize_name(alias): spec['name']
        for spec in menu_definitions()['menus']
        for alias in spec['aliases']
    }
    for food, snapshot in rows:
        display = display_names.get(food.normalized_name, food.name.replace('_', ' · '))
        # 재료 위치만 다른 통용 이름을 묶고 원본 기준량은 각 자료에 유지한다.
        display = {
            '열무비빔밥': '비빔밥 · 열무',
            '육회비빔밥': '비빔밥 · 육회',
            '낙지비빔밥': '비빔밥 · 낙지',
        }.get(normalize_name(display), display)
        group_key = (normalize_name(display), food.company or '')
        groups.setdefault(group_key, {'name': display, 'company': food.company, 'variants': []})[
            'variants'
        ].append(summarize(food, snapshot).model_dump(mode='json'))
    result = list(groups.values())
    for group in result:
        group['variants'].sort(
            key=lambda food: (
                food['basis_unit'] != 'g',
                any(value is None for value in food['nutrients'].values()),
                food['source']['food_code'],
            )
        )
        group['selected'] = group['variants'][0]
    result.sort(
        key=lambda group: (
            normalize_name(group['name']) != query_key,
            group['company'] is not None,
            group['selected']['basis_unit'] != 'g',
            group['name'],
            group['company'] or '',
        )
    )
    return {
        'query': query,
        'total': len(result),
        'source_total': len(rows),
        'requires_confirmation': len(result) > 1,
        'items': [group['selected'] for group in result[offset : offset + limit]],
        'groups': result[offset : offset + limit],
    }
