'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Siren, X } from 'lucide-react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useState } from 'react'
import { toast } from 'sonner'
import { Btn, Card, EmptyState, ErrorState, PageHeader, Segmented, SkeletonRows } from '@/components/common/primitives'
import { IncidentStatus, SeverityBadge } from '@/components/common/signals'
import { createIncident, getIncidents, getServices } from '@/lib/api'
import { duration, timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Incident } from '@/lib/types'

function NewIncidentDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter()
  const qc = useQueryClient()
  const services = useQuery({ queryKey: ['services'], queryFn: getServices })
  const [title, setTitle] = useState('')
  const [symptom, setSymptom] = useState('')
  const [severity, setSeverity] = useState<Incident['severity']>('sev2')
  const [affected, setAffected] = useState<string[]>([])
  const create = useMutation({
    mutationFn: createIncident,
    onSuccess: (inc) => {
      qc.invalidateQueries({ queryKey: ['incidents'] })
      toast.success(`${inc.id} reported`)
      router.push(`/incidents/${inc.id}`)
    },
  })
  const valid = title.trim() && symptom.trim() && affected.length > 0

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 pt-[8vh]" role="dialog" aria-modal="true" aria-labelledby="new-inc">
      <div className="fixed inset-0 bg-black/40 animate-fade" onClick={onClose} />
      <form
        onSubmit={(e) => { e.preventDefault(); if (valid) create.mutate({ title, symptom, severity, affected }) }}
        className="relative w-full max-w-lg rounded-xl border bg-card shadow-2xl animate-rise"
      >
        <header className="flex items-center justify-between border-b px-5 py-3">
          <h2 id="new-inc" className="text-sm font-semibold">Report incident</h2>
          <button type="button" onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted" aria-label="Close"><X className="size-4" /></button>
        </header>
        <div className="space-y-4 p-5">
          <label className="block">
            <span className="mb-1 block text-xs font-medium">Title</span>
            <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Checkout failing for EU users" className="h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium">Symptom</span>
            <input value={symptom} onChange={(e) => setSymptom(e.target.value)} placeholder="p95 > 5s on /cart/checkout" className="h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" />
          </label>
          <div>
            <span className="mb-1 block text-xs font-medium">Severity</span>
            <Segmented label="Severity" value={severity} onChange={setSeverity} options={[{ value: 'sev1', label: 'SEV1' }, { value: 'sev2', label: 'SEV2' }, { value: 'sev3', label: 'SEV3' }]} />
          </div>
          <div>
            <span className="mb-1 block text-xs font-medium">Affected services <span className="font-normal text-muted-foreground">(where the symptom shows)</span></span>
            <div className="flex flex-wrap gap-1.5">
              {services.data?.map((s) => {
                const on = affected.includes(s.name)
                return (
                  <button type="button" key={s.id} aria-pressed={on} onClick={() => setAffected((a) => (on ? a.filter((x) => x !== s.name) : [...a, s.name]))}
                    className={cn('h-7 rounded-md border px-2 font-mono text-xs', on ? 'border-primary/40 bg-primary-soft text-primary' : 'text-muted-foreground hover:bg-muted')}>
                    {s.name}
                  </button>
                )
              })}
              {services.isLoading && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
              {services.data?.length === 0 && <p className="text-xs text-muted-foreground">No services were detected in this repository, so there is nothing to attach the incident to yet.</p>}
            </div>
          </div>
          {create.isError && <p className="text-xs text-danger">{(create.error as Error).message}</p>}
        </div>
        <footer className="flex justify-end gap-2 border-t px-5 py-3">
          <Btn type="button" onClick={onClose}>Cancel</Btn>
          <Btn type="submit" variant="primary" disabled={!valid || create.isPending}>{create.isPending && <Loader2 className="animate-spin" />}Report</Btn>
        </footer>
      </form>
    </div>
  )
}

function IncidentsList() {
  const params = useSearchParams()
  const router = useRouter()
  const [filter, setFilter] = useState<'all' | 'open' | 'resolved'>('all')
  const incidents = useQuery({ queryKey: ['incidents'], queryFn: getIncidents })
  const showNew = params.get('new') === '1'
  const rows = incidents.data?.filter((i) => filter === 'all' || i.status === filter) ?? []
  const count = (s: 'open' | 'resolved') => incidents.data?.filter((i) => i.status === s).length ?? 0

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
      <PageHeader
        title="Incidents"
        description="Past incidents are graph memory: resolving one with a confirmed root cause creates or strengthens dependency edges."
        actions={<Btn variant="primary" onClick={() => router.push('/incidents?new=1')}><Plus />Report incident</Btn>}
      />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <Segmented label="Filter" size="xs" value={filter} onChange={setFilter} options={[
            { value: 'all', label: `All ${incidents.data?.length ?? ''}` },
            { value: 'open', label: `Open ${count('open')}` },
            { value: 'resolved', label: `Resolved ${count('resolved')}` },
          ]} />
        </div>
        {incidents.isLoading ? <SkeletonRows rows={5} /> : incidents.isError ? <ErrorState error={incidents.error} onRetry={() => incidents.refetch()} /> : rows.length === 0 ? (
          <EmptyState icon={Siren} title={filter === 'open' ? 'No open incidents' : 'No incidents yet'} description={filter === 'open' ? 'Report one when something breaks.' : "Rhizo derives incidents from this repository's closed issues labelled bug or incident (when a commit closed them) and from fix/revert commits. None were found in its history. You can report one."} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="px-4 py-2 font-medium">Incident</th>
                  <th className="px-2 py-2 font-medium">Status</th>
                  <th className="hidden px-2 py-2 font-medium md:table-cell">Affected</th>
                  <th className="hidden px-2 py-2 font-medium lg:table-cell">Root cause</th>
                  <th className="px-4 py-2 text-right font-medium">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {rows.map((i) => (
                  <tr key={i.id} className="cursor-pointer hover:bg-muted/50" onClick={() => router.push(`/incidents/${i.id}`)}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <SeverityBadge severity={i.severity} />
                        <Link href={`/incidents/${i.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{i.title}</Link>
                      </div>
                      <div className="mt-0.5 font-mono text-xs text-muted-foreground">{i.id} · {i.symptom}</div>
                    </td>
                    <td className="px-2 py-3"><IncidentStatus status={i.status} /></td>
                    <td className="hidden px-2 py-3 md:table-cell">
                      <div className="flex max-w-xs flex-wrap gap-1">{i.affected.map((a) => <span key={a} className="rounded bg-muted px-1.5 font-mono text-[11px]">{a}</span>)}</div>
                    </td>
                    <td className="hidden px-2 py-3 font-mono text-xs lg:table-cell">{i.root_cause ?? <span className="text-muted-foreground">–</span>}</td>
                    <td className="px-4 py-3 text-right text-xs whitespace-nowrap text-muted-foreground">
                      {timeAgo(i.started_at)}
                      <div className="text-subtle-foreground">{i.status === 'resolved' ? `took ${duration(i.started_at, i.resolved_at)}` : `open ${duration(i.started_at, null)}`}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {showNew && <NewIncidentDialog onClose={() => router.replace('/incidents')} />}
    </div>
  )
}

export default function IncidentsPage() {
  return <Suspense><IncidentsList /></Suspense>
}
