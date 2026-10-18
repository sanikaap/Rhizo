'use client'

import { AlertCircle, Inbox, Loader2, RotateCw } from 'lucide-react'
import { useEffect, useId } from 'react'
import { cn } from '@/lib/utils'
import { ApiError } from '@/lib/api'

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-md border bg-card text-card-foreground shadow-[0_1px_2px_rgba(28,25,23,0.04)]', className)} {...props} />
}

export function CardHeader({
  title, description, action, className,
}: { title: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn('flex items-center justify-between gap-4 border-b bg-background/60 px-5 py-3.5', className)}>
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-[13px] font-bold leading-6 tracking-[0.1em] uppercase">{title}</h2>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

export function PageHeader({
  title, description, actions, eyebrow,
}: { title: string; description?: React.ReactNode; actions?: React.ReactNode; eyebrow?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-medium text-muted-foreground">{eyebrow}</div>}
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-muted', className)} />
}

export function SkeletonRows({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('space-y-3 p-4', className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="size-7 rounded-md" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3 w-1/3" />
            <Skeleton className="h-2.5 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function EmptyState({
  icon: Icon = Inbox, title, description, action, className,
}: { icon?: React.ElementType; title: string; description?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-10 text-center', className)}>
      <div className="mb-3 grid size-10 place-items-center rounded-lg border bg-muted text-muted-foreground">
        <Icon className="size-5" />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  const e = error instanceof ApiError ? error : null
  const upstream = e?.status === 503 || e?.code === 'UPSTREAM'
  return (
    <div role="alert" className={cn('flex flex-col items-center px-6 py-10 text-center', className)}>
      <div className="mb-3 grid size-10 place-items-center rounded-lg bg-danger-soft text-danger">
        <AlertCircle className="size-5" />
      </div>
      <p className="text-sm font-medium">{upstream ? 'FalkorDB is unreachable' : 'Something went wrong'}</p>
      <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
        {upstream
          ? 'Rhizo answers only from the graph, so it cannot respond until the database is back.'
          : error instanceof Error ? error.message : 'Unknown error'}
      </p>
      {onRetry && (
        <button onClick={onRetry} className="mt-4 inline-flex h-8 items-center gap-1.5 rounded-md border bg-card px-3 text-xs font-medium hover:bg-muted">
          <RotateCw className="size-3.5" /> Retry
        </button>
      )}
    </div>
  )
}

export function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <kbd className={cn('inline-flex h-5 min-w-5 items-center justify-center rounded border bg-muted px-1 font-mono text-[10px] text-muted-foreground', className)}>
      {children}
    </kbd>
  )
}

export function Segmented<T extends string>({
  value, onChange, options, size = 'sm', label,
}: { value: T; onChange: (v: T) => void; options: { value: T; label: React.ReactNode }[]; size?: 'sm' | 'xs'; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border bg-muted p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            'rounded-[5px] font-medium text-muted-foreground transition-colors hover:text-foreground',
            size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-6 px-2 text-[11px]',
            value === o.value && 'bg-card text-foreground shadow-xs',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Btn({
  variant = 'outline', size = 'md', className, ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'outline' | 'ghost'; size?: 'sm' | 'md' }) {
  return (
    <button
      className={cn(
        'inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0',
        size === 'md' ? 'h-8 px-3 text-sm' : 'h-7 px-2.5 text-xs [&_svg]:size-3.5',
        variant === 'primary' && 'bg-primary text-primary-foreground hover:bg-primary/90',
        variant === 'outline' && 'border bg-card hover:bg-muted',
        variant === 'ghost' && 'text-muted-foreground hover:bg-muted hover:text-foreground',
        className,
      )}
      {...props}
    />
  )
}

export function ConfirmDialog({
  title, body, confirmLabel, pending, onConfirm, onClose,
}: { title: string; body: React.ReactNode; confirmLabel: string; pending?: boolean; onConfirm: () => void; onClose: () => void }) {
  const id = useId()
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="alertdialog" aria-modal="true" aria-labelledby={`${id}-t`} aria-describedby={`${id}-b`}>
      <div className="absolute inset-0 bg-black/40 animate-fade" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-xl border bg-popover p-5 shadow-2xl animate-rise">
        <h2 id={`${id}-t`} className="text-base font-semibold">{title}</h2>
        <div id={`${id}-b`} className="mt-2 text-sm leading-6 text-muted-foreground">{body}</div>
        <div className="mt-5 flex justify-end gap-2">
          <Btn onClick={onClose} autoFocus>Cancel</Btn>
          <Btn variant="primary" className="bg-danger hover:bg-danger/90" onClick={onConfirm} disabled={pending}>
            {pending && <Loader2 className="animate-spin" />}{confirmLabel}
          </Btn>
        </div>
      </div>
    </div>
  )
}
