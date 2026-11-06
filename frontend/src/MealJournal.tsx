import { PortionInput } from './PortionInput'
import type { Amount } from './PortionInput'
import { ConnectionNotice } from './ConnectionNotice'
import { useEffect, useRef, useState } from 'react'
import { api, message, post } from './api'
import { displayName } from './FoodCard'
import { MealGroupCard } from './MealGroupCard'
import { GroupedFoods } from './GroupedFoods'
import { EditorialArtwork } from './BrandArtwork'
import type { Feedback, Food, Meal, MealGroup, Search } from './types'

const localNow=()=>{const date=new Date();return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16)}

export function MealJournal({ account, feedback, onFeedback, onRecordsChange }: { onRecordsChange?: () => void; account:boolean; feedback:Feedback[];onFeedback:(value:Feedback|null,previousId?:string)=>void }) {
  const [mode,setMode]=useState<'catalog'|'custom'>('catalog'),[query,setQuery]=useState(''),[foods,setFoods]=useState<Food[]>([]),[selected,setSelected]=useState<Food|null>(null)
  const [foodSearch,setFoodSearch]=useState<Search|null>(null)
  const [customAmount,setCustomAmount]=useState<Amount>(null)
  const [amount,setAmount]=useState('200'),[unit,setUnit]=useState<'g'|'mL'>('g'),[date,setDate]=useState(localNow()),[notes,setNotes]=useState('')
  const [meals,setMeals]=useState<MealGroup[]>([]),[total,setTotal]=useState(0),[entryTotal,setEntryTotal]=useState(0),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState('')
  const [loadError, setLoadError] = useState(''), [loadAttempt, setLoadAttempt] = useState(0)
  const [cancelled, setCancelled] = useState(false)
  const pendingBody=useRef<Record<string,unknown>|null>(null)
  const requestAbort=useRef<AbortController|null>(null)
  const load=async(more=false)=>{requestAbort.current?.abort();const controller=new AbortController();requestAbort.current=controller;setLoading(true);setLoadError('');try{const data=await api<{items:MealGroup[];total:number;total_entries:number}>(`/meal-groups?limit=10&offset=${more?meals.length:0}&cancelled=${cancelled}`,{},controller.signal);if(!controller.signal.aborted){setMeals(old=>more?[...old,...data.items]:data.items);setTotal(data.total);setEntryTotal(data.total_entries)}}catch(e){if(!controller.signal.aborted)setLoadError(message(e))}finally{if(!controller.signal.aborted)setLoading(false)}}
  useEffect(()=>{void load();return()=>requestAbort.current?.abort()},[cancelled])
  const edit=()=>{pendingBody.current=null;setNotice('')}
  return <section className="meal-journal" aria-labelledby="journal-title">
    <div className="illustrated-heading"><div><p className="eyebrow">MY EVERYDAY JOURNAL</p><h1 id="journal-title">실제로 먹은 한 끼</h1><p className="intro-description">계획과 조금 달라도 괜찮아요.<br />먹은 메뉴와 내 입맛을 차곡차곡 남겨요.</p><span className="scope-badge">{account?'현재 계정의 식사':'현재 브라우저의 체험 식사'}</span></div><EditorialArtwork kind="journal" priority /></div>
    <ConnectionNotice key={`journal-load:${loadAttempt}`} loading={loading} error={loadError} loadingText="식사 기록을 불러오고 있어요" errorTitle="식사 기록을 불러오지 못했어요" retryLabel="식사 기록 다시 연결" onRetry={() => { setLoadAttempt(value => value + 1); void load() }} />
    <details className="journal-form"><summary className="add-entry-heading">＋ 먹은 식사 추가</summary><div className="history-tabs"><button className={mode==='catalog'?'active':''} onClick={()=>{setMode('catalog');setSelected(null);setFoods([]);edit()}}>등록 음식 찾기</button><button className={mode==='custom'?'active':''} onClick={()=>{setMode('custom');setSelected(null);setFoods([]);edit()}}>음식 이름 직접 입력</button></div>
    <label className="journal-name">{mode==='catalog'?'음식 검색':'먹은 음식 이름'}<div className="search-form"><input value={query} onChange={e=>{setQuery(e.target.value);setSelected(null);edit()}} placeholder={mode==='catalog'?'예: 비빔밥':'예: 집에서 만든 채소볶음'} maxLength={mode==='catalog'?80:100}/>{mode==='catalog'&&<button className="secondary" disabled={busy||!query.trim()} onClick={async()=>{setBusy(true);setError('');try{const data=await api<Search>(`/food-groups?q=${encodeURIComponent(query)}&limit=20`);setFoods(data.items);setFoodSearch(data);setNotice(data.total>20?'처음 20개를 보여드려요. 이름을 더 구체적으로 입력해 주세요.':data.total===0?'등록된 음식이 없어요. 직접 입력으로 기록할 수 있어요.':'')}catch(e){setError(message(e))}finally{setBusy(false)}}}>찾기</button>}</div></label>
    {foods.length>0&&!selected&&foodSearch&&<div className="food-list journal-search"><GroupedFoods search={foodSearch} onSelect={food=>{setSelected(food);setAmount(String(Number(food.basis_amount)));setUnit(food.basis_unit);edit()}}/></div>}
    {selected&&<p className="selected-name">{displayName(selected.name)} <small>{selected.company??'일반 음식'}</small></p>}
    <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');setNotice('');try{if(mode==='catalog'&&!selected)throw new Error('검색 결과에서 음식을 선택해 주세요.');if(!date)throw new Error('먹은 시각을 입력해 주세요.');const body=pendingBody.current??{client_record_id:crypto.randomUUID(),food_id:mode==='catalog'?selected?.id:null,name:mode==='custom'?query:null,portion:mode==='custom'&&customAmount===null?null:{amount:mode==='custom'?customAmount:amount,unit},eaten_at:new Date(date).toISOString(),notes};pendingBody.current=body;await post<Meal>('/meals',body);pendingBody.current=null;setNotes('');setQuery('');setCustomAmount(null);setSelected(null);setFoods([]);setNotice('실제 식사를 기록했어요. 먹은 뒤 평가도 남길 수 있어요.');await load();onRecordsChange?.()}catch(e){setError(message(e))}finally{setBusy(false)}}}>
      <div className="journal-fields"><div><PortionInput label="먹은 양" value={mode==='custom'?customAmount:amount} onChange={value=>{if(mode==='custom')setCustomAmount(value);else setAmount(value??'');edit()}} disabled={busy} allowUnknown={mode==='custom'} reference={selected?.basis_amount} referenceLabel="자료 기준량" unit={unit} max={10000}/>{mode==='custom'&&customAmount!==null&&<label>분량 단위<select aria-label="식사 양 단위" value={unit} onChange={e=>{setUnit(e.target.value as 'g'|'mL');edit()}}><option value="g">g</option><option value="mL">mL</option></select></label>}</div><label>먹은 시각<input type="datetime-local" value={date} onChange={e=>{setDate(e.target.value);edit()}}/></label><label>메모 <span className="muted">선택 사항</span><input value={notes} onChange={e=>{setNotes(e.target.value);edit()}} maxLength={300} placeholder="예: 점심, 회사 근처"/></label></div>
      <p className="muted small">{mode==='custom'?'직접 입력 음식은 분량을 몰라도 이름과 시각을 기록해요. 알 수 없는 영양은 비워둬요.':'등록 음식의 기준량과 먹은 양으로 영양을 계산해요. 자료의 g·mL 기준을 사용해요.'}</p><button className="primary" disabled={busy||loading}>{busy?'저장 중…':'먹은 식사 기록'}</button>
    </form></details>{error&&<div className="notice error" role="alert">{error}<button className="text-button" onClick={() => void load()}>기록 다시 불러오기</button></div>}{notice&&<p className="notice success" role="status">{notice}</p>}
    <div className="section-heading"><h2>{cancelled ? '취소한 기록' : '식사 기록'}</h2><span>{total}회 · 음식 {entryTotal}개</span><button className="text-button" onClick={() => { setCancelled(value => !value); setError('') }}>{cancelled ? '식사 기록으로 돌아가기' : '취소한 기록 보기'}</button></div>{!loading&&!loadError&&meals.length===0&&<div className="empty-state"><h3>{cancelled ? '취소한 기록이 없어요' : '아직 식사 기록이 없어요'}</h3><p>{cancelled ? '잘못 남긴 기록을 취소하면 여기에서 다시 확인할 수 있어요.' : '추천을 선택하지 않아도 먹은 식사를 직접 남길 수 있어요.'}</p></div>}
    <div className="journal-groups">{meals.map(group => <MealGroupCard key={group.id} group={group} feedback={feedback} onFeedback={onFeedback} onChange={action => { void load(); onRecordsChange?.(); if(action)setNotice(action === 'cancel' ? '이 끼니의 기록을 함께 취소했어요. 원기록과 평가는 보존돼요.' : action === 'restore' ? '이 끼니의 기록과 평가를 함께 복원했어요.' : '실제 먹은 양과 시각을 수정했어요.') }} />)}</div>
    {meals.length<total&&<button className="secondary" disabled={loading} onClick={()=>void load(true)}>식사 기록 더 보기</button>}
  </section>
}
