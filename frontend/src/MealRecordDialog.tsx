import { useEffect, useRef, useState } from 'react'
import { Icon } from './BrandArtwork'
import { PortionInput, amountText, draftAmount } from './PortionInput'
import type { Amount } from './PortionInput'
import type { PlanMeal } from './plannerTypes'

export const localTime = (value = new Date().toISOString()) => {
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

export function MealRecordDialog({ meal, drafts, pending, onClose, onSave, error, onRetry }: {
  meal: PlanMeal; drafts: Record<string, Amount>; pending: boolean;
  onClose: () => void; onSave: (amounts: Record<string, Amount>, eatenAt: string, skipped: string[]) => void; error?: string; onRetry?: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [amounts, setAmounts] = useState(() => Object.fromEntries(meal.items.map(item => [item.item_id, draftAmount(item, drafts)])))
  const [time, setTime] = useState(localTime())
  const [skipped, setSkipped] = useState<Record<string, boolean>>({})
  const omitted = meal.items.filter(item => skipped[item.item_id] || (amounts[item.item_id] !== null && amounts[item.item_id] !== '' && Number(amounts[item.item_id]) === 0)).map(item => item.item_id)
  useEffect(() => { const node = dialog.current!; node.showModal(); return () => node.close() }, [])
  return <dialog className="service-dialog" ref={dialog} aria-labelledby="record-meal-title" onCancel={event => { if (pending) event.preventDefault(); else onClose() }}>
    <button className="dialog-close" aria-label="식사 확인 닫기" disabled={pending} onClick={onClose}><Icon name="close" /></button>
    <span className="status-pill">{meal.label} · 식사 기록</span><h2 id="record-meal-title">실제로 먹은 만큼 남겨요</h2>
    <p>계획한 양에서 절반·그대로를 고르거나 실제 먹은 양을 입력해요. 직접 적은 음식은 분량을 몰라도 기록할 수 있어요. 계획한 분량은 그대로 보관해요.</p>
    <form onSubmit={event => { event.preventDefault(); if (omitted.length < meal.items.length) onSave(Object.fromEntries(Object.entries(amounts).filter(([id]) => !omitted.includes(id))), new Date(time).toISOString(), omitted) }}>
      {meal.items.map(item => <div className={`record-food ${omitted.includes(item.item_id) ? 'not-eaten' : ''}`} key={item.item_id}>
        <h3>{item.name}<small>계획 {amountText(item.amount_g)}</small></h3>
        <PortionInput label={`실제로 먹은 ${item.name} 양`} value={amounts[item.item_id]} onChange={value => setAmounts(old => ({ ...old, [item.item_id]: value }))} disabled={pending || skipped[item.item_id]} allowUnknown={!item.menu_id} allowZero reference={item.amount_g} referenceLabel="계획한 양" quickBasis="planned" />
        {item.menu_id && Number.isFinite(item.reference_portion_g) && Number(item.reference_portion_g) > 0 && Number(item.reference_portion_g) !== Number(item.amount_g) && <details className="record-reference"><summary>메뉴 참고 기준량 {amountText(String(item.reference_portion_g))}</summary><p>메뉴 자료의 참고 분량이에요. 위 빠른 선택은 계획한 {amountText(item.amount_g)}을 기준으로 해요.</p><button type="button" className="text-button" aria-label={`${item.name} 메뉴 기준량으로 입력`} disabled={pending || skipped[item.item_id] || Number(item.reference_portion_g) > 2000} onClick={() => setAmounts(old => ({ ...old, [item.item_id]: String(item.reference_portion_g) }))}>메뉴 기준량으로 입력</button></details>}
        <label className="record-skip"><input type="checkbox" checked={omitted.includes(item.item_id)} disabled={pending} onChange={event => { setSkipped(old => ({ ...old, [item.item_id]: event.target.checked })); if (!event.target.checked && amounts[item.item_id] !== null && amounts[item.item_id] !== '' && Number(amounts[item.item_id]) === 0) setAmounts(old => ({ ...old, [item.item_id]: item.amount_g })) }} />이번에는 안 먹었어요</label>
      </div>)}
      <label>먹은 시각<input type="datetime-local" required disabled={pending} value={time} onChange={event => setTime(event.target.value)} /></label>
      <p className="muted small">저장한 뒤에도 식사 기록에서 분량·시각을 고치거나 완료를 되돌릴 수 있어요.</p>
      <p className="record-selection-note" role="status">{omitted.length === meal.items.length ? '먹은 음식을 하나 이상 선택해 주세요. 아직 안 먹었다면 창을 닫아 주세요.' : `음식 ${meal.items.length - omitted.length}개를 기록해요.${omitted.length ? ` 안 먹은 ${omitted.length}개는 계획에 남기고 기록에서 제외해요.` : ' 0g을 입력하면 안 먹은 음식으로 처리해요.'}`}</p>
      {error && <div className="error" role="alert">{error}{onRetry && <button type="button" className="text-button" disabled={pending} onClick={onRetry}>같은 내용 다시 시도</button>}</div>}
      <div className="dialog-actions"><button type="button" className="secondary" disabled={pending} onClick={onClose}>아직 안 먹었어요</button><button className="primary" disabled={pending || omitted.length === meal.items.length}>{pending ? '기록 중…' : '이 내용으로 기록'}</button></div>
    </form>
  </dialog>
}
