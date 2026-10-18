"use client";
import { useSyncExternalStore } from 'react'

const KEY = 'rhizo.repo'
const listeners = new Set<() => void>()
let current: string | null = null
let loaded = false

function load() {
  if (loaded || typeof window === 'undefined') return
  loaded = true
  try {
    current = window.localStorage.getItem(KEY)
  } catch {
    current = null
  }
}

export function currentRepoId(): string | null {
  load()
  return current
}

export function setCurrentRepoId(id: string | null) {
  load()
  if (id === current) return
  current = id
  try {
    if (id) window.localStorage.setItem(KEY, id)
    else window.localStorage.removeItem(KEY)
  } catch {}
  listeners.forEach((l) => l())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export const useCurrentRepoId = () => useSyncExternalStore(subscribe, currentRepoId, () => null)
