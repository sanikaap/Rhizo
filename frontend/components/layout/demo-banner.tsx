'use client'

import { FlaskConical, Loader2, Trash2 } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { toast } from 'sonner'
import { Btn, ConfirmDialog } from '@/components/common/primitives'
import { SYNCING, useCurrentRepo, useRemoveRepo } from '@/hooks/use-repos'
import { ApiError } from '@/lib/api'
import type { Repo } from '@/lib/types'

export function DemoBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-warning-soft px-1.5 py-px text-[11px] font-semibold text-warning">
      <FlaskConical className="size-3" />Demo
    </span>
  )
}

export function RemoveDemoButton({ repo, size = 'sm', onRemoved }: { repo: Repo; size?: 'sm' | 'md'; onRemoved?: () => void }) {
  const [open, setOpen] = useState(false)
  const remove = useRemoveRepo(() => {
    setOpen(false)
    toast.success('Demo data removed. It will not come back unless you load it again.')
    onRemoved?.()
  })
  const syncing = SYNCING.includes(repo.status)
  return (
    <>
      <Btn size={size} onClick={() => setOpen(true)} disabled={syncing && repo.status !== 'queued'} title={syncing ? 'Wait for the demo to finish loading' : undefined}>
        <Trash2 />Remove demo data
      </Btn>
      {open && (
        <ConfirmDialog
          title="Remove demo data?"
          body={<>This deletes the <span className="font-mono">{repo.full_name}</span> graph, its incidents and its evaluation from your account only. The demo is not loaded again unless you choose Load demo repo on the Repositories page.</>}
          confirmLabel="Remove demo"
          pending={remove.isPending}
          onClose={() => setOpen(false)}
          onConfirm={() =>
            remove.mutate(repo, { onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not remove the demo.') })
          }
        />
      )}
    </>
  )
}

export function DemoBanner() {
  const { current } = useCurrentRepo()
  const router = useRouter()
  if (!current?.is_demo) return null
  const syncing = SYNCING.includes(current.status)
  return (
    <div className="flex flex-wrap items-center gap-3 border-b bg-warning-soft/60 px-4 py-2.5 text-sm sm:px-8" role="status">
      <DemoBadge />
      <p className="min-w-0 flex-1 text-muted-foreground">
        {syncing ? (
          <span className="inline-flex items-center gap-2">
            <Loader2 className="size-3.5 animate-spin" />
            Preparing the demo graph from <span className="font-mono text-foreground">{current.full_name}</span>: {current.message ?? 'queued'} ({current.progress}%)
          </span>
        ) : current.status === 'failed' ? (
          <>The demo could not be built: {current.error}</>
        ) : (
          <>You are exploring <span className="font-mono text-foreground">{current.full_name}</span>, built from its public git history by the same pipeline as any connected repo.</>
        )}
      </p>
      <Link href="/repos" className="text-xs font-medium text-primary hover:underline">Connect your GitHub repo</Link>
      <RemoveDemoButton repo={current} onRemoved={() => router.push('/repos')} />
    </div>
  )
}
