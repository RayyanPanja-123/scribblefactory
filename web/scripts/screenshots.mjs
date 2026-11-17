// Dashboard screenshots for review. Needs the API on :8765 and `npm run preview` on :4173.
// Run from web/: node scripts/screenshots.mjs [outDir]   (default ../library/_review)
import { createRequire } from 'node:module'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

// Playwright is installed for the engine; reuse it rather than adding a second copy.
const { chromium } = createRequire(new URL('../../engine/package.json', import.meta.url))('playwright')
const BASE = process.env.DASHBOARD_URL ?? 'http://localhost:4173'
const out = resolve(process.argv[2] ?? '../library/_review')
mkdirSync(out, { recursive: true })

const shots = [
  ['dashboard-overview.png', '/', {}],
  ['dashboard-series.png', '/series', {}],
  ['dashboard-series-detail.png', '/series/marathon-1904', {}],
  ['dashboard-overview-reduced-motion.png', '/', { reducedMotion: 'reduce' }],
]
const browser = await chromium.launch()
try {
  for (const [name, path, opts] of shots) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, ...opts })
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
    await page.goto(BASE + path, { waitUntil: 'networkidle' })
    await page.waitForSelector('.raised')
    await page.waitForTimeout(1800) // entrance, count-up and chart draw-in settle
    await page.screenshot({ path: resolve(out, name) })
    console.log(resolve(out, name), errors.length ? `ERRORS: ${errors.join(' | ')}` : '')
    await page.close()
  }
} finally {
  await browser.close()
}
