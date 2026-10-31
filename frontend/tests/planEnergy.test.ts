import assert from 'node:assert/strict'
import test from 'node:test'
import { energyGap, nutritionNotes, portionPreview } from '../src/planEnergy.ts'
import type { Plan, PlanMeal } from '../src/plannerTypes.ts'

const nutrients = (energy: string | null) => ({ energy_kcal: energy, protein_g: '10', carbohydrate_g: '20', fat_g: '5' })
const meal = (): PlanMeal => ({
  key: 'lunch', label: '점심', consumed: false, locked: false, status: 'ready',
  nutrients: nutrients('200'), minutes: 10, energy_reference: '200', reason: '시험용 식단',
  constraints: { no_cook: false, tools: [], max_minutes: null, avoided_foods: [] },
  items: [{ item_id: 'one', menu_id: 'one', name: '시험 음식', amount_g: '100',
    min_g: 50, max_g: 100, nutrients: nutrients('200'), reference_nutrients: nutrients('200'),
    food: null, nutrition_note: '시험용 참고값', role: 'main', preparation: null,
    tools: [], minutes: null, ingredients: [] }],
})
const plan = (): Plan => ({
  id: 'test-plan', version: 1, plan_date: '2026-01-01',
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  settings: { energy_target: '800' }, nutrients: nutrients('400'), missing_nutrients: [],
  meals: [meal()], target_difference: nutrients('-400'), notes: [], catalog_version: 'test-catalog',
})

test('과거 공통 안내가 고정 탓으로 읽히지 않게 표시하되 저장한 문구는 보존한다', () => {
  const value = plan()
  value.notes = ['현재 분량과 고정한 끼니를 유지하면 하루 열량 목표와 차이가 남아요. 양이나 고정 상태를 직접 조절할 수 있어요.', '다른 안내']
  const before = structuredClone(value)
  assert.match(nutritionNotes(value)[0], /400kcal 낮아요/)
  assert.equal(nutritionNotes(value)[1], '다른 안내')
  assert.ok(!nutritionNotes(value)[0].includes('고정한 끼니'))
  value.missing_nutrients = ['energy_kcal']
  assert.match(nutritionNotes(value)[0], /비교를 보류/)
  assert.deepEqual(value.notes, before.notes)
})

test('목표 차이와 추천 분량 상한을 확인하고 원본은 바꾸지 않는다', () => {
  const value = plan(), before = structuredClone(value)
  const result = energyGap(value)
  assert.equal(result.difference, -400)
  assert.equal(result.atUpperLimit, true)
  assert.equal(result.visible, true)
  assert.deepEqual(value, before)
})

test('결측은 0으로 비교하지 않고 먹은 끼니는 조절 대상에서 뺀다', () => {
  const value = plan(); value.missing_nutrients = ['energy_kcal']; value.meals[0].consumed = true
  const result = energyGap(value)
  assert.equal(result.difference, null)
  assert.deepEqual(result.editable, [])
  assert.equal(result.atUpperLimit, false)
})

test('고정한 끼니도 직접 양을 조절할 수 있고 옛 자료에 범위가 없으면 상한으로 단정하지 않는다', () => {
  const value = plan(); value.meals[0].locked = true; delete value.meals[0].items[0].max_g
  assert.equal(energyGap(value).editable.length, 1)
  assert.equal(energyGap(value).atUpperLimit, false)
})

test('입력한 분량으로 끼니와 하루 예상값을 계산하되 저장값은 유지한다', () => {
  const value = meal(), before = structuredClone(value)
  assert.deepEqual(portionPreview(value, { one: '150' }, '400', true), { meal: 300, day: 500 })
  assert.deepEqual(value, before)
})

test('과거 항목은 현재 영양비율로 미리보고 하루 결측은 합계를 확정하지 않는다', () => {
  const value = meal(); delete value.items[0].reference_nutrients
  assert.deepEqual(portionPreview(value, { one: '50' }, '400', false), { meal: 100, day: null })
  value.items[0].nutrients.energy_kcal = null
  assert.equal(portionPreview(value, { one: '50' }, '400', true), null)
})

test('비어 있거나 허용되지 않는 분량은 예상 열량으로 보여주지 않는다', () => {
  for (const amount of ['', '0', '-1', '2001', 'NaN']) assert.equal(portionPreview(meal(), { one: amount }, '400', true), null)
})
