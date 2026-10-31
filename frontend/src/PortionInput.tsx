import { useRef } from 'react'

export type Amount = string | null
export const amountText = (amount: Amount, unit = 'g') => amount === null ? '분량 모름' : `${Number(amount).toLocaleString('ko-KR', { maximumFractionDigits: 3 })}${unit}`
export const sameAmount = (left: Amount, right: Amount) => left === null || right === null ? left === right : Number(left) === Number(right)
export const draftAmount = (item: { item_id: string; amount_g: Amount }, drafts: Record<string, Amount>) => Object.hasOwn(drafts, item.item_id) ? drafts[item.item_id] : item.amount_g

export function PortionInput({ label, value, onChange, disabled = false, allowUnknown = false, reference, referenceLabel = '기준 분량', unit = 'g', max = 2000, allowZero = false, quickBasis = 'reference' }: {
  label: string; value: Amount; onChange: (amount: Amount) => void; disabled?: boolean; allowUnknown?: boolean;
  reference?: string | number | null; referenceLabel?: string; unit?: string; max?: number; allowZero?: boolean; quickBasis?: 'reference' | 'planned';
}) {
  const known = useRef(value ?? '')
  if (value !== null) known.current = value
  const base = Number(reference)
  const planned = quickBasis === 'planned'
  return <div className="portion-input">
    <label>{label}{value !== null && <span className="portion-value"><input aria-label={label} type="number" min={allowZero ? '0' : max > 2000 ? '0.001' : '0.01'} max={max} step={max > 2000 ? '0.001' : '0.01'} required disabled={disabled} value={value} onChange={event => onChange(event.target.value)} /><span>{unit}</span></span>}</label>
    {allowUnknown && <label className="portion-unknown"><input type="checkbox" checked={value === null} disabled={disabled} onChange={event => onChange(event.target.checked ? null : known.current)} />분량을 몰라요</label>}
    {value === null && <p className="portion-help">분량을 비워서 남겨요. 영양 수치는 추정하지 않아요.</p>}
    {(!allowUnknown || planned) && Number.isFinite(base) && base > 0 && <div className={`portion-quick${planned ? ' portion-quick--planned' : ''}`}><span>{referenceLabel} {amountText(String(base), unit)}</span><div>{[[0.5, '절반'], [1, planned ? '그대로' : '기준량'], [1.5, '조금 더 (1.5배)']].map(([ratio, text]) => {
      const amount = String(Math.round(base * Number(ratio) * 100) / 100)
      return <button type="button" key={ratio} aria-label={`${label} ${text}`} aria-pressed={value !== null && Number(value) === Number(amount)} disabled={disabled || Number(amount) > max} onClick={() => onChange(amount)}>{text}{planned && <small>{amountText(amount, unit)}</small>}</button>
    })}</div><small>{planned ? '절반·그대로·조금 더는 계획한 양을 기준으로 해요. 직접 입력해도 계획은 바뀌지 않아요.' : '기준량으로 고른 양은 참고 분량이에요. 직접 입력할 수도 있어요.'}</small></div>}
  </div>
}
