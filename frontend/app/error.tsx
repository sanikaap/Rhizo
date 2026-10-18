'use client'

import { useEffect } from 'react'
import { ErrorState } from '@/components/common/primitives'

export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error)
  }, [error])
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md items-center justify-center px-6">
      <ErrorState error={error} onRetry={reset} />
    </div>
  )
}
