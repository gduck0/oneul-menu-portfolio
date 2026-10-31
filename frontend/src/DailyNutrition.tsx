import type { Ref } from 'react'
import { nutritionNotes } from './planEnergy'
import { PlanMacro } from './PlanMacro'
import { grams, kcal } from './plannerDisplay'
import type { Plan } from './plannerTypes'

export function DailyNutrition({ plan, compact = false, summaryRef }: { plan: Plan; compact?: boolean; summaryRef?: Ref<HTMLElement> }) {
  const notes = nutritionNotes(plan)
  const energy = plan.nutrients.energy_kcal
  const goal = Number(plan.settings.energy_target)
  const partial = plan.missing_nutrients.includes('energy_kcal')
  const comparable = energy !== null && !partial && Number.isFinite(goal) && goal > 0
  const ratio = comparable ? Number(energy) / goal : null
  const percentage = ratio === null ? null : Math.round(ratio * 100)
  const total = plan.meals.reduce((sum, meal) => sum + Number(meal.nutrients.energy_kcal ?? 0), 0)
  const circumference = 2 * Math.PI * 60
  if (compact) return <section ref={summaryRef} tabIndex={summaryRef ? -1 : undefined} className="day-nutrition" aria-labelledby="day-nutrition-title">
    <div className="day-nutrition-strip">
      <div className="day-energy">
        <div className={`energy-ring ${comparable ? '' : 'incomplete'}`} role="img" aria-label={comparable ? `입력 목표 대비 ${percentage}%` : '영양 자료 일부 없음 · 전체 비교 보류'}>
          <svg viewBox="0 0 144 144" aria-hidden="true"><circle className="ring-track" cx="72" cy="72" r="60" />{ratio !== null && <circle className="ring-fill" cx="72" cy="72" r="60" strokeDasharray={`${Math.min(1, Math.max(0, ratio)) * circumference} ${circumference}`} />}</svg><span><strong>{percentage === null ? '—' : `${percentage}%`}</strong></span>
        </div>
        <div><h2 id="day-nutrition-title">{partial ? '확인된 계획 열량' : '계획한 하루 영양'}</h2><strong>{energy === null ? '자료 없음' : <>{kcal(energy)} <small>kcal</small></>}</strong><p>내가 정한 목표 {kcal(goal)} kcal{comparable && <> · {Number(energy) >= goal ? '+' : '−'}{kcal(Math.abs(Number(energy) - goal))} kcal</>}</p></div>
      </div>
      <dl className="day-macros">{([['carbohydrate_g', '탄수화물', 'carbohydrate_target'], ['protein_g', '단백질', 'protein_target'], ['fat_g', '지방', 'fat_target']] as const).map(([field, label, target]) => {
        const value = plan.nutrients[field], targetValue = Number(plan.settings[target]), complete = value !== null && !plan.missing_nutrients.includes(field)
        return <div key={field}><dt>{label}{!complete && <span className="partial-mark"> · 일부</span>}</dt><dd>{grams(value)}{value !== null && <small> g</small>}</dd>{complete && targetValue > 0 && <span className="mini-track" role="img" aria-label={`${label} 목표 ${grams(String(targetValue))}g 대비 약 ${Math.round(Number(value) / targetValue * 100)}%`}><i style={{ width: `${Math.min(100, Number(value) / targetValue * 100)}%` }} /></span>}</div>
      })}</dl>
    </div>
    <details className="nutrition-detail"><summary>영양 목표·계산 기준 자세히</summary><DailyNutrition plan={plan} /></details>
    {partial && <p className="nutrition-partial-note">자료가 없는 음식은 합계에서 빠져 있어요. 전체 목표 비교는 보류해요.</p>}
  </section>
  return <section className="plan-summary daily-nutrition" aria-labelledby="nutrition-title">
    <header className="daily-nutrition-heading"><div><h2 id="nutrition-title">계획한 하루 영양</h2><p>먹은 기록과 별도로, 지금 식단의 참고 영양을 보여줘요.</p></div><span className={`nutrition-data-label ${partial ? 'partial' : ''}`}>{partial ? '일부 영양 자료 없음' : '메뉴 참고값 기준'}</span></header>
    <div className={`daily-energy ${comparable ? '' : 'incomplete'}`}>
      <div className="energy-ring" role="img" aria-label={comparable ? `계획 열량 약 ${kcal(energy)}kcal, 입력 목표 ${kcal(goal)}kcal의 ${percentage}%` : `확인된 열량 ${energy === null ? '자료 없음' : `약 ${kcal(energy)}kcal`}. 전체 목표 비교는 보류해요.`}>
        <svg viewBox="0 0 144 144" aria-hidden="true"><circle className="ring-track" cx="72" cy="72" r="60" />{ratio !== null && <circle className="ring-fill" cx="72" cy="72" r="60" strokeDasharray={`${Math.min(1, Math.max(0, ratio)) * circumference} ${circumference}`} />}</svg>
        <span><strong>{percentage === null ? '—' : `${percentage}%`}</strong><small>{percentage === null ? '전체 비교 보류' : '입력한 목표 대비'}</small></span>
      </div>
      <div className="daily-energy-copy"><span>{partial ? '확인된 열량 합계' : '계획한 열량'}</span><strong>{energy === null ? '자료 없음' : <>약 {kcal(energy)}<small>kcal</small></>}</strong><p>내가 정한 목표 {kcal(goal)}kcal</p>{comparable && <p className="energy-difference">{percentage! > 100 ? `목표보다 약 ${kcal(Number(energy) - goal)}kcal 높아요` : percentage! < 100 ? `목표까지 약 ${kcal(goal - Number(energy))}kcal 남았어요` : '반올림한 비율은 목표와 비슷해요'}</p>}{!comparable && <p className="energy-difference">{partial ? '자료가 없는 음식은 합계에 포함되지 않아요.' : '열량 자료가 모이면 목표와 비교해요.'}</p>}</div>
    </div>
    <div className="meal-energy-distribution"><h3>끼니별 열량</h3><div className="meal-energy-track" aria-hidden="true">{plan.meals.map(meal => <span className={`energy-segment segment-${meal.key}`} key={meal.key} style={{ flexGrow: total > 0 ? Number(meal.nutrients.energy_kcal ?? 0) / total : 0 }} />)}</div><ul>{plan.meals.map(meal => <li key={meal.key}><span><i className={`segment-${meal.key}`} aria-hidden="true" />{meal.label}</span><strong>{meal.nutrients.energy_kcal === null ? '자료 없음' : `${kcal(meal.nutrients.energy_kcal)} kcal`}</strong></li>)}</ul><p>{partial ? '확인 가능한 열량만 나눠 표시했어요.' : '끼니별 열량이 하루 합계에서 차지하는 비중이에요.'}</p></div>
    <dl className="daily-macros"><PlanMacro plan={plan} field="protein_g" target="protein_target" label="단백질" /><PlanMacro plan={plan} field="carbohydrate_g" target="carbohydrate_target" label="탄수화물" /><PlanMacro plan={plan} field="fat_g" target="fat_target" label="지방" /></dl>
    {notes.length > 0 && <div className="plan-summary-notes">{notes.map(note => <p className="plan-notice" key={note}>{note}</p>)}</div>}
  </section>
}
