import { useEffect, useRef, useState } from 'react'
import { message } from './api'
import { EditorialArtwork } from './BrandArtwork'
import { MealConditions } from './MealConditions'
import type { MealConstraints } from './plannerTypes'
import type { PersonalSettings as Settings } from './types'

export function PersonalSettings({ settings, account, onSave, onDirtyChange, firstSetup = false, onContinue }: { settings: Settings | null; account: boolean; onSave: (value: Settings) => Promise<Settings>; onDirtyChange?: (dirty: boolean) => void; firstSetup?: boolean; onContinue: () => void }) {
  const [goal, setGoal] = useState<Settings['goal']>('balanced')
  const [favorite, setFavorite] = useState(''), [avoided, setAvoided] = useState(''), [frequent, setFrequent] = useState('')
  const [energy, setEnergy] = useState(''), [count, setCount] = useState('3'), [conditions, setConditions] = useState<Record<string, MealConstraints>>({})
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [saved, setSaved] = useState(false)
  const [baseline, setBaseline] = useState('')
  const dirtyRef = useRef(false), saving = useRef(false), title = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (firstSetup) title.current?.focus({ preventScroll: true }) }, [firstSetup])
  const draft = { goal, favorite, avoided, frequent, energy, count, conditions }
  const dirty = baseline !== '' && JSON.stringify(draft) !== baseline
  dirtyRef.current = dirty
  const applySettings = (value: Settings) => {
    const next = { goal: value.goal, favorite: value.favorite_foods.join(', '), avoided: value.avoided_foods.join(', '), frequent: value.frequent_foods.join(', '), energy: value.energy_target ?? '', count: String(value.meal_count ?? 3), conditions: value.default_constraints ?? {} }
    setGoal(next.goal); setFavorite(next.favorite); setAvoided(next.avoided); setFrequent(next.frequent); setEnergy(next.energy); setCount(next.count); setConditions(next.conditions); setBaseline(JSON.stringify(next))
  }
  useEffect(() => { if (settings && !dirtyRef.current) applySettings(settings) }, [settings])
  useEffect(() => { onDirtyChange?.(dirty); return () => onDirtyChange?.(false) }, [dirty, onDirtyChange])
  useEffect(() => {
    if (!dirty) return
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', protect)
    return () => window.removeEventListener('beforeunload', protect)
  }, [dirty])
  const names = (value: string) => value.split(',').map(x => x.trim()).filter(Boolean)
  return <section className="personal-panel" aria-labelledby="personal-title">
    {firstSetup && <div className="first-setup-note">
      <ol aria-label="첫 식단 준비"><li>가입 완료</li><li aria-current="step">취향 설정</li><li>첫 식단 만들기</li></ol>
      <strong>첫 식단에 담을 취향을 알려주세요.</strong><p>모두 선택 사항이에요. 나중에 언제든 바꿀 수 있어요.</p>
      <button type="button" className="inline-link" disabled={busy || dirty || !settings} onClick={onContinue}>현재 설정으로 먼저 시작 →</button>
      {dirty && <small>바꾼 내용은 아래에서 저장하거나 되돌린 뒤 시작해 주세요.</small>}
    </div>}
    <div className="illustrated-heading"><div><p className="eyebrow">A TABLE THAT FEELS LIKE YOU</p><h1 id="personal-title" ref={title} tabIndex={-1}>내 입맛을 닮은 식탁</h1><p className="intro-description">좋아하는 메뉴도, 피하고 싶은 음식도.<br />나를 위한 한 끼의 기준을 정해요.</p><span className="scope-badge">{account ? '현재 계정에 저장' : '현재 브라우저의 체험 설정'}</span></div><EditorialArtwork kind="preferences" priority /></div>
    <p className="muted">기본 우선순위는 새 식단에 적용돼요. 오늘만 다른 기준을 고를 수도 있어요. 열량 우선은 입력한 하루 목표에 가까워지도록 구성해요.</p>
    {dirty && <p className="settings-draft-note" role="status">저장 전 초안이에요. 다른 화면에 다녀와도 유지돼요. 새로고침하거나 계정을 바꾸기 전에는 저장해 주세요.</p>}
    <form onSubmit={async event => {
      event.preventDefault()
      if (saving.current) return
      const next = (event.nativeEvent as SubmitEvent).submitter?.getAttribute('value') === 'continue'
      const tooMany = [['좋아하는 음식', favorite], ['제외할 음식', avoided], ['자주 먹는 음식', frequent]].find(([, value]) => names(value).length > 10)
      if (tooMany) { setError(tooMany[0] + '은 쉼표로 구분해 10개까지 입력해 주세요.'); return }
      if (next && !dirty) { onContinue(); return }
      saving.current = true; setBusy(true); setError(''); setSaved(false)
      try {
        const savedSettings = await onSave({ goal, favorite_foods: names(favorite), avoided_foods: names(avoided), frequent_foods: names(frequent), energy_target: energy || null, meal_count: Number(count) as 2 | 3 | 4, default_constraints: conditions })
        applySettings(savedSettings); setSaved(true)
        if (next) onContinue()
      } catch (e) { setError(message(e)) }
      finally { saving.current = false; setBusy(false) }
    }}>
      <fieldset className="settings-form-fields" disabled={busy || !settings}>
      <fieldset className="settings-defaults" disabled={busy}><legend>평소 식단의 기준</legend><div className="plan-fields"><label>하루 열량 목표 · 선택<input type="number" min="600" max="5000" value={energy} onChange={event => { setEnergy(event.target.value); setSaved(false) }} placeholder="정한 목표가 있을 때 입력" /></label><label>평소 끼니 수<select value={count} onChange={event => { setCount(event.target.value); setSaved(false) }}><option value="2">2끼</option><option value="3">3끼</option><option value="4">3끼 + 간식</option></select></label></div><details className="default-conditions"><summary>평소 준비 시간·기구 설정</summary>{(count === '2' ? ['lunch', 'dinner'] : count === '4' ? ['breakfast', 'lunch', 'dinner', 'snack'] : ['breakfast', 'lunch', 'dinner']).map(key => <div key={key}><h3>{{ breakfast: '아침', lunch: '점심', dinner: '저녁', snack: '간식' }[key]}</h3><MealConditions label={`기본 ${key}`} value={conditions[key] ?? { no_cook: false, tools: [], max_minutes: null, avoided_foods: [] }} disabled={busy} onChange={value => { setConditions(old => ({ ...old, [key]: { ...(old[key] ?? { no_cook: false, tools: [], max_minutes: null, avoided_foods: [] }), ...value } })); setSaved(false) }} /></div>)}</details><small>새 식단을 만들 때 가져와요. 오늘만 다른 조건을 선택할 수도 있어요.</small></fieldset>
      <fieldset className="goal-options"><legend>기본 추천 목적</legend>{([['balanced','목표와 다양성'],['energy','열량 목표 우선'],['protein','단백질 우선'],['similarity','익숙한 메뉴 중심']] as const).map(([key,label]) => <label key={key} className={goal===key?'active':''}><input type="radio" name="default-goal" value={key} checked={goal===key} onChange={()=>{setGoal(key);setSaved(false)}} />{label}</label>)}</fieldset>
      <div className="personal-fields"><label>좋아하는 음식<input value={favorite} onChange={e=>{setFavorite(e.target.value);setSaved(false)}} placeholder="예: 김밥, 국수" maxLength={400}/><small>추천받을 때 더 자주 만나볼 수 있어요.</small></label><label>제외할 음식<input value={avoided} onChange={e=>{setAvoided(e.target.value);setSaved(false)}} placeholder="예: 피자, 샐러드" maxLength={400}/><small>입력한 이름이 들어간 메뉴는 추천에서 빼요.</small></label><label>평소 자주 먹는 음식<input value={frequent} onChange={e=>{setFrequent(e.target.value);setSaved(false)}} placeholder="예: 비빔밥, 샌드위치" maxLength={400}/><small>익숙한 메뉴를 고를 때 참고해요.</small></label></div>
      <p className="muted small">쉼표로 구분해 각 10개까지 입력해 주세요. 재료·알레르기 검증은 제공하지 않아요.</p>
      {error&&<p className="notice error" role="alert">{error}</p>}{saved&&<p className="notice success" role="status">저장했어요. 새 식단과 메뉴 추천부터 반영돼요.</p>}
      <div className="settings-save-actions">{dirty && <button type="button" className="secondary" disabled={busy} onClick={() => { if (settings) applySettings(settings); setSaved(false) }}>저장한 설정으로 되돌리기</button>}<button className="secondary" type="submit" value="save" disabled={busy||!settings}>설정 저장</button><button className="primary" type="submit" value="continue" disabled={busy||!settings}>{busy ? '저장 중…' : dirty ? '저장하고 식단 만들기' : '이 설정으로 식단 만들기'}</button></div>
      </fieldset>
      <p className="settings-next-note">식단 화면에서 기준을 한 번 더 확인해요. 기존 식단과 식사 기록은 그대로 보관해요.</p>
    </form>
  </section>
}
