'use client'

import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, Bot, Boxes, Code, Code2, EyeOff, Flame, GitCompareArrows, Link2, Plus, Sparkles, TriangleAlert } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Btn, Card, CardHeader, EmptyState, ErrorState, SkeletonRows } from '@/components/common/primitives'
import { riskTone, SeverityBadge, StatCard } from '@/components/common/signals'
import { HeaderActions } from '@/components/layout/header-actions'
import { getGraph, getHiddenDependencies, getIncidents, getRankings } from '@/lib/api'
import { timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Provenance, RankingMetric } from '@/lib/types'

const SUGGESTIONS = [
  'What breaks if paymentservice fails?',
  'Why is frontend returning errors?',
  'Find hidden dependencies',
  'Which services are most critical?',
]

const METRICS: { value: RankingMetric; label: string }[] = [
  { value: 'pagerank', label: 'PageRank' },
  { value: 'centrality', label: 'Betweenness' },
  { value: 'community', label: 'Community' },
]

const PROVENANCE: { p: Provenance; title: string; body: string; icon: React.ElementType; tile: string }[] = [
  { p: 'declared', title: 'Declared', body: 'Parsed from Kubernetes manifests and compose files.', icon: Code, tile: 'border-emerald-200 bg-emerald-50 text-emerald-600' },
  { p: 'observed', title: 'Observed', body: 'Seen in runtime traces between live services.', icon: Activity, tile: 'border-blue-200 bg-blue-50 text-blue-600' },
  { p: 'code', title: 'Code', body: 'Imports between the repo\'s own packages (Python, JS/TS).', icon: Code2, tile: 'border-sky-200 bg-sky-50 text-sky-600' },
  { p: 'inferred', title: 'Inferred', body: 'Shared resources, co-change history and incidents. Verify before relying on it.', icon: Sparkles, tile: 'border-violet-200 bg-violet-50 text-violet-500' },
]

const DOT = { success: 'bg-success', warning: 'bg-amber-500', danger: 'bg-danger' } as const
const HIDDEN_SHOWN = 4

function CountBadge({ tone, children }: { tone: 'danger' | 'warning'; children: React.ReactNode }) {
  return (
    <span className={cn(
      'rounded-sm border px-2 py-0.5 text-[11px] font-bold tracking-wide uppercase',
      tone === 'danger' ? 'border-danger/20 bg-danger-soft text-danger' : 'border-amber-200 bg-warning-soft text-warning',
    )}>
      {children}
    </span>
  )
}

const footerLink = 'block border-t bg-background/60 py-3.5 text-center text-xs font-bold tracking-[0.12em] uppercase transition-colors'

export default function OverviewPage() {
  const router = useRouter()
  const [q, setQ] = useState('')
  const [metric, setMetric] = useState<RankingMetric>('pagerank')
  const graph = useQuery({ queryKey: ['graph', {}], queryFn: () => getGraph() })
  const hidden = useQuery({ queryKey: ['hidden', null], queryFn: () => getHiddenDependencies() })
  const incidents = useQuery({ queryKey: ['incidents'], queryFn: getIncidents })
  const ranks = useQuery({ queryKey: ['rankings', metric], queryFn: () => getRankings(metric, 5) })

  const ask = (text: string) => text.trim() && router.push(`/investigator?q=${encodeURIComponent(text.trim())}`)
  const services = graph.data?.nodes.filter((n) => n.label === 'Service').length
  const liveEdges = graph.data?.edges.filter((e) => e.type === 'DEPENDS_ON' || e.type === 'USES') ?? []
  const open = incidents.data?.filter((i) => i.status === 'open') ?? []
  const prov = Object.fromEntries((['declared', 'code', 'observed', 'inferred'] as Provenance[]).map((p) => [p, liveEdges.filter((e) => e.provenance === p).length]))

  return (
    <div className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:py-8">
      <HeaderActions>
        <Link href="/change-check" className="hidden sm:block">
          <Btn className="h-9 text-xs font-bold tracking-[0.08em] uppercase"><GitCompareArrows />Change check</Btn>
        </Link>
        <Link href="/incidents?new=1">
          <Btn variant="primary" className="h-9 text-xs font-bold tracking-[0.08em] uppercase"><Plus />Report incident</Btn>
        </Link>
      </HeaderActions>

      <section className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-4" aria-label="Key numbers">
        <StatCard label="Total services" icon={Boxes} value={services ?? '–'} />
        <StatCard label="Live dependencies" icon={Link2} value={liveEdges.length ? liveEdges.length.toLocaleString() : '–'} />
        <StatCard label="Hidden deps" icon={EyeOff} tone="warning" value={hidden.data?.length ?? '–'} />
        <StatCard label="Open incidents" icon={TriangleAlert} tone={open.length ? 'danger' : undefined} value={incidents.data ? open.length : '–'} />
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <Card className="flex flex-col xl:row-span-2">
          <CardHeader
            title={<><Flame className="size-4 text-danger" />Open incidents</>}
            action={open.length > 0 && <CountBadge tone="danger">{open.length} active</CountBadge>}
          />
          <div className="flex-1">
            {incidents.isLoading ? <SkeletonRows rows={3} /> : incidents.isError ? <ErrorState error={incidents.error} onRetry={() => incidents.refetch()} /> : open.length === 0 ? (
              <EmptyState icon={Flame} title="No open incidents" description="When one is declared, Rhizo suggests suspects, responders and similar past incidents." />
            ) : (
              <ul className="divide-y">
                {open.map((i) => (
                  <li key={i.id}>
                    <Link href={`/incidents/${i.id}`} className="block px-5 py-5 transition-colors hover:bg-muted/50">
                      <div className="flex items-center justify-between gap-2 text-[11px] text-subtle-foreground">
                        <span className="font-mono">{i.id}</span>
                        <span>{timeAgo(i.started_at)}</span>
                      </div>
                      <div className="mt-1.5 text-[15px] font-semibold">{i.title}</div>
                      <div className="mt-2 flex min-w-0 items-center gap-2 text-xs text-subtle-foreground">
                        <SeverityBadge severity={i.severity} />
                        <span className="truncate">Affected: <span className="font-medium text-foreground/80">{i.affected.join(', ')}</span></span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <Link href="/incidents" className={cn(footerLink, 'text-muted-foreground hover:text-foreground')}>View all incidents</Link>
        </Card>

        <Card>
          <CardHeader
            title="Most critical services"
            action={
              <label className="flex items-center gap-2 text-[10px] font-semibold tracking-wide text-subtle-foreground uppercase">
                Sort by
                <select
                  value={metric}
                  onChange={(e) => setMetric(e.target.value as RankingMetric)}
                  className="rounded-sm border border-emerald-200 bg-primary-soft px-1.5 py-0.5 text-[11px] font-semibold tracking-normal text-primary normal-case outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                  aria-label="Ranking metric"
                >
                  {METRICS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </label>
            }
          />
          {ranks.isLoading ? <SkeletonRows rows={5} /> : ranks.isError ? <ErrorState error={ranks.error} onRetry={() => ranks.refetch()} /> : (
            <>
              <div className="flex justify-between border-b px-5 py-2.5 text-[11px] font-semibold tracking-[0.1em] text-subtle-foreground uppercase">
                <span>Service name</span>
                <span>Score</span>
              </div>
              <ol className="divide-y">
                {ranks.data!.items.map((it) => {
                  const tone = it.service.risk_score === undefined ? 'success' : riskTone(it.service.risk_score)
                  return (
                    <li key={it.service.id}>
                      <Link
                        href={`/graph?focus=${it.service.name}&simulate=1`}
                        title="Blast radius"
                        className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-muted/50"
                      >
                        <span className={cn('size-1.5 shrink-0 rounded-full', DOT[tone])} />
                        <span className="truncate text-sm font-semibold">{it.service.name}</span>
                        {it.community !== undefined && <span className="text-[11px] text-subtle-foreground">group {it.community}</span>}
                        <span className="ml-auto font-mono text-xs tabular-nums">{it.score.toFixed(2)}</span>
                      </Link>
                    </li>
                  )
                })}
              </ol>
              {ranks.data!.algorithm === 'degree_fallback' && (
                <p className="border-t px-5 py-2.5 text-[11px] text-muted-foreground">Degree-based approximation (algorithm unavailable in this FalkorDB build)</p>
              )}
            </>
          )}
        </Card>

        <div className="rounded-md bg-primary p-5 text-white shadow-[0_8px_24px_rgba(5,150,105,0.25)]">
          <h2 className="flex items-center gap-2 text-[13px] font-bold tracking-[0.1em] uppercase"><Bot className="size-5" />Investigator</h2>
          <form onSubmit={(e) => { e.preventDefault(); ask(q) }} className="mt-4 flex h-11 items-center rounded-md bg-emerald-700/70 pr-1 pl-3.5 focus-within:ring-2 focus-within:ring-white/40">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Ask a dependency question…"
              className="h-full flex-1 bg-transparent text-sm outline-none placeholder:text-emerald-200/80"
              aria-label="Ask Rhizo"
            />
            <button disabled={!q.trim()} className="grid size-9 place-items-center rounded-md text-emerald-100 hover:bg-white/10 disabled:opacity-60" aria-label="Ask">
              <ArrowRight className="size-4" />
            </button>
          </form>
          <div className="mt-5 text-[11px] font-semibold tracking-[0.1em] text-emerald-200 uppercase">Example queries</div>
          <ul className="mt-2.5 space-y-2">
            {SUGGESTIONS.map((s) => (
              <li key={s}>
                <button onClick={() => ask(s)} className="w-full rounded-md bg-emerald-700/50 px-3 py-2.5 text-left text-[13px] transition-colors hover:bg-emerald-700">
                  &ldquo;{s}&rdquo;
                </button>
              </li>
            ))}
          </ul>
        </div>

        <Card className="self-start">
          <CardHeader
            title="Hidden dependencies"
            action={hidden.data && hidden.data.length > 0 && <CountBadge tone="warning">{hidden.data.length} detected</CountBadge>}
          />
          {hidden.isLoading ? <SkeletonRows rows={3} /> : hidden.isError ? <ErrorState error={hidden.error} onRetry={() => hidden.refetch()} /> : hidden.data!.length === 0 ? (
            <EmptyState icon={EyeOff} title="No hidden dependencies" description="Every shared resource and co-change pair is already covered by a declared dependency." />
          ) : (
            <>
              <ul className="space-y-2.5 p-5">
                {hidden.data!.slice(0, HIDDEN_SHOWN).map((h) => (
                  <li key={h.id} title={h.evidence} className="rounded-md border bg-background px-3.5 py-3">
                    <div className="flex items-center gap-2 font-mono text-[13px]">
                      <span className="flex min-w-0 flex-wrap items-center gap-x-2">
                        <span>{h.a.name}</span>
                        <span className="text-subtle-foreground">↔</span>
                        <span>{h.b.name}</span>
                      </span>
                      <span className="ml-auto shrink-0 text-[11px] text-subtle-foreground">{h.confidence.toFixed(2)}</span>
                    </div>
                    <p className="mt-1 truncate text-xs text-muted-foreground">
                      <span className={cn('mr-1.5 text-[10px] font-bold tracking-wide uppercase', h.kind === 'shared_resource' ? 'text-warning' : 'text-muted-foreground')}>
                        {h.kind === 'shared_resource' ? 'Shared resource' : 'Co-change'}
                      </span>
                      {h.evidence}
                    </p>
                  </li>
                ))}
              </ul>
              <Link href="/graph?provenance=inferred" className="block pb-5 text-center text-xs font-bold tracking-[0.12em] text-primary uppercase hover:underline">
                Show all {hidden.data!.length} on graph
              </Link>
            </>
          )}
        </Card>

        <Card className="self-start">
          <CardHeader title="Edge provenance" />
          <div className="p-5">
            {graph.isLoading ? <SkeletonRows rows={3} className="p-0" /> : graph.isError ? <ErrorState error={graph.error} onRetry={() => graph.refetch()} /> : (
              <ul className="space-y-5">
                {PROVENANCE.map(({ p, title, body, icon: Icon, tile }) => (
                  <li key={p} className="flex gap-3.5">
                    <span className={cn('grid size-9 shrink-0 place-items-center rounded-md border', tile)}><Icon className="size-4" /></span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-[13px] font-bold tracking-wide uppercase">{title}</span>
                        <span className="font-mono text-xs tabular-nums text-muted-foreground">{prov[p]} edges</span>
                      </div>
                      <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{body}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-5 text-[11px] leading-5 text-subtle-foreground">
              Inferred edges expire after 90 days unless re-observed or confirmed by an incident.
            </p>
            <Link href="/repos" className="mt-4 block rounded-md border py-2.5 text-center text-xs font-bold tracking-[0.12em] text-muted-foreground uppercase transition-colors hover:bg-muted hover:text-foreground">
              Data sources
            </Link>
          </div>
        </Card>
      </div>
    </div>
  )
}
