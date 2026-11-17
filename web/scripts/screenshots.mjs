// Dashboard screenshots + a WCAG contrast check of every visible text. Run from web/ after `npm run build`:
//   node scripts/screenshots.mjs           real library (read-only GETs)
//   node scripts/screenshots.mjs --demo    temp demo library (scripts/make-demo-library.py), deleted afterwards
// Starts its own API (:8766) and `vite preview` (:4174), so it never clashes with a running dev setup.
// Output: ../library/_review/dashboard-v2-*.png
import { spawn, execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { existsSync, mkdirSync, rmSync } from 'node:fs'
import { resolve } from 'node:path'

const { chromium } = createRequire(new URL('../../engine/package.json', import.meta.url))('playwright')
const ROOT = resolve(import.meta.dirname, '../..')
const WEB = resolve(ROOT, 'web')
const PY = resolve(ROOT, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const OUT = resolve(ROOT, 'library/_review')
const API_PORT = 8766, WEB_PORT = 4174
const demo = process.argv.includes('--demo')
const tag = demo ? '-demo' : ''

let library = resolve(ROOT, 'library')
if (demo) library = execFileSync(PY, [resolve(WEB, 'scripts/make-demo-library.py')], { cwd: ROOT, encoding: 'utf8' }).trim()
mkdirSync(OUT, { recursive: true })

const procs = [
  spawn(PY, ['-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', String(API_PORT), '--log-level', 'warning'],
    { cwd: ROOT, env: { ...process.env, SCRIBBLE_LIBRARY: library }, stdio: 'inherit' }),
  spawn(process.execPath, [resolve(WEB, 'node_modules/vite/bin/vite.js'), 'preview', '--port', String(WEB_PORT), '--strictPort'],
    { cwd: WEB, env: { ...process.env, SCRIBBLE_API: `http://127.0.0.1:${API_PORT}` }, stdio: 'ignore' }),
]
const BASE = `http://localhost:${WEB_PORT}`

async function waitUp(url) {
  for (let i = 0; i < 150; i++) {
    try { if ((await fetch(url)).ok) return } catch {}
    await new Promise((r) => setTimeout(r, 200))
  }
  throw new Error(`${url} did not come up`)
}

/** In the page: every visible text vs what is painted under it (elementsFromPoint, so sibling layers like the
 *  sliding tab pill count), WCAG 2.x ratio. Colours go through a canvas, so oklab()/color-mix() resolve to sRGB. */
function contrastCheck() {
  const ctx = Object.assign(document.createElement('canvas'), { width: 1, height: 1 }).getContext('2d', { willReadFrequently: true })
  const rgba = (c) => {
    ctx.clearRect(0, 0, 1, 1)
    ctx.fillStyle = c
    ctx.fillRect(0, 0, 1, 1)
    const d = ctx.getImageData(0, 0, 1, 1).data
    return [d[0], d[1], d[2], d[3] / 255]
  }
  const over = (top, bot) => [0, 1, 2].map((i) => top[i] * top[3] + bot[i] * (1 - top[3])).concat(1)
  const lum = ([r, g, b]) => [r, g, b].map((v) => (v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
    .reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0)
  const bgAt = (x, y) => {
    const layers = []
    for (const e of document.elementsFromPoint(x, y)) {
      const c = rgba(getComputedStyle(e).backgroundColor)
      if (c[3] > 0) layers.push(c)
      if (c[3] >= 1) break
    }
    return layers.reverse().reduce((acc, c) => over(c, acc), [255, 255, 255, 1])
  }
  const fails = [], seen = new Set()
  const tabbar = document.querySelector('nav[aria-label=Tabs]')
  let covered = 0
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  for (let n; (n = walker.nextNode());) {
    const el = n.parentElement
    if (!n.textContent.trim() || !el || seen.has(el) || el.closest('.sr-only')) continue
    const cs = getComputedStyle(el), r = el.getBoundingClientRect()
    if (!r.width || cs.visibility === 'hidden' || r.bottom < 0 || r.top > innerHeight) continue
    seen.add(el)
    const [cx, cy] = [r.left + r.width / 2, r.top + r.height / 2]
    const clip = el.closest('main')?.getBoundingClientRect() // scrolled out of the frame's visible area
    if ((clip && (cy < clip.top || cy > clip.bottom)) ||
        (!tabbar.contains(el) && tabbar.contains(document.elementFromPoint(cx, cy)))) {
      covered++ // scrolled under the floating tab bar: checked again once scrolled clear
      continue
    }
    const bg = bgAt(cx, cy)
    const fg = over(rgba(el instanceof SVGElement ? cs.fill : cs.color), bg)
    const [a, b] = [lum(fg), lum(bg)]
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
    const px = parseFloat(cs.fontSize), large = px >= 24 || (px >= 18.66 && +cs.fontWeight >= 700)
    if (ratio < (large ? 3 : 4.5)) fails.push(`${ratio.toFixed(2)}:1 "${n.textContent.trim().slice(0, 30)}" ${cs.color} ${px}px`)
  }
  return { checked: seen.size - covered, fails }
}

const shots = [
  ['overview', '/'],
  ['series', '/series'],
  ['series-detail', demo ? '/series/great-emu-war' : '/series/marathon-1904'],
]
let browser
try {
  await Promise.all([waitUp(`http://127.0.0.1:${API_PORT}/api/health`), waitUp(BASE)])
  browser = await chromium.launch()
  for (const [name, path] of shots) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
    await page.goto(BASE + path, { waitUntil: 'networkidle' })
    await page.waitForSelector('.raised')
    await page.waitForTimeout(1800) // entrance, count-up and chart draw-in settle
    const file = resolve(OUT, `dashboard-v2-${name}${tag}.png`)
    await page.screenshot({ path: file })
    const top = await page.evaluate(contrastCheck)
    // scrolled to the end: the last content must clear the tab bar by >= 24 px; then check what was underneath
    const clearance = await page.evaluate(async () => {
      const main = document.querySelector('main')
      main.scrollTop = main.scrollHeight
      await new Promise((r) => setTimeout(r, 150))
      const last = Math.max(...[...main.querySelectorAll('.raised, .inset')].map((e) => e.getBoundingClientRect().bottom))
      return Math.round(document.querySelector('nav[aria-label=Tabs]').getBoundingClientRect().top - last)
    })
    const end = await page.evaluate(contrastCheck)
    const fails = [...new Set([...top.fails, ...end.fails])]
    console.log(file, `contrast: ${top.checked} + ${end.checked} texts (top, scrolled to end), ${fails.length} below AA;`,
      `tab bar clearance ${clearance}px${clearance >= 24 ? '' : ' (TOO SMALL)'}`, ...fails.map((f) => `\n  ${f}`),
      errors.length ? `\n  ERRORS: ${errors.join(' | ')}` : '')
    await page.evaluate(() => (document.querySelector('main').scrollTop = 0))
    if (name === 'overview' && demo) { // hovered KPI card + chart tooltip
      await page.locator('.raised.lift').first().hover()
      await page.waitForTimeout(500)
      const hover = resolve(OUT, `dashboard-v2-hover${tag}.png`)
      await page.screenshot({ path: hover })
      const svg = page.locator('svg[aria-label^="Posts per month"]')
      const box = await svg.boundingBox()
      await page.mouse.move(box.x + box.width * 0.86, box.y + box.height * 0.5)
      await page.waitForTimeout(400)
      const tip = resolve(OUT, `dashboard-v2-chart-hover${tag}.png`)
      await page.screenshot({ path: tip })
      console.log(hover, '\n' + tip)
    }
    await page.close()
  }
} finally {
  await browser?.close()
  for (const p of procs) p.kill()
  if (demo && existsSync(library)) rmSync(library, { recursive: true, force: true })
}
