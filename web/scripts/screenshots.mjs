// Dashboard screenshots + a WCAG contrast check of every visible text. Run from web/ after `npm run build`:
//   node scripts/screenshots.mjs           real library (read-only GETs)
//   node scripts/screenshots.mjs --demo    temp demo library (scripts/make-demo-library.py), deleted afterwards
// Starts its own API (:8766) and `vite preview` (:4174), so it never clashes with a running dev setup.
// Output: ../library/_review/dashboard-v4-*.png (real: dashboard-v4-real-*). Real library: looks only. Demo: also runs jobs.
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
  let covered = 0
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  for (let n; (n = walker.nextNode());) {
    const el = n.parentElement
    // disabled controls are exempt (WCAG 1.4.3 "inactive user interface components")
    if (!n.textContent.trim() || !el || seen.has(el) || el.closest('.sr-only, :disabled, [aria-disabled="true"]')) continue
    const cs = getComputedStyle(el), r = el.getBoundingClientRect()
    if (!r.width || cs.visibility === 'hidden' || r.bottom < 0 || r.top > innerHeight) continue
    seen.add(el)
    const [cx, cy] = [r.left + r.width / 2, r.top + r.height / 2]
    const clip = el.closest('main')?.getBoundingClientRect() // scrolled out of the frame's visible area
    const hit = document.elementFromPoint(cx, cy) // something else on top: the tab bar, a modal's scrim
    if ((clip && (cy < clip.top || cy > clip.bottom)) || (hit && !el.contains(hit) && !hit.contains(el))) {
      covered++ // not visible right now (under the tab bar, behind a dialog): checked where it is visible
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

const results = []
let browser
const API = `http://127.0.0.1:${API_PORT}`
const getJobs = async () => (await fetch(`${API}/api/jobs`)).json()

async function open(path, opts = {}) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, ...opts })
  page.errors = []
  page.on('pageerror', (e) => page.errors.push(e.message))
  page.on('console', (m) => m.type() === 'error' && !/Failed to load resource/.test(m.text()) && page.errors.push(m.text()))
  await page.goto(BASE + path, { waitUntil: 'networkidle' })
  await page.waitForSelector('main .raised')
  await page.waitForTimeout(1600) // entrance, count-up and chart draw-in settle
  return page
}

const scrollTo = (page, sel) => page.evaluate((s) => {
  const el = document.querySelector(s), main = document.querySelector('main')
  main.scrollTop += el.getBoundingClientRect().top - main.getBoundingClientRect().top - 8
}, sel).then(() => page.waitForTimeout(500))

/** screenshot + contrast check of what is on screen; `clearance` also scrolls to the end and checks the tab bar gap */
async function shoot(page, name, { clearance = false } = {}) {
  const file = resolve(OUT, `dashboard-v4-${demo ? '' : 'real-'}${name}.png`)
  await page.screenshot({ path: file })
  const { checked, fails } = await page.evaluate(contrastCheck)
  let gap = null, total = checked
  if (clearance) {
    gap = await page.evaluate(async () => {
      const main = document.querySelector('main')
      main.scrollTop = main.scrollHeight
      await new Promise((r) => setTimeout(r, 200))
      const last = Math.max(...[...main.querySelectorAll('.raised, .inset')].map((e) => e.getBoundingClientRect().bottom))
      return Math.round(document.querySelector('nav[aria-label=Tabs]').getBoundingClientRect().top - last)
    })
    const end = await page.evaluate(contrastCheck)
    total += end.checked
    fails.push(...end.fails.filter((f) => !fails.includes(f)))
  }
  results.push({ file, total, fails, gap, errors: [...page.errors] })
  console.log(file, `contrast: ${total} texts, ${fails.length} below AA` + (gap === null ? '' : `; tab bar clearance ${gap}px${gap >= 24 ? '' : ' (TOO SMALL)'}`),
    ...fails.map((f) => `\n  ${f}`), page.errors.length ? `\n  ERRORS: ${page.errors.join(' | ')}` : '')
}

async function until(pred, what, ms = 90_000) {
  for (const end = Date.now() + ms; Date.now() < end;) {
    const v = await pred()
    if (v) return v
    await new Promise((r) => setTimeout(r, 150))
  }
  throw new Error(`timed out waiting for ${what}`)
}

const openDrawer = async (page) => {
  await page.getByRole('button', { name: /^Jobs/ }).click()
  await page.waitForTimeout(900)
}

try {
  await Promise.all([waitUp(`${API}/api/health`), waitUp(BASE)])
  browser = await chromium.launch()

  if (!demo) {
    // real library: look only. Nothing here clicks an action or starts a job.
    let page = await open('/')
    await shoot(page, 'frame', { clearance: true })
    await page.close()
    page = await open('/series/marathon-1904/part-01')
    await shoot(page, 'part-detail')
    await page.close()
  } else {
    // 1. the single bezel frame
    const page = await open('/')
    await shoot(page, 'frame', { clearance: true })

    // 2. empty drawer (fresh API: no jobs yet)
    await openDrawer(page)
    await shoot(page, 'drawer-empty')
    await page.keyboard.press('Escape')
    await page.waitForTimeout(500)

    // 3. a slow real job (stills + 5 s test render of the showcase part), and one queued behind it
    const post = (slug, part, steps) => fetch(`${API}/api/jobs`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ slug, part, steps }),
    }).then((r) => r.json())
    const slow = await post('great-emu-war', 'part-07', ['render-stills', 'test-render'])
    await post('moon-diner', 'part-02', ['run --stage prep'])
    await until(async () => {
      const j = (await getJobs()).find((x) => x.id === slow.id)
      if (j && !['queued', 'running'].includes(j.status)) throw new Error(`slow job ended early: ${j.status}\n${j.output.join('\n')}`)
      return j?.status === 'running' && j.current_step === 1 && j.output.length >= 2 // stills done, test render under way
    }, 'the test-render step to start')
    await openDrawer(page)
    await page.waitForTimeout(1200)
    await shoot(page, 'drawer-running')
    await page.keyboard.press('Escape')

    // 4. history, one row expanded
    await until(async () => (await getJobs()).every((j) => !['queued', 'running'].includes(j.status)), 'all jobs to finish', 240_000)
    const done = await getJobs()
    console.log(done.map((j) => `job ${j.id}: ${j.status} (${j.output.length} lines)`).join('\n'))
    await page.waitForTimeout(600)
    await openDrawer(page)
    await page.getByRole('tab', { name: /History/ }).click()
    await page.waitForTimeout(700)
    await page.locator('aside[aria-label=Jobs] [aria-expanded]').first().click()
    await page.waitForTimeout(900)
    await shoot(page, 'drawer-history')
    await page.close()
  }
} finally {
  await browser?.close()
  for (const p of procs) p.kill()
  if (demo && existsSync(library)) rmSync(library, { recursive: true, force: true })
}
const bad = results.filter((r) => r.fails.length || r.errors.length || (r.gap !== null && r.gap < 24))
console.log(`\n${results.length} screenshots, ${results.reduce((a, r) => a + r.total, 0)} texts checked, ${bad.length} with problems`)
process.exitCode = bad.length ? 1 : 0
