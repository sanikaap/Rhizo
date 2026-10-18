'use client'

import { ChevronsUpDown, FolderGit2 } from 'lucide-react'
import Link from 'next/link'
import { StatusDot } from '@/components/common/signals'
import { DemoBadge } from '@/components/layout/demo-banner'
import { SYNCING, useCurrentRepo, useSelectRepo } from '@/hooks/use-repos'

export function RepoSwitcher() {
  const { repos, current } = useCurrentRepo()
  const select = useSelectRepo()
  if (!repos?.length) {
    return (
      <Link href="/repos" className="flex h-9 items-center gap-2 rounded-md border px-2.5 text-sm text-muted-foreground hover:bg-muted">
        <FolderGit2 className="size-4" />Connect your GitHub repo
      </Link>
    )
  }
  const syncing = current && SYNCING.includes(current.status)
  return (
    <div className="flex items-center gap-2">
    {current?.is_demo && <DemoBadge />}
    <label className="relative flex h-9 items-center gap-2 rounded-md border bg-background pr-2 pl-2.5 text-sm hover:bg-muted">
      <StatusDot tone={current?.status === 'failed' ? 'danger' : syncing ? 'warning' : 'success'} pulse={!!syncing} />
      <span className="sr-only">Repository</span>
      <select
        value={current?.id ?? ''}
        onChange={(e) => (e.target.value === '__manage' ? window.location.assign('/repos') : select(e.target.value))}
        className="max-w-[12rem] cursor-pointer appearance-none truncate bg-transparent pr-5 font-mono text-[13px] outline-none"
      >
        {repos.map((r) => (
          <option key={r.id} value={r.id}>{r.full_name}{r.is_demo ? ' [Demo]' : ''}{SYNCING.includes(r.status) ? ' (syncing)' : r.status === 'failed' ? ' (failed)' : ''}</option>
        ))}
        <option value="__manage">Manage repositories…</option>
      </select>
      <ChevronsUpDown className="pointer-events-none absolute right-2 size-3.5 text-subtle-foreground" />
    </label>
    </div>
  )
}
