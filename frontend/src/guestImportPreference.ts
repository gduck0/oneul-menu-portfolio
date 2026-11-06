export type PreferenceStorage = Pick<Storage, 'getItem' | 'setItem'>

export const guestImportPreferenceKey = (accountId: string) => `oneul.guest-import.deferred.v1:${encodeURIComponent(accountId)}`

export function readGuestImportDeferred(accountId: string, storage: () => PreferenceStorage = () => localStorage): boolean {
  try { return storage().getItem(guestImportPreferenceKey(accountId)) === 'later' }
  catch { return false }
}

export function deferGuestImport(accountId: string, storage: () => PreferenceStorage = () => localStorage): boolean {
  try { storage().setItem(guestImportPreferenceKey(accountId), 'later'); return true }
  catch { return false }
}
