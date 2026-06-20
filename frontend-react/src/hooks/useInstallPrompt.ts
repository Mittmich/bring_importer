import { useState, useEffect } from 'react'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

// Capture the event at module load time to avoid missing it if it fires
// before React mounts and attaches its useEffect listener.
let _earlyPrompt: BeforeInstallPromptEvent | null = null
window.addEventListener(
  'beforeinstallprompt',
  (e) => {
    e.preventDefault()
    _earlyPrompt = e as BeforeInstallPromptEvent
  },
  { once: true },
)

function isIos() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent)
}

function isStandalone() {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    ('standalone' in navigator && (navigator as any).standalone === true)
  )
}

export function useInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(
    _earlyPrompt,
  )
  const ios = isIos()
  const standalone = isStandalone()

  useEffect(() => {
    // Pick up any event that fires after mount (e.g. on subsequent visits)
    function handleBeforeInstallPrompt(e: Event) {
      e.preventDefault()
      setDeferredPrompt(e as BeforeInstallPromptEvent)
    }
    function handleAppInstalled() {
      setDeferredPrompt(null)
      _earlyPrompt = null
    }
    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt)
    window.addEventListener('appinstalled', handleAppInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt)
      window.removeEventListener('appinstalled', handleAppInstalled)
    }
  }, [])

  async function triggerInstall() {
    if (!deferredPrompt) return
    await deferredPrompt.prompt()
    await deferredPrompt.userChoice
    setDeferredPrompt(null)
    _earlyPrompt = null
  }

  return {
    canInstall: !standalone && !!deferredPrompt,
    triggerInstall,
    showIosInstructions: !standalone && ios,
  }
}
