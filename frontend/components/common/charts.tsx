'use client'

import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { useState } from 'react'
import { cn } from '@/lib/utils'

export interface DonutSlice { key: string; label: string; value: number; color: string }

export function Donut({ slices, size = 148, thickness = 16, centerLabel = 'total' }: { slices: DonutSlice[]; size?: number; thickness?: number; centerLabel?: string }) {
  const [hover, setHover] = useState<string | null>(null)
  const total = slices.reduce((a, s) => a + s.value, 0)
  const r = (size - thickness) / 2
  const c = 2 * Math.PI * r
  const gap = slices.filter((s) => s.value).length > 1 ? 3 : 0
  let offset = 0
  const active = slices.find((s) => s.key === hover)

  return (
    <div className="flex items-center gap-6">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" role="img" aria-label={slices.map((s) => `${s.label} ${s.value}`).join(', ')}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--muted)" strokeWidth={thickness} />
          {total > 0 && slices.map((s) => {
            if (!s.value) return null
            const len = (s.value / total) * c
            const dash = Math.max(0, len - gap)
            const el = (
              <circle
                key={s.key}
                cx={size / 2} cy={size / 2} r={r} fill="none"
                stroke={s.color}
                strokeWidth={hover === s.key ? thickness + 4 : thickness}
                strokeDasharray={`${dash} ${c - dash}`}
                strokeDashoffset={-offset}
                onMouseEnter={() => setHover(s.key)}
                onMouseLeave={() => setHover(null)}
                className="cursor-pointer transition-[stroke-width,opacity] duration-150"
                style={{ opacity: hover && hover !== s.key ? 0.35 : 1 }}
              />
            )
            offset += len
            return el
          })}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold tabular-nums tracking-tight">{active ? active.value : total}</span>
          <span className="text-[11px] text-muted-foreground">{active ? active.label.toLowerCase() : centerLabel}</span>
        </div>
      </div>
      <ul className="min-w-0 flex-1 space-y-2.5 text-sm">
        {slices.map((s) => (
          <li
            key={s.key}
            onMouseEnter={() => setHover(s.key)}
            onMouseLeave={() => setHover(null)}
            className={cn('flex items-center gap-2 transition-opacity', hover && hover !== s.key && 'opacity-40')}
          >
            <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: s.color }} />
            <span>{s.label}</span>
            <span className="ml-auto font-mono tabular-nums">{s.value}</span>
            <span className="w-9 text-right font-mono text-xs tabular-nums text-muted-foreground">{total ? Math.round((s.value / total) * 100) : 0}%</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function SignalMeter({ value, steps = 5, showValue = true, className }: { value: number; steps?: number; showValue?: boolean; className?: string }) {
  const lit = Math.round(value * steps)
  const tone = value >= 0.8 ? 'bg-primary' : value >= 0.55 ? 'bg-primary/70' : 'bg-warning'
  return (
    <div className={cn('flex items-center gap-2', className)} title={`Confidence ${value.toFixed(2)}`} role="meter" aria-label="Confidence" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className="flex h-3.5 items-end gap-[2px]" aria-hidden>
        {Array.from({ length: steps }, (_, i) => (
          <span
            key={i}
            className={cn('w-[4px] rounded-[1.5px] transition-colors', i < lit ? tone : 'bg-border')}
            style={{ height: `${((i + 1) / steps) * 100}%` }}
          />
        ))}
      </div>
      {showValue && <span className="w-8 font-mono text-[11px] tabular-nums text-muted-foreground">{value.toFixed(2)}</span>}
    </div>
  )
}

export interface RankRow { id: string; label: string; value: number; meta?: React.ReactNode; href?: string }

export function RankBars({ rows, max = 1, action = 'Blast radius' }: { rows: RankRow[]; max?: number; action?: string }) {
  return (
    <ol className="space-y-1.5 p-4">
      {rows.map((r, i) => {
        const pct = Math.max(6, (r.value / max) * 100)
        return (
          <li key={r.id} className="group flex items-center gap-3">
            <span className="w-4 shrink-0 text-right font-mono text-[11px] text-subtle-foreground tabular-nums">{i + 1}</span>
            <div className="relative h-9 min-w-0 flex-1 overflow-hidden rounded-lg bg-muted/70">
              <div
                className={cn('absolute inset-y-0 left-0 rounded-lg transition-[width,background-color] duration-500 ease-out', i === 0 ? 'bg-primary/20' : 'bg-primary/10', 'group-hover:bg-primary/25')}
                style={{ width: `${pct}%` }}
              >
                <span className="absolute inset-y-1.5 right-1.5 w-1 rounded-full bg-primary" />
              </div>
              <div className="relative flex h-full items-center gap-2 px-3">
                <span className="truncate font-mono text-[13px] font-medium">{r.label}</span>
                {r.meta}
              </div>
            </div>
            <span className="w-10 shrink-0 text-right font-mono text-xs font-medium tabular-nums">{r.value.toFixed(2)}</span>
            {r.href && (
              <Link href={r.href} aria-label={`${action} of ${r.label}`} title={action}
                className="grid size-7 shrink-0 place-items-center rounded-md text-subtle-foreground opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100 hover:bg-muted hover:text-primary">
                <ArrowUpRight className="size-3.5" />
              </Link>
            )}
          </li>
        )
      })}
    </ol>
  )
}
