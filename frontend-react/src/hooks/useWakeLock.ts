import { useCallback, useEffect, useRef, useState } from 'react'

const supported = typeof navigator !== 'undefined' && 'wakeLock' in navigator

/**
 * Holds a screen wake lock so the display does not dim/sleep — handy for
 * reading a recipe while cooking. The OS auto-releases the lock whenever the
 * document is hidden (tab switch, screen off), so we re-acquire it on
 * `visibilitychange` while the user still wants it active.
 */
export function useWakeLock() {
  const [active, setActive] = useState(false)
  const sentinelRef = useRef<WakeLockSentinel | null>(null)
  // Tracks the user's intent independently of whether the lock is currently
  // held, so the visibilitychange handler knows whether to re-acquire.
  const wantedRef = useRef(false)

  const request = useCallback(async () => {
    if (!supported) return
    try {
      const sentinel = await navigator.wakeLock.request('screen')
      sentinelRef.current = sentinel
      sentinel.addEventListener('release', () => {
        sentinelRef.current = null
        // Reflect a system-initiated release (e.g. low battery) in the UI,
        // unless the user still wants it (then visibilitychange re-acquires).
        if (!wantedRef.current) setActive(false)
      })
      setActive(true)
    } catch {
      // request() rejects on low battery or without user activation.
      wantedRef.current = false
      setActive(false)
    }
  }, [])

  const enable = useCallback(() => {
    wantedRef.current = true
    void request()
  }, [request])

  const disable = useCallback(() => {
    wantedRef.current = false
    setActive(false)
    sentinelRef.current?.release().catch(() => {})
    sentinelRef.current = null
  }, [])

  const toggle = useCallback(() => {
    if (wantedRef.current) disable()
    else enable()
  }, [enable, disable])

  useEffect(() => {
    if (!supported) return
    function onVisibility() {
      if (document.visibilityState === 'visible' && wantedRef.current && !sentinelRef.current) {
        void request()
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      wantedRef.current = false
      sentinelRef.current?.release().catch(() => {})
      sentinelRef.current = null
    }
  }, [request])

  return { supported, active, toggle, enable, disable }
}
