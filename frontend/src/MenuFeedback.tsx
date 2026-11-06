import { useEffect, useState } from 'react'
import { api, message } from './api'
import { feedbackReasons, feedbackScope } from './feedbackScope'
import type { Feedback, FeedbackReason, Rating } from './types'

export function MenuFeedback({ phase, contextId, foodId, value, onChange }: { phase: Feedback['phase']; contextId: string; foodId: string | null; value?: Feedback; onChange: (value: Feedback | null, previousId?: string) => void }) {
  const [rating,setRating]=useState<Rating|null>(value?.rating??null),[reason,setReason]=useState<FeedbackReason|''>(value?.reason??'')
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
  useEffect(()=>{setRating(value?.rating??null);setReason(value?.reason??'')},[value?.id,value?.rating,value?.reason])
  const changed = rating !== (value?.rating ?? null) || reason !== (value?.reason ?? '')
  const save=async()=>{
    if(!rating)return
    setBusy(true);setError('');setNotice('')
    try {
      const data=await api<Feedback>('/feedback',{method:'PUT',body:JSON.stringify({phase,context_id:contextId,food_id:foodId,rating,reason:reason||null})})
      onChange(data)
      setNotice('평가를 저장했어요. '+feedbackScope(data.phase,data.food_id,data.rating,data.reason??''))
    } catch(e){setError(message(e))} finally{setBusy(false)}
  }
  return <div className="feedback-panel">
    <fieldset disabled={busy}><legend>{phase==='recommendation'?'이 대안은 어떤가요?':'먹어 보니 어땠나요?'}</legend>
      <div className="rating-options">{([['like',phase==='consumed'?'만족':'먹고 싶어요'],['neutral','보통'],['dislike',phase==='consumed'?'아쉬워요':'별로예요']] as [Rating,string][]).map(([key,label])=><button type="button" key={key} aria-pressed={rating===key} className={rating===key?'active':''} onClick={()=>{setRating(key);setNotice('')}}>{label}</button>)}</div>
      <label className="feedback-reason">이유 <span className="muted">선택 사항</span><select aria-label="평가 이유" value={reason} onChange={event=>{setReason(event.target.value as FeedbackReason|'');setNotice('')}}><option value="">이유 없이 기록만</option>{(Object.entries(feedbackReasons) as [FeedbackReason,string][]).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
      <div className="feedback-scope" role="status"><strong>{changed ? '저장하면 이렇게 반영해요' : value ? '이 평가의 반영 범위' : '평가의 반영 범위'}</strong><p>{feedbackScope(phase,foodId,rating,reason)}</p><small>‘맛·메뉴 취향’을 고른 등록 음식 평가만 다음 추천의 메뉴 선호에 참고해요.</small>{changed&&<span className="feedback-unsaved">아직 저장 전이에요.</span>}</div>
      <div className="feedback-actions"><button type="button" className="secondary" disabled={!rating} onClick={()=>void save()}>{busy?'저장 중…':value?'평가 수정':'평가 저장'}</button>{value&&<button type="button" className="text-button" onClick={async()=>{setBusy(true);setError('');try{await api('/feedback/'+value.id,{method:'DELETE'});onChange(null,value.id);setRating(null);setReason('');setNotice('평가를 취소했어요.')}catch(e){setError(message(e))}finally{setBusy(false)}}}>평가 취소</button>}</div>
    </fieldset>
    {notice&&<p className="small" role="status">{notice}</p>}{error&&<p className="error small" role="alert">{error}</p>}
  </div>
}
