import { SkeletonRows } from '@/components/common/primitives'

export default function Loading() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6" aria-busy="true" aria-label="Loading">
      <SkeletonRows rows={6} />
    </div>
  )
}
