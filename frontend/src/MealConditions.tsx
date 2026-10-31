import { useEffect, useRef, useState } from 'react'
import type { MealConstraints } from './plannerTypes'

export function MealConditions({ value, onChange, disabled, label }: { value: MealConstraints; onChange: (value: Partial<MealConstraints>) => void; disabled: boolean; label: string }) {
  const namesKey = JSON.stringify(value.avoided_foods)
  const lastNames = useRef(namesKey)
  const [avoidedText, setAvoidedText] = useState(() => value.avoided_foods.join(', '))
  useEffect(() => {
    if (lastNames.current === namesKey) return
    lastNames.current = namesKey
    setAvoidedText(value.avoided_foods.join(', '))
  }, [namesKey])
  return <div className="meal-condition-fields">
    <label className="plan-check"><input type="checkbox" checked={value.no_cook} disabled={disabled} aria-label={`${label} 조리 없이 먹기`} onChange={e => onChange({ no_cook: e.target.checked })} />조리 없이 먹기<small>완제품·미리 준비한 음식 사용</small></label>
    <label className="plan-check"><input type="checkbox" checked={value.prepared_sides ?? false} disabled={disabled} aria-label={`${label} 준비된 밥·반찬 사용`} onChange={e => onChange({ prepared_sides: e.target.checked })} />준비된 밥·반찬 사용<small>이미 만든 밥·채소 반찬이 있을 때 선택</small></label>
    <label>사용할 기구<select aria-label={`${label} 사용할 기구`} value={value.tools[0] ?? ''} disabled={disabled} onChange={e => onChange({ tools: e.target.value ? [e.target.value] : [] })}><option value="">제한 없음</option><option value="pan">프라이팬</option><option value="pot">냄비</option><option value="rice">밥솥</option><option value="steam">찜기</option><option value="stone">돌솥</option></select></label>
    <label>준비 시간<select aria-label={`${label} 준비 시간`} value={value.max_minutes ?? ''} disabled={disabled} onChange={e => onChange({ max_minutes: e.target.value ? Number(e.target.value) : null })}><option value="">제한 없음</option><option value="10">10분 이내</option><option value="15">15분 이내</option><option value="20">20분 이내</option><option value="30">30분 이내</option><option value="60">60분 이내</option></select></label>
    <label>피할 음식<input aria-label={`${label} 피할 음식`} value={avoidedText} disabled={disabled} placeholder="예: 김치, 소고기" maxLength={200} onChange={e => {
      const text = e.target.value
      const names = text.split(',').map(name => name.trim()).filter(Boolean)
      setAvoidedText(text)
      lastNames.current = JSON.stringify(names)
      onChange({ avoided_foods: names })
    }} onBlur={() => setAvoidedText(value.avoided_foods.join(', '))} /><small>쉼표로 나눠 입력해요.{value.avoided_foods.length > 0 && ` 제외할 음식 ${value.avoided_foods.length}개: ${value.avoided_foods.join(' · ')}`}</small></label>
  </div>
}
