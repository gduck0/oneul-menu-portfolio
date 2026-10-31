import { useEffect, useRef, useState } from 'react'
import { message, post } from './api'
import type { User } from './types'
import { BrandMark, Icon } from './BrandArtwork'

export function AuthDialog({ onClose, onIdentity }: { onClose: () => void; onIdentity: (user: User, mode: 'login' | 'register') => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState(''), [password, setPassword] = useState(''), [confirm, setConfirm] = useState('')
  const [error, setError] = useState(''), [pending, setPending] = useState(false)
  useEffect(() => { const node = dialog.current!; node.showModal(); return () => node.close() }, [])
  return <dialog ref={dialog} className="auth-dialog" aria-labelledby="auth-title" onCancel={event => { if (pending) event.preventDefault(); else onClose() }}>
    <button type="button" className="dialog-close" aria-label="닫기" onClick={onClose} disabled={pending}><Icon name="close" /></button>
    <span className="dialog-brand" aria-hidden="true"><BrandMark /></span>
    <h2 id="auth-title">내 식단을 이어가세요</h2><p className="muted">로그인하면 내 설정과 식단을 계정에 저장해요.<br />체험 자료와 계정 자료는 따로 보관해요.</p>
    <div className="segmented"><button type="button" className={mode === 'login' ? 'active' : ''} aria-pressed={mode === 'login'} disabled={pending} onClick={() => { setMode('login'); setError('') }}>로그인</button><button type="button" className={mode === 'register' ? 'active' : ''} aria-pressed={mode === 'register'} disabled={pending} onClick={() => { setMode('register'); setError('') }}>회원가입</button></div>
    <form onSubmit={async event => {
      event.preventDefault(); setError('')
      if (mode === 'register' && password !== confirm) { setError('비밀번호가 서로 달라요.'); return }
      setPending(true)
      try { const result = await post<{ user: User }>(`/auth/${mode}`, { username, password }); onIdentity(result.user, mode) }
      catch (error) { setError(message(error)) }
      finally { setPending(false); setPassword(''); setConfirm('') }
    }}>
      <label>아이디<input autoFocus autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} minLength={3} maxLength={30} required pattern="[a-zA-Z0-9가-힣_]+" /><small>영문·숫자·한글·밑줄, 3~30자</small></label>
      <label>비밀번호<input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={event => setPassword(event.target.value)} minLength={10} maxLength={128} required /><small>10자 이상</small></label>
      {mode === 'register' && <label>비밀번호 확인<input type="password" autoComplete="new-password" value={confirm} onChange={event => setConfirm(event.target.value)} minLength={10} maxLength={128} required /></label>}
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary full" disabled={pending}>{pending ? '확인하고 있어요…' : mode === 'login' ? '로그인' : '계정 만들기'}</button>
    </form>
  </dialog>
}
