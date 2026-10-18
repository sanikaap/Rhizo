'use client'

import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowUp, Bomb, Check, ChevronRight, CornerDownRight, Crown, FileSearch, Glasses, Info, Loader2, RotateCcw, Sparkles, Square, Stethoscope, Wrench } from 'lucide-react'
import { useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { EvidenceDrawer, type EvidenceEntry } from '@/components/agent/evidence-drawer'
import { Markdown } from '@/components/agent/markdown'
import { Btn, ErrorState, Kbd } from '@/components/common/primitives'
import { BasisBadge } from '@/components/common/signals'
import { GraphCanvas, GraphLegend } from '@/components/graph/graph-canvas'
import { HeaderActions } from '@/components/layout/header-actions'
import { type ToolStep, type Turn, useAgent } from '@/hooks/use-agent'
import { getGraph, getHealth } from '@/lib/api'
import { timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

const STARTERS = [
  { icon: Bomb, label: 'Impact Analysis', q: 'What breaks if paymentservice fails?' },
  { icon: Stethoscope, label: 'Root Cause', q: 'Why is frontend returning 5xx errors?' },
  { icon: Glasses, label: 'Hidden Coupling', q: 'Find hidden dependencies nobody declared' },
  { icon: Crown, label: 'Criticality', q: 'Which services are the most critical?' },
]

function Highlighted({ text, names }: { text: string; names: Set<string> }) {
  return (
    <>
      {text.split(/(\s+)/).map((w, i) =>
        names.has(w) ? <code key={i} className="rounded-sm bg-primary-soft px-1 font-mono text-[11px] text-primary">{w}</code> : w,
      )}
    </>
  )
}

const label = 'text-[11px] font-semibold tracking-[0.1em] text-subtle-foreground uppercase'

function followUps(t: Turn): string[] {
  const svc = t.steps.map((s) => (s.args as { service?: string } | null)?.service).find(Boolean)
  const used = new Set(t.steps.map((s) => s.name))
  const out: [string, string][] = svc
    ? [
        ['get_upstream_suspects', `Why would ${svc} fail?`],
        ['get_blast_radius', `What breaks if ${svc} fails?`],
        ['find_hidden_dependencies', `Find hidden dependencies of ${svc}`],
      ]
    : [
        ['find_hidden_dependencies', 'Find hidden dependencies'],
        ['rank_criticality', 'Which services are most critical?'],
        ['get_blast_radius', 'What breaks if currencyservice fails?'],
      ]
  return out.filter(([tool]) => !used.has(tool)).map(([, q]) => q).slice(0, 3)
}

function Steps({ steps }: { steps: ToolStep[] }) {
  const [open, setOpen] = useState<string | null>(null)
  if (!steps.length) return null
  return (
    <ol className="mb-3 space-y-1" aria-label="Tool calls">
      {steps.map((s) => (
        <li key={s.id} className="rounded-md border bg-background text-xs">
          <button onClick={() => setOpen(open === s.id ? null : s.id)} className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left" aria-expanded={open === s.id}>
            {s.status === 'running' ? <Loader2 className="size-3.5 animate-spin text-primary" /> : <Check className="size-3.5 text-success" />}
            <Wrench className="size-3 text-subtle-foreground" />
            <span className="font-mono font-medium">{s.name}</span>
            <span className="truncate text-muted-foreground">{s.summary ?? 'querying graph…'}</span>
            {s.duration_ms !== undefined && <span className="ml-auto shrink-0 font-mono text-subtle-foreground">{s.duration_ms}ms</span>}
            <ChevronRight className={cn('size-3.5 shrink-0 text-subtle-foreground transition-transform', open === s.id && 'rotate-90', s.duration_ms === undefined && 'ml-auto')} />
          </button>
          {open === s.id && (
            <pre className="overflow-x-auto border-t px-2.5 py-2 font-mono text-[11px] text-muted-foreground">{JSON.stringify(s.args, null, 2)}</pre>
          )}
        </li>
      ))}
    </ol>
  )
}

function TurnView({
  turn, onEvidence, onSelect, active, names, onEntity, onFollowUp, last,
}: {
  turn: Turn; onEvidence: (e: EvidenceEntry[]) => void; onSelect: () => void; active: boolean
  names: string[]; onEntity: (name: string) => void; onFollowUp: (q: string) => void; last: boolean
}) {
  return (
    <article className="animate-rise space-y-3">
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-lg rounded-br-sm bg-primary px-3 py-2 text-sm text-primary-foreground">{turn.question}</p>
      </div>
      <div
        onClick={onSelect}
        className={cn('rounded-lg border bg-card p-3.5 transition-colors', active && turn.highlight && 'border-primary/40 ring-1 ring-primary/20')}
      >
        <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Sparkles className="size-3.5 text-primary" />Rhizo
          {turn.status === 'streaming' && !turn.answer && <span className="ml-1 text-subtle-foreground">thinking…</span>}
        </div>
        <Steps steps={turn.steps} />
        {turn.insufficient ? (
          <div className="flex gap-2.5 rounded-md border border-warning/40 bg-warning-soft p-3 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
            <div>
              <p className="font-medium">Not enough graph data to answer</p>
              <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{turn.insufficient}</p>
            </div>
          </div>
        ) : turn.error ? (
          <div className="flex gap-2 rounded-md bg-danger-soft p-3 text-sm text-danger"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{turn.error}</div>
        ) : (
          turn.answer && <div className={cn(turn.status === 'streaming' && 'caret')}><Markdown text={turn.answer} names={turn.status === 'done' ? names : undefined} onEntity={onEntity} /></div>
        )}
        {turn.status === 'done' && !turn.insufficient && (
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t pt-2.5">
            {turn.stopped ? <span className="text-[11px] font-medium text-muted-foreground">Stopped</span> : turn.basis && <BasisBadge basis={turn.basis} />}
            <span className="font-mono text-[11px] text-muted-foreground">{turn.took_ms} ms · {turn.steps.length} tool call{turn.steps.length === 1 ? '' : 's'}</span>
            {turn.evidence.length > 0 && (
              <button onClick={(e) => { e.stopPropagation(); onEvidence(turn.evidence) }} className="ml-auto flex items-center gap-1 text-xs font-medium text-primary hover:underline">
                <FileSearch className="size-3.5" />View evidence
              </button>
            )}
          </div>
        )}
      </div>
      {last && turn.status === 'done' && !turn.stopped && (
        <div className="flex flex-wrap gap-1.5 pl-1 animate-fade" aria-label="Suggested follow-ups">
          {followUps(turn).map((q) => (
            <button key={q} onClick={() => onFollowUp(q)} className="flex items-center gap-1 rounded-full border bg-card px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground">
              <CornerDownRight className="size-3" />{q}
            </button>
          ))}
        </div>
      )}
    </article>
  )
}

function Investigator() {
  const params = useSearchParams()
  const { turns, ask, running, stop, reset } = useAgent()
  const [focusId, setFocusId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [evidence, setEvidence] = useState<EvidenceEntry[] | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const graph = useQuery({ queryKey: ['graph', {}], queryFn: () => getGraph() })
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 30_000 })
  const scroller = useRef<HTMLDivElement>(null)
  const asked = useRef(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const q = params.get('q')
    if (q && !asked.current) { asked.current = true; ask(q) }
  }, [params, ask])

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' })
  }, [turns])

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (e.key === '/' && !el.closest('input, textarea, [contenteditable]')) { e.preventDefault(); inputRef.current?.focus() }
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [])

  const names = useMemo(() => graph.data?.nodes.map((n) => n.name) ?? [], [graph.data])
  const nameSet = useMemo(() => new Set(names), [names])
  const counts = { services: graph.data?.nodes.filter((n) => n.label === 'Service').length ?? 0, resources: graph.data?.nodes.filter((n) => n.label === 'Resource').length ?? 0 }
  const up = health.data?.falkordb === 'up'
  const focusEntity = (name: string) => {
    const id = graph.data?.nodes.find((n) => n.name === name)?.id
    if (!id) return
    if (id !== focusId) return setFocusId(id)
    setFocusId(null)
    requestAnimationFrame(() => setFocusId(id))
  }

  const latest = turns.at(-1)
  useEffect(() => { if (latest) setActiveId(latest.id) }, [latest?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const active = turns.find((t) => t.id === activeId)
  const highlight = useMemo(() => active?.highlight ?? null, [active?.highlight])

  const submit = (q = input) => {
    if (!q.trim() || running) return
    ask(q.trim())
    setInput('')
  }

  return (
    <div className="flex h-[calc(100dvh-4rem)] flex-col lg:flex-row">
      <HeaderActions>
        <span className="hidden items-center gap-2 rounded-md border bg-card px-3 py-2 text-xs sm:flex">
          <span className={cn('size-2 rounded-full', health.isLoading ? 'bg-subtle-foreground' : up ? 'bg-success' : 'bg-danger')} />
          <span className="text-muted-foreground">Graph {up ? 'live' : health.isLoading ? '…' : 'offline'}:</span>
          <span className="font-semibold">FalkorDB</span>
        </span>
      </HeaderActions>

      <section className="flex min-h-0 flex-1 flex-col border-r bg-card lg:max-w-[420px]" aria-label="Conversation">
        <div className="flex items-start justify-between gap-3 border-b px-6 py-5">
          <div>
            <h1 className="flex items-center gap-2 text-sm font-bold tracking-[0.1em] uppercase"><Info className="size-4 text-primary" />Inquiry engine</h1>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">Answers are derived directly from the dependency graph. Every claim includes verifiable provenance.</p>
          </div>
          {turns.length > 0 && <Btn size="sm" variant="ghost" onClick={reset} disabled={running}><RotateCcw />New</Btn>}
        </div>

        <div ref={scroller} className="flex-1 space-y-6 overflow-y-auto px-6 py-6 scrollbar-thin" aria-live="polite">
          {turns.length === 0 ? (
            <div>
              <div className={cn(label, 'mb-4')}>Start your investigation</div>
              <ul className="space-y-3">
                {STARTERS.map((s) => (
                  <li key={s.q}>
                    <button onClick={() => submit(s.q)} className="group flex w-full items-center gap-4 rounded-md border bg-background/60 p-4 text-left transition-colors hover:border-primary/40 hover:bg-card">
                      <span className="grid size-9 shrink-0 place-items-center rounded-md border bg-card text-subtle-foreground group-hover:text-primary"><s.icon className="size-4" /></span>
                      <span className="min-w-0">
                        <span className="block text-[13px] font-semibold">{s.label}</span>
                        <span className="mt-0.5 block text-xs text-muted-foreground">&ldquo;<Highlighted text={s.q} names={nameSet} />&rdquo;</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            turns.map((t, i) => (
              <TurnView
                key={t.id} turn={t} active={t.id === activeId} last={i === turns.length - 1}
                onSelect={() => setActiveId(t.id)} onEvidence={setEvidence}
                names={names} onEntity={focusEntity} onFollowUp={(q) => submit(q)}
              />
            ))
          )}
        </div>

        <form onSubmit={(e) => { e.preventDefault(); submit() }} className="border-t bg-background/60 px-6 py-5">
          <div className="flex gap-2 rounded-md border bg-card p-3 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20">
            <ChevronRight className="mt-1.5 size-4 shrink-0 text-primary" />
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
              rows={2}
              placeholder="e.g. What breaks if catalog-cache goes down?"
              className="max-h-32 min-h-12 flex-1 resize-none bg-transparent py-1 text-sm outline-none placeholder:text-subtle-foreground"
              aria-label="Question"
            />
            {running ? (
              <Btn type="button" className="size-9 self-end px-0" onClick={stop} aria-label="Stop answer" title="Stop">
                <Square className="fill-current" />
              </Btn>
            ) : (
              <Btn type="submit" variant="primary" className="size-9 self-end px-0" disabled={!input.trim()} aria-label="Send">
                <ArrowUp />
              </Btn>
            )}
          </div>
          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-subtle-foreground">
            <span><Kbd>Enter</Kbd> to ask</span>
            <span><Kbd>Shift + Enter</Kbd> for newline</span>
            <span><Kbd>/</Kbd> to focus</span>
            <span className="w-full">Click a service name in an answer to find it on the graph.</span>
          </p>
        </form>
      </section>

      <section className="relative hidden min-h-0 flex-1 flex-col lg:flex" aria-label="Live graph">
        <div className="flex items-center gap-4 border-b bg-card px-6 py-3.5">
          <GraphLegend />
          <span className="ml-auto text-[11px] text-muted-foreground">A → B : A depends on B</span>
        </div>
        <div className="min-h-0 flex-1">
          {graph.isError ? <ErrorState error={graph.error} className="h-full justify-center" /> :
            graph.data && <GraphCanvas nodes={graph.data.nodes} edges={graph.data.edges} highlight={highlight} layout="layered" focusId={focusId} selectedId={focusId} />}
        </div>
        <div className="flex items-center gap-6 border-t bg-background px-6 py-2.5 text-[11px] font-semibold tracking-[0.08em] text-subtle-foreground uppercase">
          <span className="flex items-center gap-2">
            <span className={cn('size-1.5 rounded-full', up ? 'bg-success' : 'bg-subtle-foreground')} />
            Data freshness: {graph.dataUpdatedAt ? timeAgo(new Date(graph.dataUpdatedAt).toISOString()) : '…'}
          </span>
          <span className="ml-auto">{counts.services} services</span>
          <span>{counts.resources} resources</span>
          {highlight ? (
            <span className="text-indigo-600">{highlight.nodeIds.length} nodes in answer</span>
          ) : <span>Paths light up as tools return</span>}
        </div>
      </section>

      {evidence && <EvidenceDrawer entries={evidence} onClose={() => setEvidence(null)} />}
    </div>
  )
}

export default function InvestigatorPage() {
  return <Suspense><Investigator /></Suspense>
}
