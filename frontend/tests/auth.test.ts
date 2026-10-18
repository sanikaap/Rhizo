import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, beforeEach, describe, test } from 'node:test'
import { jwtVerify } from 'jose'
import { NextRequest } from 'next/server'
import * as route from '../app/api/auth/[action]/route'
import { db } from '../lib/server/db'
import { SESSION_COOKIE } from '../lib/server/session'
import { proxy } from '../proxy'

const dir = mkdtempSync(join(tmpdir(), 'rhizo-auth-'))
process.env.AUTH_DB_PATH = join(dir, 'auth.db')
process.env.AUTH_SECRET = 'test-secret-' + 'x'.repeat(32)

const BASE = 'http://localhost:5173'
let ip = 0

function request(action: string, body?: unknown, cookie?: string, clientIp = `10.0.0.${++ip}`) {
  return new NextRequest(`${BASE}/api/auth/${action}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {
      ...(body === undefined ? {} : { 'content-type': 'application/json' }),
      ...(cookie ? { cookie: `${SESSION_COOKIE}=${cookie}` } : {}),
      'x-forwarded-for': clientIp,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

const params = (action: string) => ({ params: Promise.resolve({ action }) })
const post = (action: string, body: unknown, clientIp?: string) => route.POST(request(action, body, undefined, clientIp), params(action))
const get = (action: string, cookie?: string) => route.GET(request(action, undefined, cookie), params(action))
const sessionOf = (res: Response) => /rhizo_session=([^;]*)/.exec(res.headers.get('set-cookie') ?? '')?.[1] ?? ''
const signupBody = (email: string, password = 'correct horse battery') => ({ email, password, confirmPassword: password })

beforeEach(() => db().exec('DELETE FROM sessions; DELETE FROM users;'))
after(() => rmSync(dir, { recursive: true, force: true }))

describe('signup', () => {
  test('creates the account, signs in with an httpOnly lax cookie, and stores only an argon2id hash', async () => {
    const res = await post('signup', signupBody('Ada@Example.COM'))
    assert.equal(res.status, 200)
    const body = await res.json()
    assert.equal(body.data.user.email, 'ada@example.com')
    const cookie = res.headers.get('set-cookie') ?? ''
    assert.match(cookie, /HttpOnly/i)
    assert.match(cookie, /SameSite=lax/i)
    const row = db().prepare('SELECT password_hash FROM users').get() as { password_hash: string }
    assert.match(row.password_hash, /^\$argon2id\$/)
    assert.ok(!row.password_hash.includes('correct horse'))
  })

  test('rejects short passwords, mismatched confirmation, bad emails and duplicates', async () => {
    assert.equal((await post('signup', signupBody('a@b.co', 'short'))).status, 400)
    assert.equal((await post('signup', { email: 'a@b.co', password: 'longenough1', confirmPassword: 'different1' })).status, 400)
    assert.equal((await post('signup', signupBody('not-an-email'))).status, 400)
    assert.equal((await post('signup', signupBody('a@b.co'))).status, 200)
    assert.equal((await post('signup', signupBody('A@B.co'))).status, 409)
  })

  test('is rate limited per client', async () => {
    const statuses = []
    for (let i = 0; i < 7; i++) statuses.push((await post('signup', signupBody(`u${i}@b.co`), '10.9.9.9')).status)
    assert.deepEqual(statuses.slice(0, 5), [200, 200, 200, 200, 200])
    assert.equal(statuses[5], 429)
  })
})

describe('login', () => {
  test('signs in with the right password, case-insensitively by email', async () => {
    await post('signup', signupBody('grace@example.com'))
    const res = await post('login', { email: ' GRACE@example.com ', password: 'correct horse battery' })
    assert.equal(res.status, 200)
    assert.ok(sessionOf(res))
  })

  test('wrong password and unknown email get the same generic 401', async () => {
    await post('signup', signupBody('grace@example.com'))
    const wrong = await post('login', { email: 'grace@example.com', password: 'wrong password!' })
    const unknown = await post('login', { email: 'nobody@example.com', password: 'whatever123' })
    assert.equal(wrong.status, 401)
    assert.equal(unknown.status, 401)
    assert.deepEqual(await wrong.json(), await unknown.json())
  })

  test('locks an email after repeated failures, even for the right password', async () => {
    await post('signup', signupBody('lock@example.com'))
    for (let i = 0; i < 5; i++) await post('login', { email: 'lock@example.com', password: 'nope-nope' })
    const res = await post('login', { email: 'lock@example.com', password: 'correct horse battery' })
    assert.equal(res.status, 429)
  })
})

describe('session, api token and logout', () => {
  test('issues a 5-minute HS256 token for the backend, then logout ends the session', async () => {
    const session = sessionOf(await post('signup', signupBody('lin@example.com')))
    const me = await (await get('me', session)).json()
    const tokenRes = await get('token', session)
    assert.equal(tokenRes.status, 200)
    const { token, expiresAt } = (await tokenRes.json()).data
    const { payload, protectedHeader } = await jwtVerify(token, new TextEncoder().encode(process.env.AUTH_SECRET), {
      issuer: 'rhizo-web',
      audience: 'rhizo-api',
    })
    assert.equal(protectedHeader.alg, 'HS256')
    assert.equal(payload.sub, me.data.id)
    assert.ok(expiresAt - Date.now() <= 5 * 60 * 1000 && expiresAt - Date.now() > 4 * 60 * 1000)

    const out = await route.POST(request('logout', {}, session), params('logout'))
    assert.match(out.headers.get('set-cookie') ?? '', /Max-Age=0/i)
    assert.equal((await get('me', session)).status, 401)
    assert.equal((await get('token', session)).status, 401)
  })

  test('no session means no token', async () => {
    assert.equal((await get('token')).status, 401)
  })
})

describe('route guard (proxy.ts)', () => {
  const page = (path: string, cookie?: string) =>
    proxy(new NextRequest(`${BASE}${path}`, { headers: cookie ? { cookie: `${SESSION_COOKIE}=${cookie}` } : {} }))
  const location = (res: Response) => res.headers.get('location')

  test('signed-out visitors go to /login with a return path; / goes to the landing page; /home stays public', () => {
    assert.equal(location(page('/graph?center=frontend')), `${BASE}/login?next=%2Fgraph%3Fcenter%3Dfrontend`)
    assert.equal(location(page('/')), `${BASE}/home`)
    assert.equal(location(page('/home')), null)
    assert.equal(location(page('/login')), null)
  })

  test('signed-in users skip /login and /signup and land in the app', async () => {
    const session = sessionOf(await post('signup', signupBody('kay@example.com')))
    assert.equal(location(page('/login', session)), `${BASE}/`)
    assert.equal(location(page('/signup', session)), `${BASE}/`)
    assert.equal(location(page('/', session)), null)
    assert.equal(location(page('/graph', session)), null)
  })
})
