'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowLeftRight, Check, CheckCircle2, GitMerge, Loader2, Sparkles, X } from 'lucide-react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useState } from 'react'
import { toast } from 'sonner'
import { Btn, Card, CardHeader, EmptyState, ErrorState, Skeleton, SkeletonRows } from '@/components/common/primitives'
import { IncidentStatus, SeverityBadge, ServiceChip } from '@/components/common/signals'
import { getGraph, getIncident, getResponders, getUpstreamSuspects, resolveIncident } from '@/lib/api'
import { duration, fmtDate } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Incident, SuggestedEdge } from '@/lib/types'

type Verdict = 'confirm' | 'refute' | null

function ResolveForm({ incident, suggested }: { incident: Incident; suggested: SuggestedEdge[] }) {
  const qc = useQueryClient()
  const graph = useQuery({ queryKey: ['graph', {}], queryFn: () => getGraph() })
  const candidates = graph.data?.nodes.filter((n) => n.label === 'Service' || n.label === 'Resource') ?? []
  const responders = useQuery({ queryKey: ['responders', incident.affected], queryFn: () => getResponders(incident.affected) })
  const [rootCause, setRootCause] = useState('')
  const [fix, setFix] = useState('')
  const [by, setBy] = useState('')
  const [verdicts, setVerdicts] = useState<Record<string, Verdict>>({})
  const [flipped, setFlipped] = useState<Record<string, boolean>>({})
  const key = (e: SuggestedEdge) => `${e.from}->${e.to}`
  const dir = (e: SuggestedEdge) => (flipped[key(e)] ? { from: e.to, to: e.from } : { from: e.from, to: e.to })

  const resolve = useMutation({
    mutationFn: () =>
      resolveIncident(incident.id, {
        root_cause: rootCause,
        fix,
        resolved_by: by || undefined,
        confirmed_edges: suggested.filter((e) => verdicts[key(e)] === 'confirm').map(dir),
        refuted_edges: suggested.filter((e) => verdicts[key(e)] === 'refute').map(dir),
      }),
    onSuccess: ({ graph_updates: g }) => {
      toast.success(`Graph updated: ${g.created} created, ${g.strengthened} strengthened${g.weakened ? `, ${g.weakened} weakened` : ''}`)
      for (const k of ['incident', 'incidents', 'graph', 'hidden', 'blast', 'service', 'rankings']) qc.invalidateQueries({ queryKey: [k] })
    },
  })

  const setV = (e: SuggestedEdge, v: Verdict) => setVerdicts((s) => ({ ...s, [key(e)]: s[key(e)] === v ? null : v }))
  const fieldCls = 'h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20'

  return (
    <Card>
      <CardHeader title="Resolve and teach the graph" description="Confirmed edges are created at 0.60 confidence or strengthened by +0.15." />
      <form onSubmit={(e) => { e.preventDefault(); resolve.mutate() }} className="space-y-4 p-4">
        <label className="block">
          <span className="mb-1 block text-xs font-medium">Root cause</span>
          <select required value={rootCause} onChange={(e) => setRootCause(e.target.value)} className={fieldCls}>
            <option value="">Select a service or resource…</option>
            {candidates.map((n) => <option key={n.id} value={n.name}>{n.name}{n.label === 'Resource' ? ' (resource)' : ''}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium">Fix</span>
          <textarea required value={fix} onChange={(e) => setFix(e.target.value)} rows={2} placeholder="What resolved it?" className={cn(fieldCls, 'h-auto py-2')} />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium">Resolved by</span>
          <select value={by} onChange={(e) => setBy(e.target.value)} className={fieldCls}>
            <option value="">Unassigned</option>
            {responders.data?.map((r) => <option key={r.engineer.id} value={String(r.engineer.properties.handle)}>{r.engineer.name}</option>)}
          </select>
        </label>

        <fieldset>
          <legend className="mb-1.5 text-xs font-medium">Did this incident reveal a dependency?</legend>
          {suggested.length === 0 ? (
            <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">No undeclared pairs among the affected services.</p>
          ) : (
            <ul className="space-y-1.5">
              {suggested.map((e) => {
                const v = verdicts[key(e)]
                return (
                  <li key={key(e)} className={cn('flex items-center gap-2 rounded-md border p-2', v === 'confirm' && 'border-success/40 bg-success-soft', v === 'refute' && 'border-danger/30 bg-danger-soft')}>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1 font-mono text-xs">
                        {dir(e).from}
                        <button type="button" onClick={() => setFlipped((f) => ({ ...f, [key(e)]: !f[key(e)] }))} className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Flip direction" title="Flip direction">
                          <ArrowLeftRight className="size-3" />
                        </button>
                        {dir(e).to}
                      </div>
                      <div className="text-[11px] text-muted-foreground">{e.reason}</div>
                    </div>
                    <button type="button" onClick={() => setV(e, 'confirm')} aria-pressed={v === 'confirm'} className={cn('grid size-7 place-items-center rounded-md border', v === 'confirm' ? 'border-success bg-success text-white' : 'text-muted-foreground hover:bg-muted')} aria-label={`Confirm ${dir(e).from} depends on ${dir(e).to}`}><Check className="size-3.5" /></button>
                    <button type="button" onClick={() => setV(e, 'refute')} aria-pressed={v === 'refute'} className={cn('grid size-7 place-items-center rounded-md border', v === 'refute' ? 'border-danger bg-danger text-white' : 'text-muted-foreground hover:bg-muted')} aria-label={`Refute ${dir(e).from} depends on ${dir(e).to}`}><X className="size-3.5" /></button>
                  </li>
                )
              })}
            </ul>
          )}
        </fieldset>

        {resolve.isError && <p className="text-xs text-danger">{(resolve.error as Error).message}</p>}
        <Btn type="submit" variant="primary" className="w-full" disabled={!rootCause || !fix.trim() || resolve.isPending}>
          {resolve.isPending ? <Loader2 className="animate-spin" /> : <GitMerge />}Resolve incident
        </Btn>
      </form>
    </Card>
  )
}

export default function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const q = useQuery({ queryKey: ['incident', id], queryFn: () => getIncident(id) })
  const inc = q.data?.incident
  const symptom = inc?.affected[0]
  const suspects = useQuery({ queryKey: ['suspects', symptom], queryFn: () => getUpstreamSuspects({ service: symptom! }), enabled: !!symptom && inc?.status === 'open' })
  const responders = useQuery({ queryKey: ['responders', inc?.affected], queryFn: () => getResponders(inc!.affected), enabled: !!inc })

  if (q.isError) return <div className="mx-auto max-w-5xl p-6"><Card><ErrorState error={q.error} onRetry={() => q.refetch()} /></Card></div>

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
      <Link href="/incidents" className="mb-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" />Incidents</Link>
      {!inc ? (
        <div className="space-y-3"><Skeleton className="h-6 w-1/3" /><Skeleton className="h-4 w-1/2" /><Skeleton className="mt-6 h-64" /></div>
      ) : (
        <>
          <div className="mb-6">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={inc.severity} />
              <span className="font-mono text-sm text-muted-foreground">{inc.id}</span>
              <IncidentStatus status={inc.status} />
              {inc.url && (
                <a href={inc.url} target="_blank" rel="noreferrer noopener" className="text-xs text-primary hover:underline">
                  {inc.source === 'github_issue' ? 'GitHub issue' : 'Fix commit'} ↗
                </a>
              )}
            </div>
            <h1 className="mt-2 text-xl font-semibold tracking-tight">{inc.title}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{inc.symptom}</p>
            <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
              <span>Started {fmtDate(inc.started_at)}</span>
              <span>{inc.status === 'resolved' ? `Resolved in ${duration(inc.started_at, inc.resolved_at)}` : `Open for ${duration(inc.started_at, null)}`}</span>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
            <div className="min-w-0 space-y-6">
              <Card>
                <CardHeader title="Affected services" description="Where the symptom was observed" action={
                  <Link href={`/investigator?q=${encodeURIComponent(`Why is ${inc.affected[0]} failing?`)}`}><Btn size="sm"><Sparkles />Investigate</Btn></Link>
                } />
                <div className="flex flex-wrap gap-1.5 p-4">{inc.affected.map((a) => <ServiceChip key={a} name={a} />)}</div>
              </Card>

              {inc.status === 'resolved' ? (
                <Card>
                  <CardHeader title="Resolution" />
                  <dl className="grid grid-cols-[110px_1fr] gap-x-4 gap-y-3 p-4 text-sm">
                    <dt className="text-muted-foreground">Root cause</dt><dd className="font-mono">{inc.root_cause}</dd>
                    <dt className="text-muted-foreground">Fix</dt><dd>{inc.fix}</dd>
                    <dt className="text-muted-foreground">Resolved by</dt><dd>{inc.resolved_by ?? '–'}</dd>
                  </dl>
                </Card>
              ) : (
                <Card>
                  <CardHeader title={`Upstream suspects for ${symptom}`} description="What it depends on, ranked by distance, recent commits and path confidence" />
                  {suspects.isLoading ? <SkeletonRows rows={3} /> : !suspects.data?.suspects.length ? (
                    <EmptyState title="No upstream dependencies" description={`${symptom} depends on nothing in the graph; the fault is likely inside it.`} />
                  ) : (
                    <ol className="divide-y">
                      {suspects.data.suspects.slice(0, 5).map((s, i) => (
                        <li key={s.service.id} className="flex items-center gap-3 px-4 py-2.5">
                          <span className="w-4 text-right font-mono text-xs text-subtle-foreground">{i + 1}</span>
                          <span className="flex-1 font-mono text-[13px] font-medium">{s.service.name}</span>
                          <span className="text-xs text-muted-foreground">{s.hops} hop{s.hops > 1 ? 's' : ''}</span>
                          <span className={cn('text-xs', s.recent_commits ? 'font-medium text-warning' : 'text-muted-foreground')}>{s.recent_commits} recent commit{s.recent_commits === 1 ? '' : 's'}</span>
                          <span className="w-10 text-right font-mono text-xs text-muted-foreground">{s.score.toFixed(2)}</span>
                        </li>
                      ))}
                    </ol>
                  )}
                </Card>
              )}

              <div className="grid gap-6 md:grid-cols-2">
                <Card>
                  <CardHeader title="Who to page" />
                  {responders.isLoading ? <SkeletonRows rows={3} /> : (
                    <ul className="divide-y">
                      {responders.data?.map((r) => (
                        <li key={r.engineer.id} className="flex items-center gap-2.5 px-4 py-2.5">
                          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary-soft text-[11px] font-semibold text-primary">{r.engineer.name.split(' ').map((p) => p[0]).join('')}</span>
                          <div className="min-w-0"><div className="text-sm font-medium">{r.engineer.name}</div><div className="truncate text-xs text-muted-foreground">{r.reason}</div></div>
                          <span className="ml-auto font-mono text-xs text-muted-foreground">{r.score.toFixed(2)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
                <Card>
                  <CardHeader title="Similar past incidents" />
                  {q.data!.similar.length === 0 ? <p className="p-4 text-xs text-muted-foreground">Nothing similar in memory.</p> : (
                    <ul className="divide-y">
                      {q.data!.similar.map(({ incident: s, similarity }) => (
                        <li key={s.id}>
                          <Link href={`/incidents/${s.id}`} className="block px-4 py-2.5 hover:bg-muted/50">
                            <div className="flex items-center gap-2 text-xs"><span className="font-mono text-muted-foreground">{s.id}</span><span className="ml-auto font-mono text-muted-foreground">{Math.round(similarity * 100)}% match</span></div>
                            <div className="mt-0.5 text-sm font-medium">{s.title}</div>
                            {s.fix && <div className="mt-0.5 flex gap-1 text-xs text-muted-foreground"><CheckCircle2 className="mt-0.5 size-3 shrink-0 text-success" />{s.fix}</div>}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
              </div>
            </div>

            <div>{inc.status === 'open' ? <ResolveForm incident={inc} suggested={q.data!.suggested_edges} /> : (
              <Card className="p-4 text-sm text-muted-foreground">
                <CheckCircle2 className="mb-2 size-5 text-success" />
                This incident is in graph memory. Its affected services and fix are used to rank similar incidents and responders.
              </Card>
            )}</div>
          </div>
        </>
      )}
    </div>
  )
}
