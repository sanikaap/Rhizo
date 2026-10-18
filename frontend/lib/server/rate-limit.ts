const windows = new Map<string, { count: number; resetAt: number }>()

export function hit(key: string, limit: number, windowMs: number): number | null {
  const now = Date.now()
  const w = windows.get(key)
  if (!w || w.resetAt <= now) {
    windows.set(key, { count: 1, resetAt: now + windowMs })
    return null
  }
  w.count += 1
  return w.count > limit ? Math.ceil((w.resetAt - now) / 1000) : null
}

export const reset = (key: string) => windows.delete(key)

export function blocked(key: string, limit: number): number | null {
  const w = windows.get(key)
  return w && w.resetAt > Date.now() && w.count >= limit ? Math.ceil((w.resetAt - Date.now()) / 1000) : null
}
