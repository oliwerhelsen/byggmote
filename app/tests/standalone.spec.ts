// The app with no Stommen at all, on a computer that has never run it: a project made in the window, its overview, its
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

// Inställningar is a window of its own. It is opened afresh each time, so it shows what the app has now.
let sw: Page
async function settings(): Promise<Page> {
  for (const p of app.windows()) if (p !== win) await p.close()
  const [p] = await Promise.all([app.waitForEvent('window'), win.getByRole('button', { name: 'Inställningar' }).click()])
  await p.waitForLoadState()
  return p
}

test.beforeAll(async () => {
  config = mkdtempSync(join(tmpdir(), 'byggmote-alone-'))
  userData = mkdtempSync(join(tmpdir(), 'byggmote-alone-user-'))
  const args = process.env.CI && process.platform === 'linux' ? ['--no-sandbox', '.'] : ['.']
  const none = { BYGGMOTE_MODELS: join(config, 'no-models'), HF_HUB_CACHE: join(config, 'no-models'), HF_HUB_OFFLINE: '1' }
  app = await electron.launch({
    args,
    cwd: here,
    env: { ...process.env, ...none, BYGGMOTE_CONFIG: config, BYGGMOTE_USER_DATA: userData, BYGGMOTE_NO_KEYCHAIN: '1', BYGGMOTE_HIDDEN: '1', BYGGMOTE_SETUP: '1' }
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
  await expect(win.getByText('Stommen är inte kopplat', { exact: true })).toBeVisible()
  await expect(win.getByText('Projekt och Roller hämtas från Stommen')).toHaveCount(0)
})

test('with no project, Inställningar opens in a window of its own and the main window still asks for one', async () => {
  sw = await settings()
  await expect(sw.getByRole('tablist', { name: 'Inställningar' })).toBeVisible()
  await expect(sw.getByRole('tab', { name: 'Allmänt' })).toHaveAttribute('aria-selected', 'true') // the pane's name is the heading
  await expect(sw.getByRole('heading', { name: 'Allmänt', level: 1 })).toHaveCount(1)
  await expect(win.getByRole('heading', { name: 'Skapa ditt första projekt' })).toBeVisible()
  await sw.close()
})

test('a project is made and opens on its overview, from which the meetings are one click away', async () => {
  await win.getByLabel('Projektets namn').fill('Kv. Björken')
  await win.getByRole('button', { name: 'Skapa projekt' }).click()
  await expect(win.getByRole('heading', { name: 'Kv. Björken', level: 1 })).toBeVisible()
  await expect(win.getByRole('heading', { name: 'Nästa möte' })).toBeVisible()
  await expect(win.getByRole('button', { name: 'Spela in möte' })).toBeVisible()
})

test('a project is renamed, a new one is named in a dialog, and a removed one leaves the select', async () => {
  await win.getByRole('button', { name: 'Översikt' }).click()
  await win.getByRole('button', { name: 'Byt namn' }).click()
  await win.getByLabel('Nytt namn').fill('Kv. Asken')
  await win.getByRole('button', { name: 'Spara' }).click()
  await expect(win.getByRole('heading', { name: 'Kv. Asken', level: 1 })).toBeVisible()

  await win.getByLabel('Projekt', { exact: true }).selectOption({ label: 'Nytt projekt…' })
  const dialog = win.getByRole('dialog', { name: 'Nytt projekt' })
  await dialog.getByLabel('Projektets namn').fill('Kv. Lönnen')
  await dialog.getByRole('button', { name: 'Skapa projekt' }).click()
  await expect(win.getByRole('heading', { name: 'Kv. Lönnen', level: 1 })).toBeVisible() // it opens on the new project's overview
  await expect(dialog).toHaveCount(0)

  await win.getByRole('button', { name: 'Ta bort projektet' }).click()
  await win.getByRole('button', { name: 'Ta bort projektet' }).last().click()
  await expect(win.getByRole('heading', { name: 'Kv. Asken', level: 1 })).toBeVisible()
  await expect(win.getByLabel('Projekt', { exact: true }).locator('option')).toHaveText(['Kv. Asken', 'Nytt projekt…'])
})

test('the window never offered to send anything to Stommen', async () => {
  await expect(win.getByText('Skicka till Stommen')).toHaveCount(0)
})

test('a computer not yet signed in reaches Stommen from Inställningar', async () => {
  sw = await settings()
  await sw.getByRole('button', { name: 'Koppla till Stommen' }).click()
  await expect(sw.getByRole('heading', { name: 'Stommen', level: 1 })).toBeVisible()
  await expect(sw.getByRole('heading', { name: 'Logga in i Stommen' })).toBeVisible()
  await expect(sw.getByRole('button', { name: 'Logga in' })).toHaveCount(1) // the form's own
})
