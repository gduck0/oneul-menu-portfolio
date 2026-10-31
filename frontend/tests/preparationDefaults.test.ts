import assert from 'node:assert/strict'
import test from 'node:test'
import { applyPreparation, extendPreparation, startingPreparation } from '../src/preparationDefaults.ts'
import type { MealConstraints } from '../src/plannerTypes.ts'

const empty = (): MealConstraints => ({ no_cook:false,prepared_sides:false,max_minutes:null,tools:[],avoided_foods:[] })
test('준비 조건을 저장하지 않은 시작만 20분을 사용하며 설정은 수정하지 않는다', () => {
  const saved = {}; const result=startingPreparation(saved,'4')
  assert.equal(result.mode,'quick');assert.equal(Object.keys(result.constraints).length,4)
  assert.ok(Object.values(result.constraints).every(value=>value.max_minutes===20 && !value.no_cook && !value.prepared_sides))
  assert.deepEqual(saved,{})
})
test('저장한 무제한과 끼니별 조건은 간편 기본값으로 덮어쓰지 않는다', () => {
  const saved={breakfast:empty(),dinner:{...empty(),max_minutes:45,tools:['pot'],avoided_foods:['생선']}}
  const before=structuredClone(saved),result=startingPreparation(saved,'3')
  assert.equal(result.mode,'saved');assert.deepEqual(result.constraints,saved)
  result.constraints.dinner.tools.push('pan');assert.deepEqual(saved,before)
})
test('간편 방식 변경은 제외 음식·기구·명시한 준비 음식·비활성 끼니를 보존한다', () => {
  const current={lunch:{...empty(),prepared_sides:true,tools:['pan'],avoided_foods:['생선']},snack:{...empty(),max_minutes:7}}
  const before=structuredClone(current),changed=applyPreparation('quick',current,'2')
  assert.equal(changed.lunch.max_minutes,20);assert.deepEqual(changed.lunch.avoided_foods,['생선']);assert.deepEqual(changed.lunch.tools,['pan']);assert.equal(changed.lunch.prepared_sides,true)
  assert.deepEqual(changed.snack,current.snack);assert.deepEqual(current,before)
})
test('조리 없음은 미리 준비된 밥을 임의로 가정하지 않는다', () => {
  const changed=applyPreparation('ready',{},'3')
  assert.ok(Object.values(changed).every(value=>value.no_cook && value.max_minutes===10 && value.prepared_sides===false))
})
test('끼니 수 변경은 기존 입력을 보존하고 새 끼니에만 선택 기준을 추가한다', () => {
  const initial=startingPreparation({},'3').constraints;initial.breakfast.max_minutes=15
  const four=extendPreparation(initial,'4','quick')
  assert.equal(four.breakfast.max_minutes,15);assert.equal(four.snack.max_minutes,20)
  four.snack.avoided_foods=['달걀'];const two=extendPreparation(four,'2','custom');const again=extendPreparation(two,'4','custom')
  assert.deepEqual(again,four)
})
test('시간 제한 해제는 제외 음식과 기구를 풀지 않는다', () => {
  const value={lunch:{...empty(),no_cook:true,max_minutes:10,tools:['pot'],avoided_foods:['두부']}}
  const changed=applyPreparation('unlimited',value,'2')
  assert.equal(changed.lunch.max_minutes,null);assert.equal(changed.lunch.no_cook,false)
  assert.deepEqual(changed.lunch.tools,['pot']);assert.deepEqual(changed.lunch.avoided_foods,['두부'])
})
