import { feedbackReasons } from './feedbackScope'
import { amountText } from './PortionInput'
import { useId } from 'react'
import { displayName, NutrientGrid, number } from './FoodCard'
import { MealEntryActions } from './MealEntryActions'
import { MenuFeedback } from './MenuFeedback'
import type { Feedback, MealGroup } from './types'

export function MealGroupCard({ group, feedback, onFeedback, onChange }: {
  group: MealGroup; feedback: Feedback[];
  onFeedback: (value: Feedback | null, previousId?: string) => void;
  onChange: (action?: string) => void
}) {
  const title = useId()
  const cancelled = Boolean(group.items[0].cancelled_at)
  return <section className={`journal-group ${cancelled ? 'cancelled' : ''}`} aria-labelledby={title}>
    <header className="journal-group-heading"><div><time dateTime={group.eaten_at}>{new Date(group.eaten_at).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })}</time><h3 id={title}>{group.label}</h3><p>{new Date(group.eaten_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })} · 음식 {group.items.length}개</p></div><span className="status-pill">{cancelled ? '취소한 식사' : '기록 완료'}</span></header>
    <div className="journal-group-energy">{group.missing_nutrients.length ? '확인된 열량' : '실제 먹은 열량'} <strong>{number(group.nutrients.energy_kcal)}</strong>{group.nutrients.energy_kcal !== null && ' kcal'}</div>
    {group.missing_nutrients.length > 0 && <p className="journal-group-note">자료가 없는 음식은 영양 합계에서 빠져 있어요.</p>}
    {group.skipped_foods.length > 0 && <p className="journal-group-note">이번에는 안 먹었어요: {group.skipped_foods.join(', ')}. 계획한 메뉴는 그대로 남아 있어요.</p>}
    <div className="journal-group-foods">{group.items.map(meal => {
      const rating = feedback.find(value => value.phase === 'consumed' && value.context_id === meal.id && value.food_id === meal.food_id)
      return <article className="journal-food" key={meal.id}>
        <div className="journal-food-title"><h4>{displayName(meal.name)}</h4><strong>{amountText(meal.portion?.amount ?? null, meal.portion?.unit ?? 'g')}</strong></div>
        <details className="journal-food-details"><summary>영양·시각·출처 보기</summary><time dateTime={meal.eaten_at}>{new Date(meal.eaten_at).toLocaleString('ko-KR')}</time>{meal.notes && <p>{meal.notes}</p>}<NutrientGrid nutrients={meal.nutrients} /><p>{meal.nutrition_source === 'catalog' ? '공식 음식 자료 기준 · 실제 분량으로 계산' : meal.nutrition_source === 'menu_reference' ? '식단 메뉴 참고값 · 실제 분량으로 계산' : '직접 입력 · 영양 자료 없음'}</p>{meal.nutrition && <p>{meal.nutrition.food.source.provider} · {meal.nutrition.food.source.food_code}<br />원본 기준 {number(meal.nutrition.food.basis_amount)}{meal.nutrition.food.basis_unit}<br />자료 기준일 {meal.nutrition.food.source.reference_date}</p>}</details>
        <MealEntryActions meal={meal} onChange={onChange} editOnly />
        {!cancelled && <details className="journal-feedback"><summary>{rating ? `내 평가: ${{ like: '만족', neutral: '보통', dislike: '아쉬워요' }[rating.rating]} · ${rating.reason ? feedbackReasons[rating.reason] : '이유 없이 기록'}` : '이 음식 평가하기'}</summary><MenuFeedback phase="consumed" contextId={meal.id} foodId={meal.food_id} value={rating} onChange={onFeedback} /></details>}
      </article>
    })}</div>
    <div className="journal-group-actions"><MealEntryActions meal={group.items[0]} onChange={onChange} groupOnly scopeLabel={group.label} groupCount={group.items.length} /></div>
  </section>
}
