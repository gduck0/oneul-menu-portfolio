import { useEffect, useRef, useState } from 'react'
import { api, message, post } from './api'
import { deferGuestImport, guestImportPreferenceKey, readGuestImportDeferred } from './guestImportPreference'

type GuestData = { plans: number; meals: number; settings: boolean }

export function GuestImport({ accountId, inSettings, onImported }: { accountId: string; inSettings: boolean; onImported: () => void }) {
  const [data, setData] = useState<GuestData | null>(null)
  const [deferred, setDeferred] = useState(() => readGuestImportDeferred(accountId))
  const [expanded, setExpanded] = useState(false)
  const [includeSettings, setIncludeSettings] = useState(true)
  const [pending, setPending] = useState(false), [loading, setLoading] = useState(true)
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [storageNotice, setStorageNotice] = useState('')
  const [revision, setRevision] = useState(0)
  const request = useRef<{ include: boolean; id: string } | null>(null)
  const alive = useRef(false)

  useEffect(() => { if (!inSettings) setExpanded(false) }, [inSettings])

  useEffect(() => {
    alive.current = true
    return () => { alive.current = false }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    api<GuestData>('/guest-data', {}, controller.signal).then(value => {
      if (!controller.signal.aborted) { setData(value); setError('') }
    }).catch(error => {
      if (!controller.signal.aborted) setError(message(error))
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [revision])

  useEffect(() => {
    const changed = (event: StorageEvent) => {
      if (event.key === guestImportPreferenceKey(accountId) || event.key === null) setDeferred(readGuestImportDeferred(accountId))
    }
    window.addEventListener('storage', changed)
    return () => window.removeEventListener('storage', changed)
  }, [accountId])

  const postpone = () => {
    const saved = deferGuestImport(accountId)
    setStorageNotice(saved ? '' : '브라우저에 보류 상태를 저장하지 못했어요. 새로고침하거나 다시 로그인하면 안내가 다시 나타날 수 있어요.')
    setDeferred(true)
    setExpanded(false)
  }

  if (notice) return <aside className="guest-import import-complete" role="status"><strong>{notice}</strong><button className="text-button" onClick={() => setNotice('')}>닫기</button></aside>

  const hasData = Boolean(data && (data.plans || data.meals || data.settings))
  if (!hasData && !error) return null

  if (deferred && (!expanded || !inSettings)) {
    if (!inSettings) return storageNotice ? <p className="guest-import-storage-notice" role="status">{storageNotice}</p> : null
    return <aside className="guest-import guest-import-deferred" aria-label="보류한 체험 기록">
      <div><h2>보류한 체험 기록</h2><p>{hasData ? `식단 ${data!.plans}개 · 식사 기록 ${data!.meals}개${data!.settings ? ' · 체험 취향' : ''}. 필요할 때 이 계정으로 가져오세요.` : '체험 기록을 확인하고 다시 가져올 수 있어요.'}</p><p>{storageNotice ? '이번 화면에서는 안내를 접어 두었어요.' : '이 브라우저에서는 자동 안내를 다시 띄우지 않아요.'}</p></div>
      <button className="secondary" onClick={() => { setExpanded(true); setRevision(value => value + 1) }}>체험 기록 가져오기</button>
      {storageNotice && <p role="status">{storageNotice}</p>}
    </aside>
  }

  return <aside className="guest-import" aria-label="체험 기록 이어가기">
    <div><span className="eyebrow">이어서 사용하기</span><h2>체험하며 만든 식단도 가져올까요?</h2>
      {hasData && <p>식단 {data!.plans}개 · 식사 기록 {data!.meals}개. 현재 계정의 기록을 덮어쓰지 않아요.</p>}
      <p>나중에 가져오려면 내 설정에서 다시 열 수 있어요.</p>
      {data?.settings && <label><input type="checkbox" checked={includeSettings} disabled={pending} onChange={event => setIncludeSettings(event.target.checked)} />체험 취향도 가져오기 · 계정에 설정이 있으면 유지</label>}
    </div>
    <div className="dialog-actions">
      <button className="secondary" disabled={pending} onClick={postpone}>나중에</button>
      {error && <button className="secondary" disabled={loading || pending} onClick={() => setRevision(value => value + 1)}>{loading ? '확인 중…' : '다시 확인'}</button>}
      <button className="primary" disabled={pending || loading || !hasData || Boolean(error)} onClick={async () => {
        setPending(true); setError('')
        if (request.current?.include !== includeSettings) request.current = { include: includeSettings, id: crypto.randomUUID() }
        try {
          const result = await post<{ plans: number; meals: number; settings_kept: boolean }>('/guest-data/import', { client_request_id: request.current.id, include_settings: includeSettings })
          if (!alive.current) return
          setNotice(`식단 ${result.plans}개와 식사 ${result.meals}개를 가져왔어요.${result.settings_kept ? ' 계정의 기존 취향은 유지했어요.' : ''}`)
          setData(null); onImported()
        } catch (error) { if (alive.current) setError(message(error)) }
        finally { if (alive.current) setPending(false) }
      }}>{pending ? '가져오는 중…' : loading ? '체험 기록 확인 중…' : '이 계정으로 가져오기'}</button>
    </div>
    {error && <p role="alert" className="error">{error}</p>}
    {storageNotice && <p role="status">{storageNotice}</p>}
  </aside>
}
