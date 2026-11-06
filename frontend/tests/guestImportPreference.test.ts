import assert from 'node:assert/strict'
import test from 'node:test'
import { deferGuestImport, guestImportPreferenceKey, readGuestImportDeferred } from '../src/guestImportPreference.ts'

function browserStorage() {
  const values = new Map<string, string>([['oneul.review.browser.v1', 'existing records']])
  return { values, getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value) } }
}

test('같은 계정은 다시 읽어도 보류하며 다른 계정과 브라우저에는 적용하지 않는다', () => {
  const first = browserStorage(), second = browserStorage()
  assert.equal(readGuestImportDeferred('account-a', () => first), false)
  assert.equal(deferGuestImport('account-a', () => first), true)
  assert.equal(readGuestImportDeferred('account-a', () => first), true)
  assert.equal(readGuestImportDeferred('account-b', () => first), false)
  assert.equal(readGuestImportDeferred('account-a', () => second), false)
  assert.equal(first.values.get('oneul.review.browser.v1'), 'existing records')
  assert.equal(first.values.size, 2)
})

test('알 수 없는 저장값은 보류로 오인하지 않고 다른 데이터도 수정하지 않는다', () => {
  const storage = browserStorage()
  storage.setItem(guestImportPreferenceKey('a'), '{broken')
  const before = [...storage.values]
  assert.equal(readGuestImportDeferred('a', () => storage), false)
  assert.deepEqual([...storage.values], before)
  assert.equal(deferGuestImport('a', () => storage), true)
  assert.equal(readGuestImportDeferred('a', () => storage), true)
})

test('브라우저 저장 접근이 차단되거나 용량이 부족하면 저장 성공을 알리지 않는다', () => {
  const blocked = () => { throw new Error('storage denied') }
  assert.equal(readGuestImportDeferred('a', blocked), false)
  assert.equal(deferGuestImport('a', blocked), false)
  const full = { getItem: () => null, setItem: () => { throw new Error('quota exceeded') } }
  assert.equal(deferGuestImport('a', () => full), false)
})
