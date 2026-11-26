// A computer that has never run the app: the first run asks who is using it, goes through the microphone, the models and
// Stommen, and ends on the app. Then the settings change what the app keeps, and the first run can be shown again.
// Nothing here fetches a model or signs in anywhere.
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'

declare const window: { api: import('../src/shared/types').Api }

const here = join(__dirname, '..')

let config: string
let userData: string
let app: ElectronApplication
let win: Page

// Inställningar is a window of its own. It is opened afresh each time, so it shows what the app has now.
let sw: Page
async function settings(): Promise<Page> {
  for (const p of app.windows()) if (p !== win) await p.close()
  const [p] = await Promise.all([app.waitForEvent('window'), win.getByRole('button', { name: 'Inställningar' }).click()])
  await p.waitForLoadState()
  return p
}

test.beforeAll(async () => {
  config = mkdtempSync(join(tmpdir(), 'byggmote-first-'))
  userData = mkdtempSync(join(tmpdir(), 'byggmote-first-user-'))
  const args = process.env.CI && process.platform === 'linux' ? ['--no-sandbox', '.'] : ['.']
  // A computer with 8 GB of memory, as a five-year-old laptop: too small for the language model, and the models step says so.
  const none = { BYGGMOTE_MODELS: join(config, 'no-models'), HF_HUB_CACHE: join(config, 'no-models'), HF_HUB_OFFLINE: '1', BYGGMOTE_MEMORY_GB: '8' }
  app = await electron.launch({
    args,
    cwd: here,
    env: { ...process.env, ...none, BYGGMOTE_CONFIG: config, BYGGMOTE_USER_DATA: userData, BYGGMOTE_NO_KEYCHAIN: '1', BYGGMOTE_HIDDEN: '1' }
  })
  win = await app.firstWindow()
})

test.afterAll(async () => {
  await app?.close()
  rmSync(config, { recursive: true, force: true })
  rmSync(userData, { recursive: true, force: true })
})

test('the first run comes first, and needs a name before it goes on', async () => {
  await expect(win.getByRole('heading', { name: 'Välkommen till Byggmöte' })).toBeVisible()
  await expect(win.getByRole('navigation', { name: 'Huvudmeny' })).toHaveCount(0)
  await expect(win.getByRole('button', { name: 'Fortsätt' })).toBeDisabled()
  await win.getByLabel('Ditt namn').fill('Anna Berg')
  await win.getByRole('button', { name: 'Fortsätt' }).click()
  await expect(win.getByRole('heading', { name: 'Mikrofon' })).toBeVisible()
})

test('the models can be left for later, and Stommen can be skipped', async () => {
  await win.getByRole('button', { name: 'Fortsätt' }).click()
  await expect(win.getByRole('heading', { name: 'Förbereder Byggmöte' })).toBeVisible()
  await expect(win.getByText(/av \d+ modeller installerade/)).toBeVisible()
  await expect(win.getByText(/Datorn har 8 GB minne och språkmodellen som skriver protokollet behöver 16 GB/)).toBeVisible()
  await win.getByRole('button', { name: 'Fortsätt, installera senare' }).click()
  await expect(win.getByRole('heading', { name: 'Stommen', exact: true })).toBeVisible()
  await win.getByRole('button', { name: 'Hoppa över' }).click()
  await expect(win.getByRole('heading', { name: 'Klart, Anna' })).toBeVisible()
  await expect(win.getByText('Installationen pågår, du kan börja ändå')).toBeVisible()
})

test('finishing opens the app, and the first run is not shown again', async () => {
  await win.getByRole('button', { name: 'Börja använda Byggmöte' }).click()
  await expect(win.getByRole('navigation', { name: 'Huvudmeny' })).toBeVisible()
  await win.reload()
  await expect(win.getByRole('navigation', { name: 'Huvudmeny' })).toBeVisible()
  await expect(win.getByRole('heading', { name: 'Välkommen till Byggmöte' })).toHaveCount(0)
})

test('the settings keep a name and a choice, and say where the meetings are', async () => {
  sw = await settings()
  await expect(sw.getByLabel('Ditt namn')).toHaveValue('Anna Berg')
  await expect(sw.getByText(join(config, 'transcripts'))).toBeVisible()
  await sw.getByLabel('Ditt namn').fill('Anna Maria Berg')
  await sw.getByLabel('Ditt namn').press('Enter') // kept as it is made: there is no Save
  await expect.poll(() => win.evaluate(() => window.api.settings().then((s) => s.name))).toBe('Anna Maria Berg')
  await sw.getByRole('tab', { name: 'Inspelning' }).click()
  const voices = sw.getByLabel('Känn igen röster')
  await expect(voices).toBeChecked()
  await voices.uncheck()
  // Kept when the main process says so, not when the box looks unticked.
  await expect.poll(() => win.evaluate(async () => (await (globalThis as unknown as { api: { settings(): Promise<{ voices: boolean }> } }).api.settings()).voices)).toBe(false)
  await win.reload()
  sw = await settings()
  await expect(sw.getByLabel('Ditt namn')).toHaveValue('Anna Maria Berg')
  await sw.getByRole('tab', { name: 'Inspelning' }).click()
  await expect(sw.getByLabel('Känn igen röster')).not.toBeChecked()
})

test('the models tab shows how many are installed, and the first run can be shown again', async () => {
  await sw.getByRole('tab', { name: 'Modeller' }).click()
  await expect(sw.getByText(/av \d+ modeller installerade/)).toBeVisible()
  await sw.getByRole('tab', { name: 'Allmänt' }).click()
  await sw.getByRole('button', { name: 'Visa introduktionen' }).click() // closes Inställningar: the first run is the main window's
  await expect(win.getByRole('heading', { name: 'Välkommen till Byggmöte' })).toBeVisible()
  await expect(win.getByLabel('Ditt namn')).toHaveValue('Anna Maria Berg')
})
