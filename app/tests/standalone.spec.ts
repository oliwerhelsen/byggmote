// The app with no Stommen at all, on a computer that has never run it: a project made in the window, the people at its
// meetings, a rename and a removal, and the first mötesserie so a meeting can be recorded at once. Nothing here asks the
// engine for a model, and nothing signs in anywhere.
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
  config = mkdtempSync(join(tmpdir(), 'byggmote-alone-'))
  userData = mkdtempSync(join(tmpdir(), 'byggmote-alone-user-'))
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

test('with no project it asks for one, and says nothing about needing Stommen', async () => {
  await expect(win.getByRole('heading', { name: 'Skapa ditt första projekt' })).toBeVisible()
  await expect(win.getByText('Stommen är inte kopplat än.')).toBeVisible()
  await expect(win.getByText('Projekt och Roller hämtas från Stommen')).toHaveCount(0)
})

test('a project is made and opens on its first meeting', async () => {
  await win.getByLabel('Projektets namn').fill('Kv. Björken')
  await win.getByRole('button', { name: 'Skapa projekt' }).click()
  await expect(win.getByRole('heading', { name: 'Byggmöte 1' })).toBeVisible()
  await expect(win.getByRole('button', { name: 'Spela in mötet' })).toBeVisible()
})

test('people are added with a Roll and are taken out', async () => {
  await win.getByRole('button', { name: 'Projekt', exact: true }).click()
  const form = win.getByRole('form', { name: 'Lägg till person i Kv. Björken' })
  await form.getByLabel('Namn').fill('Anna Lind')
  await form.getByLabel('Roll').fill('Platschef')
  await form.getByRole('button', { name: 'Lägg till' }).click()
  await expect(win.getByText('Anna Lind, Platschef')).toBeVisible()

  await form.getByLabel('Namn').fill('Erik Berg')
  await form.getByRole('button', { name: 'Lägg till' }).click()
  await expect(win.getByText('Erik Berg', { exact: true })).toBeVisible()

  await win.getByRole('button', { name: 'Ta bort Erik Berg från Kv. Björken' }).click()
  await expect(win.getByText('Erik Berg')).toHaveCount(0)
  await expect(win.getByText('Anna Lind, Platschef')).toBeVisible()
})

test('a project is renamed, and a removed one leaves the list', async () => {
  await win.getByRole('button', { name: 'Byt namn' }).click()
  await win.getByLabel('Nytt namn').fill('Kv. Asken')
  await win.getByRole('button', { name: 'Spara' }).click()
  await expect(win.getByRole('heading', { name: 'Kv. Asken' })).toBeVisible()

  await win.getByLabel('Projektets namn').fill('Kv. Lönnen')
  await win.getByRole('button', { name: 'Skapa projekt' }).click()
  await expect(win.getByRole('heading', { name: 'Byggmöte 1' })).toBeVisible() // it opens on the new project
  await win.getByRole('button', { name: 'Projekt', exact: true }).click()
  await expect(win.getByRole('heading', { name: 'Kv. Lönnen' })).toBeVisible()
  await win.getByRole('region', { name: 'Kv. Lönnen' }).getByRole('button', { name: 'Ta bort projektet' }).click()
  await win.getByRole('button', { name: 'Ta bort projektet' }).last().click()
  await expect(win.getByRole('heading', { name: 'Kv. Lönnen' })).toHaveCount(0)
  await expect(win.getByRole('heading', { name: 'Kv. Asken' })).toBeVisible()
})

test('the window never offered to send anything to Stommen', async () => {
  await expect(win.getByText('Skicka till Stommen')).toHaveCount(0)
})
