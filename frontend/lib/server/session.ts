import { createHash, randomBytes } from 'node:crypto'
import { db } from './db'

export const SESSION_COOKIE = 'rhizo_session'
export const SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000

export interface PublicUser { id: string; email: string }

const sha256 = (s: string) => createHash('sha256').update(s).digest('hex')
export const randomId = (bytes = 12) => randomBytes(bytes).toString('base64url')

export function createSession(userId: string): string {
  const token = randomBytes(32).toString('base64url')
  const now = Date.now()
  db().prepare('DELETE FROM sessions WHERE expires_at < ?').run(now)
  db().prepare('INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)').run(sha256(token), userId, now + SESSION_TTL_MS)
  return token
}

export function sessionUser(sessionToken: string | undefined): PublicUser | null {
  if (!sessionToken) return null
  const row = db()
    .prepare('SELECT u.id, u.email, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?')
    .get(sha256(sessionToken)) as (PublicUser & { expires_at: number }) | undefined
  if (!row || row.expires_at < Date.now()) return null
  return { id: row.id, email: row.email }
}

export function endSession(sessionToken: string | undefined) {
  if (sessionToken) db().prepare('DELETE FROM sessions WHERE token_hash = ?').run(sha256(sessionToken))
}

export const sessionCookie = {
  httpOnly: true,
  sameSite: 'lax' as const,
  secure: process.env.NODE_ENV === 'production',
  path: '/',
}
