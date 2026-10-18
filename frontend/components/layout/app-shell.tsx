'use client'

import { useQuery } from '@tanstack/react-query'
import { ChevronRight, LogOut, Menu, Search, X } from 'lucide-react'
import Image from 'next/image'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Kbd, SkeletonRows } from '@/components/common/primitives'
import { StatusDot } from '@/components/common/signals'
import { useCurrentRepo } from '@/hooks/use-repos'
import { getHealth, getIncidents } from '@/lib/api'
import { authApi } from '@/lib/auth-client'
import { cn } from '@/lib/utils'
import { CommandPalette } from './command-palette'
import { DemoBanner } from './demo-banner'
import { HEADER_ACTIONS_ID, HEADER_META_ID } from './header-actions'
import { ShortcutsDialog, useShortcuts } from './shortcuts'
import { ALL_PAGES, NAV } from './nav'
import { RepoSwitcher } from './repo-switcher'

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-3 px-1 text-xl font-bold tracking-tight text-white">
      <Image src="/logo-mark.svg" alt="" width={36} height={36} priority className="rounded-md shadow-[0_0_18px_rgba(5,150,105,0.35)] ring-1 ring-white/10" />
      Rhizo
    </Link>
  )
}

function UserCard() {
  const me = useQuery({ queryKey: ['me'], queryFn: authApi.me, staleTime: 5 * 60_000 })
  const [busy, setBusy] = useState(false)
  if (!me.data) return null
  const initials = me.data.email.slice(0, 2).toUpperCase()
  const signOut = async () => {
    setBusy(true)
    await authApi.logout().catch(() => {})
    window.location.assign('/login')
  }
  return (
    <div className="flex items-center gap-3 rounded-md bg-sidebar-card px-3 py-2.5">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-xs font-bold text-white">{initials}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-white">{me.data.email}</span>
      </span>
      <button onClick={signOut} disabled={busy} className="grid size-8 shrink-0 place-items-center rounded-md text-sidebar-muted hover:bg-sidebar-hover hover:text-white" aria-label="Sign out" title="Sign out">
        <LogOut className="size-4" />
      </button>
    </div>
  )
}

const isActive = (path: string, href: string) => path === href || (href !== '/' && path.startsWith(`${href}/`))

const BARE_ROUTES = ['/home', '/login', '/signup']
const ACCOUNT_ROUTES = ['/repos']

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname()
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 30_000 })
  const { current } = useCurrentRepo()
  const incidents = useQuery({ queryKey: ['incidents'], queryFn: getIncidents, enabled: !!current })
  const open = incidents.data?.filter((i) => i.status === 'open').length ?? 0
  const up = health.data?.falkordb === 'up'

  return (
    <div className="flex h-full flex-col bg-sidebar">
      <div className="flex h-20 items-center px-5">
        <Logo />
      </div>
      <nav className="flex-1 space-y-7 overflow-y-auto px-3 py-4 scrollbar-thin" aria-label="Main">
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="mb-2 px-3 text-[11px] font-semibold tracking-[0.14em] text-sidebar-muted uppercase">{g.group}</div>
            <ul className="space-y-1">
              {g.items.map(({ href, label, icon: Icon }) => {
                const active = isActive(path, href)
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      onClick={onNavigate}
                      aria-current={active ? 'page' : undefined}
                      className={cn(
                        'flex h-10 items-center gap-3 rounded-md border-r-2 border-transparent px-3 text-[15px] text-sidebar-foreground transition-colors hover:bg-sidebar-hover hover:text-white',
                        active && 'border-primary bg-primary/10 text-success hover:bg-primary/15 hover:text-success',
                      )}
                    >
                      <Icon className="size-[18px]" strokeWidth={1.8} />
                      {label}
                      {href === '/incidents' && open > 0 && (
                        <span className="ml-auto rounded-full bg-danger px-1.5 font-mono text-[10px] font-semibold text-white">{open}</span>
                      )}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>
      <div className="space-y-2 p-3">
        <Link href="/repos" onClick={onNavigate} className="flex items-center gap-2.5 rounded-md px-3 py-1.5 text-xs hover:bg-sidebar-hover">
          <StatusDot tone={health.isLoading ? 'muted' : up ? 'success' : 'danger'} pulse={!health.isLoading && !up} />
          <span className="font-semibold text-sidebar-foreground">FalkorDB</span>
          <span className="ml-auto text-sidebar-muted">
            {health.isLoading ? 'Checking…' : up ? 'Connected' : 'Unreachable'}
          </span>
        </Link>
        <UserCard />
      </div>
    </div>
  )
}

function useRepoGate(bare: boolean, exempt: boolean): 'show' | 'wait' {
  const router = useRouter()
  const { repos, current } = useCurrentRepo(!bare)
  const noRepos = !exempt && repos !== undefined && repos.length === 0
  useEffect(() => {
    if (noRepos) router.replace('/repos')
  }, [noRepos, router])
  return exempt || current ? 'show' : 'wait'
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const { help, setHelp } = useShortcuts()
  const page = ALL_PAGES.find((p) => isActive(path, p.href))
  const bare = BARE_ROUTES.includes(path)
  const gate = useRepoGate(bare, bare || ACCOUNT_ROUTES.includes(path) || !page)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((o) => !o)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (bare) return <>{children}</>

  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 lg:block">
        <Sidebar />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/40 animate-fade" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 animate-fade">
            <button onClick={() => setMobileOpen(false)} className="absolute top-6 right-3 rounded-md p-1.5 text-sidebar-foreground hover:bg-sidebar-hover" aria-label="Close navigation">
              <X className="size-4" />
            </button>
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-card px-4 sm:px-8">
          <button onClick={() => setMobileOpen(true)} className="-ml-1 rounded-md p-1.5 text-muted-foreground hover:bg-muted lg:hidden" aria-label="Open navigation">
            <Menu className="size-5" />
          </button>
          <div className="flex min-w-0 items-center gap-4">
            <span className="truncate text-base font-semibold">{page?.title ?? page?.label ?? 'Rhizo'}</span>
            <div id={HEADER_META_ID} className="hidden items-center gap-2 border-l pl-4 text-xs empty:hidden md:flex" />
            {page?.crumb && (
              <span className="hidden items-center gap-1.5 border-l pl-4 text-xs text-subtle-foreground md:flex">
                Rhizo <ChevronRight className="size-3" /> <span className="font-medium text-foreground">{page.crumb}</span>
              </span>
            )}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <RepoSwitcher />
            <button
              onClick={() => setPaletteOpen(true)}
              className="flex h-9 items-center gap-2 rounded-md border bg-background px-2.5 text-sm text-muted-foreground hover:bg-muted xl:w-56"
              aria-label="Search and jump (Ctrl+K)"
            >
              <Search className="size-4" />
              <span className="hidden truncate xl:inline">Search or ask…</span>
              <Kbd className="ml-auto hidden xl:inline-flex">⌘K</Kbd>
            </button>
            <button onClick={() => setHelp(true)} className="hidden size-9 place-items-center rounded-md font-mono text-sm text-muted-foreground hover:bg-muted hover:text-foreground sm:grid" aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">?</button>
            <div id={HEADER_ACTIONS_ID} className="flex items-center gap-2 empty:hidden sm:border-l sm:pl-3" />
          </div>
        </header>
        <DemoBanner />
        <main className="flex-1">{gate === 'show' ? children : <SkeletonRows rows={6} className="mx-auto max-w-4xl p-8" />}</main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      {help && <ShortcutsDialog onClose={() => setHelp(false)} />}
    </div>
  )
}
