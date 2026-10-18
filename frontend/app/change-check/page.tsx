'use client'

import { useMutation, useQuery } from '@tanstack/react-query'
import { ClipboardCopy, FileCode2, GitPullRequest, Loader2, Play, ShieldCheck } from 'lucide-react'
import Link from 'next/link'
import { useState } from 'react'
import { toast } from 'sonner'
import { Btn, Card, CardHeader, EmptyState, ErrorState, PageHeader, Segmented, Skeleton } from '@/components/common/primitives'
import { BasisBadge, ConfidenceBar, RiskGauge, SeverityBadge } from '@/components/common/signals'
import { changeCheck, getServices } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { ChangeCheck } from '@/lib/types'

const nameOf = (id: string) => id.replace(/^[a-z]+:/, '')

function toMarkdown(r: ChangeCheck) {
  return [
    `### Rhizo change check: risk ${r.risk_score}/100`,
    `**Changed services:** ${r.services.map((s) => `\`${s.name}\``).join(', ') || 'none mapped'}`,
    '',
    '| Impacted | Hops | Confidence | Basis |', '|---|---|---|---|',
    ...r.impacted.map((i) => `| \`${i.service.name}\` | ${i.hops} | ${i.path_confidence.toFixed(2)} | ${i.basis} |`),
    '',
    r.coupled_files.length ? `**Usually changed together:** ${r.coupled_files.map((f) => `\`${f.path}\``).join(', ')}` : '',
    r.reviewers.length ? `**Suggested reviewers:** ${r.reviewers.map((x) => `@${x.engineer.properties.handle ?? x.engineer.name}`).join(', ')}` : '',
  ].join('\n')
}

export default function ChangeCheckPage() {
  const [mode, setMode] = useState<'files' | 'services'>('files')
  const [files, setFiles] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const services = useQuery({ queryKey: ['services'], queryFn: getServices })
  const run = useMutation({ mutationFn: changeCheck })

  const fileList = files.split(/\s+/).map((f) => f.trim()).filter(Boolean)
  const canRun = mode === 'files' ? fileList.length > 0 : picked.length > 0
  const submit = () => run.mutate(mode === 'files' ? { files: fileList } : { services: picked })
  const r = run.data

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
      <PageHeader
        title="Change Check"
        description="See what a change can break before it merges: impacted services, files that usually change with it, reviewers and similar past incidents."
      />

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <Card className="h-fit">
          <CardHeader title="What's changing?" action={
            <Segmented label="Input" size="xs" value={mode} onChange={setMode} options={[{ value: 'files', label: 'Files' }, { value: 'services', label: 'Services' }]} />
          } />
          <div className="p-4">
            {mode === 'files' ? (
              <>
                <label htmlFor="files" className="mb-1.5 block text-xs text-muted-foreground">
                  Paste the output of <code className="rounded bg-muted px-1 font-mono">git diff --name-only</code>
                </label>
                <textarea
                  id="files"
                  value={files}
                  onChange={(e) => setFiles(e.target.value)}
                  rows={7}
                  spellCheck={false}
                  placeholder={"One repo-relative path per line, e.g. the output of\ngit diff --name-only main"}
                  className="w-full resize-y rounded-md border bg-background p-2.5 font-mono text-xs leading-5 outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                />
              </>
            ) : services.isLoading ? <Skeleton className="h-32" /> : (
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Services">
                {services.data?.map((s) => {
                  const on = picked.includes(s.name)
                  return (
                    <button
                      key={s.id}
                      onClick={() => setPicked((p) => (on ? p.filter((x) => x !== s.name) : [...p, s.name]))}
                      aria-pressed={on}
                      className={cn('h-7 rounded-md border px-2 font-mono text-xs transition-colors', on ? 'border-primary/40 bg-primary-soft text-primary' : 'text-muted-foreground hover:bg-muted')}
                    >
                      {s.name}
                    </button>
                  )
                })}
              </div>
            )}
            <Btn variant="primary" className="mt-4 w-full" disabled={!canRun || run.isPending} onClick={submit}>
              {run.isPending ? <Loader2 className="animate-spin" /> : <Play />}Run change check
            </Btn>
            <p className="mt-3 text-[11px] leading-4 text-muted-foreground">
              <GitPullRequest className="mr-1 inline size-3" />The same check runs on every pull request via the <code className="font-mono">rhizo-check</code> GitHub Action.
            </p>
          </div>
        </Card>

        <div className="min-w-0 space-y-6">
          {run.isPending ? (
            <Card className="p-6"><div className="flex items-center gap-6"><Skeleton className="h-24 w-32" /><div className="flex-1 space-y-2"><Skeleton className="h-4 w-1/2" /><Skeleton className="h-3 w-3/4" /><Skeleton className="h-3 w-2/3" /></div></div></Card>
          ) : run.isError ? (
            <Card><ErrorState error={run.error} onRetry={submit} /></Card>
          ) : !r ? (
            <Card><EmptyState icon={GitPullRequest} title="No check run yet" description="Add the files or services in your change and Rhizo traces every dependency path into them." className="py-16" /></Card>
          ) : (
            <>
              <Card className="flex flex-col items-center gap-6 p-5 sm:flex-row">
                <RiskGauge value={r.risk_score} />
                <div className="min-w-0 flex-1 text-center sm:text-left">
                  <p className="text-base font-medium">
                    {r.impacted.length === 0 ? 'No downstream services are affected by this change.' : `${r.impacted.length} service${r.impacted.length > 1 ? 's' : ''} can break if this change misbehaves.`}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Changed: {r.services.length ? r.services.map((s) => <code key={s.id} className="mr-1 rounded bg-muted px-1 font-mono text-xs">{s.name}</code>) : 'no files map to a known service'}
                  </p>
                  <Btn size="sm" className="mt-3" onClick={() => navigator.clipboard.writeText(toMarkdown(r)).then(() => toast.success('Copied PR comment markdown'))}>
                    <ClipboardCopy />Copy as PR comment
                  </Btn>
                </div>
              </Card>

              <Card>
                <CardHeader title="Impacted services" description="Every service with a dependency path into the change, nearest first" />
                {r.impacted.length === 0 ? <EmptyState icon={ShieldCheck} title="Contained change" description="Nothing depends on the changed services." /> : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-left text-xs text-muted-foreground">
                        <tr className="border-b">
                          <th className="px-4 py-2 font-medium">Service</th>
                          <th className="px-2 py-2 font-medium">Hops</th>
                          <th className="px-2 py-2 font-medium">Path</th>
                          <th className="px-2 py-2 font-medium">Confidence</th>
                          <th className="px-4 py-2 font-medium">Basis</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {r.impacted.map((i) => (
                          <tr key={i.service.id} className="hover:bg-muted/50">
                            <td className="px-4 py-2.5 font-mono text-[13px] font-medium">
                              {i.service.name}
                              <span className="ml-1.5 rounded bg-muted px-1 text-[10px] text-muted-foreground">T{String(i.service.properties.tier)}</span>
                            </td>
                            <td className="px-2 py-2.5 font-mono tabular-nums">{i.hops}</td>
                            <td className="max-w-xs px-2 py-2.5 font-mono text-xs text-muted-foreground">
                              <span className="line-clamp-1">{i.path.map(nameOf).join(' → ')}</span>
                            </td>
                            <td className="px-2 py-2.5"><ConfidenceBar value={i.path_confidence} /></td>
                            <td className="px-4 py-2.5"><BasisBadge basis={i.basis} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <div className="grid gap-6 xl:grid-cols-3">
                <Card>
                  <CardHeader title="Usually changed together" description="Co-change from git history" />
                  {r.coupled_files.length === 0 ? <p className="p-4 text-xs text-muted-foreground">No coupled files.</p> : (
                    <ul className="divide-y">
                      {r.coupled_files.map((f) => (
                        <li key={f.path} className="flex items-center gap-2 px-4 py-2 text-xs">
                          <FileCode2 className="size-3.5 shrink-0 text-subtle-foreground" />
                          <span className="truncate font-mono" title={f.path}>{f.path}</span>
                          <span className="ml-auto shrink-0 font-mono text-muted-foreground">{f.count}×</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
                <Card>
                  <CardHeader title="Suggested reviewers" description="Recent commits + incident history" />
                  <ul className="divide-y">
                    {r.reviewers.map((x) => (
                      <li key={x.engineer.id} className="flex items-center gap-2.5 px-4 py-2.5">
                        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary-soft text-[11px] font-semibold text-primary">{x.engineer.name.split(' ').map((p) => p[0]).join('')}</span>
                        <div className="min-w-0">
                          <div className="text-sm font-medium">{x.engineer.name}</div>
                          <div className="truncate text-xs text-muted-foreground">{x.reason}</div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </Card>
                <Card>
                  <CardHeader title="Similar past incidents" description="Overlap in affected services" />
                  {r.similar_incidents.length === 0 ? <p className="p-4 text-xs text-muted-foreground">No similar incidents.</p> : (
                    <ul className="divide-y">
                      {r.similar_incidents.map(({ incident: i, similarity }) => (
                        <li key={i.id}>
                          <Link href={`/incidents/${i.id}`} className="block px-4 py-2.5 hover:bg-muted/50">
                            <div className="flex items-center gap-2 text-xs">
                              <SeverityBadge severity={i.severity} />
                              <span className="font-mono text-muted-foreground">{i.id}</span>
                              <span className="ml-auto font-mono text-muted-foreground">{Math.round(similarity * 100)}%</span>
                            </div>
                            <div className="mt-1 text-sm">{i.title}</div>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
