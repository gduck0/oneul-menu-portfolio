import type { Nutrition, Nutrients } from './types'

export const displayName = (name: string) => name.replaceAll('_', ' · ')
export const number = (value: string | null) => value === null ? '자료 없음' : new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 }).format(Number(value))
export const categoryName: Record<string, string> = { rice: '밥·김밥', noodles: '면 요리', chicken: '닭 요리', meat: '고기 요리', salad: '샐러드', pizza: '피자', burger: '버거', sandwich: '샌드위치', tteokbokki: '떡볶이' }

export function NutrientGrid({ nutrients }: { nutrients: Nutrients }) {
  return <dl className="nutrients">{([
    ['energy_kcal', '열량', 'kcal'], ['protein_g', '단백질', 'g'], ['fat_g', '지방', 'g'], ['carbohydrate_g', '탄수화물', 'g'],
  ] as const).map(([key, label, unit]) => <div key={key}><dt>{label}</dt><dd>{number(nutrients[key])}{nutrients[key] !== null && <small>{unit}</small>}</dd></div>)}</dl>
}

function sourceUrl(value: string) {
  try { const url = new URL(value); if (url.protocol === 'https:' && ['data.go.kr', 'www.data.go.kr'].includes(url.hostname)) return url.href } catch { }
  return 'https://www.data.go.kr/data/15100064/standard.do'
}

export function FoodCard({ nutrition, reason, label, difference, children }: {
  nutrition: Nutrition; reason?: string; label?: string; difference?: { energy: string; protein: string; carbohydrate?: string | null }; children?: React.ReactNode
}) {
  const food = nutrition.food
  return <article className={`food-card ${label === '먹고 싶었던 음식' ? 'original-card' : ''}`}>
    <div className="card-top"><span className="tag">{label ?? categoryName[food.category ?? ''] ?? '음식'}</span><span className="amount-tag">{number(nutrition.portion.amount)}{nutrition.portion.unit}</span></div>
    <h3>{displayName(food.name)}</h3><p className="company">{food.company ?? '일반 음식 자료'}</p>
    {reason && <p className="reason">{reason}</p>}
    <NutrientGrid nutrients={nutrition.nutrients} />
    {difference && <div className="differences"><span>열량 {Number(difference.energy) > 0 ? '+' : ''}{number(difference.energy)}kcal</span><span>단백질 {Number(difference.protein) > 0 ? '+' : ''}{number(difference.protein)}g</span>{difference.carbohydrate !== undefined && <span className={difference.carbohydrate === null ? 'unknown-difference' : ''}>탄수화물 {difference.carbohydrate === null ? '비교 자료 없음' : difference.carbohydrate}</span>}<small>원래 음식 대비 차이 · 증가와 감소를 함께 확인하세요</small></div>}
    {nutrition.missing_nutrients.length > 0 && <p className="missing-note">자료 없는 성분은 차이를 비교하지 않았어요.</p>}
    <details className="source"><summary>기준량·출처 확인</summary><p>원본 영양 기준: {number(food.basis_amount)}{food.basis_unit}<br />식품코드: {food.source.food_code}<br />출처: {food.source.provider}<br />자료 기준일: {food.source.reference_date}<br />원본 식품중량: {food.source_weight ?? '자료 없음'}</p><p>원본 식품중량은 1인분을 뜻하지 않아요.</p><a href={sourceUrl(food.source.url)} target="_blank" rel="noreferrer noopener">공식 자료 보기 ↗</a></details>
    {children}
  </article>
}
