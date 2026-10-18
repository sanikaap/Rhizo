'use client'

import { useQuery } from '@tanstack/react-query'
import { Box, CornerDownLeft, Siren, Sparkles } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Kbd } from '@/components/common/primitives'
import { getIncidents, getServices } from '@/lib/api'
import { useCurrentRepoId } from '@/lib/repo-store'
import { cn } from '@/lib/utils'
import { ALL_PAGES } from './nav'

type Item = { id: string; group: string; label: string; hint?: string; icon: React.ElementType; href: string }

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter()
  const [q, setQ] = useState('')
  const [idx, setIdx] = useState(0)
  const listRef = useRef<HTMLUListElement>(null)
  const repoId = useCurrentRepoId()
  const withRepo = open && !!repoId
  const services = useQuery({ queryKey: ['services'], queryFn: getServices, enabled: withRepo })
  const incidents = useQuery({ queryKey: ['incidents'], queryFn: getIncidents, enabled: withRepo })

  useEffect(() => {
    if (open) { setQ(''); setIdx(0) }
  }, [open])

  const items = useMemo<Item[]>(() => {
    const s = q.trim().toLowerCase()
    const match = (...xs: (string | undefined)[]) => !s || xs.some((x) => x?.toLowerCase().includes(s))
    const out: Item[] = []
    if (s) out.push({ id: 'ask', group: 'Ask', label: `Ask Rhizo: “${q.trim()}”`, icon: Sparkles, href: `/investigator?q=${encodeURIComponent(q.trim())}` })
    out.push(...ALL_PAGES.filter((p) => match(p.label, p.hint)).map((p) => ({ id: p.href, group: 'Pages', label: p.label, hint: p.hint, icon: p.icon, href: p.href })))
    out.push(
      ...(services.data ?? [])
        .filter((n) => match(n.name, String(n.properties.team)))
        .slice(0, 8)
        .map((n) => ({ id: n.id, group: 'Services', label: n.name, hint: `tier ${n.properties.tier} · ${n.properties.team}`, icon: Box, href: `/graph?focus=${n.name}` })),
    )
    out.push(
      ...(incidents.data ?? [])
        .filter((i) => match(i.id, i.title))
        .slice(0, 5)
        .map((i) => ({ id: i.id, group: 'Incidents', label: `${i.id} ${i.title}`, hint: i.status, icon: Siren, href: `/incidents/${i.id}` })),
    )
    return out
  }, [q, services.data, incidents.data])

  useEffect(() => setIdx(0), [q])
  useEffect(() => {
    listRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [idx])

  if (!open) return null

  const go = (it?: Item) => {
    if (!it) return
    router.push(it.href)
    onClose()
  }

  let lastGroup = ''
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]" role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="absolute inset-0 bg-black/40 animate-fade" onClick={onClose} />
      <div className="relative w-full max-w-xl overflow-hidden rounded-xl border bg-popover shadow-2xl animate-rise">
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onClose()
            else if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, items.length - 1)) }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)) }
            else if (e.key === 'Enter') go(items[idx])
          }}
          placeholder="Jump to a service or page, or ask a question…"
          className="h-12 w-full border-b bg-transparent px-4 text-sm outline-none placeholder:text-muted-foreground"
          role="combobox"
          aria-expanded="true"
          aria-controls="palette-list"
          aria-activedescendant={items[idx] ? `opt-${items[idx].id}` : undefined}
        />
        <ul id="palette-list" ref={listRef} role="listbox" className="max-h-80 overflow-y-auto p-1.5 scrollbar-thin">
          {items.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted-foreground">No matches</li>}
          {items.map((it, i) => {
            const header = it.group !== lastGroup
            lastGroup = it.group
            return (
              <li key={it.id} role="presentation">
                {header && <div className="px-2.5 pt-2 pb-1 text-[11px] font-medium text-subtle-foreground">{it.group}</div>}
                <div
                  id={`opt-${it.id}`}
                  role="option"
                  aria-selected={i === idx}
                  data-active={i === idx}
                  onMouseEnter={() => setIdx(i)}
                  onClick={() => go(it)}
                  className={cn('flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-sm', i === idx && 'bg-muted')}
                >
                  <it.icon className={cn('size-4 shrink-0 text-muted-foreground', it.group === 'Ask' && 'text-primary')} />
                  <span className={cn('truncate', it.group === 'Services' && 'font-mono text-[13px]')}>{it.label}</span>
                  {it.hint && <span className="ml-auto truncate pl-3 text-xs text-muted-foreground">{it.hint}</span>}
                </div>
              </li>
            )
          })}
        </ul>
        <div className="flex items-center gap-3 border-t px-3 py-2 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> navigate</span>
          <span className="flex items-center gap-1"><Kbd><CornerDownLeft className="size-3" /></Kbd> open</span>
          <span className="flex items-center gap-1"><Kbd>esc</Kbd> close</span>
        </div>
      </div>
    </div>
  )
}
