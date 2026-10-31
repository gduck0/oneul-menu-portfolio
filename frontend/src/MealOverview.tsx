import { useId, useRef } from 'react'
import type { Ref } from 'react'
import { sameAmount } from './PortionInput'
import type { Amount } from './PortionInput'
import { FoodArtwork } from './FoodArtwork'
import { kcal } from './plannerDisplay'
import type { MealKey, PlanMeal } from './plannerTypes'

type Props = { meals: PlanMeal[]; selected: MealKey; onSelect: (key: MealKey, openDetail?: boolean) => void; amounts: Record<string, Amount>; panelId: string; summaryRef?: Ref<HTMLElement> }

export function MealOverview({ meals, selected, onSelect, amounts, panelId, summaryRef }: Props) {
  const id = useId()
  const tabs = useRef<(HTMLButtonElement | null)[]>([])
  return <section ref={summaryRef} tabIndex={summaryRef ? -1 : undefined} className="day-overview" aria-labelledby={id}>
    <div className="overview-heading"><h2 id={id}>하루 식단 한눈에</h2><span>끼니를 골라 자세히 바꿔요</span></div>
    <div className="meal-overview" data-count={meals.length} role="tablist" aria-label="수정할 끼니" style={{ gridTemplateColumns: `repeat(${meals.length}, minmax(0, 1fr))` }}>
      {meals.map((meal, index) => {
        const main = meal.items.find(item => item.role === 'main' || item.role === 'protein') ?? meal.items[0]
        const rest = meal.items.filter(item => item !== main)
        const dirty = meal.items.some(item => amounts[item.item_id] !== undefined && !sameAmount(amounts[item.item_id], item.amount_g))
        const partial = meal.items.some(item => item.nutrients.energy_kcal === null)
        return <button type="button" role="tab" id={`${panelId}-tab-${meal.key}`} aria-controls={panelId} aria-selected={selected === meal.key} tabIndex={selected === meal.key ? 0 : -1} key={meal.key} className="overview-tab" ref={element => { tabs.current[index] = element }} onClick={() => onSelect(meal.key, true)} onKeyDown={event => {
          const next = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? (index + 1) % meals.length : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? (index - 1 + meals.length) % meals.length : event.key === 'Home' ? 0 : event.key === 'End' ? meals.length - 1 : null
          if (next === null) return
          event.preventDefault(); onSelect(meals[next].key); tabs.current[next]?.focus()
        }}>
          <span className="overview-top"><span>{meal.label}</span><span className={`overview-state ${meal.consumed ? 'is-done' : ''}`}>{meal.consumed ? '기록 완료' : dirty ? '양 편집 중' : meal.locked ? '고정' : selected === meal.key ? '선택 중' : '계획'}</span></span>
          <span className="overview-food">{main && <FoodArtwork item={main} />}<strong>{main?.name ?? '메뉴 미정'}</strong></span>
          <span className="overview-sides">{rest.length ? rest.map(item => item.name).join(' · ') : main ? '한 가지 메뉴로 간편하게' : '먹고 싶은 메뉴를 담아보세요'}{meal.consumed && <small className="overview-plan-reference">계획 {meal.nutrients.energy_kcal === null ? '영양 자료 없음' : `${partial ? '확인된 ' : ''}${kcal(meal.nutrients.energy_kcal)} kcal`}</small>}</span>
          <span className={`overview-bottom${meal.consumed ? ' overview-actual' : ''}`}><span>{meal.nutrients.energy_kcal === null ? '영양 자료 없음' : `${meal.consumed ? '계획' : partial ? '확인된' : '약'} ${kcal(meal.nutrients.energy_kcal)} kcal`}</span><span>자세히 보기</span></span>
        </button>
      })}
    </div>
  </section>
}
