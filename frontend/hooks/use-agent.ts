'use client'

import { useCallback, useRef, useState } from 'react'
import type { EvidenceEntry } from '@/components/agent/evidence-drawer'
import { askAgent } from '@/lib/api'
import { edgeIdsFromPaths, type Highlight, hopsFromPaths } from '@/lib/graph-utils'
import type { Basis } from '@/lib/types'

export interface ToolStep { id: string; name: string; args: unknown; status: 'running' | 'done'; duration_ms?: number; summary?: string }
export interface Turn {
  id: string
  question: string
  steps: ToolStep[]
  evidence: EvidenceEntry[]
  answer: string
  status: 'streaming' | 'done' | 'error'
  insufficient?: string
  stopped?: boolean
  error?: string
  basis?: Basis
  took_ms?: number
  highlight?: Highlight
}

export function useAgent() {
  const [turns, setTurns] = useState<Turn[]>([])
  const busy = useRef(false)
  const stopRef = useRef(false)
  const [running, setRunning] = useState(false)

  const ask = useCallback(async (question: string, ctx?: { service?: string }) => {
    if (busy.current || !question.trim()) return
    busy.current = true
    stopRef.current = false
    setRunning(true)
    const id = crypto.randomUUID()
    const patch = (fn: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.id === id ? fn(t) : t)))
    setTurns((ts) => [...ts, { id, question, steps: [], evidence: [], answer: '', status: 'streaming' }])

    try {
      for await (const ev of askAgent(question, ctx)) {
        if (stopRef.current) {
          patch((t) => ({ ...t, status: 'done', stopped: true, steps: t.steps.map((s) => ({ ...s, status: 'done' })) }))
          break
        }
        switch (ev.type) {
          case 'tool_call':
            patch((t) => ({ ...t, steps: [...t.steps, { id: ev.data.id, name: ev.data.name, args: ev.data.args, status: 'running' }] }))
            break
          case 'tool_result':
            patch((t) => {
              const step = t.steps.find((s) => s.id === ev.data.id)
              return {
                ...t,
                steps: t.steps.map((s) => (s.id === ev.data.id ? { ...s, status: 'done', duration_ms: ev.data.duration_ms, summary: ev.data.summary } : s)),
                evidence: [...t.evidence, { tool: step?.name ?? 'tool', duration_ms: ev.data.duration_ms, summary: ev.data.summary, evidence: ev.data.evidence }],
              }
            })
            break
          case 'graph_path': {
            const { node_ids, edge_ids, paths } = ev.data
            const hop = paths.length ? hopsFromPaths(paths) : undefined
            patch((t) => ({
              ...t,
              highlight: {
                nodeIds: node_ids,
                edgeIds: edge_ids.length ? edge_ids : edgeIdsFromPaths(paths),
                hopById: hop,
                rootIds: hop ? undefined : node_ids.slice(0, 1),
                animate: !!hop,
              },
            }))
            break
          }
          case 'insufficient_data':
            patch((t) => ({ ...t, insufficient: ev.data.reason }))
            break
          case 'answer_token':
            patch((t) => ({ ...t, answer: t.answer + ev.data.text }))
            break
          case 'error':
            patch((t) => ({ ...t, status: 'error', error: ev.data.message }))
            break
          case 'done':
            patch((t) => ({ ...t, status: t.status === 'error' ? 'error' : 'done', basis: ev.data.basis, took_ms: ev.data.took_ms }))
            break
        }
      }
    } catch (e) {
      patch((t) => ({ ...t, status: 'error', error: e instanceof Error ? e.message : 'Agent stream failed' }))
    } finally {
      busy.current = false
      setRunning(false)
    }
  }, [])

  return { turns, ask, running, stop: () => { stopRef.current = true }, reset: () => setTurns([]) }
}
