import { Compass } from 'lucide-react'
import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = { title: 'Not found' }

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 grid size-12 place-items-center rounded-lg border bg-muted text-muted-foreground">
        <Compass className="size-6" />
      </div>
      <h1 className="text-lg font-semibold">Page not found</h1>
      <p className="mt-2 text-sm text-muted-foreground">There is no page at this address. It may have moved, or the link may be wrong.</p>
      <div className="mt-6 flex gap-2">
        <Link href="/" className="inline-flex h-8 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">Go to Overview</Link>
        <Link href="/repos" className="inline-flex h-8 items-center rounded-md border bg-card px-3 text-sm font-medium hover:bg-muted">Repositories</Link>
      </div>
    </div>
  )
}
