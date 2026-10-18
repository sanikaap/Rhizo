'use client'

import { Check, Copy, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Evidence } from '@/lib/types'

export interface EvidenceEntry { tool: string; duration_ms: number; summary: string; evidence: Evidence }

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1200) }) }}
      className="absolute top-2 right-2 rounded p-1 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100 hover:bg-card hover:text-foreground"
      aria-label="Copy Cypher"
    >
      {done ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
    </button>
  )
}

export function EvidenceDrawer({ entries, onClose }: { entries: EvidenceEntry[]; onClose: () => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Evidence">
      <div className="absolute inset-0 bg-black/30 animate-fade" onClick={onClose} />
      <aside className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col border-l bg-card shadow-2xl animate-fade">
        <header className="flex items-center justify-between border-b px-5 py-3">
          <div>
            <h2 className="text-sm font-semibold">Evidence</h2>
            <p className="text-xs text-muted-foreground">Every Cypher query, parameter and returned id behind this answer</p>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-muted" aria-label="Close evidence"><X className="size-4" /></button>
        </header>
        <div className="flex-1 space-y-6 overflow-y-auto p-5 scrollbar-thin">
          {entries.map((e, i) => (
            <section key={i}>
              <div className="mb-2 flex items-center gap-2">
                <span className="grid size-5 place-items-center rounded bg-primary-soft font-mono text-[10px] font-semibold text-primary">{i + 1}</span>
                <span className="font-mono text-sm font-medium">{e.tool}</span>
                <span className="ml-auto font-mono text-xs text-muted-foreground">{e.duration_ms} ms</span>
              </div>
              <p className="mb-2 text-xs text-muted-foreground">{e.summary}</p>
              {e.evidence.cypher.map((c, j) => (
                <div key={j} className="group relative mb-2">
                  <pre className="overflow-x-auto rounded-md border bg-muted p-3 font-mono text-[11.5px] leading-5 scrollbar-thin">{c}</pre>
                  <CopyButton text={c} />
                </div>
              ))}
              <dl className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-1.5 text-xs">
                <dt className="text-muted-foreground">Params</dt>
                <dd className="font-mono break-all">{JSON.stringify(e.evidence.params)}</dd>
                <dt className="text-muted-foreground">Returned</dt>
                <dd className="flex flex-wrap gap-1">
                  {e.evidence.returned_ids.length === 0 ? <span className="text-muted-foreground">nothing</span> :
                    e.evidence.returned_ids.map((id) => <span key={id} className="rounded border bg-background px-1 font-mono text-[11px]">{id}</span>)}
                </dd>
                {e.evidence.note && (<><dt className="text-muted-foreground">Note</dt><dd>{e.evidence.note}</dd></>)}
              </dl>
            </section>
          ))}
        </div>
      </aside>
    </div>
  )
}
