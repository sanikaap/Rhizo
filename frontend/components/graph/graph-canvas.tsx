'use client'

import { forceCollide } from 'd3-force-3d'
import dynamic from 'next/dynamic'
import { Minus, Plus, Scan } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ForceGraphMethods, LinkObject, NodeObject } from 'react-force-graph-2d'
import { DASH, type Highlight, layeredPositions, type Palette, readPalette, withAlpha } from '@/lib/graph-utils'
import { cn } from '@/lib/utils'
import type { GraphEdge, GraphNode } from '@/lib/types'

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false }) as unknown as typeof import('react-force-graph-2d').default

type ND = { id: string; node: GraphNode }
type LD = { id: string; edge: GraphEdge }
type N = NodeObject<ND>
type L = LinkObject<ND, LD>

export interface GraphCanvasProps {
  nodes: GraphNode[]
  edges: GraphEdge[]
  highlight?: Highlight | null
  selectedId?: string | null
  onSelectNode?: (id: string | null) => void
  className?: string
  showLabels?: boolean
  layout?: 'force' | 'layered'
  focusId?: string | null
}

const esc = (v: unknown) => String(v).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
const radius = (n: GraphNode) => (n.label === 'Service' ? 7 : n.label === 'Resource' ? 6.5 : 4.5)

export function GraphCanvas({ nodes, edges, highlight, selectedId, onSelectNode, className, showLabels = true, layout = 'force', focusId }: GraphCanvasProps) {
  const wrap = useRef<HTMLDivElement>(null)
  const fg = useRef<ForceGraphMethods<N, L> | undefined>(undefined)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [hover, setHover] = useState<string | null>(null)
  const [pal, setPal] = useState<Palette | null>(null)
  const [revealHop, setRevealHop] = useState(Infinity)
  const fitted = useRef(false)

  const nodeCache = useRef(new Map<string, N>())
  const data = useMemo(() => {
    const ns = nodes.map((n) => {
      const prev = nodeCache.current.get(n.id)
      const obj = prev ? Object.assign(prev, { node: n }) : ({ id: n.id, node: n } as N)
      nodeCache.current.set(n.id, obj)
      return obj
    })
    const ids = new Set(nodes.map((n) => n.id))
    const ls = edges
      .filter((e) => ids.has(e.source_id) && ids.has(e.target_id))
      .map((e) => ({ id: e.id, source: e.source_id, target: e.target_id, edge: e }) as L)
    return { nodes: ns, links: ls }
  }, [nodes, edges])

  useEffect(() => setPal(readPalette()), [])

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    fg.current?.d3Force('charge')?.strength(-260)
    fg.current?.d3Force('link')?.distance(70)
    fg.current?.d3Force('collide', forceCollide<N>((n) => radius(n.node) + 12))
  }, [data])

  useEffect(() => {
    if (layout === 'layered') {
      const pos = layeredPositions(data.nodes.map((n) => n.id), edges)
      for (const n of data.nodes) {
        const p = pos.get(n.id)!
        n.fx = p.x; n.fy = p.y
      }
    } else for (const n of data.nodes) { n.fx = undefined; n.fy = undefined }
    fg.current?.d3ReheatSimulation()
  }, [data, edges, layout])

  const firstLayout = useRef(true)
  useEffect(() => {
    if (firstLayout.current) { firstLayout.current = false; return }
    fitted.current = false
    fg.current?.d3ReheatSimulation()
  }, [layout])

  useEffect(() => {
    const n = focusId ? nodeCache.current.get(focusId) : undefined
    if (n?.x === undefined || !fg.current) return
    fg.current.centerAt(n.x, n.y, 500)
    if ((fg.current.zoom() ?? 1) < 1.6) fg.current.zoom(1.8, 500)
  }, [focusId])

  useEffect(() => {
    if (!highlight?.animate || !highlight.hopById) { setRevealHop(Infinity); return }
    const max = Math.max(0, ...Object.values(highlight.hopById))
    setRevealHop(0)
    let h = 0
    const t = setInterval(() => {
      h += 1
      setRevealHop(h)
      if (h >= max) clearInterval(t)
    }, 250)
    return () => clearInterval(t)
  }, [highlight])

  const hl = useMemo(() => {
    if (!highlight) return null
    const visible = (id: string) => (highlight.hopById?.[id] ?? 0) <= revealHop
    return {
      nodes: new Set(highlight.nodeIds.filter(visible)),
      edges: new Set(highlight.edgeIds),
      hop: highlight.hopById ?? {},
      roots: new Set(highlight.rootIds ?? Object.entries(highlight.hopById ?? {}).filter(([, h]) => h === 0).map(([id]) => id)),
      visible,
    }
  }, [highlight, revealHop])

  const neighbours = useMemo(() => {
    if (!hover) return null
    const s = new Set([hover])
    for (const e of edges) {
      if (e.source_id === hover) s.add(e.target_id)
      if (e.target_id === hover) s.add(e.source_id)
    }
    return s
  }, [hover, edges])

  const nodeAlpha = (id: string) => {
    if (hl) return hl.nodes.has(id) ? 1 : 0.15
    if (neighbours) return neighbours.has(id) ? 1 : 0.25
    return 1
  }
  const linkOn = (l: L) => {
    const s = (l.source as N).id ?? (l.source as string)
    const t = (l.target as N).id ?? (l.target as string)
    if (hl) return hl.edges.has(l.id) && hl.visible(s) && hl.visible(t)
    if (neighbours) return s === hover || t === hover
    return true
  }

  const fit = () => {
    const box = fg.current?.getGraphBbox()
    if (!fg.current || !box || !size.w) return
    const pad = 64
    const bw = Math.max(1, box.x[1] - box.x[0])
    const bh = Math.max(1, box.y[1] - box.y[0])
    const k = Math.min(2.2, (size.w - pad * 2) / bw, (size.h - pad * 2) / bh)
    fg.current.centerAt((box.x[0] + box.x[1]) / 2, (box.y[0] + box.y[1]) / 2, 300)
    fg.current.zoom(Math.max(0.2, k), 300)
  }
  const zoomBy = (k: number) => fg.current?.zoom((fg.current?.zoom() ?? 1) * k, 150)

  useEffect(() => {
    if (!fitted.current || !size.w) return
    const t = setTimeout(fit, 200)
    return () => clearTimeout(t)
  }, [size.w, size.h]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={wrap} className={cn('dot-grid relative h-full min-h-[320px] w-full overflow-hidden', className)}>
      {pal && size.w > 0 && (
        <ForceGraph2D<ND, LD>
          ref={fg as never}
          width={size.w}
          height={size.h}
          graphData={data}
          backgroundColor="rgba(0,0,0,0)"
          cooldownTicks={120}
          onEngineStop={() => {
            if (!fitted.current) { fit(); fitted.current = true }
          }}
          nodeRelSize={1}
          nodeVal={(n) => radius(n.node) ** 2}
          nodeLabel={(n) =>
            `<div style="font:12px var(--font-sans);padding:6px 8px;border-radius:6px;background:var(--popover);color:var(--popover-foreground);border:1px solid var(--border)"><b style="font-family:var(--font-mono)">${esc(n.node.name)}</b><br/><span style="color:var(--muted-foreground)">${esc(n.node.label)}${n.node.properties.tier ? ` · tier ${esc(n.node.properties.tier)}` : ''}${n.node.properties.kind ? ` · ${esc(n.node.properties.kind)}` : ''}${n.node.risk_score !== undefined ? ` · criticality ${n.node.risk_score}` : ''}</span></div>`
          }
          onNodeHover={(n) => setHover(n?.id ?? null)}
          onNodeClick={(n) => onSelectNode?.(n.id)}
          onBackgroundClick={() => onSelectNode?.(null)}
          nodeCanvasObject={(n, ctx, scale) => {
            const g = n.node
            const r = radius(g)
            const x = n.x!, y = n.y!
            const a = nodeAlpha(n.id)
            const hop = hl?.hop[n.id]
            const isRoot = hl?.roots.has(n.id)
            const isVictim = hl && hl.nodes.has(n.id) && !isRoot && hop !== undefined
            const selected = n.id === selectedId
            let fill = g.label === 'Resource' ? pal.resource : g.label === 'Engineer' ? pal.engineer : pal.service
            if (isRoot) fill = pal.danger
            else if (isVictim) fill = pal.warning
            ctx.globalAlpha = a
            ctx.beginPath()
            if (g.label === 'Resource') ctx.roundRect(x - r - 2.5, y - r - 2.5, (r + 2.5) * 2, (r + 2.5) * 2, 3.5)
            else ctx.arc(x, y, r + (selected ? 3.5 : 2.5), 0, 2 * Math.PI)
            ctx.fillStyle = withAlpha(fill, selected || isRoot ? 0.22 : 0.12)
            ctx.fill()
            ctx.beginPath()
            if (g.label === 'Resource') ctx.roundRect(x - r, y - r, r * 2, r * 2, 1.5)
            else ctx.arc(x, y, r, 0, 2 * Math.PI)
            ctx.fillStyle = isVictim ? withAlpha(fill, Math.max(0.55, 1 - (hop! - 1) * 0.2)) : fill
            ctx.fill()
            ctx.fillStyle = '#ffffff'
            if (g.label === 'Resource') {
              for (const dy of [-2.2, 0, 2.2]) { ctx.beginPath(); ctx.ellipse(x, y + dy, 2.6, 0.85, 0, 0, 2 * Math.PI); ctx.fill() }
            } else if (g.label === 'Service') {
              ctx.beginPath(); ctx.roundRect(x - 2.8, y - 2.2, 5.6, 3.6, 0.6); ctx.fill()
              ctx.fillRect(x - 1.4, y + 2, 2.8, 0.7)
            }
            if (isRoot || selected) {
              ctx.beginPath()
              ctx.arc(x, y, r + 3.5 + 1.5 / scale, 0, 2 * Math.PI)
              ctx.strokeStyle = isRoot ? pal.danger : pal.service
              ctx.lineWidth = 1.5 / scale
              ctx.stroke()
            }
            if (showLabels && (scale > 0.9 || a === 1 && (hl || neighbours))) {
              const fs = 11 / scale
              const ty = y + r + 6 / scale
              ctx.font = `${selected || isRoot ? 600 : 500} ${fs}px ${pal.mono}`
              ctx.textAlign = 'center'
              ctx.textBaseline = 'top'
              if (selected) {
                const w = ctx.measureText(g.name).width + 10 / scale
                ctx.beginPath()
                ctx.roundRect(x - w / 2, ty - 3 / scale, w, fs + 6 / scale, 3 / scale)
                ctx.fillStyle = withAlpha(pal.service, 0.1)
                ctx.fill()
              }
              ctx.fillStyle = selected ? pal.service : withAlpha(pal.fg.startsWith('#') ? pal.fg : '#1c1917', a === 1 ? 0.85 : a)
              ctx.fillText(g.name, x, ty)
            }
            ctx.globalAlpha = 1
          }}
          nodePointerAreaPaint={(n, color, ctx) => {
            ctx.fillStyle = color
            ctx.beginPath()
            ctx.arc(n.x!, n.y!, radius(n.node) + 5, 0, 2 * Math.PI)
            ctx.fill()
          }}
          linkColor={(l) => {
            const on = linkOn(l)
            const base = hl && on ? pal.danger : l.edge.type === 'USES' ? pal.resource : l.edge.type === 'CO_CHANGES_WITH' || l.edge.provenance === 'inferred' ? pal.inferred : pal.edge
            const conf = l.edge.type === 'DEPENDS_ON' && l.edge.provenance !== 'inferred' ? 1 : 0.45 + l.edge.confidence * 0.55
            return withAlpha(base.startsWith('#') ? base : '#a1a1aa', on ? (hl ? 0.9 : conf) : 0.08)
          }}
          linkWidth={(l) => (hl && linkOn(l) ? 2 : 1.2)}
          linkLineDash={(l) => (l.edge.type === 'CO_CHANGES_WITH' ? [2, 3] : DASH[l.edge.provenance])}
          linkCurvature={(l) => (l.edge.type === 'CO_CHANGES_WITH' ? 0.25 : 0)}
          linkDirectionalArrowLength={(l) => (l.edge.type === 'CO_CHANGES_WITH' ? 0 : 5)}
          linkDirectionalArrowRelPos={(l) => {
            const s = l.source as N, t = l.target as N
            const len = Math.hypot((t.x ?? 0) - (s.x ?? 0), (t.y ?? 0) - (s.y ?? 0)) || 1
            return Math.max(0.5, 1 - (radius(t.node) + 4) / len)
          }}
          linkLabel={(l) =>
            `<div style="font:12px var(--font-sans);padding:6px 8px;border-radius:6px;background:var(--popover);color:var(--popover-foreground);border:1px solid var(--border);max-width:280px"><b>${esc(l.edge.type)}</b> · ${esc(l.edge.provenance)} · ${l.edge.confidence.toFixed(2)}${l.edge.evidence ? `<br/><span style="color:var(--muted-foreground)">${esc(l.edge.evidence)}</span>` : ''}</div>`
          }
        />
      )}
      <div className="absolute right-4 bottom-4 flex flex-col overflow-hidden rounded-md border bg-card shadow-sm">
        {[
          { label: 'Zoom in', icon: Plus, on: () => zoomBy(1.3) },
          { label: 'Zoom out', icon: Minus, on: () => zoomBy(1 / 1.3) },
          { label: 'Fit graph', icon: Scan, on: fit },
        ].map(({ label, icon: Icon, on }) => (
          <button key={label} onClick={on} className="grid size-10 place-items-center border-b text-subtle-foreground last:border-b-0 hover:bg-muted hover:text-foreground" aria-label={label} title={label}>
            <Icon className="size-4" />
          </button>
        ))}
      </div>
    </div>
  )
}

const LegendLine = ({ dash, color = 'var(--edge)' }: { dash?: string; color?: string }) => (
  <svg width="22" height="6" aria-hidden><line x1="0" y1="3" x2="22" y2="3" stroke={color} strokeWidth="1.5" strokeDasharray={dash} /></svg>
)

const LEGEND = [
  { label: 'Service', mark: <span className="size-2.5 rounded-full bg-[var(--node-service)]" /> },
  { label: 'Resource', mark: <span className="size-2.5 rounded-full bg-[var(--node-resource)]" /> },
  { label: 'Declared', mark: <LegendLine /> },
  { label: 'Code', mark: <LegendLine dash="6 2" /> },
  { label: 'Observed', mark: <LegendLine dash="1 2" color="#a8a29e" /> },
  { label: 'Inferred', mark: <LegendLine dash="4 3" color="var(--edge-inferred)" /> },
]

export function GraphLegend({ className, variant = 'bar' }: { className?: string; variant?: 'bar' | 'list' }) {
  if (variant === 'list')
    return (
      <ul className={cn('space-y-3 text-[13px] text-foreground/80', className)}>
        {LEGEND.map((l) => <li key={l.label} className="flex items-center gap-3"><span className="flex w-5 justify-center">{l.mark}</span>{l.label}</li>)}
        <li className="flex items-center gap-3 text-xs text-muted-foreground"><span className="w-5 text-center">→</span>A → B: A depends on B</li>
      </ul>
    )
  return (
    <div className={cn('flex flex-wrap items-center gap-x-6 gap-y-1.5 text-[11px] font-semibold tracking-[0.1em] text-subtle-foreground uppercase', className)}>
      {LEGEND.map((l) => <span key={l.label} className="flex items-center gap-2">{l.mark}{l.label}</span>)}
    </div>
  )
}
