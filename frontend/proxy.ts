import { NextResponse, type NextRequest } from 'next/server'
import { SESSION_COOKIE, sessionUser } from '@/lib/server/session'

const PUBLIC = ['/home', '/login', '/signup']
const AUTH_PAGES = ['/login', '/signup']

export function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl
  const signedIn = !!sessionUser(req.cookies.get(SESSION_COOKIE)?.value)

  if (AUTH_PAGES.includes(pathname)) return signedIn ? NextResponse.redirect(new URL('/', req.url)) : NextResponse.next()
  if (signedIn || PUBLIC.includes(pathname)) return NextResponse.next()
  if (pathname === '/') return NextResponse.redirect(new URL('/home', req.url))

  const login = new URL('/login', req.url)
  login.searchParams.set('next', pathname + search)
  return NextResponse.redirect(login)
}

export const config = {
  matcher: ['/((?!api/|_next/|favicon\\.ico|.*\\.(?:png|jpg|jpeg|svg|ico|webp|txt|xml)$).*)'],
}
