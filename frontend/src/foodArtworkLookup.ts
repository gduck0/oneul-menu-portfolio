import catalog from './foodArtworkCatalog.json' with { type: 'json' }

type Artwork = { label: string; src: string }
type MenuArtwork = { name: string; artwork: string | null }
type ArtworkItem = { menu_id: string | null; name: string }
const artworks: Record<string, Artwork> = catalog.artworks
const menus: Record<string, MenuArtwork> = catalog.menus

const normalizeName = (name: string) => name.normalize('NFKC').trim().replace(/\s+/g, ' ').replace(/\s*·\s*/g, '·')
const names = new Map<string, Set<string | null>>()
for (const menu of Object.values(menus)) {
  const name = normalizeName(menu.name)
  const matches = names.get(name) ?? new Set<string | null>()
  matches.add(menu.artwork)
  names.set(name, matches)
}

export function getFoodArtwork(item: ArtworkItem): (Artwork & { key: string }) | null {
  let key: string | null | undefined
  if (item.menu_id) {
    if (!Object.hasOwn(menus, item.menu_id)) return null
    const menu = menus[item.menu_id]
    if (normalizeName(menu.name) !== normalizeName(item.name)) return null
    key = menu.artwork
  } else {
    const matches = names.get(normalizeName(item.name))
    if (!matches || matches.size !== 1) return null
    key = [...matches][0]
  }
  if (!key || !Object.hasOwn(artworks, key)) return null
  return { key, ...artworks[key] }
}
