'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef } from 'react'
import { deleteRepo, listRepos, loadDemoRepo } from '@/lib/api'
import { setCurrentRepoId, useCurrentRepoId } from '@/lib/repo-store'
import type { Repo, RepoStatus } from '@/lib/types'

export const SYNCING: RepoStatus[] = ['queued', 'cloning', 'detecting', 'ingesting']
const POLL_MS = 2000
const ACCOUNT_KEYS = new Set(['repos', 'me', 'health'])

export function useRepos(enabled = true) {
  return useQuery({
    queryKey: ['repos'],
    queryFn: listRepos,
    enabled,
    refetchInterval: (q) => ((q.state.data ?? []).some((r) => SYNCING.includes(r.status)) ? POLL_MS : false),
  })
}

export function useResetRepoData() {
  const qc = useQueryClient()
  return useCallback(() => {
    qc.removeQueries({ predicate: (q) => !ACCOUNT_KEYS.has(String(q.queryKey[0])) })
  }, [qc])
}

export function useSelectRepo() {
  const reset = useResetRepoData()
  return useCallback(
    (id: string | null) => {
      setCurrentRepoId(id)
      reset()
    },
    [reset],
  )
}

export function useCurrentRepo(enabled = true): { repos: Repo[] | undefined; current: Repo | undefined; loading: boolean } {
  const repos = useRepos(enabled)
  const id = useCurrentRepoId()
  const select = useSelectRepo()
  const current = repos.data?.find((r) => r.id === id)
  const lastStatus = useRef<RepoStatus | undefined>(undefined)

  useEffect(() => {
    if (!repos.data) return
    if (!current) {
      const next = repos.data.find((r) => r.status === 'ready') ?? repos.data[0]
      select(next?.id ?? null)
    }
  }, [repos.data, current, select])

  useEffect(() => {
    if (lastStatus.current && SYNCING.includes(lastStatus.current) && current?.status === 'ready') select(current.id)
    lastStatus.current = current?.status
  }, [current?.status, current?.id, select])

  return { repos: repos.data, current, loading: repos.isLoading }
}

export function useRemoveRepo(onDone?: (repo: Repo) => void) {
  const qc = useQueryClient()
  const select = useSelectRepo()
  const current = useCurrentRepoId()
  return useMutation({
    mutationFn: async (repo: Repo) => {
      await deleteRepo(repo.id)
      return repo
    },
    onSuccess: (repo) => {
      if (repo.id === current) select(null)
      qc.invalidateQueries({ queryKey: ['repos'] })
      onDone?.(repo)
    },
  })
}

export function useLoadDemo(onDone?: (repo: Repo) => void) {
  const qc = useQueryClient()
  const select = useSelectRepo()
  return useMutation({
    mutationFn: loadDemoRepo,
    onSuccess: (repo) => {
      select(repo.id)
      qc.invalidateQueries({ queryKey: ['repos'] })
      onDone?.(repo)
    },
  })
}
