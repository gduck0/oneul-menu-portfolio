import { useEffect, useRef } from 'react'

export function RecommendationSettingsDialog({ onDecision }: { onDecision: (decision: 'settings' | 'saved' | 'cancel') => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { const node = dialog.current!; node.showModal(); return () => node.close() }, [])
  return <dialog ref={dialog} className="service-dialog recommendation-settings-dialog" aria-labelledby="recommend-settings-title" onCancel={event => { event.preventDefault(); onDecision('cancel') }}>
    <h2 id="recommend-settings-title">바꾼 내 설정이 아직 저장되지 않았어요</h2>
    <p>끼니 수·제외 음식·취향을 바꿨다면 먼저 저장해 주세요. 지금 추천하면 저장해 둔 설정을 사용해요.</p>
    <p className="muted">입력한 초안과 기존 식단·기록은 그대로 남겨요. 오늘만 고른 준비 조건도 유지해요.</p>
    <div className="dialog-actions"><button type="button" className="primary" autoFocus onClick={() => onDecision('settings')}>설정 저장하러 가기</button><button type="button" className="secondary" onClick={() => onDecision('saved')}>저장한 설정으로 계속</button><button type="button" className="text-button" onClick={() => onDecision('cancel')}>추천 취소</button></div>
  </dialog>
}
