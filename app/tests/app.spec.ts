// The built app against the real engine and a knowledge base the engine wrote (fixture.py). No model runs: what is
// tested is that the window shows what the engine's files say, and the way from one view to the next.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'

const here = join(__dirname, '..')
const python = join(here, '..', 'engine', '.venv', ...(process.platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python']))

let config: string
let app: ElectronApplication
let win: Page

test.beforeAll(async () => {
  config = mkdtempSync(join(tmpdir(), 'byggmote-app-'))
  execFileSync(python, [join(__dirname, 'fixture.py')], { env: { ...process.env, BYGGMOTE_CONFIG: config } })
  // A CI runner on Linux does not let Chromium make its sandbox: there, and only there, the app starts without it.
  const args = process.env.CI && process.platform === 'linux' ? ['--no-sandbox', '.'] : ['.']
  // Hidden: a test run does not take the screen, and whoever sits at the computer cannot click in it.
  app = await electron.launch({ args, cwd: here, env: { ...process.env, BYGGMOTE_CONFIG: config, BYGGMOTE_HIDDEN: '1' } })
  win = await app.firstWindow()
})

test.afterAll(async () => {
  await app?.close()
  rmSync(config, { recursive: true, force: true })
})

test.beforeEach(async () => {
  if (await win.getByRole('button', { name: 'Till möten' }).count()) await win.getByRole('button', { name: 'Till möten' }).click()
  await expect(win.getByRole('heading', { name: 'Tidigare möten' })).toBeVisible()
})

test('the meetings of a project, the next one and what is still open', async () => {
  await expect(win.getByRole('heading', { name: 'Byggmöte 5' })).toBeVisible()
  await expect(win.getByText('En öppen punkt följer med från tidigare möten. En har passerat sitt datum.')).toBeVisible()
  const rows = win.locator('tbody tr')
  await expect(rows).toHaveCount(2)
  await expect(rows.nth(0)).toContainText('Byggmöte 4')
  await expect(rows.nth(0)).toContainText('Utkast, 1 att kontrollera')
  await expect(rows.nth(1)).toContainText('2026-10-22')
  const open = win.getByRole('region', { name: 'Öppna punkter' })
  await expect(open).toContainText('3.4.1')
  await expect(open).toContainText('Förfallen 2026-11-12')
})

test('the agenda has the open point under its heading', async () => {
  await win.getByRole('button', { name: 'Se dagordningen' }).click()
  await expect(win.getByRole('heading', { name: 'Dagordning, byggmöte 5' })).toBeVisible()
  const economy = win.locator('.headings > li').filter({ has: win.getByRole('heading', { name: 'Ekonomi' }) })
  await expect(economy).toContainText('3.4.1')
  await expect(economy).toContainText('Att göra, Platschef')
  await expect(win.locator('.headings > li')).toHaveCount(11)
})

test('a protocol: who was there, the points with their checks, and the transcript', async () => {
  await win.getByRole('button', { name: 'Byggmöte 4' }).click()
  await expect(win.getByRole('heading', { name: 'Protokoll, byggmöte 4' })).toBeVisible()
  await expect(win.locator('.attendees li').first()).toHaveText('Maria Lindqvist, Projektledare')

  const decision = win.locator('.point').filter({ hasText: '4.4.1' })
  await expect(decision).toContainText('Beslut')
  await expect(decision).toContainText('Kontrollera beloppet 86 500 kr.')
  await expect(decision).toContainText('åttiosex och fem')

  const carried = win.locator('.point').filter({ hasText: '3.4.1' })
  await expect(carried).toContainText('Kvarstår, från byggmöte 3')
  await expect(carried).toContainText('Togs inte upp på mötet.')
  await expect(carried).toContainText('Senast 2026-11-12, förfallen.')

  // a point's time shows its line in the transcript
  await decision.getByRole('button', { name: 'Lyssna från 17:42' }).click()
  await expect(win.locator('.lines li.active')).toContainText('Beställaren godkänner ÄTA 14')

  await win.getByRole('searchbox').fill('stomresningen')
  await expect(win.locator('.lines li')).toHaveCount(1)
  await expect(win.getByText('Mötet har inget ljud sparat.')).toBeVisible()
})

test('nothing is recorded before everyone knows', async () => {
  await win.getByRole('button', { name: 'Spela in mötet' }).click()
  await expect(win.getByRole('heading', { name: 'Byggmöte 5' })).toBeVisible()
  const start = win.getByRole('button', { name: 'Börja spela in' })
  await expect(start).toBeDisabled()
  await win.getByRole('checkbox', { name: 'Alla i rummet vet att mötet spelas in' }).check()
  await expect(start).toBeEnabled()
  await expect(win.locator('.heading')).toHaveCount(11)
})
