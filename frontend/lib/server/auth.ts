import { db } from './db'
import { hashPassword, needsRehash, verifyPassword } from './password'
import { blocked, hit, reset } from './rate-limit'
import { createSession, type PublicUser, randomId } from './session'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const MIN_PASSWORD = 8
const MAX_PASSWORD = 200
const WINDOW_MS = 15 * 60 * 1000
const SIGNUPS_PER_IP = 5
const LOGINS_PER_IP = 20
const FAILURES_PER_EMAIL = 5
const BAD_CREDENTIALS = 'Incorrect email or password.'

export class AuthError extends Error {
  constructor(public status: number, public code: string, message: string, public retryAfter?: number) {
    super(message)
  }
}

interface UserRow { id: string; email: string; password_hash: string }

const normEmail = (e: unknown) => (typeof e === 'string' ? e.trim().toLowerCase() : '')
const userByEmail = (email: string) =>
  db().prepare('SELECT id, email, password_hash FROM users WHERE email = ?').get(email) as UserRow | undefined

const tooMany = (wait: number) => new AuthError(429, 'TOO_MANY_ATTEMPTS', 'Too many attempts. Try again in a few minutes.', wait)

function limit(key: string, max: number) {
  const wait = hit(key, max, WINDOW_MS)
  if (wait !== null) throw tooMany(wait)
}

function requirePassword(pw: unknown): asserts pw is string {
  if (typeof pw !== 'string' || pw.length < MIN_PASSWORD) throw new AuthError(400, 'WEAK_PASSWORD', `Password must be at least ${MIN_PASSWORD} characters.`)
  if (pw.length > MAX_PASSWORD) throw new AuthError(400, 'WEAK_PASSWORD', 'Password is too long.')
}

export interface SignedIn { user: PublicUser; sessionToken: string }

export async function signup(input: { email?: unknown; password?: unknown; confirmPassword?: unknown }, ip: string): Promise<SignedIn> {
  limit(`signup:${ip}`, SIGNUPS_PER_IP)
  const email = normEmail(input.email)
  if (!EMAIL_RE.test(email) || email.length > 254) throw new AuthError(400, 'INVALID_EMAIL', 'Enter a valid email address.')
  requirePassword(input.password)
  if (input.confirmPassword !== input.password) throw new AuthError(400, 'PASSWORD_MISMATCH', 'Passwords do not match.')
  if (userByEmail(email)) throw new AuthError(409, 'EMAIL_TAKEN', 'An account with this email already exists. Sign in instead.')

  const user = { id: randomId(), email, password_hash: await hashPassword(input.password) }
  db().prepare('INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)').run(user.id, user.email, user.password_hash, Date.now())
  return { user: { id: user.id, email }, sessionToken: createSession(user.id) }
}

let dummyHash: Promise<string> | null = null

export async function login(input: { email?: unknown; password?: unknown }, ip: string): Promise<SignedIn> {
  limit(`login:${ip}`, LOGINS_PER_IP)
  const email = normEmail(input.email)
  if (!email || typeof input.password !== 'string' || !input.password) throw new AuthError(400, 'MISSING_FIELDS', 'Enter your email and password.')
  const failureKey = `login-fail:${email}`
  const lockedFor = blocked(failureKey, FAILURES_PER_EMAIL)
  if (lockedFor !== null) throw tooMany(lockedFor)
  const user = userByEmail(email)
  const ok = user
    ? await verifyPassword(input.password, user.password_hash)
    : (await verifyPassword(input.password, await (dummyHash ??= hashPassword('not-a-real-password'))), false)
  if (!user || !ok) {
    hit(failureKey, FAILURES_PER_EMAIL, WINDOW_MS)
    throw new AuthError(401, 'INVALID_CREDENTIALS', BAD_CREDENTIALS)
  }
  reset(failureKey)
  if (needsRehash(user.password_hash)) {
    db().prepare('UPDATE users SET password_hash = ? WHERE id = ?').run(await hashPassword(input.password), user.id)
  }
  return { user: { id: user.id, email: user.email }, sessionToken: createSession(user.id) }
}
