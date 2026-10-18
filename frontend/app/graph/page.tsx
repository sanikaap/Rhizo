'use client'

import { useQuery } from '@tanstack/react-query'
import { Loader2, SlidersHorizontal, Workflow, X } from 'lucide-react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useMemo, useState } from 'react'
import { EmptyState, ErrorState, Skeleton } from '@/components/common/primitives'
import { GraphCanvas, GraphLegend } from '@/components/graph/graph-canvas'
import { NodeDrawer } from '@/components/graph/node-drawer'
import { HeaderActions, HeaderMeta } from '@/components/layout/header-actions'
import { SYNCING, useCurrentRepo } from '@/hooks/use-repos'
import { getBlastRadius, getGraph } from '@/lib/api'
import { edgeIdsFromPaths, hopsFromPaths } from '@/lib/graph-utils'
import { cn } from '@/lib/utils'
import type { Provenance } from '@/lib/types'

const PROVS: Provenance[] = ['declared', 'code', 'observed', 'inferred']

function GraphExplorer() {
  const params = useSearchParams()
  const router = useRouter()
  const [selected, setSelected] = useState<string | null>(params.get('focus') ? `svc:${params.get('focus')}` : null)
  const [simulate, setSimulate] = useState(params.get('simulate') === '1')
  const [prov, setProv] = useState<Provenance[]>(params.get('provenance') ? (params.get('provenance')!.split(',') as Provenance[]) : PROVS)
  const [minConf, setMinConf] = useState(0)
  const [daysAgo, setDaysAgo] = useState(0)
  const [scope, setScope] = useState<'all' | 'neighbourhood'>('all')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [layout, setLayout] = useState<'force' | 'layered'>('layered')
  const [hoverPath, setHoverPath] = useState<string[] | null>(null)

  const asOf = useMemo(() => (daysAgo ? new Date(Date.now() - daysAgo * 86_400_000).toISOString() : undefined), [daysAgo])
  const selName = selected?.replace(/^[a-z]+:/, '')
  const query = {
    min_confidence: minConf,
    provenance: prov.length === 3 ? undefined : prov,
    as_of: asOf,
    ...(scope === 'neighbourhood' && selName ? { center: selName, depth: 2 } : {}),
  }
  const graph = useQuery({ queryKey: ['graph', query], queryFn: () => getGraph(query), placeholderData: (p) => p })
  const blast = useQuery({
    queryKey: ['blast', selName, asOf],
    queryFn: () => getBlastRadius({ service: selName!, as_of: asOf }),
    enabled: !!selName && simulate,
  })

  useEffect(() => {
    const p = new URLSearchParams()
    if (selName) p.set('focus', selName)
    if (simulate && selName) p.set('simulate', '1')
    if (prov.length < 3) p.set('provenance', prov.join(','))
    router.replace(`/graph${p.size ? `?${p}` : ''}`, { scroll: false })
  }, [selName, simulate, prov, router])

  const highlight = useMemo(() => {
    if (hoverPath && selected)
      return { nodeIds: hoverPath, edgeIds: edgeIdsFromPaths([hoverPath]), hopById: hopsFromPaths([hoverPath]), rootIds: [selected] }
    if (!simulate || !blast.data || !selected) return null
    const hop = hopsFromPaths(blast.data.items.map((i) => i.path))
    hop[selected] = 0
    return { nodeIds: [selected, ...blast.data.items.map((i) => i.service.id)], edgeIds: edgeIdsFromPaths(blast.data.items.map((i) => i.path)), hopById: hop, rootIds: [selected], animate: true }
  }, [simulate, blast.data, selected, hoverPath])

  const toggleProv = (p: Provenance) => setProv((cur) => (cur.includes(p) ? (cur.length > 1 ? cur.filter((x) => x !== p) : cur) : [...cur, p]))

  const label = 'text-[11px] font-semibold tracking-[0.1em] text-subtle-foreground uppercase'
  const filters = (
    <div className="space-y-7 text-sm">
      <fieldset>
        <legend className={cn(label, 'mb-3')}>Provenance</legend>
        <div className="flex gap-1.5">
          {PROVS.map((p) => (
            <button
              key={p}
              onClick={() => toggleProv(p)}
              aria-pressed={prov.includes(p)}
              className={cn(
                'h-8 rounded-sm border px-2 text-[11px] font-semibold capitalize transition-colors',
                prov.includes(p) ? 'border-indigo-200 bg-indigo-50 text-indigo-600' : 'bg-card text-muted-foreground hover:bg-muted',
              )}
            >
              {p}
            </button>
          ))}
        </div>
      </fieldset>
      <div>
        <label htmlFor="minconf" className={cn(label, 'mb-2 flex justify-between')}>
          Min confidence <span className="font-mono text-xs tracking-normal text-foreground">{minConf.toFixed(2)}</span>
        </label>
        <input id="minconf" type="range" min={0} max={1} step={0.05} value={minConf} onChange={(e) => setMinConf(+e.target.value)} className="range w-full" />
      </div>
      <div>
        <label htmlFor="asof" className={cn(label, 'mb-2 flex items-center justify-between')}>
          Time travel
          <span className={cn('rounded-sm px-1.5 py-0.5 text-[11px] font-semibold tracking-normal normal-case', daysAgo ? 'bg-warning-soft text-warning' : 'bg-primary-soft text-primary')}>
            {daysAgo ? `${daysAgo}d ago` : 'Live now'}
          </span>
        </label>
        <input id="asof" type="range" min={0} max={180} step={5} value={180 - daysAgo} onChange={(e) => setDaysAgo(180 - +e.target.value)} className="range w-full" aria-valuetext={daysAgo ? `${daysAgo} days ago` : 'now'} />
        <p className="mt-1.5 text-[11px] leading-4 text-subtle-foreground italic">Showing edges valid at this moment (valid_from ≤ t &lt; valid_to).</p>
      </div>
      <div>
        <div className={cn(label, 'mb-3')}>Analysis scope</div>
        <div role="radiogroup" aria-label="Scope" className="space-y-2">
          {([['all', 'Whole graph'], ['neighbourhood', '2 hops of selection']] as const).map(([v, l]) => (
            <button
              key={v}
              role="radio"
              aria-checked={scope === v}
              onClick={() => setScope(v)}
              className={cn('block h-10 w-full rounded-sm border px-3 text-left text-xs font-semibold transition-colors', scope === v ? 'border-stone-900 bg-stone-900 text-white' : 'bg-card hover:bg-muted')}
            >
              {l}
            </button>
          ))}
        </div>
        {scope === 'neighbourhood' && !selName && <p className="mt-1.5 text-[11px] text-subtle-foreground">Select a node to narrow the graph.</p>}
      </div>
      <div className="border-t pt-6">
        <div className={cn(label, 'mb-4')}>Legend</div>
        <GraphLegend variant="list" />
      </div>
    </div>
  )

  const clear = () => { setSelected(null); setSimulate(false); setHoverPath(null) }

  return (
    <div className="flex h-[calc(100dvh-4rem)] flex-col">
      <HeaderMeta>
        {graph.data ? (
          <>
            <span className="font-semibold">{graph.data.nodes.length} Nodes</span>
            <span className="size-1 rounded-full bg-subtle-foreground" />
            <span className="text-subtle-foreground">{graph.data.edges.length} Edges</span>
            {asOf && <span className="font-medium text-warning">· as of {daysAgo} days ago</span>}
          </>
        ) : <span className="text-subtle-foreground">Loading…</span>}
      </HeaderMeta>
      <HeaderActions>
        <div role="radiogroup" aria-label="Layout" className="inline-flex rounded-md border bg-muted p-0.5">
          {(['layered', 'force'] as const).map((v) => (
            <button
              key={v}
              role="radio"
              aria-checked={layout === v}
              onClick={() => setLayout(v)}
              className={cn('h-7 rounded-[5px] px-3 text-xs font-semibold capitalize text-subtle-foreground transition-colors hover:text-foreground', layout === v && 'bg-card text-foreground shadow-xs')}
            >
              {v}
            </button>
          ))}
        </div>
        <button onClick={() => setFiltersOpen((o) => !o)} className="flex h-9 items-center gap-1.5 rounded-md border bg-card px-2.5 text-xs font-medium hover:bg-muted md:hidden" aria-expanded={filtersOpen}>
          <SlidersHorizontal className="size-3.5" />Filters
        </button>
      </HeaderActions>
      <div className="relative flex min-h-0 flex-1">
        <aside className={cn('w-64 shrink-0 overflow-y-auto border-r bg-card p-5 scrollbar-thin', filtersOpen ? 'absolute inset-y-0 left-0 z-20 shadow-lg' : 'hidden md:block')}>
          <div className="mb-4 flex items-center justify-between md:hidden">
            <span className="text-sm font-semibold">Filters</span>
            <button onClick={() => setFiltersOpen(false)} aria-label="Close filters"><X className="size-4" /></button>
          </div>
          {filters}
        </aside>
        <div className="relative min-w-0 flex-1">
          {graph.isLoading ? (
            <div className="grid h-full place-items-center"><Skeleton className="size-40 rounded-full" /></div>
          ) : graph.isError ? (
            <ErrorState error={graph.error} onRetry={() => graph.refetch()} className="h-full justify-center" />
          ) : !graph.data?.nodes.length ? (
            <EmptyGraph />
          ) : (
            <GraphCanvas nodes={graph.data!.nodes} edges={graph.data!.edges} highlight={highlight} selectedId={selected} onSelectNode={setSelected} layout={layout} focusId={selected} />
          )}
          {graph.data && (
            <div className="absolute top-4 left-1/2 flex max-w-[calc(100%-2rem)] -translate-x-1/2 items-center divide-x rounded-full border bg-card/95 text-[11px] font-semibold tracking-[0.08em] whitespace-nowrap uppercase shadow-sm backdrop-blur">
              <span className="truncate px-4 py-2.5 text-subtle-foreground">
                {!selName ? 'Click a node to inspect or simulate failure' : simulate ? `Simulating ${selName} failure` : `Inspecting ${selName}`}
              </span>
              {selected && (
                <button onClick={clear} className="px-4 py-2.5 tracking-[0.08em] text-danger uppercase hover:text-danger/80">
                  {simulate ? 'Clear simulation' : 'Clear selection'}
                </button>
              )}
            </div>
          )}
        </div>
        {selected && (
          <NodeDrawer
            id={selected}
            onClose={clear}
            simulate={simulate}
            onSimulate={setSimulate}
            blast={blast.data}
            blastLoading={blast.isFetching}
            onHoverPath={setHoverPath}
          />
        )}
      </div>
    </div>
  )
}

function EmptyGraph() {
  const { current } = useCurrentRepo()
  const syncing = !!current && SYNCING.includes(current.status)
  return (
    <EmptyState
      icon={syncing ? Loader2 : Workflow}
      className="h-full"
      title={syncing ? 'Building the graph' : 'Nothing in this graph yet'}
      description={syncing
        ? `${current?.message ?? 'Queued'} (${current?.progress ?? 0}%)`
        : current?.message ?? 'No services, resources or edges match these filters.'}
    />
  )
}

export default function GraphPage() {
  return <Suspense><GraphExplorer /></Suspense>
}
