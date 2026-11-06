import { useEffect, useState } from 'react'
import { api, message } from './api'
import type { ActualMeal, Plan } from './plannerTypes'

export function useActualMeals(plan: Plan | null, revision: number) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ key: string; meals: Record<string, ActualMeal>; error: string } | null>(null)
  const consumed = plan?.meals.filter(meal => meal.consumed) ?? []
  const key = consumed.length ? `${plan!.id}:${plan!.version}:${revision}:${attempt}` : ''
  useEffect(() => {
    if (!key || !plan) return
    const controller = new AbortController()
    api<{ plan_id: string; plan_version: number; meals: Record<string, ActualMeal> }>(`/plans/${plan.id}/actual-meals`, {}, controller.signal).then(value => {
      if (controller.signal.aborted) return
      if (value.plan_id !== plan.id || value.plan_version !== plan.version) throw new Error('식단이 바뀌었어요. 실제 식사는 식사 기록에서 확인해 주세요.')
      setResult({ key, meals: value.meals, error: '' })
    }).catch(error => { if (!controller.signal.aborted) setResult({ key, meals: {}, error: message(error) }) })
    return () => controller.abort()
  }, [key])
  return { meals: result?.key === key ? result.meals : {}, loading: Boolean(key && result?.key !== key), error: result?.key === key ? result.error : '', retry: () => setAttempt(value => value + 1) }
}
