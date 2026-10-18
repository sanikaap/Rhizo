'use client'

import { useState, useSyncExternalStore } from 'react'

const VIDEO_SRC = 'https://designerstephen.github.io/public-assets/videos/serene-art-hero.mp4'
const POSTER_SRC = '/landing/hero-poster.webp'
const REDUCED_MOTION = '(prefers-reduced-motion: reduce)'

function subscribe(onChange: () => void) {
  const query = window.matchMedia(REDUCED_MOTION)
  query.addEventListener('change', onChange)
  return () => query.removeEventListener('change', onChange)
}

function usePrefersReducedMotion() {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(REDUCED_MOTION).matches,
    () => false,
  )
}

export function HeroBackdrop({ classes }: { classes: { backdrop: string; fallback: string; video: string; overlay: string; wash: string } }) {
  const reduced = usePrefersReducedMotion()
  const [failed, setFailed] = useState(false)
  const mode = reduced || failed ? 'fallback' : 'video'

  return (
    <div className={classes.backdrop} data-mode={mode} aria-hidden="true">
      <div className={classes.fallback} />
      {mode === 'video' && (
        <video
          className={classes.video}
          src={VIDEO_SRC}
          poster={POSTER_SRC}
          muted
          autoPlay
          loop
          playsInline
          preload="metadata"
          tabIndex={-1}
          onError={() => setFailed(true)}
        />
      )}
      <div className={classes.overlay} />
      <div className={classes.wash} />
    </div>
  )
}
