import type { Metadata } from 'next'
import { Instrument_Serif } from 'next/font/google'
import { cookies } from 'next/headers'
import Image from 'next/image'
import Link from 'next/link'
import { HeroBackdrop } from '@/components/landing/hero-backdrop'
import { SESSION_COOKIE, sessionUser } from '@/lib/server/session'
import { cn } from '@/lib/utils'
import s from './landing.module.css'

export const metadata: Metadata = { title: 'Home' }

const serif = Instrument_Serif({ weight: '400', subsets: ['latin'], variable: '--font-serif', display: 'swap' })

const NAV_LINKS = [
  { href: '#features', label: 'Features' },
  { href: '#how', label: 'How it works' },
  { href: '#demo', label: 'Demo' },
  { href: '#github', label: 'GitHub' },
]

const STEPS = [
  {
    id: 'github',
    title: 'Connect a repo',
    body: 'Paste a public GitHub URL. Rhizo reads its compose files, Kubernetes manifests, imports and git history. Nothing in the repo is ever run.',
  },
  {
    id: 'map',
    title: 'Map dependencies',
    body: 'Every service, resource and edge lands in a FalkorDB graph with its provenance: declared, found in code, or inferred from what changes together.',
  },
  {
    id: 'ask',
    title: 'Ask what breaks',
    body: 'Pick a service or a diff and get the blast radius, the likely root causes and who to page, each backed by the query that found it.',
  },
]

const container = 'mx-auto w-full max-w-[1280px] px-8'

function Brand({ size = 30 }: { size?: number }) {
  return (
    <Link href="/home" className={cn(s.focus, 'inline-flex items-center gap-3 rounded-md')} aria-label="Rhizo home">
      <Image src="/logo-mark.svg" alt="" width={size + 2} height={size + 2} priority className="rounded-md" />
      <span className={s.serif} style={{ fontSize: size, lineHeight: 1 }}>Rhizo</span>
    </Link>
  )
}

export default async function HomePage() {
  const signedIn = !!sessionUser((await cookies()).get(SESSION_COOKIE)?.value)
  const primary = signedIn ? { href: '/', label: 'Open app' } : { href: '/signup', label: 'Get started' }

  return (
    <div className={cn(serif.variable, s.page, 'min-h-dvh font-sans text-[15px]')}>
      <section className={cn(s.hero, 'flex min-h-screen flex-col')} aria-labelledby="hero-title">
        <HeroBackdrop classes={{ backdrop: s.backdrop, fallback: s.fallback, video: s.video, overlay: s.overlay, wash: s.wash }} />

        <header className={cn(container, 'grid grid-cols-2 items-center py-6 md:grid-cols-3')}>
          <div className={s.ink}>
            <Brand />
          </div>
          <nav aria-label="Landing" className="hidden justify-center gap-10 text-sm font-medium md:flex">
            {NAV_LINKS.map((l) => (
              <a key={l.href} href={l.href} className={cn(s.navLink, s.focus)}>{l.label}</a>
            ))}
          </nav>
          <div className="flex items-center justify-end gap-3 text-sm whitespace-nowrap sm:gap-5">
            {!signedIn && <Link href="/login" className={cn(s.ghost, s.focus, 'px-1 py-2')}>Sign in</Link>}
            <Link href={primary.href} className={cn(s.pill, s.focus, 'px-4 py-2.5 text-sm sm:px-5')}>{primary.label}</Link>
          </div>
        </header>

        <div className={cn(container, 'flex flex-1 flex-col items-center justify-center pb-24 text-center')}>
          <h1 id="hero-title" className={cn(s.serif, s.title, s.rise, 'max-w-[13ch] md:max-w-[15ch]')}>
            Know what breaks <em>before</em> it breaks
          </h1>
          <p className={cn(s.lead, s.rise, s.delay1, 'mt-8 text-base md:text-lg')}>
            Connect a GitHub repo. Rhizo maps how your services depend on each other, finds the couplings nobody declared, and shows
            the blast radius of any failure, with the evidence.
          </p>
          <div className={cn(s.rise, s.delay2, 'mt-12')}>
            <Link href={primary.href} className={cn(s.pill, s.focus, s.ctaMain)}>{primary.label}</Link>
          </div>
        </div>
      </section>

      <section id="features" className="scroll-mt-4 py-24 md:py-32" aria-labelledby="features-title">
        <div className={container}>
          <h2 id="features-title" className={cn(s.serif, 'max-w-2xl text-4xl leading-[1.05] tracking-[-0.02em] md:text-5xl')}>
            From a repository to its blast radius, in three steps.
          </h2>
          <ol id="how" className="mt-16 grid scroll-mt-8 gap-10 md:grid-cols-3 md:gap-12">
            {STEPS.map((step, i) => (
              <li key={step.id} id={step.id} className={cn(s.step, 'scroll-mt-8 pt-6')}>
                <span className={cn(s.serif, s.stepNumber, 'text-2xl')} aria-hidden="true">0{i + 1}</span>
                <h3 className={cn(s.serif, 'mt-3 text-[28px] leading-tight')}>{step.title}</h3>
                <p className={cn(s.muted, 'mt-3 leading-[1.625]')}>{step.body}</p>
              </li>
            ))}
          </ol>
          <p id="demo" className={cn(s.muted, 'mt-16 scroll-mt-8 border-l-2 border-[#0f766e] pl-4 leading-[1.625]')}>
            Every new account starts with a demo: Google&apos;s public microservices-demo, mapped by the same pipeline. Remove it whenever you
            connect your own.
          </p>
        </div>
      </section>

      <footer className={cn(container, 'flex flex-col gap-6 border-t border-[#0f766e]/20 py-10 sm:flex-row sm:items-center sm:justify-between')}>
        <Brand size={24} />
        <p className={cn(s.muted, 'text-sm')}>© 2026 Rhizo. Built on FalkorDB.</p>
      </footer>
    </div>
  )
}
