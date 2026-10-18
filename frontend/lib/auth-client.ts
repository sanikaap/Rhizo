export interface AuthUser { id: string; email: string }
export interface ApiToken { token: string; expiresAt: number }

export class AuthApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public retryAfter?: number) {
    super(message)
  }
}

async function call<T>(action: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api/auth/${action}`, body === undefined
      ? { cache: 'no-store' }
      : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  } catch {
    throw new AuthApiError(0, 'Cannot reach the server. Check your connection.', 'NETWORK')
  }
  const json = await res.json().catch(() => null)
  if (!res.ok) throw new AuthApiError(res.status, json?.error?.message ?? res.statusText, json?.error?.code, json?.error?.retryAfter)
  return json.data as T
}

export const authApi = {
  me: () => call<AuthUser>('me'),
  token: () => call<ApiToken>('token'),
  signup: (b: { email: string; password: string; confirmPassword: string }) => call<{ user: AuthUser }>('signup', b),
  login: (b: { email: string; password: string }) => call<{ user: AuthUser }>('login', b),
  logout: () => call<{ ok: true }>('logout', {}),
}

export function safeNext(next: string | null) {
  return next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\') ? next : '/'
}
