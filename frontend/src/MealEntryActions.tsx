import { useRef, useState } from 'react'
import { api, message, post } from './api'
import { PortionInput, amountText } from './PortionInput'
import type { Amount } from './PortionInput'
import { localTime } from './MealRecordDialog'
import type { Meal } from './types'

type HistoryItem = { action: string; created_at: string; before: Meal[] }

export function MealEntryActions({ meal, onChange, editOnly = false, groupOnly = false, scopeLabel = '식사', groupCount = 1 }: { meal: Meal; onChange: (action?: string) => void; editOnly?: boolean; groupOnly?: boolean; scopeLabel?: string; groupCount?: number }) {
  const [mode, setMode] = useState<'closed' | 'edit' | 'cancel'>('closed')
  const [amount, setAmount] = useState<Amount>(meal.portion?.amount ?? null), [time, setTime] = useState(localTime(meal.eaten_at)), [notes, setNotes] = useState(meal.notes)
  const [pending, setPending] = useState(false), [error, setError] = useState(''), [history, setHistory] = useState<HistoryItem[] | null>(null)
  const request = useRef<{ key: string; id: string } | null>(null)
  const save = async (action: 'edit' | 'cancel' | 'restore') => {
    const values = { expected_version: meal.version, ...(action === 'edit' ? { portion: amount === null ? null : { amount, unit: meal.portion?.unit ?? 'g' }, eaten_at: new Date(time).toISOString(), notes } : {}) }
    const key = action + JSON.stringify(values)
    if (request.current?.key !== key) request.current = { key, id: crypto.randomUUID() }
    setPending(true); setError('')
    try {
      const body = { ...values, client_request_id: request.current.id }
      if (action === 'edit') await api('/meals/' + meal.id, { method: 'PATCH', body: JSON.stringify(body) })
      else await post(`/meals/${meal.id}/${action}`, body)
      request.current = null; setMode('closed'); setHistory(null); onChange(action)
    } catch (error) { setError(message(error)) } finally { setPending(false) }
  }
  return <div className="entry-actions">
    <div className="entry-action-row">{!groupOnly && <button className="secondary" disabled={pending || Boolean(meal.cancelled_at)} onClick={() => { if (mode !== 'edit') { setAmount(meal.portion?.amount ?? null); setTime(localTime(meal.eaten_at)); setNotes(meal.notes) }; setMode(mode === 'edit' ? 'closed' : 'edit'); setError('') }}>분량·시각 수정</button>}{!editOnly && (meal.cancelled_at ? <button className="secondary" disabled={pending} onClick={() => void save('restore')}>{scopeLabel} 전체 복원 ({groupCount}개)</button> : <button className="text-button" disabled={pending} onClick={() => { setMode(mode === 'cancel' ? 'closed' : 'cancel'); setError('') }}>{scopeLabel} 전체 취소 ({groupCount}개)</button>)}
      {!groupOnly && <button className="text-button" disabled={pending} onClick={async () => { if (history) { setHistory(null); return }; setPending(true); try { setHistory(await api<HistoryItem[]>('/meals/' + meal.id + '/changes')) } catch (error) { setError(message(error)) } finally { setPending(false) } }}>수정 이력</button>}</div>
    {mode === 'edit' && <form className="entry-edit" onSubmit={event => { event.preventDefault(); void save('edit') }}><PortionInput label="실제 먹은 양" value={amount} onChange={setAmount} disabled={pending} allowUnknown={meal.food_id === null} reference={meal.portion?.amount} referenceLabel="기록한 양" unit={meal.portion?.unit ?? 'g'} max={10000} /><label>먹은 시각<input type="datetime-local" required value={time} disabled={pending} onChange={event => setTime(event.target.value)} /></label><label>메모<input maxLength={300} value={notes} disabled={pending} onChange={event => setNotes(event.target.value)} /></label><div className="dialog-actions"><button type="button" className="secondary" disabled={pending} onClick={() => setMode('closed')}>닫기</button><button className="primary" disabled={pending}>{pending ? '저장 중…' : '변경 내용 저장'}</button></div></form>}
    {mode === 'cancel' && <div className="cancel-confirm"><strong>잘못 남긴 식사인가요?</strong><p>{scopeLabel}의 음식 {groupCount}개 기록을 함께 취소해요. 원기록과 평가는 보존하며 취소한 기록에서 전체를 복원할 수 있어요.</p><button className="secondary" disabled={pending} onClick={() => setMode('closed')}>기록 유지</button><button className="danger-button" disabled={pending} onClick={() => void save('cancel')}>{scopeLabel} 전체 취소 확인</button></div>}
    {history && <div className="entry-history">{history.length ? history.map((entry, index) => <p key={index}>{new Date(entry.created_at).toLocaleString('ko-KR')} · {{ edit: '내용 수정', cancel: '기록 취소', restore: '기록 복원' }[entry.action] ?? entry.action}<small>변경 전: {entry.before.map(value => `${value.name} ${amountText(value.portion?.amount ?? null, value.portion?.unit ?? 'g')}`).join(', ')}</small></p>) : <p>아직 수정한 이력이 없어요.</p>}</div>}
    {error && <p role="alert" className="error">{error}<button className="text-button" disabled={pending} onClick={() => onChange()}>최신 기록 불러오기</button></p>}
  </div>
}
