'use client'

import { useQuery } from '@tanstack/react-query'
import { Flame, Sparkles, X } from 'lucide-react'
import Link from 'next/link'
import { Btn, ErrorState, SkeletonRows } from '@/components/common/primitives'
import { BasisBadge, ConfidenceBar, HiddenKindBadge, RiskGauge, ServiceChip } from '@/components/common/signals'
import { getHiddenDependencies, getService } from '@/lib/api'
import type { BlastRadius } from '@/lib/types'

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <section className="border-t px-5 py-4">
      <h3 className="mb-2.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.1em] text-subtle-foreground uppercase">
        {title}
        {count !== undefined && <span className="rounded bg-muted px-1 font-mono text-[10px]">{count}</span>}
      </h3>
      {children}
    </section>
  )
}

export function NodeDrawer({
  id, onClose, simulate, onSimulate, blast, blastLoading, onHoverPath,
}: {
  id: string; onClose: () => void; simulate: boolean; onSimulate: (v: boolean) => void
  blast?: BlastRadius; blastLoading: boolean; onHoverPath?: (path: string[] | null) => void
}) {
  const name = id.replace(/^[a-z]+:/, '')
  const isService = id.startsWith('svc:')
  const detail = useQuery({ queryKey: ['service', name], queryFn: () => getService(name), enabled: isService })
  const hidden = useQuery({ queryKey: ['hidden', name], queryFn: () => getHiddenDependencies(name), enabled: isService })
  const n = detail.data?.node

  return (
    <aside className="absolute inset-y-0 right-0 z-20 flex w-full max-w-sm flex-col border-l bg-card shadow-xl animate-fade sm:static sm:w-96 sm:shadow-none" aria-label={`${name} details`}>
      <header className="flex items-start gap-3 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-medium text-muted-foreground">{isService ? 'Service' : 'Resource'}</div>
          <h2 className="truncate font-mono text-base font-semibold">{name}</h2>
          {n && (
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span>Tier {String(n.properties.tier)}</span>
              <span>Team {String(n.properties.team)}</span>
              <span>{String(n.properties.language)}</span>
              {n.risk_score !== undefined && <span>Criticality {n.risk_score}</span>}
            </div>
          )}
        </div>
        <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Close details">
          <X className="size-4" />
        </button>
      </header>

      <div className="flex gap-2 px-4 pb-3">
        <Btn size="sm" variant={simulate ? 'primary' : 'outline'} onClick={() => onSimulate(!simulate)} aria-pressed={simulate}>
          <Flame />{simulate ? 'Simulating failure' : 'Simulate failure'}
        </Btn>
        <Link href={`/investigator?q=${encodeURIComponent(`What breaks if ${name} fails?`)}`}>
          <Btn size="sm"><Sparkles />Ask</Btn>
        </Link>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {simulate && (
          <Section title="Blast radius" count={blast?.items.length}>
            {blastLoading && !blast ? <SkeletonRows rows={3} className="p-0" /> : blast && (
              <>
                <div className="mb-3 flex justify-center"><RiskGauge value={blast.risk_score} size={120} /></div>
                {blast.items.length > 0 && <p className="mb-1.5 text-[11px] text-muted-foreground">Hover a service to trace its path</p>}
                {blast.items.length === 0 ? (
                  <p className="text-xs text-muted-foreground">Nothing depends on {name}. Its failure stays contained.</p>
                ) : (
                  <ul className="space-y-0.5">
                    {blast.items.map((i) => (
                      <li
                        key={i.service.id}
                        tabIndex={0}
                        onMouseEnter={() => onHoverPath?.(i.path)}
                        onMouseLeave={() => onHoverPath?.(null)}
                        onFocus={() => onHoverPath?.(i.path)}
                        onBlur={() => onHoverPath?.(null)}
                        title={i.path.map((p) => p.replace(/^[a-z]+:/, '')).join(' → ')}
                        className="-mx-1.5 flex cursor-default items-center gap-2 rounded px-1.5 py-1 text-xs outline-none hover:bg-muted focus-visible:bg-muted"
                      >
                        <span className="grid size-5 place-items-center rounded bg-warning-soft font-mono text-[10px] text-warning">{i.hops}</span>
                        <span className="min-w-0 flex-1 truncate font-mono">{i.service.name}</span>
                        <ConfidenceBar value={i.path_confidence} />
                        {i.basis !== 'declared' && <BasisBadge basis={i.basis} />}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </Section>
        )}

        {!isService ? (
          <Section title="About">
            <p className="text-xs leading-5 text-muted-foreground">Resources fail through the services that use them. Simulate failure to see which services, and what depends on them, would break.</p>
          </Section>
        ) : detail.isLoading ? <SkeletonRows rows={4} /> : detail.isError ? <ErrorState error={detail.error} /> : detail.data && (
          <>
            <Section title="Depends on" count={detail.data.upstream.length}>
              {detail.data.upstream.length === 0 ? <p className="text-xs text-muted-foreground">No upstream dependencies.</p> : (
                <div className="flex flex-wrap gap-1.5">
                  {detail.data.upstream.filter((u) => u.hops === 1).map((u) => <ServiceChip key={u.service.id} name={u.service.name} />)}
                  {detail.data.upstream.some((u) => u.hops > 1) && (
                    <span className="self-center text-xs text-muted-foreground">+{detail.data.upstream.filter((u) => u.hops > 1).length} transitive</span>
                  )}
                </div>
              )}
              {!simulate && <p className="mt-2 text-xs text-muted-foreground">{detail.data.blast_radius_count} service{detail.data.blast_radius_count === 1 ? '' : 's'} depend on {name}.</p>}
            </Section>
            {detail.data.resources.length > 0 && (
              <Section title="Uses">
                <div className="flex flex-wrap gap-1.5">{detail.data.resources.map((r) => <ServiceChip key={r.id} name={r.name} kind="Resource" />)}</div>
              </Section>
            )}
            {!!hidden.data?.length && (
              <Section title="Hidden dependencies" count={hidden.data.length}>
                <ul className="space-y-2">
                  {hidden.data.map((h) => (
                    <li key={h.id} className="rounded-md border border-warning/30 bg-warning-soft/50 p-2 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-medium">{h.a.name === name ? h.b.name : h.a.name}</span>
                        <HiddenKindBadge kind={h.kind} />
                      </div>
                      <p className="mt-1 text-muted-foreground">{h.evidence}</p>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            <Section title="Who to page">
              <ul className="space-y-2">
                {detail.data.responders.map((r, i) => (
                  <li key={r.engineer.id} className="flex items-center gap-2.5">
                    <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary-soft text-[11px] font-semibold text-primary">
                      {r.engineer.name.split(' ').map((p) => p[0]).join('')}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 text-sm font-medium">
                        {r.engineer.name}
                        {i === 0 && <span className="rounded bg-primary-soft px-1 text-[10px] font-medium text-primary">Best match</span>}
                      </div>
                      <div className="truncate text-xs text-muted-foreground">{r.reason}</div>
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
          </>
        )}
      </div>
    </aside>
  )
}
