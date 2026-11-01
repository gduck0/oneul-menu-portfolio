from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select

from app.personal_models import MealEntry, MenuFeedback


def rating_scores(session, owner):
    scores = defaultdict(list)
    rows = session.scalars(
        select(MenuFeedback)
        .where(MenuFeedback.owner_key == owner)
        .order_by(MenuFeedback.updated_at.desc(), MenuFeedback.id.desc())
        .limit(500)
    ).all()
    seen = set()
    for row in rows:
        if row.reason != 'taste':
            continue
        if row.phase == 'consumed':
            meal = session.get(MealEntry, row.context_id)
            if meal is None or meal.cancelled_at is not None:
                continue
        key = (row.food_code, row.phase)
        if row.food_code is None or key in seen:
            continue
        seen.add(key)
        value = {'like': 1, 'neutral': 0, 'dislike': -1}[row.rating]
        scores[row.food_code].append(
            Decimal(value) * Decimal('0.06' if row.phase == 'consumed' else '0.03')
        )
    return {
        key: max(Decimal('-0.09'), min(Decimal('0.09'), sum(values)))
        for key, values in scores.items()
    }
