'use client'

import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

export const HEADER_ACTIONS_ID = 'header-actions'
export const HEADER_META_ID = 'header-meta'

function Slot({ id, children }: { id: string; children: React.ReactNode }) {
  const [target, setTarget] = useState<HTMLElement | null>(null)
  useEffect(() => setTarget(document.getElementById(id)), [id])
  return target ? createPortal(children, target) : null
}

export function HeaderActions({ children }: { children: React.ReactNode }) {
  return <Slot id={HEADER_ACTIONS_ID}>{children}</Slot>
}

export function HeaderMeta({ children }: { children: React.ReactNode }) {
  return <Slot id={HEADER_META_ID}>{children}</Slot>
}
