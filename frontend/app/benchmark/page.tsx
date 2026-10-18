'use client'

import { useQuery } from '@tanstack/react-query'
import { FlaskConical, GitCommitHorizontal, History } from 'lucide-react'
import Link from 'next/link'
import { Btn, Card, CardHeader, EmptyState, ErrorState, PageHeader, SkeletonRows } from '@/components/common/primitives'
import { useCurrentRepo } from '@/hooks/use-repos'
import { ApiError, getBenchmark } from '@/lib/api'
import { timeAgo } from '@/lib/format'
import type { Evaluation, SystemScore } from '@/lib/types'

const pct = (v: number | null) => (v === null ? 'n/a' : `${Math.round(v * 100)}%`)

function Bar({ value, tone }: { value: number | null; tone: 'muted' | 'primary' }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
      <div className={tone === 'primary' ? 'h-full bg-primary' : 'h-full bg-subtle-foreground/60'} style={{ width: `${Math.round((value ?? 0) * 100)}%` }} />
    </div>
  )
}

function SystemRow({ s, tone }: { s: SystemScore; tone: 'muted' | 'primary' }) {
  return (
    <tr className="border-t align-middle">
      <th scope="row" className="py-3 pr-4 text-left text-sm font-medium">{s.name}</th>
      <td className="py-3 pr-4 font-mono text-sm tabular-nums">{s.predicted}</td>
      <td className="py-3 pr-4 font-mono text-sm tabular-nums">{s.hits}</td>
      <td className="w-1/4 py-3 pr-4">
        <div className="flex items-center gap-2"><span className="w-10 font-mono text-sm tabular-nums">{pct(s.precision)}</span><Bar value={s.precision} tone={tone} /></div>
      </td>
      <td className="w-1/4 py-3">
        <div className="flex items-center gap-2"><span className="w-10 font-mono text-sm tabular-nums">{pct(s.recall)}</span><Bar value={s.recall} tone={tone} /></div>
      </td>
    </tr>
  )
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <p className="text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">{label}</p>
      <p className="mt-1 font-mono text-xl font-semibold tabular-nums">{value}</p>
    </div>
  )
}

function Result({ r }: { r: Evaluation }) {
  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Commits used">
        <Stat label="Commits read" value={r.commits_total} />
        <Stat label="Eligible commits" value={r.commits_eligible} />
        <Stat label="Training (older 80%)" value={r.train_commits} />
        <Stat label="Held out (latest 20%)" value={r.test_commits} />
      </section>
      {r.status === 'insufficient_history' ? (
        <Card>
          <EmptyState icon={History} title="Not enough history to evaluate" description={r.reason ?? undefined} />
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader title="Predicting later co-changes" description={`${r.truth_pairs} service pairs changed together in the held-out commits${r.split_at ? `, from ${new Date(r.split_at).toLocaleDateString()} on` : ''}.`} />
            <div className="overflow-x-auto px-5 pb-2">
              <table className="w-full min-w-[560px]">
                <thead>
                  <tr className="text-left text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
                    <th className="py-2 pr-4 font-semibold">System</th>
                    <th className="py-2 pr-4 font-semibold">Predicted pairs</th>
                    <th className="py-2 pr-4 font-semibold">Hits</th>
                    <th className="py-2 pr-4 font-semibold">Precision</th>
                    <th className="py-2 font-semibold">Recall</th>
                  </tr>
                </thead>
                <tbody>{r.systems.map((s, i) => <SystemRow key={s.name} s={s} tone={i === 0 ? 'muted' : 'primary'} />)}</tbody>
              </table>
            </div>
          </Card>
          <Card>
            <CardHeader title="Hidden dependencies that came true" description="Mined from the older commits only, never declared, and then co-changed in the held-out commits." />
            {r.hidden_hits.length ? (
              <ul className="flex flex-wrap gap-2 p-5">
                {r.hidden_hits.map((p) => (
                  <li key={`${p.a}|${p.b}`} className="rounded-md border px-2 py-1 font-mono text-xs">{p.a} ↔ {p.b}</li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={GitCommitHorizontal} title="None in this run" description="No co-change pair mined from the training commits reappeared in the held-out commits." />
            )}
          </Card>
        </>
      )}
      <p className="text-xs text-muted-foreground">
        Commits are split by time: the latest 20% are hidden, hidden dependencies are mined from the rest, and both systems predict which service pairs change together later. Bot, bulk (over 30 files) and cross-cutting (over 4 services) commits are excluded. Evaluated {timeAgo(r.created_at)}.
      </p>
    </div>
  )
}

export default function BenchmarkPage() {
  const { current } = useCurrentRepo()
  const result = useQuery({
    queryKey: ['benchmark', current?.id, current?.last_synced_at],
    queryFn: getBenchmark,
    enabled: !!current,
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
  })
  const missing = result.error instanceof ApiError && result.error.status === 404

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 lg:py-8">
      <PageHeader
        title="Benchmark"
        description={<>Held-out evaluation on {current ? <span className="font-mono">{current.full_name}</span> : 'this repository'}: does knowing hidden dependencies predict what changes together next, better than declared edges alone?</>}
      />
      {result.isLoading ? (
        <Card><SkeletonRows rows={5} className="p-5" /></Card>
      ) : missing ? (
        <Card>
          <EmptyState
            icon={FlaskConical}
            title="No evaluation yet"
            description="The benchmark runs at the end of each sync. Wait for this repository to finish syncing, or sync it again."
            action={<Link href="/repos"><Btn>Go to repositories</Btn></Link>}
          />
        </Card>
      ) : result.error ? (
        <Card><ErrorState error={result.error} onRetry={() => result.refetch()} /></Card>
      ) : result.data ? (
        <Result r={result.data} />
      ) : null}
    </div>
  )
}
