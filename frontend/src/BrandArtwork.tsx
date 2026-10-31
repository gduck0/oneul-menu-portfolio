export function BrandMark() {
  return <svg className="brand-mark" viewBox="0 0 48 48" fill="none" aria-hidden="true"><path d="M7 24c1 11 7 17 17 17s16-6 17-17" fill="#f0cbb8" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" /><ellipse cx="24" cy="24" rx="17" ry="6" fill="#f7f5ee" stroke="currentColor" strokeWidth="2.2" /><path d="M18 39v4h12v-4M18 15c-3-4 3-6 1-10m9 10c-3-4 3-6 1-10" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
}

export function Icon({ name }: { name: 'refresh' | 'lock' | 'check' | 'arrow' | 'clock' | 'plus' | 'close' }) {
  const paths = { refresh: 'M20 7v5h-5M4 17v-5h5M6.1 7a7 7 0 0 1 11.5-1.5L20 8M4 16l2.4 2.5A7 7 0 0 0 18 17', lock: 'M7 10V7a5 5 0 0 1 10 0v3M6 10h12v11H6zM12 14v3', check: 'm5 12 4 4L19 6', arrow: 'M4 12h15m-5-5 5 5-5 5', clock: 'M12 5v7l4 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0', plus: 'M12 4v16M4 12h16', close: 'm6 6 12 12M6 18 18 6' }
  return <svg viewBox="0 0 24 24" width="18" height="18" focusable="false" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}

type ArtworkKind = 'bowl' | 'sandwich' | 'journal' | 'preferences'

export function EditorialArtwork({ kind, className = '', priority = false }: { kind: ArtworkKind; className?: string; priority?: boolean }) {
  return <img className={`editorial-art ${className}`} src={`/illustrations/${kind}-v1-800.webp`} srcSet={`/illustrations/${kind}-v1-480.webp 480w, /illustrations/${kind}-v1-800.webp 800w`} sizes={kind === 'bowl' ? '(max-width: 760px) 150px, 400px' : '(max-width: 760px) 100px, 240px'} width="800" height="800" alt="" aria-hidden="true" decoding="async" loading={priority ? 'eager' : 'lazy'} fetchPriority={priority ? 'high' : 'auto'} />
}
