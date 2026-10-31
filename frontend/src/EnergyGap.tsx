import { kcal, mealLabels } from './plannerDisplay'
import { energyGap } from './planEnergy'
import type { MealKey, Plan } from './plannerTypes'

type Props = { plan: Plan; selected: MealKey; pending: boolean; onSelect: (key: MealKey) => void; onPortion: (key: MealKey) => void; onConditions: (key: MealKey) => void; onAdd: (key: MealKey) => void }

export function EnergyGap({ plan, selected, pending, onSelect, onPortion, onConditions, onAdd }: Props) {
  const gap = energyGap(plan)
  if (!gap.visible) return null
  const meal = gap.editable.find(value => value.key === selected) ?? gap.editable[0]
  const below = gap.difference !== null && gap.difference < 0
  const constrained = plan.meals.filter(value => value.constraints.max_minutes || value.constraints.no_cook || value.constraints.tools.length || value.constraints.avoided_foods.length)
  const fixed = plan.meals.filter(value => value.locked || value.consumed)
  return <details className="energy-gap" aria-labelledby="energy-gap-title">
    <summary className="energy-gap-summary"><span><strong id="energy-gap-title">{gap.difference === null ? '영양 자료가 일부 없어 목표 비교를 보류해요' : <>목표보다 약 {kcal(Math.abs(gap.difference))}kcal {below ? '적어요' : '많아요'}</>}</strong><small>메뉴를 확인하고, 필요하면 조절해요.</small></span><span className="energy-gap-toggle">차이 확인·조절</span></summary>
    <div className="energy-gap-body">
    {gap.difference === null ? <p>직접 입력한 음식이나 비어 있는 끼니의 영양은 알 수 없어요. 확인된 값만 더했으므로 부족·초과를 확정하지 않아요. 메뉴를 확인하거나 영양 자료가 있는 메뉴로 바꿀 수 있어요.</p> : <>
      <p>입력한 목표는 선택 기준이에요. 메뉴별 추천 분량 범위 안에서 준비 조건·취향·메뉴 구성을 함께 고려해 골라요.</p>
      {below && gap.atUpperLimit && <p className="energy-gap-limit">현재 메뉴는 추천 분량 상한에 도달했어요. 범위 밖으로 무리하게 늘리기보다 음식을 추가하거나 다른 구성을 찾아보세요.</p>}
      {!below && gap.atLowerLimit && <p className="energy-gap-limit">현재 메뉴는 추천 분량 하한에 도달했어요. 다른 메뉴로 바꾸거나 실제 먹을 양을 직접 조절할 수 있어요.</p>}
    </>}
    {(constrained.length > 0 || fixed.length > 0) && <details><summary>이번 식단에 적용된 조건 보기</summary><ul>{constrained.map(value => <li key={value.key}>{value.label}: {[value.constraints.no_cook ? '조리 없이 먹기' : '', value.constraints.max_minutes ? value.constraints.max_minutes + '분 이내' : '', value.constraints.tools.length ? '선택한 기구만 사용' : '', value.constraints.avoided_foods.length ? '제외 음식 적용' : ''].filter(Boolean).join(' · ')}</li>)}{fixed.map(value => <li key={'fixed-' + value.key}>{value.label}: {value.consumed ? '먹은 기록이 있어 유지' : '메뉴 전체 고정'}</li>)}</ul><p>이 조건들이 함께 적용됐어요. 어느 조건 하나가 차이의 원인이라고 단정하지 않아요.</p></details>}
    {meal ? <>
      <label className="energy-gap-meal">조절할 끼니<select aria-label="열량을 조절할 끼니" value={meal.key} disabled={pending} onChange={event => onSelect(event.target.value as MealKey)}>{gap.editable.map(value => <option key={value.key} value={value.key}>{mealLabels[value.key]} · {value.nutrients.energy_kcal === null ? '영양 자료 없음' : `${value.items.some(item => item.nutrients.energy_kcal === null) ? '확인된 ' : ''}${kcal(value.nutrients.energy_kcal)}kcal`}{value.locked ? ' · 고정' : ''}</option>)}</select></label>
      <div className="energy-gap-actions">{(below && gap.atUpperLimit) || !meal.items.length ? <button className="primary" disabled={pending || meal.items.length >= 12} onClick={() => onAdd(meal.key)}>음식 추가하기</button> : <button className="primary" disabled={pending} onClick={() => onPortion(meal.key)}>{gap.difference === null ? '메뉴·분량 확인하기' : '분량 조절하기'}</button>}<button className="secondary" disabled={pending || meal.locked} onClick={() => onConditions(meal.key)}>조건 보고 재추천</button>{below && gap.atUpperLimit && <button className="text-button" disabled={pending} onClick={() => onPortion(meal.key)}>분량 직접 조절</button>}</div>
      <small>{meal.locked ? '고정한 메뉴도 양 조절·음식 추가는 가능해요. 자동 재추천은 끼니에서 고정을 해제한 뒤 사용할 수 있어요.' : '선택한 끼니만 조절해요. 다른 끼니와 먹은 기록은 유지해요.'}</small>
    </> : <p>모든 끼니를 먹은 것으로 기록했어요. 실제 먹은 양은 식사 기록에서 확인하고 수정할 수 있어요.</p>}
    </div>
  </details>
}
