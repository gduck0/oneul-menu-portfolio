import { useEffect, useRef } from 'react'
import { PortionInput, amountText, draftAmount, sameAmount } from './PortionInput'
import type { Amount } from './PortionInput'
import { MealConditions } from './MealConditions'
import { Icon } from './BrandArtwork'
import { FoodArtwork } from './FoodArtwork'
import { grams, kcal, roleLabels } from './plannerDisplay'
import type { MealConstraints, PlanMeal } from './plannerTypes'
import { portionPreview } from './planEnergy'

type Props = {
  focusRequest?: { id: number; section: 'portion' | 'conditions' | 'overview' }; onConditionRecommend?: () => void;
  dayEnergy?: string | null; energyTarget?: number; completeEnergy?: boolean;
  meal: PlanMeal; constraints: MealConstraints; pending: boolean; amounts: Record<string, Amount>;
  onAmount: (id: string, value: Amount) => void; onConstraint: (value: Partial<MealConstraints>) => void;
  onEdit: (action: string, fields?: Record<string, unknown>) => void;
  onPick: (action?: 'set' | 'add' | 'update_item', itemId?: string) => void;
  onCompare?: () => void;
  onOverview?: () => void;
}

export function PlanMealCard({ meal, constraints, pending, amounts, onAmount, onConstraint, onEdit, onPick, onCompare, onOverview, focusRequest, onConditionRecommend, dayEnergy = null, energyTarget = 0, completeEnergy = false }: Props) {
  const card = useRef<HTMLElement>(null), portionSection = useRef<HTMLDetailsElement>(null), conditionsSection = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    if (!focusRequest) return
    const section = focusRequest.section === 'portion' ? portionSection.current : focusRequest.section === 'conditions' ? conditionsSection.current : card.current
    if (!section) return
    if (section instanceof HTMLDetailsElement) section.open = true
    const frame = requestAnimationFrame(() => {
      if (!section.getClientRects().length) return
      const target = section.querySelector<HTMLElement>(focusRequest.section === 'overview' ? 'h2' : 'input,select,button')
      target?.focus({ preventScroll: true }); section.scrollIntoView({ block: 'start', behavior: 'instant' })
    })
    return () => cancelAnimationFrame(frame)
  }, [focusRequest?.id])
  const partial = meal.items.some(item => item.nutrients.energy_kcal === null)
  const dirty = meal.items.some(item => amounts[item.item_id] !== undefined && !sameAmount(amounts[item.item_id], item.amount_g))
  const preview = dirty ? portionPreview(meal, amounts, dayEnergy, completeEnergy) : null
  const plannedDetails = <div className="selected-layout"><div className="selected-foods">
      <ul className="selected-food-list">{meal.items.map(item => <li key={item.item_id}><FoodArtwork item={item} /><div><h3>{item.name}</h3><p>{roleLabels[item.role] ?? '직접 입력'} <span>· {amountText(item.amount_g)}</span>{meal.consumed && <span> · 계획 분량</span>}</p></div>{!meal.consumed && <button className="item-change" aria-label={item.name + '만 변경'} disabled={pending} onClick={() => onPick('update_item', item.item_id)}><Icon name="refresh" />변경</button>}</li>)}</ul>
      {!meal.items.length && <div className="plan-empty-meal"><h3>메뉴를 직접 골라도 좋아요</h3><p>조건을 바꾸거나 먹고 싶은 메뉴를 담아주세요.</p></div>}
      {!meal.consumed && <button className="inline-link add-food" disabled={pending || meal.items.length >= 12} onClick={() => onPick('add')}><Icon name="plus" />음식 하나 추가</button>}
    </div><aside className="meal-insight" aria-label={meal.label + ' 참고 영양'}><span>{partial ? '확인된 참고 영양' : '이 끼니의 참고 영양'}</span><strong className="meal-energy">{meal.nutrients.energy_kcal === null ? '자료 없음' : <>{kcal(meal.nutrients.energy_kcal)} <small>kcal</small></>}</strong><dl className="meal-macro-list">{([['carbohydrate_g', '탄수화물'], ['protein_g', '단백질'], ['fat_g', '지방']] as const).map(([field, label]) => <div key={field}><dt>{label}</dt><dd>{grams(meal.nutrients[field])}{meal.nutrients[field] !== null && ' g'}</dd></div>)}</dl><p className="meal-time"><Icon name="clock" />{meal.minutes !== null ? '참고 준비 ' + meal.minutes + '분' : '직접 정한 끼니'}</p><small>{partial ? '자료가 없는 음식은 합계에서 빠져 있어요.' : '현재 계획 분량 기준이에요.'}</small></aside></div>
  return <article ref={card} className={`plan-meal selected-meal meal-${meal.key} ${meal.locked ? 'locked' : ''} ${meal.consumed ? 'consumed' : ''}`} aria-label={`${meal.label} 메뉴`}>
    {onOverview && <button type="button" className="meal-back-overview" onClick={onOverview}>↑ 하루 개요로 돌아가기</button>}
    <div className="plan-meal-top"><div><span className="meal-label-en">{({ breakfast: 'BREAKFAST', lunch: 'LUNCH', dinner: 'DINNER', snack: 'SNACK' })[meal.key]}</span><h2 tabIndex={-1}>{meal.label} 식단</h2><p className="editor-description">{meal.consumed ? '기록된 식단의 계획 메뉴와 분량을 확인해요.' : '이 끼니만 바꾸고, 다른 끼니는 그대로 두세요.'}</p></div>{meal.consumed ? <span className="status-pill done"><Icon name="check" />식사 기록 완료</span> : <button className={meal.locked ? 'plan-lock active' : 'plan-lock'} aria-label={`${meal.label} 전체 ${meal.locked ? '고정 해제' : '고정'}`} title="이 끼니 전체의 자동 추천 교체를 막아요. 직접 메뉴와 양은 바꿀 수 있어요." aria-pressed={meal.locked} disabled={pending || !meal.items.length} onClick={() => onEdit('lock', { locked: !meal.locked })}><Icon name="lock" />{meal.locked ? '고정 해제' : '전체 고정'}</button>}</div>
    {plannedDetails}
    {meal.consumed ? <p className="meal-complete">이미 기록된 식단이에요. 표시된 메뉴·영양은 계획 기준이에요.</p> : <div className="meal-editor-footer"><span className="edit-scope">{dirty ? '입력한 양은 아직 저장 전이에요.' : meal.locked ? '이 끼니 전체를 고정했어요. 직접 변경은 가능해요.' : '이 끼니 전체를 바꿔요. 다른 끼니는 유지해요.'}</span><div className="plan-meal-actions"><button className="plan-primary" disabled={pending || meal.locked || dirty} onClick={() => onEdit('replace', { constraints })}><Icon name="refresh" />다른 메뉴 추천</button></div>{meal.undo_replacement && <div className="replacement-undo"><p>이전 메뉴: {meal.undo_replacement.names.length ? meal.undo_replacement.names.join(', ') : '메뉴를 정하기 전'}<small>이번 추천을 받기 전의 메뉴·분량·준비 조건으로 돌아가요. 이 끼니를 다시 수정하거나 기록하기 전까지 사용할 수 있어요.</small></p><button className="secondary" disabled={pending || dirty} onClick={() => onEdit('undo_replace', { replacement_request_id: meal.undo_replacement!.request_id })}>변경 전으로 되돌리기</button></div>}<details className="meal-change-menu"><summary>{onCompare ? '직접 고르기·영양 비교' : '직접 고르기'}</summary><p className="muted small">직접 바꿔도 자동으로 고정하지 않아요. 원할 때 끼니 전체를 고정할 수 있어요.</p><div><button disabled={pending} onClick={() => onPick('set')}>끼니 전체 직접 고르기</button>{onCompare && <button disabled={pending} onClick={onCompare}>메뉴 영양 비교</button>}</div></details>{meal.locked && <small>다른 메뉴를 추천받으려면 위의 고정 해제를 눌러 주세요.</small>}{dirty && <small>구성·양 조절에서 입력한 양을 적용하거나 원래대로 돌린 뒤 추천받을 수 있어요. </small>}</div>}
    <details ref={portionSection} className="plan-utilities"><summary>{meal.consumed ? '계획 메뉴별 준비·출처' : '구성·양 조절'}</summary>
      {preview && <div className="portion-preview" role="status"><strong>입력한 양을 모두 적용하면</strong><p>이 끼니 약 {kcal(preview.meal)}kcal{preview.day !== null && <> · 하루 약 {kcal(preview.day)}kcal</>}</p>{preview.day !== null && energyTarget > 0 && <p>{Math.abs(preview.day - energyTarget) < 0.5 ? '하루 목표와 거의 같아요.' : <>하루 목표보다 약 {kcal(Math.abs(preview.day - energyTarget))}kcal {preview.day < energyTarget ? '적어요' : '많아요'}.</>}</p>}<small>적용 전 미리보기예요. 아래 ‘양 적용’을 음식별로 눌러 저장해 주세요.</small></div>}
      {meal.items.map(item => <div className="plan-item" key={item.item_id}><h4>{item.name}</h4><p className="plan-item-meta">{item.nutrition_note}</p>{item.min_g != null && item.max_g != null && <p className="portion-range">추천 참고 범위 {item.min_g}–{item.max_g}g · 직접 먹을 양은 입력할 수 있어요.</p>}
        {!meal.consumed && <><form className="plan-portion" onSubmit={event => { event.preventDefault(); onEdit('portion', { item_id: item.item_id, amount_g: draftAmount(item, amounts) }) }}><PortionInput label={`${meal.label} ${item.name} 먹을 양`} value={draftAmount(item, amounts)} disabled={pending} allowUnknown={!item.menu_id} reference={item.reference_portion_g ?? item.amount_g} referenceLabel={item.reference_portion_g ? '메뉴 기준량' : '계획한 양'} onChange={value => onAmount(item.item_id, value)} /><button disabled={pending}>양 적용</button></form>
          <div className="item-edit-actions">{amounts[item.item_id] !== undefined && !sameAmount(amounts[item.item_id], item.amount_g) && <button className="text-button" disabled={pending} onClick={() => onAmount(item.item_id, item.amount_g)}>원래 양으로</button>}<button className="text-button" disabled={pending} onClick={() => onEdit('remove', { item_id: item.item_id })}>구성에서 빼기</button></div></>}
        <details className="plan-item-details"><summary>준비 안내·영양 출처</summary>{item.preparation ? <><p><strong>{item.prepared ? '준비된 음식 이용' : '준비 방법 참고'}</strong><br />{item.preparation}</p><p>재료 예시: {item.ingredients.join(', ')}</p></> : <p>내가 정한 음식이에요. 조리법과 영양을 임의로 추정하지 않아요.</p>}<small>재료량을 검증한 계량 레시피는 아직 제공하지 않아요. 구매 음식은 제품 표시, 직접 조리는 사용하는 레시피를 확인해 주세요.</small>{item.food && <p>{item.food.source.provider} · {item.food.source.food_code}<br />{item.food.source.reference_date}<br /><a href={item.food.source.url} target="_blank" rel="noreferrer">영양 자료 출처 보기 ↗</a></p>}</details></div>)}

    </details>
    <details ref={conditionsSection} className="plan-why"><summary>추천 이유·준비 조건</summary><p>{meal.reason}</p><small>끼니 참고 기준 약 {kcal(meal.energy_reference)}kcal</small>{!meal.consumed && <><MealConditions value={constraints} label={meal.label} disabled={pending} onChange={onConstraint} />{onConditionRecommend && <button className="plan-primary condition-recommend" disabled={pending || meal.locked || dirty} onClick={onConditionRecommend}>{pending ? '추천 중…' : '이 조건으로 다시 추천'}</button>}<small>변경한 준비 조건은 다른 메뉴를 추천받을 때 적용해요. 전체 재료·알레르기 판별은 제공하지 않아요.</small></>}</details>
  </article>
}
