import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import catalog from '../src/foodArtworkCatalog.json' with { type: 'json' }
import { getFoodArtwork } from '../src/foodArtworkLookup.ts'

const source = JSON.parse(readFileSync(new URL('../../backend/app/data/planner-menus.json', import.meta.url), 'utf8')) as { version: string; menus: { menu_id: string; name: string }[] }
const menu = (name: string) => {
  const item = source.menus.find(value => value.name === name)
  assert.ok(item, name)
  return item
}

test('등록 메뉴마다 연결 또는 기본 표시를 명시한다', () => {
  assert.equal(catalog.catalogVersion, source.version)
  assert.deepEqual(Object.keys(catalog.menus).sort(), source.menus.map(item => item.menu_id).sort())
  assert.equal(Object.keys(catalog.artworks).length, 32)
  assert.equal(source.menus.filter(item => getFoodArtwork(item)).length, 102)
})

test('덮밥·김밥·생선·달걀은 다른 음식의 그림을 받지 않는다', () => {
  for (const [name, key] of [['불고기덮밥', 'beef-rice'], ['김밥', 'gimbap'], ['갈치구이 · 기름', 'grilled-fish'], ['달걀말이 · 채소', 'rolled-egg'], ['소고기미역국', 'seaweed-soup']]) {
    assert.equal(getFoodArtwork(menu(name))?.key, key, name)
  }
})

test('후속 메뉴에 이름 일부가 닮은 그림을 붙이지 않는다', () => {
  for (const name of ['김치볶음밥', '팥죽', '흑임자죽', '자장면', '짬뽕', '연어구이', '달걀프라이']) {
    assert.equal(getFoodArtwork(menu(name)), null, name)
    assert.equal(getFoodArtwork({ menu_id: null, name }), null, name)
  }
})

test('직접 입력은 확인된 전체 이름만 연결한다', () => {
  assert.equal(getFoodArtwork({ menu_id: null, name: '  달걀말이·채소  ' })?.key, 'rolled-egg')
  for (const name of ['점심', '닭', '엄마표 비빔밥', '국수', '비빔밥 샌드위치', '__proto__']) {
    assert.equal(getFoodArtwork({ menu_id: null, name }), null)
  }
})

test('알 수 없거나 이름과 어긋나는 메뉴 ID는 기본 표시한다', () => {
  assert.equal(getFoodArtwork({ menu_id: 'unknown-menu', name: '쌀밥' }), null)
  assert.equal(getFoodArtwork({ ...menu('쌀밥'), name: '불고기덮밥' }), null)
  assert.equal(getFoodArtwork({ menu_id: '__proto__', name: '쌀밥' }), null)
})

test('공용 그림도 조리 형태를 구분한다', () => {
  assert.notEqual(getFoodArtwork(menu('고등어구이 · 석쇠'))?.key, getFoodArtwork(menu('고등어조림'))?.key)
  assert.notEqual(getFoodArtwork(menu('국수 · 잔치국수'))?.key, getFoodArtwork(menu('국수 · 비빔국수'))?.key)
  assert.notEqual(getFoodArtwork(menu('된장찌개'))?.key, getFoodArtwork(menu('시금치된장국'))?.key)
})

test('연결된 그림 파일이 모두 존재한다', () => {
  for (const artwork of Object.values(catalog.artworks)) {
    const path = fileURLToPath(new URL('../public' + artwork.src, import.meta.url))
    assert.ok(existsSync(path), artwork.src)
  }
})
