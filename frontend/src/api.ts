export async function api<T>(path: string, options: RequestInit = {}, external?: AbortSignal): Promise<T> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  external?.addEventListener('abort', abort, { once: true })
  if (external?.aborted) controller.abort()
  const timeout = window.setTimeout(abort, 25000)
  try {
    const response = await fetch(`/api${path}`, {
      ...options, credentials: 'same-origin', signal: controller.signal,
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    })
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      const detail = typeof body?.detail === 'string' ? body.detail : response.status === 422 ? '입력한 값과 단위를 확인해 주세요.' : '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.'
      throw new Error(detail)
    }
    return response.status === 204 ? undefined as T : await response.json() as T
  } catch (error) {
    if (controller.signal.aborted && !external?.aborted) throw new Error('응답이 지연되고 있어요. 다시 시도해 주세요.')
    if (error instanceof TypeError) throw new Error('서버에 연결하지 못했어요. 연결을 확인하고 다시 시도해 주세요.')
    throw error
  } finally {
    window.clearTimeout(timeout)
    external?.removeEventListener('abort', abort)
  }
}

export const post = <T>(path: string, data: unknown, signal?: AbortSignal) => api<T>(path, { method: 'POST', body: JSON.stringify(data) }, signal)
export const message = (error: unknown) => error instanceof Error ? error.message : '처리하지 못했어요. 다시 시도해 주세요.'
