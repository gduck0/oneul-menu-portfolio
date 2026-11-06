import type { Feedback, FeedbackReason, Rating } from './types'

export const feedbackReasons: Record<FeedbackReason, string> = {
  taste: '맛·메뉴 취향', portion: '양이 맞지 않음', unavailable: '오늘 먹기 어려움',
  purpose: '추천 목적과 맞지 않음', variety: '다른 메뉴를 원함',
}

export function feedbackScope(phase: Feedback['phase'], foodId: string | null, rating: Rating | null, reason: FeedbackReason | '') {
  if (foodId === null) return '직접 입력 음식의 평가로만 남겨요. 등록 메뉴의 취향 점수에는 연결하지 않아요.'
  if (rating === null) return '만족도를 고른 뒤 반영 범위를 확인해 주세요. 저장하기 전에는 추천에 반영되지 않아요.'
  if (reason === 'taste') return rating === 'neutral'
    ? '이 메뉴의 취향을 보통으로 참고해요. 같은 단계의 이전 맛 평가 대신 사용해요.'
    : `다음 추천에서 이 메뉴의 선호도를 ${rating === 'dislike' ? '조금 낮추는' : '조금 높이는'} 데 참고해요. 메뉴를 항상 제외하거나 보장하지는 않아요.`
  if (phase === 'recommendation' && reason === 'unavailable' && rating === 'dislike') return '이 음식 비교에서 다시 추천받을 때만 제외해요. 새로 검색하면 풀리고, 메뉴 취향에는 반영하지 않아요.'
  if (reason === 'portion') return '양에 대한 평가로만 남겨요. 메뉴 취향과 저장한 분량은 바꾸지 않아요.'
  if (reason === 'unavailable') return '오늘의 사정에 대한 평가로만 남겨요. 메뉴 취향이나 저장한 제외 음식은 바꾸지 않아요.'
  if (reason) return '이번 식사의 의견으로만 남겨요. 메뉴 취향이나 저장한 추천 설정은 바꾸지 않아요.'
  return '평가만 기록해요. 이유 없는 평가는 메뉴를 좋아하거나 싫어한다는 뜻으로 사용하지 않아요.'
}
