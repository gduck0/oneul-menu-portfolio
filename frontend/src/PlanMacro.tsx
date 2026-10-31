import { grams } from './plannerDisplay'
import type { Plan } from './plannerTypes'

export function PlanMacro({ plan, field, target, label }: { plan: Plan; field: 'protein_g' | 'carbohydrate_g' | 'fat_g'; target: string; label: string }) {
  const value = plan.nutrients[field], goal = plan.settings[target], delta = plan.target_difference[field]
  const comparable = value !== null && goal != null && Number(goal) > 0 && delta !== null && !plan.missing_nutrients.includes(field)
  const percentage = comparable ? Number(value) / Number(goal) * 100 : null
  return <div className={`macro-card macro-${field}`}><dt><span className="macro-dot" aria-hidden="true" />{label}</dt><dd>{grams(value)}{value !== null && <small>g</small>}</dd>{goal != null ? <><div className={`macro-meter ${comparable ? '' : 'incomplete'}`} role="img" aria-label={comparable ? `${label} 입력한 목표 ${grams(String(goal))}g 대비 약 ${Math.round(percentage!)}%` : `${label} 전체 목표 비교 보류`}><span style={{ width: `${Math.min(100, Math.max(0, percentage ?? 0))}%` }} /></div><p className="plan-macro-target">목표 {grams(String(goal))}g<br />{!comparable ? '자료 일부 없음 · 비교 보류' : Number(delta) < 0 ? `약 ${grams(String(Math.abs(Number(delta))))}g 부족` : Number(delta) > 0 ? `약 ${grams(delta)}g 초과` : '참고값 기준 목표 일치'}</p></> : <p className="plan-macro-target">{plan.missing_nutrients.includes(field) ? '확인 가능한 값의 합계' : '메뉴 참고값 합계'}<br />목표 미설정</p>}</div>
}
