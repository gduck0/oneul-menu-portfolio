import { amountText } from './PortionInput'
import { kcal, mealLabels } from './plannerDisplay'
import type { FixedMeal, MealConstraints, MealKey } from './plannerTypes'
import type { PersonalSettings, Preference } from './types'

type Props = {
  settings: PersonalSettings | null; energy: string; count: string; preference: Preference;
  day: string; today: string; protein: string; carbs: string; fat: string;
  slots: MealKey[]; constraints: Record<string, MealConstraints>; fixed: Partial<Record<MealKey, FixedMeal>>;
  startingConstraints?: Record<string, MealConstraints>; preparationDefault?: boolean;
  pending: boolean; onReset: () => void;
}

const preferenceLabels: Record<Preference, string> = { balanced: '목표와 다양성', protein: '단백질 우선', energy: '열량 우선', similarity: '익숙한 메뉴 우선' }
const comparableConditions = (value?: MealConstraints) => JSON.stringify({ no_cook: value?.no_cook ?? false, prepared_sides: value?.prepared_sides ?? false, max_minutes: value?.max_minutes ?? null, tools: [...value?.tools ?? []].sort(), avoided_foods: [...value?.avoided_foods ?? []].sort() })

export function PlanSetupSummary({ settings, energy, count, preference, day, today, protein, carbs, fat, slots, constraints, fixed, pending, onReset, startingConstraints, preparationDefault = false }: Props) {
  const changed = energy !== (settings?.energy_target ?? '1800') || count !== String(settings?.meal_count ?? 3) || preference !== (settings?.goal ?? 'balanced') || day !== today || Boolean(protein || carbs || fat) || slots.some(key => fixed[key] || comparableConditions(constraints[key]) !== comparableConditions(startingConstraints?.[key] ?? settings?.default_constraints?.[key]))
  const prepared = slots.flatMap(key => {
    const value = constraints[key]
    if (!value || fixed[key]) return []
    const parts = [value.no_cook ? '조리 없이' : '', value.prepared_sides ? '준비된 밥·반찬 사용' : '', value.max_minutes ? `${value.max_minutes}분 이내` : '', value.tools.length ? value.tools.join('·') : '', value.avoided_foods.length ? `${value.avoided_foods.join(', ')} 제외` : ''].filter(Boolean)
    return parts.length ? [`${mealLabels[key]} · ${parts.join(' / ')}`] : []
  })
  return <section className="setup-summary" aria-label="이번 식단에 반영할 설정">
    <p className="setup-summary-source">{changed ? '오늘만 바꾼 기준이에요' : preparationDefault ? '간편한 준비 기준을 더했어요' : settings?.energy_target ? '저장한 설정으로 준비했어요' : '시작할 기준을 준비했어요'}</p>
    <dl className="setup-summary-values">
      <div><dt>하루 목표</dt><dd>{energy && Number.isFinite(Number(energy)) ? kcal(energy) : '입력 필요'}<small> kcal</small></dd></div>
      <div><dt>끼니</dt><dd>{count === '4' ? '3끼 + 간식' : `${count}끼`}</dd></div>
      <div><dt>우선순위</dt><dd>{preferenceLabels[preference]}</dd></div>
    </dl>
    <div className="setup-summary-context">
      {!settings?.energy_target && energy === '1800' && <p>1,800kcal는 시작용 예시예요. 개인 권장량이 아니에요.</p>}
      {!!settings?.favorite_foods.length && <p><span>좋아하는 음식</span>{' '}{settings.favorite_foods.join(', ')}</p>}
      {!!settings?.avoided_foods.length && <p><span>제외할 음식</span>{' '}{settings.avoided_foods.join(', ')}</p>}
      {!!settings?.frequent_foods.length && <p><span>평소 자주 먹는 음식</span>{' '}{settings.frequent_foods.join(', ')}</p>}
      {prepared.length ? prepared.map(text => <p className="setup-preparation" key={text}>{text}</p>) : <p className="setup-preparation">추가한 준비 조건이 없어요.</p>}
      {slots.filter(key => fixed[key]).map(key => <p key={key}><span>{mealLabels[key]} 유지</span>{' '}{fixed[key]!.name} · {amountText(fixed[key]!.amount_g)}{!fixed[key]!.menu_id && ' · 영양 자료 없음'}</p>)}
      {day !== today && <p><span>계획 날짜</span>{' '}{day}</p>}
      {(protein || carbs || fat) && <p><span>추가 목표</span>{' '}{[protein && `단백질 ${protein}g`, carbs && `탄수화물 ${carbs}g`, fat && `지방 ${fat}g`].filter(Boolean).join(' · ')}</p>}
    </div>
    {changed && <button type="button" className="text-button setup-reset" disabled={pending} onClick={onReset}>{settings?.energy_target ? '저장한 기준으로 되돌리기' : '시작 기준으로 되돌리기'}</button>}
  </section>
}
