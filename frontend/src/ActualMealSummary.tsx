import { amountText } from './PortionInput'
import { grams, kcal } from './plannerDisplay'
import type { ActualMeal, PlanMeal } from './plannerTypes'

export function ActualMealSummary({ meal, actual, loading, error, onRetry }: { meal: PlanMeal; actual?: ActualMeal; loading: boolean; error: string; onRetry: () => void }) {
  const saved = actual?.state === 'ready' ? actual : null
  const complete = saved && !saved.missing_nutrients.includes('energy_kcal') && saved.nutrients.energy_kcal !== null
  const planComplete = meal.nutrients.energy_kcal !== null && meal.items.every(item => item.nutrients.energy_kcal !== null)
  const difference = complete && planComplete ? Number(saved.nutrients.energy_kcal) - Number(meal.nutrients.energy_kcal) : null
  return <section className="actual-meal-summary" aria-label={`${meal.label} 실제 섭취 요약`}>
    <div className="actual-summary-heading"><h3>실제로 먹은 식사</h3><span>기록 완료</span></div>
    {!saved ? <div role={error || actual?.state === 'unavailable' ? 'alert' : 'status'}><p>{loading ? '실제 식사 기록을 확인하고 있어요.' : error ? `실제 기록을 불러오지 못했어요. ${error}` : '연결된 실제 기록을 확인하지 못했어요. 계획량을 실제 섭취량으로 표시하지 않아요.'}</p>{!loading && <button type="button" className="secondary" onClick={onRetry}>실제 기록 다시 불러오기</button>}</div> : <>
      <div className="actual-energy"><span>{complete ? '실제 먹은 열량' : '확인된 실제 열량'}</span><strong>{saved.nutrients.energy_kcal === null ? '자료 없음' : <>{kcal(saved.nutrients.energy_kcal)}<small> kcal</small></>}</strong></div>
      <p className="actual-plan-comparison">계획 {planComplete ? `${kcal(meal.nutrients.energy_kcal)} kcal` : '영양 자료 일부 없음'}{difference !== null && <> · {Math.abs(difference) < 0.5 ? '계획과 비슷하게 먹었어요' : `계획보다 약 ${kcal(Math.abs(difference))} kcal ${difference < 0 ? '적게' : '더'} 먹었어요`}</>}</p>
      {!complete && <p className="actual-missing-note">자료 없는 음식은 합계에서 빠져 있어요. 계획과 전체 열량 비교는 보류해요.</p>}
      <ul className="actual-food-list">{saved.items.map(item => {
        const planned = meal.items.filter(value => value.name === item.name && (value.food?.id ?? null) === item.food_id)
        return <li key={item.id}><strong>{item.name}</strong><span className="actual-portions"><small>계획 {planned.length === 1 ? amountText(planned[0].amount_g) : '메뉴 목록 참고'}</small><strong>실제 {amountText(item.portion?.amount ?? null, item.portion?.unit ?? 'g')}</strong></span></li>
      })}</ul>
      {saved.skipped_foods.length > 0 && <p className="actual-skipped">이번에는 안 먹었어요: {saved.skipped_foods.join(', ')}</p>}
      <dl className="actual-macros">{([['carbohydrate_g', '탄수화물'], ['protein_g', '단백질'], ['fat_g', '지방']] as const).map(([field,label]) => <div key={field}><dt>{label}{saved.missing_nutrients.includes(field) && ' · 일부'}</dt><dd>{grams(saved.nutrients[field])}{saved.nutrients[field] !== null && ' g'}</dd></div>)}</dl>
    </>}
    <small>계획은 보관하고, 식사 기록에서 고친 최신 분량을 보여줘요.</small>
  </section>
}
