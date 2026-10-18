'use client'

import { X } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Kbd } from '@/components/common/primitives'

export const GOTO: Record<string, { href: string; label: string }> = {
  o: { href: '/', label: 'Overview' },
  a: { href: '/investigator', label: 'Investigator (ask)' },
  g: { href: '/graph', label: 'Graph' },
  c: { href: '/change-check', label: 'Change Check' },
  b: { href: '/benchmark', label: 'Benchmark' },
  i: { href: '/incidents', label: 'Incidents' },
  r: { href: '/repos', label: 'Repositories' },
}

const typing = (t: EventTarget | null) => !!(t as HTMLElement | null)?.closest?.('input, textarea, select, [contenteditable]')

export function useShortcuts() {
  const router = useRouter()
  const [help, setHelp] = useState(false)
  useEffect(() => {
    let pendingG = 0
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e.target)) return
      if (e.key === '?') { e.preventDefault(); setHelp((h) => !h); return }
      if (e.key === 'Escape') setHelp(false)
      if (pendingG && Date.now() - pendingG < 1200 && GOTO[e.key]) {
        e.preventDefault()
        pendingG = 0
        setHelp(false)
        router.push(GOTO[e.key].href)
        return
      }
      pendingG = e.key === 'g' ? Date.now() : 0
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [router])
  return { help, setHelp }
}

export function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  const rows: [React.ReactNode, string][] = [
    [<><Kbd>⌘</Kbd><Kbd>K</Kbd></>, 'Search, jump or ask'],
    [<Kbd key="slash">/</Kbd>, 'Focus the question box (Investigator)'],
    [<Kbd key="q">?</Kbd>, 'Toggle this help'],
    ...Object.entries(GOTO).map(([k, v]) => [<><Kbd>g</Kbd><Kbd>{k}</Kbd></>, `Go to ${v.label}`] as [React.ReactNode, string]),
  ]
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="kbd-title">
      <div className="absolute inset-0 bg-black/40 animate-fade" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-xl border bg-popover shadow-2xl animate-rise">
        <header className="flex items-center justify-between border-b px-4 py-3">
          <h2 id="kbd-title" className="text-sm font-semibold">Keyboard shortcuts</h2>
          <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted" aria-label="Close"><X className="size-4" /></button>
        </header>
        <dl className="divide-y px-4">
          {rows.map(([keys, label], i) => (
            <div key={i} className="flex items-center justify-between py-2 text-sm">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="flex gap-1">{keys}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}
