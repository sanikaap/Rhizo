import type { Provenance } from '@/lib/types'

export interface Highlight {
  nodeIds: string[]
  edgeIds: string[]
  hopById?: Record<string, number>
  rootIds?: string[]
  animate?: boolean
}

export function hopsFromPaths(paths: string[][]): Record<string, number> {
  const hop: Record<string, number> = {}
  for (const p of paths)
    p.forEach((id, i) => {
      const h = p.length - 1 - i
      hop[id] = Math.min(hop[id] ?? Infinity, h)
    })
  return hop
}

export const DASH: Record<Provenance, number[] | null> = { declared: null, code: [6, 2], inferred: [4, 3], observed: [1, 2] }

export function readPalette() {
  const s = getComputedStyle(document.documentElement)
  const v = (k: string) => s.getPropertyValue(k).trim()
  return {
    service: v('--node-service'),
    resource: v('--node-resource'),
    engineer: v('--node-engineer'),
    edge: v('--edge'),
    inferred: v('--edge-inferred'),
    primary: v('--primary'),
    danger: v('--danger'),
    warning: v('--warning'),
    fg: v('--foreground'),
    muted: v('--muted-foreground'),
    canvas: v('--canvas'),
    font: getComputedStyle(document.body).fontFamily,
    mono: v('--font-mono-face') || 'ui-monospace, monospace',
  }
}
export type Palette = ReturnType<typeof readPalette>

export function withAlpha(hex: string, a: number) {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  const n = parseInt(full, 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

export function edgeIdsFromPaths(paths: string[][]): string[] {
  const out = new Set<string>()
  for (const p of paths)
    for (let i = 0; i < p.length - 1; i++)
      out.add(`${p[i + 1].startsWith('res:') ? 'USES' : 'DEPENDS_ON'}:${p[i]}->${p[i + 1]}`)
  return [...out]
}

export function layeredPositions(
  nodeIds: string[],
  edges: { source_id: string; target_id: string; type: string }[],
  gapX = 130,
  gapY = 58,
): Map<string, { x: number; y: number }> {
  const ids = new Set(nodeIds)
  const dir = edges.filter((e) => (e.type === 'DEPENDS_ON' || e.type === 'USES') && ids.has(e.source_id) && ids.has(e.target_id))
  const level = new Map(nodeIds.map((id) => [id, 0]))
  for (let pass = 0; pass < nodeIds.length; pass++) {
    let changed = false
    for (const e of dir) {
      const want = level.get(e.source_id)! + 1
      if (want > level.get(e.target_id)!) { level.set(e.target_id, want); changed = true }
    }
    if (!changed) break
  }
  const cols: string[][] = []
  for (const id of [...nodeIds].sort()) (cols[level.get(id)!] ??= []).push(id)
  const preds = (id: string) => dir.filter((e) => e.target_id === id).map((e) => e.source_id)
  const succs = (id: string) => dir.filter((e) => e.source_id === id).map((e) => e.target_id)
  const rowOf = () => new Map(cols.flatMap((c) => c.map((id, i) => [id, i - (c.length - 1) / 2] as const)))
  const bary = (ns: string[], row: Map<string, number>) => (ns.length ? ns.reduce((a, n) => a + row.get(n)!, 0) / ns.length : Infinity)
  for (let sweep = 0; sweep < 4; sweep++) {
    const down = sweep % 2 === 0
    const order = down ? cols.keys() : [...cols.keys()].reverse()
    for (const c of order) {
      if (!cols[c]) continue
      const row = rowOf()
      const key = new Map(cols[c].map((id) => [id, bary(down ? preds(id) : succs(id), row)]))
      cols[c].sort((a, b) => (key.get(a)! === Infinity || key.get(b)! === Infinity ? 0 : key.get(a)! - key.get(b)!))
    }
  }
  const mid = (cols.length - 1) / 2
  const row = rowOf()
  return new Map(nodeIds.map((id) => [id, { x: (level.get(id)! - mid) * gapX, y: row.get(id)! * gapY }]))
}
