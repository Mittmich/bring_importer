// Center-crop an image File to a 16:9 landscape frame and downscale it, then
// return a JPEG data URL. Used for recipe hero images so every recipe shows a
// consistent landscape banner regardless of the source photo's orientation.

const TARGET_RATIO = 16 / 9
const MAX_WIDTH = 1280
const JPEG_QUALITY = 0.82

export function cropToLandscape(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)
      const iw = img.width
      const ih = img.height
      // Largest 16:9 rectangle that fits inside the source, centered.
      let cropW = iw
      let cropH = Math.round(iw / TARGET_RATIO)
      if (cropH > ih) {
        cropH = ih
        cropW = Math.round(ih * TARGET_RATIO)
      }
      const sx = Math.round((iw - cropW) / 2)
      const sy = Math.round((ih - cropH) / 2)

      const outW = Math.min(cropW, MAX_WIDTH)
      const outH = Math.round(outW / TARGET_RATIO)
      const canvas = document.createElement('canvas')
      canvas.width = outW
      canvas.height = outH
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        reject(new Error('Could not get canvas context'))
        return
      }
      ctx.drawImage(img, sx, sy, cropW, cropH, 0, 0, outW, outH)
      resolve(canvas.toDataURL('image/jpeg', JPEG_QUALITY))
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Could not load image'))
    }
    img.src = url
  })
}
