import type { Plan, PlanMeal } from './plannerTypes'

export function energyGap(plan: Plan) {
  const target = Number(plan.settings.energy_target)
  const complete = plan.nutrients.energy_kcal !== null && !plan.missing_nutrients.includes('energy_kcal')
  const actual = complete ? Number(plan.nutrients.energy_kcal) : null
  const difference = actual !== null && target > 0 ? actual - target : null
  const editable = plan.meals.filter(meal => !meal.consumed)
  const bounded = editable.flatMap(meal => meal.items).filter(item => item.menu_id)
  const atUpperLimit = bounded.length > 0 && bounded.every(item => item.max_g != null && Number(item.amount_g) >= item.max_g - 0.01)
  const atLowerLimit = bounded.length > 0 && bounded.every(item => item.min_g != null && Number(item.amount_g) <= item.min_g + 0.01)
  return { target, actual, difference, editable, atUpperLimit, atLowerLimit,
    visible: difference === null || Math.abs(difference) > target * 0.1 }
}

export function nutritionNotes(plan: Plan) {
  return plan.notes.map(note => {
    if (!note.startsWith('현재 분량과 고정한 끼니를 유지하면 하루 열량 목표와 차이가 남아요.')) return note
    const gap = energyGap(plan)
    if (gap.difference === null) return '자료가 없는 음식은 합계에서 빠져 있어 하루 목표 비교를 보류해요.'
    return `입력한 하루 목표보다 약 ${Math.round(Math.abs(gap.difference)).toLocaleString('ko-KR')}kcal ${gap.difference < 0 ? '낮아요' : '높아요'}. 메뉴별 추천 분량 범위와 직접 정한 메뉴·양, 준비 조건에 따라 차이가 날 수 있어요.`
  })
}

export function portionPreview(meal: PlanMeal, amounts: Record<string, string | null>, dayEnergy: string | null, complete: boolean) {
  if (!meal.items.length || meal.items.some(item => item.nutrients.energy_kcal === null)) return null
  let after = 0
  for (const item of meal.items) {
    const amount = Number(amounts[item.item_id] ?? item.amount_g), original = Number(item.amount_g)
    if (!Number.isFinite(amount) || amount <= 0 || amount > 2000 || original <= 0) return null
    const reference = item.reference_nutrients?.energy_kcal
    after += reference != null ? Number(reference) * amount / 100 : Number(item.nutrients.energy_kcal) * amount / original
  }
  const before = Number(meal.nutrients.energy_kcal)
  return { meal: after, day: complete && dayEnergy !== null ? Number(dayEnergy) - before + after : null }
}
