import { EyeOff, Network, ShieldCheck } from 'lucide-react'
import Image from 'next/image'
import Link from 'next/link'

const POINTS = [
  { icon: Network, text: 'Blast radius for any service, hop by hop' },
  { icon: EyeOff, text: 'Hidden coupling no manifest declares' },
  { icon: ShieldCheck, text: 'Every answer cites the graph' },
]

export function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle: React.ReactNode; children: React.ReactNode; footer?: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-forest bg-[radial-gradient(ellipse_at_top_left,var(--forest-top),transparent_60%)] p-12 font-display text-white lg:flex">
        <Link href="/home" className="flex items-center gap-3 text-2xl font-semibold tracking-tight">
          <Image src="/logo-mark.svg" alt="" width={36} height={36} priority className="rounded-md ring-1 ring-white/10" />
          Rhizo
        </Link>
        <div>
          <h2 className="text-5xl leading-[1.02] font-bold tracking-tight">
            Know what
            <br />
            breaks first.
          </h2>
          <ul className="mt-10 space-y-4">
            {POINTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-forest-text">
                <span className="grid size-9 place-items-center rounded-lg border border-forest-line bg-forest-card text-emerald"><Icon className="size-4" /></span>
                {text}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sm text-forest-muted">© 2026 Rhizo.</p>
      </aside>

      <main className="flex flex-col items-center justify-center bg-background px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm">
          <Link href="/home" className="mb-10 flex items-center gap-2.5 text-lg font-bold tracking-tight lg:hidden">
            <Image src="/logo.svg" alt="Rhizo" width={148} height={32} priority />
          </Link>
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">{subtitle}</p>
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-8 text-center text-sm text-muted-foreground">{footer}</div>}
        </div>
      </main>
    </div>
  )
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[11px] font-semibold tracking-[0.1em] text-subtle-foreground uppercase">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-subtle-foreground">{hint}</span>}
    </label>
  )
}

export const inputCls =
  'h-11 w-full rounded-md border bg-card px-3 text-sm outline-none transition-colors placeholder:text-subtle-foreground focus:border-primary focus:ring-2 focus:ring-primary/20'

export const submitCls =
  'flex h-11 w-full items-center justify-center gap-2 rounded-md bg-primary text-sm font-bold tracking-[0.06em] text-white uppercase transition-colors hover:bg-primary/90 disabled:opacity-60'

export function FormError({ message }: { message: string | null }) {
  if (!message) return null
  return <p role="alert" className="rounded-md border border-danger/20 bg-danger-soft px-3 py-2 text-sm text-danger">{message}</p>
}
