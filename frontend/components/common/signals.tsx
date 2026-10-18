'use client'

import { CheckCircle2, CircleDot, Code2, Eye, GitFork, HelpCircle, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { SignalMeter } from './charts'
import type { Basis, Incident } from '@/lib/types'

const BASIS: Record<Basis, { label: string; icon: React.ElementType; cls: string; hint: string }> = {
  declared: { label: 'Declared', icon: CheckCircle2, cls: 'text-foreground border-border', hint: 'From manifests (compose / k8s)' },
  code: { label: 'Code', icon: Code2, cls: 'text-foreground border-border', hint: 'An import between two of the repo\'s own packages' },
  observed: { label: 'Observed', icon: Eye, cls: 'text-foreground border-border', hint: 'From runtime traces' },
  inferred: { label: 'Inferred', icon: Sparkles, cls: 'text-warning border-warning/40 bg-warning-soft', hint: 'Shared resource, co-change or incident; verify before relying on it' },
  connectivity_fallback: { label: 'Weak basis', icon: HelpCircle, cls: 'text-danger border-danger/40 bg-danger-soft', hint: 'No DEPENDS_ON edges; answer from loose connectivity only' },
  'n/a': { label: 'n/a', icon: CircleDot, cls: 'text-muted-foreground border-border', hint: '' },
}

export function BasisBadge({ basis, className }: { basis: Basis; className?: string }) {
  const b = BASIS[basis] ?? BASIS['n/a']
  return (
    <span title={b.hint} className={cn('inline-flex h-5 items-center gap-1 rounded border px-1.5 text-[11px] font-medium', b.cls, className)}>
      <b.icon className="size-3" />
      {b.label}
    </span>
  )
}

const SEV: Record<Incident['severity'], string> = {
  sev1: 'bg-danger',
  sev2: 'bg-amber-500',
  sev3: 'bg-stone-500',
}
export function SeverityBadge({ severity }: { severity: Incident['severity'] }) {
  return <span className={cn('inline-flex h-5 items-center rounded-sm px-1.5 text-[10px] font-bold tracking-wide text-white uppercase', SEV[severity])}>{severity}</span>
}

export function StatusDot({ tone, pulse }: { tone: 'success' | 'warning' | 'danger' | 'muted'; pulse?: boolean }) {
  const c = { success: 'bg-success', warning: 'bg-warning', danger: 'bg-danger', muted: 'bg-subtle-foreground' }[tone]
  return (
    <span className="relative inline-flex size-2 shrink-0">
      {pulse && <span className={cn('absolute inset-0 animate-ping rounded-full opacity-60', c)} />}
      <span className={cn('relative size-2 rounded-full', c)} />
    </span>
  )
}

export function IncidentStatus({ status }: { status: Incident['status'] }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <StatusDot tone={status === 'open' ? 'danger' : 'success'} pulse={status === 'open'} />
      {status === 'open' ? 'Open' : 'Resolved'}
    </span>
  )
}

export function ConfidenceBar({ value, className, showValue = true }: { value: number; className?: string; showValue?: boolean }) {
  return <SignalMeter value={value} className={className} showValue={showValue} />
}

export const riskTone = (r: number) => (r >= 70 ? 'danger' : r >= 40 ? 'warning' : 'success')
export const TONE_TEXT = { danger: 'text-danger', warning: 'text-warning', success: 'text-success' } as const
export const riskLabel =(r: number) => (r >= 70 ? 'High' : r >= 40 ? 'Medium' : 'Low')

export function RiskGauge({ value, size = 132, label = 'Risk score' }: { value: number; size?: number; label?: string }) {
  const tone = riskTone(value)
  const r = 52
  const c = Math.PI * r
  return (
    <div className="flex flex-col items-center" role="meter" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <svg width={size} height={size * 0.62} viewBox="0 0 120 72" aria-hidden>
        <path d="M8 64 A52 52 0 0 1 112 64" fill="none" stroke="var(--muted)" strokeWidth="9" strokeLinecap="round" />
        <path
          d="M8 64 A52 52 0 0 1 112 64" fill="none" stroke={`var(--${tone})`} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={`${(c * value) / 100} ${c}`} style={{ transition: 'stroke-dasharray 400ms ease-out' }}
        />
      </svg>
      <div className="-mt-9 text-center">
        <div className="text-3xl font-semibold tabular-nums tracking-tight">{value}</div>
        <div className={cn('text-xs font-medium', TONE_TEXT[tone])}>{riskLabel(value)} risk</div>
      </div>
    </div>
  )
}

export function StatCard({
  label, value, hint, icon: Icon, tone,
}: { label: string; value: React.ReactNode; hint?: React.ReactNode; icon: React.ElementType; tone?: 'danger' | 'warning' }) {
  return (
    <div className="flex items-center gap-4 rounded-md border bg-card px-5 py-5 shadow-[0_1px_2px_rgba(28,25,23,0.04)]">
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-semibold tracking-[0.1em] text-subtle-foreground uppercase">{label}</div>
        <div className={cn('mt-1.5 text-2xl font-bold tabular-nums tracking-tight', tone === 'danger' && 'text-danger')}>{value}</div>
        {hint && <div className="mt-0.5 truncate text-xs text-muted-foreground">{hint}</div>}
      </div>
      <Icon className={cn('size-8 shrink-0', tone === 'danger' ? 'text-danger/80' : tone === 'warning' ? 'text-amber-300' : 'text-emerald-200')} strokeWidth={1.6} />
    </div>
  )
}

export function ServiceChip({ name, kind = 'Service', className }: { name: string; kind?: 'Service' | 'Resource'; className?: string }) {
  return (
    <span className={cn('inline-flex h-6 items-center gap-1.5 rounded-md border bg-card px-2 font-mono text-xs', className)}>
      <span className={cn('size-1.5 rounded-full', kind === 'Resource' ? 'bg-[var(--node-resource)]' : 'bg-[var(--node-service)]')} />
      {name}
    </span>
  )
}

export function HiddenKindBadge({ kind }: { kind: 'shared_resource' | 'co_change' }) {
  return (
    <span className="inline-flex h-5 items-center gap-1 rounded border px-1.5 text-[11px] font-medium text-muted-foreground">
      <GitFork className="size-3" />
      {kind === 'shared_resource' ? 'Shared resource' : 'Co-change'}
    </span>
  )
}
