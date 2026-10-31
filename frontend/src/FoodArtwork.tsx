import { useState } from 'react'
import { BrandMark } from './BrandArtwork'
import { getFoodArtwork } from './foodArtworkLookup'
import type { PlanItem } from './plannerTypes'

export function FoodArtwork({ item }: { item: PlanItem }) {
  const artwork = getFoodArtwork(item)
  const [failedSource, setFailedSource] = useState<string | null>(null)
  if (!artwork || failedSource === artwork.src) return <span className="food-artwork food-art-table" data-artwork-key="table" aria-hidden="true"><BrandMark /></span>
  return <img className={`food-artwork food-art-${artwork.key}`} data-artwork-key={artwork.key} src={artwork.src} width="160" height="160" alt="" aria-hidden="true" loading="lazy" decoding="async" onError={() => setFailedSource(artwork.src)} />
}
