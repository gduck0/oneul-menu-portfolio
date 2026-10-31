import { useEffect, useRef } from 'react'

export function UnsavedSettingsDialog({ onDecision }: { onDecision: (leave: boolean) => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { const node = dialog.current!; node.showModal(); return () => node.close() }, [])
  return <dialog ref={dialog} className="service-dialog" aria-labelledby="unsaved-settings-title" onCancel={event => { event.preventDefault(); onDecision(false) }}>
    <h2 id="unsaved-settings-title">저장하지 않은 설정이 있어요</h2>
    <p>계정을 바꾸면 지금 입력한 초안은 사라져요. 저장한 설정과 기존 식단·기록은 그대로 유지돼요.</p>
    <div className="dialog-actions"><button className="secondary" autoFocus onClick={() => onDecision(false)}>계속 편집하기</button><button className="primary" onClick={() => onDecision(true)}>저장하지 않고 계속</button></div>
  </dialog>
}
