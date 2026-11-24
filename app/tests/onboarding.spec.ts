// A computer that has never run the app: the first run asks who is using it, goes through the microphone, the models and
// Stommen, and ends on the app. Then the settings change what the app keeps, and the first run can be shown again.
// Nothing here fetches a model or signs in anywhere.
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'

const here = join(__dirname, '..')

let config: string
let userData: string
let app: ElectronApplication
let win: Page

test.beforeAll(async () => {
  config = mkdtempSync(join(tmpdir(), 'byggmote-first-'))
  userData = mkdtempSync(join(tmpdir(), 'byggmote-first-user-'))
  const args = process.env.CI && process.platform === 'linux' ? ['--no-sandbox', '.'] : ['.']
  const none = { BYGGMOTE_MODELS: join(config, 'no-models'), HF_HUB_CACHE: join(config, 'no-models'), HF_HUB_OFFLINE: '1' }
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
  await expect(win.getByRole('heading', { name: 'Taligenkänning och protokoll' })).toBeVisible()
  await expect(win.getByRole('list', { name: 'Modeller' }).getByRole('button', { name: 'Hämta', exact: true }).first()).toBeVisible()
  await win.getByRole('button', { name: 'Fortsätt, hämta senare' }).click()
  await expect(win.getByRole('heading', { name: 'Stommen', exact: true })).toBeVisible()
  await win.getByRole('button', { name: 'Hoppa över' }).click()
  await expect(win.getByRole('heading', { name: 'Klart, Anna' })).toBeVisible()
  await expect(win.getByText('Modellerna hämtas, du kan börja ändå')).toBeVisible()
})

test('finishing opens the app, and the first run is not shown again', async () => {
  await win.getByRole('button', { name: 'Börja använda Byggmöte' }).click()
  await expect(win.getByRole('navigation', { name: 'Huvudmeny' })).toBeVisible()
  await win.reload()
  await expect(win.getByRole('navigation', { name: 'Huvudmeny' })).toBeVisible()
  await expect(win.getByRole('heading', { name: 'Välkommen till Byggmöte' })).toHaveCount(0)
})

test('the settings keep a name and a choice, and say where the meetings are', async () => {
  await win.getByRole('button', { name: 'Inställningar' }).click()
  await expect(win.getByLabel('Ditt namn')).toHaveValue('Anna Berg')
  await expect(win.getByText(join(config, 'transcripts'))).toBeVisible()
  await win.getByLabel('Ditt namn').fill('Anna Maria Berg')
  await win.getByRole('button', { name: 'Spara namn' }).click()
  await expect(win.getByText('Sparat.')).toBeVisible()
  await win.getByRole('tab', { name: 'Inspelning' }).click()
  const voices = win.getByLabel('Känn igen röster')
  await expect(voices).toBeChecked()
  await voices.uncheck()
  // Kept when the main process says so, not when the box looks unticked.
  await expect.poll(() => win.evaluate(async () => (await window.api.settings()).voices)).toBe(false)
  await win.reload()
  await win.getByRole('button', { name: 'Inställningar' }).click()
  await expect(win.getByLabel('Ditt namn')).toHaveValue('Anna Maria Berg')
  await win.getByRole('tab', { name: 'Inspelning' }).click()
  await expect(win.getByLabel('Känn igen röster')).not.toBeChecked()
})

test('the models tab lists them, and the first run can be shown again', async () => {
  await win.getByRole('tab', { name: 'Modeller' }).click()
  await expect(win.getByRole('list', { name: 'Modeller' })).toBeVisible()
  await win.getByRole('tab', { name: 'Allmänt' }).click()
  await win.getByRole('button', { name: 'Visa introduktionen' }).click()
  await expect(win.getByRole('heading', { name: 'Välkommen till Byggmöte' })).toBeVisible()
  await expect(win.getByLabel('Ditt namn')).toHaveValue('Anna Maria Berg')
})
