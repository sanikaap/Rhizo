'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ExternalLink, FlaskConical, FolderGit2, Loader2, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Btn, Card, CardHeader, ConfirmDialog, EmptyState, ErrorState, PageHeader, SkeletonRows } from '@/components/common/primitives'
import { StatusDot } from '@/components/common/signals'
import { DemoBadge, RemoveDemoButton } from '@/components/layout/demo-banner'
import { SYNCING, useCurrentRepo, useLoadDemo, useRemoveRepo, useRepos, useSelectRepo } from '@/hooks/use-repos'
import { ApiError, connectRepo, syncRepo } from '@/lib/api'
import { timeAgo } from '@/lib/format'
import type { Repo } from '@/lib/types'
import { cn } from '@/lib/utils'

const GITHUB_URL = /^https:\/\/github\.com\/[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}\/[A-Za-z0-9._-]{1,100}\/?$/

const STATUS_LABEL: Record<Repo['status'], string> = {
  queued: 'Queued',
  cloning: 'Cloning',
  detecting: 'Detecting services',
  ingesting: 'Building the graph',
  ready: 'Ready',
  failed: 'Failed',
}

function ConnectForm() {
  const qc = useQueryClient()
  const select = useSelectRepo()
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const connect = useMutation({
    mutationFn: connectRepo,
    onSuccess: (repo) => {
      setUrl('')
      qc.invalidateQueries({ queryKey: ['repos'] })
      select(repo.id)
      toast.success(`Connected ${repo.full_name}. The first sync has started.`)
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Could not connect the repository.'),
  })
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const value = url.trim()
    if (!GITHUB_URL.test(value)) return setError('Use a public GitHub URL like https://github.com/owner/repo')
    setError(null)
    connect.mutate(value)
  }
  return (
    <Card>
      <CardHeader title="Connect a repository" description="Public GitHub repositories only. Nothing in the repo is ever run." />
      <form onSubmit={submit} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start">
        <label className="min-w-0 flex-1">
          <span className="sr-only">GitHub repository URL</span>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            className="h-9 w-full rounded-md border bg-background px-3 font-mono text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            aria-invalid={!!error}
            aria-describedby={error ? 'connect-error' : undefined}
          />
          {error && <p id="connect-error" className="mt-1.5 text-xs text-danger">{error}</p>}
        </label>
        <Btn type="submit" variant="primary" className="h-9" disabled={connect.isPending}>
          {connect.isPending && <Loader2 className="animate-spin" />}Connect
        </Btn>
      </form>
    </Card>
  )
}

function RepoRow({ repo, current }: { repo: Repo; current: boolean }) {
  const qc = useQueryClient()
  const select = useSelectRepo()
  const syncing = SYNCING.includes(repo.status)
  const refresh = () => qc.invalidateQueries({ queryKey: ['repos'] })
  const sync = useMutation({
    mutationFn: () => syncRepo(repo.id),
    onSuccess: refresh,
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not start the sync.'),
  })
  const [confirming, setConfirming] = useState(false)
  const remove = useRemoveRepo(() => {
    setConfirming(false)
    toast.success(`Deleted ${repo.full_name} and its graph.`)
  })
  const tone = repo.status === 'ready' ? 'success' : repo.status === 'failed' ? 'danger' : 'warning'

  return (
    <li className={cn('space-y-2 px-5 py-4', current && 'bg-primary/5')}>
      <div className="flex flex-wrap items-center gap-3">
        <StatusDot tone={tone} pulse={syncing} />
        <button onClick={() => select(repo.id)} className="min-w-0 text-left font-mono text-sm font-semibold hover:underline" title="Work on this repository">
          {repo.full_name}
        </button>
        {repo.is_demo && <DemoBadge />}
        {current && <span className="rounded bg-primary/10 px-1.5 text-[11px] font-medium text-primary">current</span>}
        <a href={repo.url} target="_blank" rel="noreferrer noopener" className="text-subtle-foreground hover:text-foreground" aria-label={`Open ${repo.full_name} on GitHub`}>
          <ExternalLink className="size-3.5" />
        </a>
        <span className="ml-auto flex items-center gap-2">
          <span className="text-xs text-muted-foreground">{repo.last_synced_at ? `Synced ${timeAgo(repo.last_synced_at)}` : 'Never synced'}</span>
          <Btn size="sm" onClick={() => sync.mutate()} disabled={syncing || sync.isPending}>
            <RefreshCw className={cn(syncing && 'animate-spin')} />Sync
          </Btn>
          {repo.is_demo ? (
            <RemoveDemoButton repo={repo} />
          ) : (
            <Btn size="sm" variant="ghost" disabled={syncing || remove.isPending} onClick={() => setConfirming(true)} aria-label={`Delete ${repo.full_name}`}>
              <Trash2 />
            </Btn>
          )}
        </span>
        {confirming && (
          <ConfirmDialog
            title={`Delete ${repo.full_name}?`}
            body="Its graph, incidents and evaluation are removed. You can connect it again later."
            confirmLabel="Delete"
            pending={remove.isPending}
            onClose={() => setConfirming(false)}
            onConfirm={() => remove.mutate(repo, { onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not delete the repository.') })}
          />
        )}
      </div>
      <div className="flex items-center gap-3 text-xs">
        <span className={cn('font-medium', repo.status === 'failed' ? 'text-danger' : 'text-muted-foreground')}>{STATUS_LABEL[repo.status]}</span>
        {syncing && (
          <div className="h-1.5 w-40 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={repo.progress} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full bg-primary transition-[width] duration-500" style={{ width: `${repo.progress}%` }} />
          </div>
        )}
      </div>
      {repo.status === 'failed' && repo.error && (
        <p className="flex items-start gap-1.5 text-xs text-danger"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{repo.error}</p>
      )}
      {repo.message && repo.status !== 'failed' && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          {repo.status === 'ready' && <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success" />}
          {repo.message}
        </p>
      )}
    </li>
  )
}

function LoadDemo() {
  const load = useLoadDemo((repo) => toast.success(`Loading ${repo.full_name}. It appears here as it syncs.`))
  return (
    <Btn onClick={() => load.mutate(undefined, { onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not load the demo.') })} disabled={load.isPending}>
      {load.isPending ? <Loader2 className="animate-spin" /> : <FlaskConical />}Load demo repo
    </Btn>
  )
}

export default function ReposPage() {
  const repos = useRepos()
  const { current } = useCurrentRepo()
  const hasDemo = !!repos.data?.some((r) => r.is_demo)

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 sm:px-6 lg:py-8">
      <PageHeader
        title="Repositories"
        description="Rhizo builds its graph from a repository you connect: services from compose files, Kubernetes manifests and Python/JS imports; owners and incidents from its own history."
      />
      <ConnectForm />
      <Card>
        <CardHeader title="Connected" description="Status updates live while a sync runs." action={repos.data?.length && !hasDemo ? <LoadDemo /> : undefined} />
        {repos.isLoading ? (
          <SkeletonRows rows={3} className="p-5" />
        ) : repos.error ? (
          <ErrorState error={repos.error} onRetry={() => repos.refetch()} />
        ) : !repos.data?.length ? (
          <EmptyState
            icon={FolderGit2}
            title="Connect your GitHub repo"
            description="Paste a public GitHub URL above. The graph, Investigator, incidents and benchmark all work from it. Or load the demo to look around first."
            action={<LoadDemo />}
          />
        ) : (
          <ul className="divide-y">{repos.data.map((r) => <RepoRow key={r.id} repo={r} current={r.id === current?.id} />)}</ul>
        )}
      </Card>
    </div>
  )
}
