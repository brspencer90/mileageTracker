// Generates the PWA icons (192/512 + maskable 512) into public/.
// Run with: node scripts/generate-icons.mjs   (or `npm run icons`)
//
// Design: solid blue rounded square with a white fuel-pump glyph.
// The glyph path is the Material Icons "local gas station" outline
// (Apache-2.0), drawn in a 24x24 viewBox.
import sharp from 'sharp'
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const outDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public')
mkdirSync(outDir, { recursive: true })

const BG = '#2a78d6'
const FG = '#ffffff'
const PUMP_PATH =
  'M19.77 7.23l.01-.01-3.72-3.72L15 4.56l2.11 2.11c-.94.36-1.61 1.26-1.61 ' +
  '2.33 0 1.38 1.12 2.5 2.5 2.5.36 0 .69-.08 1-.21v7.21c0 .55-.45 1-1 ' +
  '1s-1-.45-1-1V14c0-1.1-.9-2-2-2h-1V5c0-1.1-.9-2-2-2H6c-1.1 0-2 .9-2 ' +
  '2v16h10v-7.5h1.5v5c0 1.38 1.12 2.5 2.5 2.5s2.5-1.12 2.5-2.5V9c0-.69-.28' +
  '-1.32-.73-1.77zM12 10H6V5h6v5zm6 0c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 ' +
  '1-.45 1-1 1z'

/**
 * @param {number} size   output pixel size
 * @param {number} glyphFrac fraction of the canvas the 24x24 glyph spans
 * @param {boolean} maskable full-bleed square (no corner radius) for maskable
 */
function iconSvg(size, glyphFrac, maskable) {
  const rx = maskable ? 0 : Math.round(size * 0.18)
  const scale = (size * glyphFrac) / 24
  const offset = (size - 24 * scale) / 2
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <rect width="${size}" height="${size}" rx="${rx}" fill="${BG}"/>
  <g transform="translate(${offset} ${offset}) scale(${scale})">
    <path d="${PUMP_PATH}" fill="${FG}"/>
  </g>
</svg>`
}

const targets = [
  { file: 'pwa-192x192.png', size: 192, glyphFrac: 0.62, maskable: false },
  { file: 'pwa-512x512.png', size: 512, glyphFrac: 0.62, maskable: false },
  // Maskable safe zone is the inner 80% circle — keep the glyph well inside it.
  { file: 'maskable-icon-512x512.png', size: 512, glyphFrac: 0.46, maskable: true },
]

for (const t of targets) {
  const svg = Buffer.from(iconSvg(t.size, t.glyphFrac, t.maskable))
  await sharp(svg).png().toFile(join(outDir, t.file))
  console.log(`wrote public/${t.file}`)
}
