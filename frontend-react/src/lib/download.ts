/**
 * Hand a generated file to the user.
 *
 * On touch devices with file sharing (iOS/Android, incl. the installed PWA) the
 * system share sheet is the natural way to save, print or send a file, and a
 * blob download is unreliable there. Elsewhere, trigger a normal download.
 */
export async function saveOrShare(blob: Blob, filename: string): Promise<void> {
  const file = new File([blob], filename, { type: blob.type })
  const touch = window.matchMedia?.('(pointer: coarse)').matches
  if (touch && navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: filename.replace(/\.pdf$/i, '') })
      return
    } catch (e) {
      // The user closing the share sheet is not an error.
      if ((e as DOMException)?.name === 'AbortError') return
      // Otherwise fall back to a download.
    }
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Give the browser a moment to start the download before revoking.
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
