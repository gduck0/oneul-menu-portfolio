import type { MealConstraints, MealKey } from './plannerTypes'

export type PreparationMode = 'quick' | 'ready' | 'saved' | 'unlimited' | 'custom'
export const preparationSlots = (count: string): MealKey[] => count === '2' ? ['lunch', 'dinner'] : count === '4' ? ['breakfast', 'lunch', 'dinner', 'snack'] : ['breakfast', 'lunch', 'dinner']
const empty = (): MealConstraints => ({ no_cook: false, prepared_sides: false, tools: [], max_minutes: null, avoided_foods: [] })
const copy = (value?: MealConstraints): MealConstraints => ({ ...empty(), ...value, tools: [...value?.tools ?? []], avoided_foods: [...value?.avoided_foods ?? []] })

export function applyPreparation(mode: Exclude<PreparationMode, 'custom'>, current: Record<string, MealConstraints>, count: string, saved: Record<string, MealConstraints> = {}) {
  const next = { ...current }
  for (const key of preparationSlots(count)) {
    const base = copy(mode === 'saved' ? saved[key] : current[key])
    next[key] = mode === 'saved' ? base : { ...base, no_cook: mode === 'ready', max_minutes: mode === 'quick' ? 20 : mode === 'ready' ? 10 : null }
  }
  return next
}

export function startingPreparation(saved: Record<string, MealConstraints> = {}, count = '3') {
  const hasSaved = Object.keys(saved).length > 0
  const mode: PreparationMode = hasSaved ? 'saved' : 'quick'
  return { mode, constraints: hasSaved ? Object.fromEntries(Object.entries(saved).map(([key, value]) => [key, copy(value)])) : applyPreparation('quick', {}, count) }
}

export function extendPreparation(current: Record<string, MealConstraints>, count: string, mode: PreparationMode, saved: Record<string, MealConstraints> = {}) {
  return { ...applyPreparation(mode === 'custom' ? 'saved' : mode, {}, count, saved), ...current }
}
