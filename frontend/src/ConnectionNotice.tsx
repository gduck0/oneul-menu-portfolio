import { useEffect, useState } from 'react'

type Props = { loading: boolean; error: string; loadingText: string; errorTitle: string; retryLabel: string; onRetry: () => void }

export function ConnectionNotice({ loading, error, loadingText, errorTitle, retryLabel, onRetry }: Props) {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    setSlow(false)
    if (!loading) return
    const timer = window.setTimeout(() => setSlow(true), 8000)
    return () => window.clearTimeout(timer)
  }, [loading])
  if (!loading && !error) return null
  return <section className={`connection-notice ${error ? 'failed' : ''}`} aria-label="연결 상태">
    <div role={error ? 'alert' : 'status'}>
      <strong>{error ? errorTitle : slow ? '연결이 평소보다 오래 걸리고 있어요' : loadingText}</strong>
      <p>{error || (slow ? '조금 더 기다리거나 연결을 다시 확인할 수 있어요.' : '저장한 정보를 확인하고 있어요. 잠시만 기다려 주세요.')}</p>
    </div>
    {(error || slow) && <><button type="button" className="secondary" onClick={onRetry}>{retryLabel}</button><small>새로고침하지 않고 다시 연결해요. 입력 중인 내용은 유지해요.</small></>}
  </section>
}
