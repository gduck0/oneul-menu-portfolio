export const kcal = (value: string | number | null | undefined) => value == null ? '자료 없음' : Math.round(Number(value)).toLocaleString('ko-KR')
export const grams = (value: string | null | undefined) => value == null ? '자료 없음' : Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 1 })
export const mealLabels = { breakfast: '아침', lunch: '점심', dinner: '저녁', snack: '간식' }
export const roleLabels: Record<string, string> = { main: '한 그릇', staple: '밥', protein: '주찬', vegetable: '채소 반찬', soup: '국·찌개', side: '곁들임' }
