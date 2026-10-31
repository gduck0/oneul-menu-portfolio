import { useEffect, useId, useRef, useState } from 'react'
import { api, message, post } from './api'
import { PortionInput, amountText, sameAmount } from './PortionInput'
import type { Amount } from './PortionInput'
import { MealConditions } from './MealConditions'
import { PlanMealCard } from './PlanMealCard'
import { MealOverview } from './MealOverview'
import { DailyNutrition } from './DailyNutrition'
import { EnergyGap } from './EnergyGap'
import { PlanSetupSummary } from './PlanSetupSummary'
import { applyPreparation, extendPreparation, startingPreparation } from './preparationDefaults'
import type { PreparationMode } from './preparationDefaults'
import { ConnectionNotice } from './ConnectionNotice'
import { EditorialArtwork, Icon } from './BrandArtwork'
import { kcal, mealLabels, roleLabels } from './plannerDisplay'
import type { PersonalSettings, Preference } from './types'
import type { FixedMeal, MealConstraints, MealKey, Plan, PlanMeal, PlannerMenu } from './plannerTypes'
import './planner.css'

const EMPTY: MealConstraints = { no_cook: false, prepared_sides: false, tools: [], max_minutes: null, avoided_foods: [] }
const BUSY: Record<string, MealConstraints> = { breakfast: { ...EMPTY, no_cook: true, max_minutes: 10 }, lunch: { ...EMPTY }, dinner: { ...EMPTY, max_minutes: 30 } }
const today = () => new Date().toLocaleDateString('sv-SE')
const slots = (count: string): MealKey[] => count === '2' ? ['lunch', 'dinner'] : count === '4' ? ['breakfast', 'lunch', 'dinner', 'snack'] : ['breakfast', 'lunch', 'dinner']

export function PlannerView({ account, settings, onSettings, onCompare, setupRequest = 0, resumeRequest = 0, onSetupHandled, settingsUnsaved = false, beforeRecommend }: { setupRequest?: number; resumeRequest?: number; onSetupHandled?: () => void; settingsUnsaved?: boolean; beforeRecommend?: () => Promise<boolean>; onCompare?: () => void; onSettings: () => void; account: boolean; settings: PersonalSettings | null }) {
  const [energy, setEnergy] = useState('1800'), [day, setDay] = useState(today()), [count, setCount] = useState('3'), [preference, setPreference] = useState<Preference>(settings?.goal ?? 'balanced')
  const [protein, setProtein] = useState(''), [carbs, setCarbs] = useState(''), [fat, setFat] = useState('')
  const [plan, setPlan] = useState<Plan | null>(null), [history, setHistory] = useState<Plan[]>([]), [available, setAvailable] = useState(0)
  const [setupOpen, setSetupOpen] = useState(false)
  const [setupDetailsOpen, setSetupDetailsOpen] = useState(false)
  const [selectedMeal, setSelectedMeal] = useState<MealKey>('breakfast')
  const [mealFocus, setMealFocus] = useState<{ key: MealKey; id: number; section: 'portion' | 'conditions' | 'overview' } | null>(null)
  const mealFocusSequence = useRef(0)
  const selectMeal = (key: MealKey, openDetail = false) => {
    if (openDetail && window.matchMedia('(max-width: 760px)').matches) { focusMeal(key, 'overview'); return }
    setMealFocus(null); setSelectedMeal(key)
  }
  const focusMeal = (key: MealKey, section: 'portion' | 'conditions' | 'overview') => { setSelectedMeal(key); setMealFocus({ key, section, id: ++mealFocusSequence.current }) }
  const mealPanelId = useId()
  const [loadError, setLoadError] = useState(''), [loadAttempt, setLoadAttempt] = useState(0)
  const setupEdited = useRef(false)
  const [loading, setLoading] = useState(true), [pending, setPending] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [constraints, setConstraints] = useState<Record<string, MealConstraints>>({}), [fixed, setFixed] = useState<Partial<Record<MealKey, FixedMeal>>>({})
  const [preparationMode, setPreparationMode] = useState<PreparationMode>(() => startingPreparation(settings?.default_constraints, String(settings?.meal_count ?? 3)).mode)
  const [draftConstraints, setDraftConstraints] = useState<Record<string, MealConstraints>>(() => startingPreparation(settings?.default_constraints, String(settings?.meal_count ?? 3)).constraints)
  const draftOverrides = useRef({ energy: false, count: false, preference: false, preparation: false })
  const handledResume = useRef(0)
  const checkingSettings = useRef(false)
  const checkSettings = async () => {
    if (busy.current || checkingSettings.current) return false
    checkingSettings.current = true
    try { return await beforeRecommend?.() ?? true } finally { checkingSettings.current = false }
  }
  const resetPreparation = () => {
    const initial = startingPreparation(settings?.default_constraints, String(settings?.meal_count ?? 3))
    setPreparationMode(initial.mode); setDraftConstraints(initial.constraints)
  }
  const choosePreparation = (mode: Exclude<PreparationMode, 'custom'>) => {
    setupEdited.current = true; draftOverrides.current.preparation = true; setPreparationMode(mode)
    setDraftConstraints(old => applyPreparation(mode, old, count, settings?.default_constraints))
  }
  const changeCount = (value: string) => { draftOverrides.current.count = true; setCount(value); setDraftConstraints(old => extendPreparation(old, value, preparationMode, settings?.default_constraints)) }
  const [picker, setPicker] = useState<{ key: MealKey; stage: 'draft' | 'plan'; action?: 'set' | 'add' | 'update_item'; itemId?: string; role?: string } | null>(null)
  const [pickerMode, setPickerMode] = useState<'catalog' | 'custom'>('catalog')
  const [pickerScope, setPickerScope] = useState<'same' | 'all'>('same')
  const [query, setQuery] = useState(''), [menus, setMenus] = useState<PlannerMenu[]>([]), [menuLoading, setMenuLoading] = useState(false), [menuError, setMenuError] = useState(''), [menuTotal, setMenuTotal] = useState(0)
  const [customName, setCustomName] = useState(''), [customAmount, setCustomAmount] = useState<Amount>(null), [amounts, setAmounts] = useState<Record<string, Amount>>({})
  const [historyOpen, setHistoryOpen] = useState(false), [historyDate, setHistoryDate] = useState(''), [historyTotal, setHistoryTotal] = useState(0), [historyLoading, setHistoryLoading] = useState(false)
  const [menuOffset, setMenuOffset] = useState(0)
  const [conflictChoice, setConflictChoice] = useState<{ choice: FixedMeal; conflicts: string[]; basis: string } | null>(null)
  const [checkingChoice, setCheckingChoice] = useState(false), [choiceError, setChoiceError] = useState('')
  const [failedChoice, setFailedChoice] = useState<FixedMeal | null>(null)
  const choiceAbort = useRef<AbortController | null>(null), conflictTitle = useRef<HTMLHeadingElement>(null)
  const historyAbort = useRef<AbortController | null>(null), menuAbort = useRef<AbortController | null>(null), historyDateInput = useRef<HTMLInputElement>(null)
  const mounted = useRef(true), busy = useRef(false), retry = useRef<(() => Promise<void>) | null>(null), dialog = useRef<HTMLElement | null>(null), pickerOrigin = useRef<HTMLElement | null>(null)
  const pendingCreate = useRef<{ key: string; body: Record<string, unknown> } | null>(null), activePlan = useRef<Plan | null>(null)
  const preferenceChanged = useRef(false), handledSetupRequest = useRef(0), setupTitle = useRef<HTMLHeadingElement>(null)
  const resultSummary = useRef<HTMLElement>(null), createdResult = useRef<string | null>(null)
  const backToOverview = () => {
    resultSummary.current?.focus({ preventScroll: true })
    resultSummary.current?.scrollIntoView({ block: 'start', behavior: 'instant' })
  }
  useEffect(() => {
    const summary = resultSummary.current
    if (!createdResult.current || createdResult.current !== plan?.id || !summary?.getClientRects().length) return
    const resultId = createdResult.current
    const frame = requestAnimationFrame(() => {
      if (createdResult.current !== resultId || activePlan.current?.id !== resultId || !summary.getClientRects().length) return
      createdResult.current = null
      summary.focus({ preventScroll: true })
      summary.scrollIntoView({ block: 'start', behavior: 'instant' })
    })
    return () => cancelAnimationFrame(frame)
  })
  const startNewPlan = () => {
    setupEdited.current = true
    draftOverrides.current = { energy: false, count: false, preference: false, preparation: false }
    createdResult.current = null
    setSetupOpen(true); setSetupDetailsOpen(false); setDay(today()); setEnergy(settings?.energy_target ?? '1800')
    setCount(String(settings?.meal_count ?? 3)); setPreference(settings?.goal ?? 'balanced')
    resetPreparation(); setFixed({}); setProtein(''); setCarbs(''); setFat('')
    setError(''); setNotice(''); retry.current = null; pendingCreate.current = null
    requestAnimationFrame(() => { setupTitle.current?.focus({ preventScroll: true }); setupTitle.current?.scrollIntoView({ block: 'start' }) })
  }
  useEffect(() => {
    if (!setupRequest || handledSetupRequest.current === setupRequest || loading || pending) return
    handledSetupRequest.current = setupRequest
    startNewPlan(); onSetupHandled?.()
  }, [setupRequest, loading, pending])
  useEffect(() => {
    if (!resumeRequest || handledResume.current === resumeRequest || !settings) return
    handledResume.current = resumeRequest
    const nextCount = draftOverrides.current.count ? count : String(settings.meal_count ?? 3)
    if (!draftOverrides.current.energy) setEnergy(settings.energy_target ?? '1800')
    if (!draftOverrides.current.count) setCount(nextCount)
    if (!draftOverrides.current.preference) setPreference(settings.goal)
    if (!draftOverrides.current.preparation) {
      const initial = startingPreparation(settings.default_constraints, nextCount)
      setPreparationMode(initial.mode); setDraftConstraints(initial.constraints)
    } else setDraftConstraints(old => extendPreparation(old, nextCount, preparationMode, settings.default_constraints))
  }, [resumeRequest, settings])
  useEffect(() => { if (!activePlan.current && !setupEdited.current && !preferenceChanged.current && settings) setPreference(settings.goal) }, [settings?.goal])
  useEffect(() => { if (!activePlan.current && !setupEdited.current && settings) { if (settings.energy_target) setEnergy(settings.energy_target); setCount(String(settings.meal_count ?? 3)); resetPreparation() } }, [settings])
  const fixedFromPlan = (value: Plan) => Object.fromEntries(value.meals.filter(meal => meal.items.length === 1 && meal.locked && (meal.key === 'lunch' || Object.hasOwn(value.settings.fixed_meals as object ?? {}, meal.key))).map(meal => {
    const item = meal.items[0]
    return [meal.key, { menu_id: item.menu_id ?? undefined, custom_name: item.menu_id ? undefined : item.name, name: item.name, amount_g: item.amount_g, reference_portion_g: item.reference_portion_g ?? (item.amount_g ? Number(item.amount_g) : undefined) }]
  }))
  const showPlan = (value: Plan, sync = false) => {
    setMealFocus(null)
    if (!mounted.current || (activePlan.current?.id === value.id && activePlan.current.version > value.version)) return
    const resetDrafts = sync || activePlan.current?.id !== value.id
    activePlan.current = value; setPlan(value)
    setSelectedMeal(key => value.meals.some(meal => meal.key === key) ? key : value.meals[0]?.key ?? key)
    setAmounts(old => resetDrafts ? {} : Object.fromEntries(Object.entries(old).filter(([id, amount]) => value.meals.some(meal => !meal.consumed && meal.items.some(item => item.item_id === id && !sameAmount(item.amount_g, amount))))))
    setHistory(old => [value, ...old.filter(item => item.id !== value.id)])
    if (sync) {
      setSetupDetailsOpen(false)
      setSetupOpen(false)
      setDay(value.plan_date); setEnergy(String(value.settings.energy_target)); setCount(String(value.settings.meal_count)); setPreference(value.settings.preference as Preference)
      setProtein(String(value.settings.protein_target ?? '')); setCarbs(String(value.settings.carbohydrate_target ?? '')); setFat(String(value.settings.fat_target ?? ''))
      setConstraints(Object.fromEntries(value.meals.map(meal => [meal.key, { ...EMPTY, ...meal.constraints }])))
      setFixed(fixedFromPlan(value))
    }
  }
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; historyAbort.current?.abort(); menuAbort.current?.abort(); choiceAbort.current?.abort() }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError('')
    Promise.all([api<{ available_total: number }>('/planner/menus?limit=1', {}, controller.signal), api<Plan[]>(`/plans?date=${today()}`, {}, controller.signal)]).then(([catalog, plans]) => {
      if (controller.signal.aborted) return
      setAvailable(catalog.available_total); setHistory(plans)
      if (plans[0] && !activePlan.current) {
        if (!setupEdited.current) showPlan(plans[0], true)
        else setNotice('입력 중인 조건을 유지했어요. 저장된 식단은 지난 식단 찾기에서 확인할 수 있어요.')
      }
    }).catch(e => { if (!controller.signal.aborted) setLoadError(message(e)) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [loadAttempt])
  const roleQuery = picker?.role && pickerScope === 'same' ? `&role=${encodeURIComponent(picker.role)}` : ''
  const pickerAvoided = [...new Set([...(settings?.avoided_foods ?? []), ...(picker?.stage === 'draft' ? draftConstraints[picker.key]?.avoided_foods ?? [] : plan?.meals.find(meal => meal.key === picker?.key)?.constraints.avoided_foods ?? [])].map(name => name.trim()).filter(Boolean))]
  const exclusionQuery = pickerAvoided.map(name => `&avoided_foods=${encodeURIComponent(name)}`).join('')
  useEffect(() => {
    choiceAbort.current?.abort(); setCheckingChoice(false); setConflictChoice(null); setChoiceError(''); setFailedChoice(null)
    return () => choiceAbort.current?.abort()
  }, [picker, exclusionQuery])
  useEffect(() => { if (conflictChoice) conflictTitle.current?.focus({ preventScroll: true }) }, [conflictChoice])
  useEffect(() => {
    if (!picker || pickerMode !== 'catalog') return
    const controller = new AbortController(); menuAbort.current = controller; setMenuLoading(true); setMenuError(''); setMenus([]); setMenuOffset(0)
    const timer = window.setTimeout(() => {
      api<{ items: PlannerMenu[]; total: number }>(`/planner/menus?q=${encodeURIComponent(query.trim())}&limit=40${roleQuery}${exclusionQuery}`, {}, controller.signal).then(result => { if (!controller.signal.aborted) { setMenus(result.items); setMenuTotal(result.total) } }).catch(e => { if (!controller.signal.aborted) setMenuError(message(e)) }).finally(() => { if (!controller.signal.aborted) setMenuLoading(false) })
    }, 200)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [picker, query, roleQuery, pickerMode, exclusionQuery])
  useEffect(() => {
    if (!picker) return
    const previous = pickerOrigin.current
    const close = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy.current) setPicker(null)
      if (e.key !== 'Tab') return
      const focusable = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href]')
      if (!focusable?.length) return
      const first = focusable[0], last = focusable[focusable.length - 1]
      if (!dialog.current?.contains(document.activeElement)) { e.preventDefault(); first.focus(); return }
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', close)
    return () => { document.removeEventListener('keydown', close); previous?.focus() }
  }, [picker])
  const loadPlans = async (filter = historyDate, more = false) => {
    historyAbort.current?.abort(); const controller = new AbortController(); historyAbort.current = controller; setHistoryLoading(true)
    try { const result = await api<{ items: Plan[]; total: number }>(`/plan-history?limit=10&offset=${more ? history.length : 0}${filter ? `&date=${filter}` : ''}`, {}, controller.signal); if (!controller.signal.aborted) { setHistory(old => more ? [...old, ...result.items.filter(item => !old.some(value => value.id === item.id))] : result.items); setHistoryTotal(result.total) } }
    catch (error) { if (!controller.signal.aborted) setError(message(error)) } finally { if (!controller.signal.aborted) setHistoryLoading(false) }
  }
  useEffect(() => { if (historyOpen) void loadPlans() }, [historyOpen, historyDate])
  const run = async (task: () => Promise<void>) => {
    if (busy.current) return
    busy.current = true; setPending(true); setError(''); setNotice(''); retry.current = task
    try { await task(); if (mounted.current) retry.current = null }
    catch (e) { if (mounted.current) setError(message(e)) }
    finally { busy.current = false; if (mounted.current) setPending(false) }
  }
  const create = async () => {
    if (!await checkSettings() || !mounted.current) return
    setupEdited.current = true
    const fixedMeals = Object.fromEntries(Object.entries(fixed).filter(([key]) => slots(count).includes(key as MealKey)).map(([key, choice]) => [key, { menu_id: choice.menu_id, custom_name: choice.custom_name, amount_g: choice.amount_g }]))
    const activeConstraints = Object.fromEntries(Object.entries(draftConstraints).filter(([key]) => slots(count).includes(key as MealKey)))
    const values = { plan_date: day, energy_target: energy, meal_count: Number(count), preference, protein_target: protein || null, carbohydrate_target: carbs || null, fat_target: fat || null, constraints: activeConstraints, fixed_meals: fixedMeals, personalize: true }
    const key = JSON.stringify(values), body = pendingCreate.current?.key === key ? pendingCreate.current.body : { ...values, client_request_id: crypto.randomUUID() }
    pendingCreate.current = { key, body }
    void run(async () => { const value = await post<Plan>('/plans', body); if (!mounted.current) return; pendingCreate.current = null; createdResult.current = value.id; showPlan(value, true); setNotice('정한 메뉴와 준비 조건으로 하루 식단을 만들었어요.') })
  }
  const edit = async (meal: PlanMeal, action: string, fields: Record<string, unknown> = {}, focusAfter = false) => {
    if (action === 'replace' && (!await checkSettings() || !mounted.current)) return
    const current = activePlan.current; if (!current) return
    const body = { client_request_id: crypto.randomUUID(), expected_version: current.version, meal_key: meal.key, action, ...fields }
    void run(async () => { const value = await api<Plan>(`/plans/${current.id}`, { method: 'PATCH', body: JSON.stringify(body) }); if (!mounted.current) return; showPlan(value); setFixed(fixedFromPlan(value)); setPicker(null); if (focusAfter) focusMeal(meal.key, 'overview'); const updatedMeal = value.meals.find(item => item.key === meal.key)!; if (action === 'undo_replace') setConstraints(old => ({ ...old, [meal.key]: { ...EMPTY, ...updatedMeal.constraints } })); setNotice(action === 'undo_replace' ? '추천 변경 전의 메뉴와 분량으로 되돌렸어요. 다른 끼니는 그대로예요.' : action === 'replace' ? updatedMeal.undo_replacement?.request_id === body.client_request_id ? '다른 끼니를 유지하며 새 메뉴를 추천했어요. 변경 전으로 되돌릴 수 있어요.' : updatedMeal.reason : action === 'set' ? '직접 정한 메뉴로 바꿨어요. 고정 상태는 유지해요.' : action === 'portion' ? updatedMeal.items.find(item => item.item_id === fields.item_id)?.menu_id ? '변경한 양으로 참고 영양을 계산했어요.' : '분량을 저장했어요. 직접 입력 음식의 영양은 추정하지 않아요.' : action === 'add' ? '기존 구성에 음식을 추가했어요.' : action === 'remove' ? '선택한 음식만 구성에서 뺐어요.' : action === 'update_item' ? '선택한 음식 하나만 바꿨어요.' : '고정 상태를 저장했어요.') })
  }
  const setConstraint = (key: MealKey, changes: Partial<MealConstraints>) => setConstraints(old => ({ ...old, [key]: { ...(old[key] ?? EMPTY), ...changes } }))
  const setDraftConstraint = (key: MealKey, changes: Partial<MealConstraints>) => { draftOverrides.current.preparation = true; setPreparationMode('custom'); setDraftConstraints(old => ({ ...old, [key]: { ...(old[key] ?? EMPTY), ...changes } })) }
  const openPicker = (key: MealKey, stage: 'draft' | 'plan', action: 'set' | 'add' | 'update_item' = 'set', itemId?: string) => { pickerOrigin.current = document.activeElement as HTMLElement | null; const role = action === 'update_item' ? plan?.meals.find(meal => meal.key === key)?.items.find(item => item.item_id === itemId)?.role : undefined; setPickerMode('catalog'); setPickerScope('same'); setPicker({ key, stage, action, itemId, role: role && ['main', 'staple', 'protein', 'vegetable', 'soup', 'side'].includes(role) ? role : undefined }); setQuery(''); setCustomName(''); setCustomAmount(null); setMenus([]) }
  const applyChoice = (choice: FixedMeal) => {
    if (!picker) return
    setConflictChoice(null)
    if (picker.stage === 'draft') { setupEdited.current = true; setFixed(old => ({ ...old, [picker.key]: choice })); setPicker(null); setNotice('새 식단에 사용할 메뉴를 정했어요. 다른 끼니를 추천할 때 유지할게요.'); return }
    const meal = plan?.meals.find(meal => meal.key === picker.key)
    if (meal) edit(meal, picker.action ?? 'set', { item_id: picker.itemId, menu_id: choice.menu_id, custom_name: choice.custom_name, amount_g: choice.amount_g })
  }
  const choose = async (choice: FixedMeal) => {
    if (!picker || busy.current || checkingChoice) return
    choiceAbort.current?.abort()
    const controller = new AbortController(); choiceAbort.current = controller
    setCheckingChoice(true); setChoiceError(''); setFailedChoice(null)
    try {
      const query = choice.menu_id ? `menu_id=${encodeURIComponent(choice.menu_id)}` : `custom_name=${encodeURIComponent(choice.custom_name ?? '')}`
      const result = await api<{ conflicts: string[]; basis: string }>(`/planner/menu-exclusion-check?${query}${exclusionQuery}`, {}, controller.signal)
      if (controller.signal.aborted || !mounted.current) return
      if (result.conflicts.length) setConflictChoice({ choice, ...result })
      else applyChoice(choice)
    } catch (error) { if (!controller.signal.aborted) { setChoiceError(message(error)); setFailedChoice(choice) } }
    finally { if (!controller.signal.aborted) setCheckingChoice(false) }
  }
  const dateLabel = new Date(`${plan?.plan_date ?? day}T12:00:00`).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'long' })
  return <section className="planner-view" aria-labelledby="planner-title">
    <header className="planner-heading">
      <div><p className="eyebrow">YOUR EVERYDAY TABLE</p><h1 id="planner-title">{plan ? plan.plan_date === today() ? '오늘의 식탁' : '나의 하루 식탁' : '오늘도, 잘 먹는 하루.'}</h1><p>{plan ? '하루를 한눈에, 바꾸고 싶은 끼니는 자세히.' : '먹고 싶은 건 남겨두고, 나머지는 함께 정해요.'}</p></div>
      <div className="planner-heading-actions"><span className="plan-date">{dateLabel}</span>{plan && <button className="secondary" aria-expanded={setupOpen} aria-controls="plan-editor" disabled={pending} onClick={() => { if (setupOpen) setSetupOpen(false); else startNewPlan() }}>{setupOpen ? '닫기' : '새 식단 만들기'}<Icon name="plus" /></button>}</div>
    </header>
    <div className="plan-toolbar"><button className="secondary" disabled={pending} aria-expanded={historyOpen} onClick={() => setHistoryOpen(value => !value)}>지난 식단 찾기</button><span className="status-pill">내 입맛으로 정하고 · 바꾸고</span></div>
    {historyOpen && <section className="plan-browser" aria-label="저장한 식단 찾기"><div className="section-heading"><h2>저장한 식단</h2><label>날짜로 찾기<input ref={historyDateInput} aria-label="식단 조회 날짜" type="date" defaultValue={historyDate} disabled={pending} /></label><button className="secondary" disabled={pending || historyLoading} onClick={() => { const value = historyDateInput.current?.value ?? ''; if (value === historyDate) void loadPlans(value); else setHistoryDate(value) }}>날짜 조회</button><button className="text-button" onClick={() => { if (historyDateInput.current) historyDateInput.current.value = ''; setHistoryDate(''); void loadPlans('') }}>전체 날짜</button></div><div className="plan-history-list">{history.map(value => <button className={value.id === plan?.id ? 'selected' : ''} key={value.id} disabled={pending} onClick={() => { void run(async () => { showPlan(await api<Plan>(`/plans/${value.id}`), true); setHistoryOpen(false) }) }}><strong>{value.plan_date}</strong><span>{kcal(Number(value.settings.energy_target))}kcal · {value.meals.length}끼</span><small>{new Date(value.created_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })} 생성</small><small className="plan-history-preview">{value.meals.map(meal => meal.items[0]?.name ?? '메뉴 미정').join(' · ')}</small></button>)}</div>{historyLoading && <p role="status">식단을 불러오고 있어요…</p>}{!historyLoading && !history.length && <p>이 날짜에 저장한 식단이 없어요. 다른 날짜를 선택하거나 새로 만들어보세요.</p>}{history.length < historyTotal && <button className="secondary" disabled={historyLoading} onClick={() => void loadPlans(historyDate, true)}>이전 식단 더 보기</button>}</section>}
    {error && <div className="plan-message error" role="alert">{error}<div>{retry.current && <button disabled={pending} onClick={() => { if (retry.current) void run(retry.current) }}>같은 요청 다시 시도</button>}{plan && <button disabled={pending} onClick={() => void run(async () => showPlan(await api<Plan>(`/plans/${plan.id}`), true))}>최신 계획 불러오기</button>}</div></div>}
    {notice && <p className="plan-message success" role="status"><Icon name="check" />{notice}</p>}
    <ConnectionNotice key={`plan-load:${loadAttempt}`} loading={loading} error={loadError} loadingText="저장한 식단과 음식 자료를 불러오고 있어요" errorTitle="식단 준비 정보를 불러오지 못했어요" retryLabel="식단 다시 불러오기" onRetry={() => setLoadAttempt(value => value + 1)} />
    {(!plan || setupOpen) && <div className={`planner-workspace ${plan ? 'editing' : ''}`} id="plan-editor">
    <form className="plan-settings" onChangeCapture={() => { setupEdited.current = true }} onSubmit={e => { e.preventDefault(); void create() }} onInvalidCapture={event => { let element = event.target as HTMLElement | null; while (element && element !== event.currentTarget) { if (element instanceof HTMLDetailsElement) element.open = true; element = element.parentElement } setSetupDetailsOpen(true) }}>
      <div className="plan-settings-heading"><div><h2 ref={setupTitle} tabIndex={-1}>{plan ? '새 식단을 준비했어요' : '오늘 식단, 이렇게 시작해요'}</h2><p>이대로 추천받거나, 오늘만 조건을 바꿔보세요.</p></div></div>
      {settingsUnsaved && <div className="settings-draft-warning" role="status"><strong>내 설정에 저장하지 않은 변경이 있어요.</strong><p>추천하기 전에 저장한 설정으로 계속할지 확인할게요.</p><button type="button" className="text-button" onClick={onSettings}>내 설정 확인</button></div>}
      <fieldset className="preparation-choice" disabled={pending || loading}><legend>오늘은 어떻게 준비할까요?</legend><p>{Object.keys(settings?.default_constraints ?? {}).length ? '저장한 준비 조건이 있어요. 오늘만 다른 방식으로 바꿀 수 있어요.' : preparationMode === 'quick' ? '저장한 준비 조건이 없어 이번에는 끼니마다 20분 이내로 시작해요.' : preparationMode === 'ready' ? '사 온 음식이나 미리 만든 음식을 10분 안에 준비해요.' : preparationMode === 'unlimited' ? '이번 식단은 준비 시간에 제한을 두지 않아요.' : '끼니마다 직접 조절한 준비 조건을 사용해요.'}</p><div>{Object.keys(settings?.default_constraints ?? {}).length > 0 && <button type="button" aria-pressed={preparationMode === 'saved'} onClick={() => choosePreparation('saved')}><strong>저장한 준비 조건</strong><small>평소 설정 그대로</small></button>}<button type="button" aria-pressed={preparationMode === 'quick'} onClick={() => choosePreparation('quick')}><strong>20분 안에 간단히</strong><small>직접 조리하는 시간 포함</small></button><button type="button" aria-pressed={preparationMode === 'ready'} onClick={() => choosePreparation('ready')}><strong>조리 없이 10분</strong><small>사 온 음식·미리 만든 음식</small></button><button type="button" aria-pressed={preparationMode === 'unlimited'} onClick={() => choosePreparation('unlimited')}><strong>시간 제한 없이</strong><small>직접 조리해도 괜찮아요</small></button></div>{preparationMode === 'custom' && <p className="preparation-custom-note">끼니별로 직접 조절한 조건을 사용해요.</p>}<small>자료의 참고 준비 시간을 기준으로 골라요. 직접 정한 메뉴는 유지하고, 내 설정과 기존 식단은 바꾸지 않아요.</small></fieldset>
      <PlanSetupSummary startingConstraints={startingPreparation(settings?.default_constraints, count).constraints} preparationDefault={!Object.keys(settings?.default_constraints ?? {}).length} settings={settings} energy={energy} count={count} preference={preference} day={day} today={today()} protein={protein} carbs={carbs} fat={fat} slots={slots(count)} constraints={draftConstraints} fixed={fixed} pending={pending} onReset={startNewPlan} />
      <div className="setup-recommend"><button type="submit" className="plan-primary" disabled={pending || loading || !available}>{pending ? '식단을 만들고 있어요…' : '이 기준으로 추천받기'}<Icon name="arrow" /></button><p>{account ? '현재 계정에 저장해요.' : '로그인 없이 이 브라우저에서 시작해요.'}{plan && ' 지금 식단도 그대로 보관해요.'}</p></div>
      <details className="setup-customize" open={setupDetailsOpen} onToggle={event => setSetupDetailsOpen(event.currentTarget.open)}><summary>오늘만 조건 바꾸기<span>열량 · 끼니 · 정해 둔 메뉴 · 준비 조건</span></summary>
      <p className="setup-customize-note">아래 변경은 이번 추천에만 사용해요. 내 설정과 기존 식단은 바꾸지 않아요.</p>
      <div className="plan-fields">
        <label>하루 열량 목표<div className="plan-unit-input"><input aria-label="하루 열량 목표" type="number" min="600" max="5000" required value={energy} disabled={pending} onChange={e => { draftOverrides.current.energy = true; setEnergy(e.target.value) }} /><span>kcal</span></div><small>{!settings?.energy_target && energy === '1800' ? '1800kcal는 시작용 예시예요. 개인 권장량이 아니에요.' : '이번 식단에 사용할 하루 기준이에요.'}</small></label>
        <label>끼니 수<select aria-label="끼니 수" value={count} disabled={pending} onChange={e => changeCount(e.target.value)}><option value="2">2끼</option><option value="3">3끼</option><option value="4">3끼 + 간식</option></select><small>끼니 수를 바꿔도 입력한 조건은 유지해요. 선택한 끼니에만 적용해요.</small></label>
        <label>선택 우선순위<select aria-label="선택 우선순위" value={preference} disabled={pending} onChange={e => { preferenceChanged.current = true; draftOverrides.current.preference = true; setPreference(e.target.value as Preference) }}><option value="balanced">목표와 다양성</option><option value="protein">단백질 우선</option><option value="energy">열량 우선</option><option value="similarity">익숙한 메뉴 우선</option></select></label>
      </div>
      <details className="energy-help"><summary>목표 열량을 잘 모르겠어요</summary><p>1800kcal는 시작을 위한 예시이며 개인에게 맞춘 권장량이 아니에요. 평소 사용하는 목표가 있다면 입력해 주세요. ‘열량 우선’은 입력한 목표에 가깝게 식단을 구성해요. 탄수화물·단백질·지방 목표는 선택 사항이에요.</p></details>
      <div className="weekday-preset"><div><strong><Icon name="clock" />바쁜 평일이라면</strong><p>아침은 조리 없이 10분, 저녁은 30분 안에.</p></div><button type="button" disabled={pending} onClick={() => { setupEdited.current = true; draftOverrides.current.count = true; draftOverrides.current.preparation = true; setCount('3'); setPreparationMode('custom'); setDraftConstraints(BUSY); setNotice('아침은 조리 없이 10분, 저녁은 30분으로 설정했어요. 준비된 밥·반찬은 있을 때 선택해 주세요.') }}>이 조건으로</button></div>
      <div className="plan-fixed-lunch"><div className="plan-step-title"><div><h3>정해 둔 점심이 있나요?</h3><p>약속도, 도시락도 그대로 넣어주세요.</p></div><span className="optional-tag">선택</span></div>{fixed.lunch ? <div className="fixed-lunch-choice"><strong><Icon name="lock" />{fixed.lunch.name}</strong><PortionInput label="정한 점심 먹을 양" value={fixed.lunch.amount_g} disabled={pending} allowUnknown={!fixed.lunch.menu_id} reference={fixed.lunch.reference_portion_g} onChange={amount => setFixed(old => ({ ...old, lunch: { ...old.lunch!, amount_g: amount } }))} /><button type="button" disabled={pending} onClick={() => openPicker('lunch', 'draft')}>점심 변경</button><button type="button" disabled={pending} onClick={() => setFixed(old => { const next = { ...old }; delete next.lunch; return next })}>점심도 추천받기</button></div> : <button className="lunch-picker-button" type="button" disabled={pending || loading} onClick={() => openPicker('lunch', 'draft')}><Icon name="plus" />점심 먼저 선택<span>메뉴 검색 또는 직접 입력</span><Icon name="arrow" /></button>}<small>직접 입력 메뉴는 분량을 몰라도 넣을 수 있어요. 영양은 추정하지 않아요.</small></div>
      <details className="fixed-other-meals"><summary>아침·저녁도 정해두고 싶어요</summary><div className="fixed-meal-choices">{slots(count).filter(key => key !== 'lunch').map(key => <div key={key}><strong>{mealLabels[key]}</strong>{fixed[key] ? <><span>{fixed[key]!.name} · {amountText(fixed[key]!.amount_g)}</span><button type="button" className="text-button" onClick={() => openPicker(key, 'draft')}>변경</button><button type="button" className="text-button" onClick={() => setFixed(old => { const next = { ...old }; delete next[key]; return next })}>추천받기</button></> : <button type="button" className="secondary" disabled={pending} onClick={() => openPicker(key, 'draft')}>직접 정하기</button>}</div>)}</div></details>
      <details className="plan-day-conditions"><summary>준비 시간 · 기구 · 피할 음식 조절</summary><div className="plan-condition-grid">{slots(count).map(key => <div key={key}><h3>{mealLabels[key]}{fixed[key] && <small> · 직접 정한 메뉴 유지</small>}</h3><MealConditions label={`새 계획 ${mealLabels[key]}`} value={draftConstraints[key] ?? EMPTY} disabled={pending || !!fixed[key]} onChange={change => setDraftConstraint(key, change)} /></div>)}</div><small>이미 만든 밥·채소 반찬은 각각 5분 차림을 가정해요. 준비 시간은 메뉴별 참고값의 합계예요.</small></details>
      <details className="plan-target-details"><summary>날짜 · 탄수화물·단백질·지방 목표 조절 <span>선택</span></summary><div className="plan-macro-fields"><label>계획 날짜<input type="date" required value={day} disabled={pending} onChange={e => setDay(e.target.value)} /></label><label>단백질 목표 g<input type="number" min="10" max="300" disabled={pending} value={protein} placeholder="예: 100" onChange={e => setProtein(e.target.value)} /></label><label>탄수화물 목표 g<input type="number" min="20" max="800" disabled={pending} value={carbs} placeholder="직접 입력" onChange={e => setCarbs(e.target.value)} /></label><label>지방 목표 g<input type="number" min="5" max="300" disabled={pending} value={fat} placeholder="직접 입력" onChange={e => setFat(e.target.value)} /></label></div></details>
      <div className="setup-customize-submit"><button type="submit" className="plan-primary" disabled={pending || loading || !available}>{pending ? '식단을 만들고 있어요…' : '바꾼 조건으로 추천받기'}<Icon name="arrow" /></button></div>
      </details>
      <p className="setup-settings-link">취향은 저장한 설정을 참고해요. <button type="button" className="inline-link" onClick={onSettings}>내 설정 관리</button></p>
    </form>
    {!plan && <aside className="table-story"><span className="story-kicker">A LITTLE LESS WORRY,<br />A LITTLE MORE APPETITE.</span><div className="story-art"><EditorialArtwork kind="bowl" priority /></div><div className="story-copy"><h2>고민은 조금 덜고,<br />내 입맛은 그대로.</h2><p>좋아하는 음식, 이미 정한 약속.<br />내 하루에 맞는 식단을 만들어보세요.</p></div><div className="story-bottom"><span>정하고</span><span>바꾸고</span><span>잘 먹고</span></div></aside>}
    </div>}
    {plan && <>
      <MealOverview meals={plan.meals} selected={selectedMeal} onSelect={selectMeal} amounts={amounts} panelId={mealPanelId} summaryRef={resultSummary} />
      <DailyNutrition plan={plan} compact />
      <EnergyGap key={plan.id} plan={plan} selected={selectedMeal} pending={pending} onSelect={selectMeal} onPortion={key => focusMeal(key, 'portion')} onConditions={key => focusMeal(key, 'conditions')} onAdd={key => { selectMeal(key); openPicker(key, 'plan', 'add') }} />
      <section className="selected-meal-panel" id={mealPanelId} role="tabpanel" aria-labelledby={`${mealPanelId}-tab-${selectedMeal}`} tabIndex={0}>
        {plan.meals.filter(meal => meal.key === selectedMeal).map(meal => <PlanMealCard key={meal.key} meal={meal} onOverview={backToOverview} focusRequest={mealFocus?.key === meal.key ? mealFocus : undefined} dayEnergy={plan.nutrients.energy_kcal} energyTarget={Number(plan.settings.energy_target)} completeEnergy={!plan.missing_nutrients.includes('energy_kcal')} onConditionRecommend={() => edit(meal, 'replace', { constraints: constraints[meal.key] ?? meal.constraints }, true)} constraints={constraints[meal.key] ?? { ...EMPTY, ...meal.constraints }} pending={pending} amounts={amounts} onAmount={(id, value) => setAmounts(old => ({ ...old, [id]: value }))} onConstraint={change => setConstraint(meal.key, change)} onEdit={(action, fields) => edit(meal, action, fields)} onPick={(action, itemId) => openPicker(meal.key, 'plan', action, itemId)} onCompare={onCompare} />)}
      </section>
      <p className="food-art-note">그림은 음식 종류를 표현한 예시예요.</p>
      <div className="plan-endnote"><span><Icon name="check" />{account ? '현재 계정에 저장된 식단' : '이 브라우저에 저장된 식단'}</span><button type="button" className="inline-link" onClick={onSettings}>내 취향 더 알려주기 <Icon name="arrow" /></button></div>
      <details className="plan-footnote"><summary>참고값과 자료에 대해</summary><p>영양은 일반 메뉴의 참고값이에요. 계산은 원래 소수값을 유지하고 화면만 반올림해요. 준비 시간·분량은 참고 설정이며 계획과 실제 식사는 따로 저장해요. 재료 반복·제외는 이름과 재료 예시 기준이며 전체 성분표가 아니에요. 화면의 손그림은 장식이며 실제 음식 사진이 아니에요.</p></details>
    </>}
    {picker && <div className="plan-dialog-backdrop" onClick={() => { if (!pending) setPicker(null) }}><section ref={dialog} className="plan-dialog" role="dialog" aria-modal="true" aria-labelledby={conflictChoice ? 'menu-conflict-title' : 'menu-picker-title'} onClick={e => e.stopPropagation()}>
      <div className="plan-dialog-title"><div><span>{mealLabels[picker.key]}{picker.stage === 'draft' ? ' · 새 식단에 고정' : ''}</span>{!conflictChoice && <h2 id="menu-picker-title">먹고 싶은 걸 골라요.</h2>}</div><button aria-label="메뉴 선택 닫기" disabled={pending} onClick={() => setPicker(null)}><Icon name="close" /></button></div>
      {conflictChoice ? <div className="menu-exclusion-confirm">
        <h2 id="menu-conflict-title" ref={conflictTitle} tabIndex={-1}>제외 설정과 겹치는 메뉴예요</h2>
        <strong className="conflict-menu-name">{conflictChoice.choice.name}</strong>
        <p>겹치는 제외 항목: <strong>{conflictChoice.conflicts.join(' · ')}</strong></p>
        <p>이 메뉴를 직접 선택할 수 있어요. 저장한 제외 설정과 다른 끼니는 바꾸지 않아요.</p>
        <small>{conflictChoice.basis === 'name_only' ? '직접 입력한 이름에서 확인했어요. 전체 재료까지 확인한 결과는 아니에요.' : '등록 메뉴의 이름과 재료 예시 기준이에요. 전체 성분을 확인한 결과는 아니에요.'}</small>
        <div className="dialog-actions"><button type="button" className="secondary" onClick={() => setConflictChoice(null)}>다른 메뉴 고르기</button><button type="button" className="primary" disabled={pending} onClick={() => applyChoice(conflictChoice.choice)}>이번 끼니에만 사용</button></div>
      </div> : <>
      {pickerAvoided.length > 0 && <p className="picker-exclusion-note">제외 기준: {pickerAvoided.join(' · ')}<small>내 설정과 이 끼니의 제외 조건을 확인해요. 겹치는 메뉴도 확인 후 직접 선택할 수 있어요.</small></p>}
      {choiceError && <p role="alert" className="error">{choiceError}{failedChoice && <button type="button" className="text-button" disabled={checkingChoice} onClick={() => void choose(failedChoice)}>제외 설정 다시 확인</button>}</p>}
      {checkingChoice && <p role="status">선택한 메뉴와 제외 설정을 확인하고 있어요…</p>}
      <div className="picker-method" role="group" aria-label="메뉴 입력 방식"><button type="button" aria-pressed={pickerMode==='catalog'} disabled={pending || checkingChoice} onClick={()=>setPickerMode('catalog')}>메뉴 찾기</button><button type="button" aria-pressed={pickerMode==='custom'} disabled={pending || checkingChoice} onClick={()=>setPickerMode('custom')}>직접 입력</button></div>
      <p className="picker-scope-note">{picker.stage === 'draft' ? `${mealLabels[picker.key]}에 정해둔 메뉴를 넣고 유지해요.` : picker.action === 'add' ? '지금 구성은 유지하고 음식 하나를 추가해요.' : picker.action === 'update_item' ? '선택한 음식 하나만 바꾸고, 나머지 구성은 유지해요.' : '이 끼니 전체를 선택한 메뉴로 바꿔요. 고정 상태는 유지해요.'}</p>{picker.role && <div className="picker-role-filter" role="group" aria-label="음식 변경 범위"><button type="button" disabled={checkingChoice} aria-pressed={pickerScope === 'same'} onClick={() => setPickerScope('same')}>{roleLabels[picker.role]} 메뉴</button><button type="button" disabled={checkingChoice} aria-pressed={pickerScope === 'all'} onClick={() => setPickerScope('all')}>전체 메뉴에서 찾기</button><p>{pickerScope === 'same' ? '지금 음식과 같은 역할의 후보부터 보여줘요.' : '다른 역할의 음식도 직접 고를 수 있어요. 나머지 구성은 유지해요.'}</p></div>}{pickerMode==='catalog'&&<><label className="plan-picker-search">식단 메뉴 검색<input autoFocus value={query} disabled={checkingChoice} onChange={e => setQuery(e.target.value)} placeholder="예: 비빔밥, 국수, 달걀말이" maxLength={80} /></label><p className="muted">{menuLoading ? '메뉴를 찾고 있어요…' : `${menuTotal}개 중 ${menus.length}개 · 메뉴 참고 분량이며 양은 바꿀 수 있어요.`}</p>{menuError && <p role="alert">{menuError}</p>}
      <div className="plan-picker-results">{menus.map(menu => <button key={menu.menu_id} disabled={pending || checkingChoice} onClick={() => void choose({ menu_id: menu.menu_id, name: menu.name, amount_g: String(menu.portion_g), reference_portion_g: menu.portion_g })}><span><strong>{menu.name}</strong><small>{roleLabels[menu.role]} · 참고 분량 {menu.portion_g}g</small>{Boolean(menu.excluded_by?.length) && <small className="menu-exclusion-badge">제외 설정 겹침: {menu.excluded_by!.join(' · ')}</small>}</span><b>약 {kcal(Number(menu.nutrients.energy_kcal) * menu.portion_g / 100)}<small>kcal</small></b></button>)}</div>
      {!menuLoading && !menuError && menus.length === 0 && <p className="picker-empty">찾는 메뉴가 없어요. 위의 직접 입력에서 이름을 적어주세요.</p>}
      {menus.length < menuTotal && !menuLoading && <button className="secondary" disabled={pending || checkingChoice} onClick={async () => { setMenuLoading(true); const signal = menuAbort.current?.signal; try { const next = menuOffset + 40; const result = await api<{ items: PlannerMenu[]; total: number }>(`/planner/menus?q=${encodeURIComponent(query.trim())}&limit=40&offset=${next}${roleQuery}${exclusionQuery}`, {}, signal); if (!signal?.aborted) { setMenus(old => [...old, ...result.items]); setMenuOffset(next) } } catch (error) { if (!signal?.aborted) setMenuError(message(error)) } finally { if (!signal?.aborted) setMenuLoading(false) } }}>메뉴 더 보기</button>}
      </>}{pickerMode==='custom'&&<form className="plan-custom-form" onSubmit={e => { e.preventDefault(); void choose({ custom_name: customName, name: customName, amount_g: customAmount }) }}><h3>내 메뉴 직접 입력</h3><label>메뉴 이름<input autoFocus required value={customName} disabled={checkingChoice} maxLength={100} placeholder="예: 오늘 회사 점심" onChange={e => setCustomName(e.target.value)} /></label><div><PortionInput label="직접 입력 메뉴 먹을 양" value={customAmount} onChange={setCustomAmount} disabled={pending || checkingChoice} allowUnknown /><button className="plan-primary" disabled={pending || checkingChoice}>직접 입력으로 선택</button></div><p>분량은 몰라도 괜찮아요. 이름을 남기고 알 수 없는 영양은 비워둬요. 제외 항목과 이름·재료 묶음이 겹치면 한 번 더 확인해요.</p></form>}
      </>}
    </section></div>}
  </section>
}
