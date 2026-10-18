import { SignJWT } from 'jose'

export const API_TOKEN_TTL_S = 5 * 60
const ISSUER = 'rhizo-web'
const AUDIENCE = 'rhizo-api'

function secret(): Uint8Array {
  const value = process.env.AUTH_SECRET ?? ''
  if (value.length < 32) throw new Error('AUTH_SECRET must be set to at least 32 characters')
  return new TextEncoder().encode(value)
}

export async function issueApiToken(userId: string): Promise<{ token: string; expiresAt: number }> {
  const now = Math.floor(Date.now() / 1000)
  const token = await new SignJWT({})
    .setProtectedHeader({ alg: 'HS256', typ: 'JWT' })
    .setSubject(userId)
    .setIssuer(ISSUER)
    .setAudience(AUDIENCE)
    .setIssuedAt(now)
    .setExpirationTime(now + API_TOKEN_TTL_S)
    .sign(secret())
  return { token, expiresAt: (now + API_TOKEN_TTL_S) * 1000 }
}
