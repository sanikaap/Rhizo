import { NextResponse, type NextRequest } from 'next/server'
import { issueApiToken } from '@/lib/server/api-token'
import { AuthError, login, signup } from '@/lib/server/auth'
import { endSession, SESSION_COOKIE, SESSION_TTL_MS, sessionCookie, sessionUser } from '@/lib/server/session'

export const dynamic = 'force-dynamic'

const ok = (data: unknown) => NextResponse.json({ data }, { headers: { 'Cache-Control': 'no-store' } })
const fail = (status: number, code: string, message: string, retryAfter?: number) =>
  NextResponse.json(
    { error: { code, message, ...(retryAfter ? { retryAfter } : {}) } },
    { status, headers: retryAfter ? { 'Retry-After': String(retryAfter) } : undefined },
  )

const clientIp = (req: NextRequest) =>
  req.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || req.headers.get('x-real-ip') || 'unknown'

const withSession = (data: unknown, sessionToken: string) => {
  const res = ok(data)
  res.cookies.set(SESSION_COOKIE, sessionToken, { ...sessionCookie, maxAge: SESSION_TTL_MS / 1000 })
  return res
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ action: string }> }) {
  const { action } = await params
  const user = sessionUser(req.cookies.get(SESSION_COOKIE)?.value)
  if (action !== 'me' && action !== 'token') return fail(404, 'NOT_FOUND', 'Not found')
  if (!user) return fail(401, 'UNAUTHENTICATED', 'Not signed in')
  if (action === 'me') return ok(user)
  try {
    return ok(await issueApiToken(user.id))
  } catch (e) {
    console.error('[auth] cannot issue API token:', e instanceof Error ? e.message : e)
    return fail(500, 'INTERNAL', 'Sign-in is not configured on the server.')
  }
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ action: string }> }) {
  const { action } = await params
  if (!req.headers.get('content-type')?.includes('application/json')) return fail(415, 'UNSUPPORTED_MEDIA_TYPE', 'Expected JSON')
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>

  try {
    switch (action) {
      case 'signup': {
        const { user, sessionToken } = await signup(body, clientIp(req))
        return withSession({ user }, sessionToken)
      }
      case 'login': {
        const { user, sessionToken } = await login(body, clientIp(req))
        return withSession({ user }, sessionToken)
      }
      case 'logout': {
        endSession(req.cookies.get(SESSION_COOKIE)?.value)
        const res = ok({ ok: true })
        res.cookies.set(SESSION_COOKIE, '', { ...sessionCookie, maxAge: 0 })
        return res
      }
      default:
        return fail(404, 'NOT_FOUND', 'Not found')
    }
  } catch (e) {
    if (e instanceof AuthError) return fail(e.status, e.code, e.message, e.retryAfter)
    console.error('[auth]', action, e instanceof Error ? e.message : e)
    return fail(500, 'INTERNAL', 'Something went wrong. Try again.')
  }
}
