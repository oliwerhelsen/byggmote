// The recording's shortcuts are the person's to change in Inställningar: a click on a command, then the new keys. What
// is chosen is kept over a restart, and the recording window, the Möte menu and what the system is asked for follow.
// Keys another command has, keys without a modifier and keys the system does not give the app are refused in words.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'

declare const window: { api: import('../src/shared/types').Api }

const here = join(__dirname, '..')
const python = join(here, '..', 'engine', '.venv', ...(process.platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python']))

let config: string
let userData: string
let app: ElectronApplication
let win: Page
let sw: Page

async function launch(): Promise<void> {
  const args = process.env.CI && process.platform === 'linux' ? ['--no-sandbox', '.'] : ['.']
  const none = { BYGGMOTE_MODELS: join(config, 'no-models'), HF_HUB_CACHE: join(config, 'no-models'), HF_HUB_OFFLINE: '1' }
  app = await electron.launch({ args, cwd: here, env: { ...process.env, ...none, BYGGMOTE_CONFIG: config, BYGGMOTE_HIDDEN: '1', BYGGMOTE_USER_DATA: userData, BYGGMOTE_SETUP: '1' } })
  win = await app.firstWindow()
  await expect(win.getByRole('heading', { name: 'Senaste möten' })).toBeVisible()
}

/** Inställningar on Inspelning, where the shortcuts are. */
async function recordingPane(): Promise<Page> {
  const [p] = await Promise.all([app.waitForEvent('window'), app.evaluate(({ Menu }) => Menu.getApplicationMenu()!.getMenuItemById('settings')!.click())])
  await p.waitForLoadState()
  await p.getByRole('tab', { name: 'Inspelning' }).click()
  return p
}

const kept = (): Promise<Record<string, string>> => win.evaluate(async () => (await window.api.settings()).shortcuts as Record<string, string>)
const choose = async (command: string, keys: string): Promise<void> => {
  await sw.getByRole('button', { name: `${command}, byt tangenter` }).click()
  await expect(sw.getByText('Tryck nya tangenter')).toBeVisible()
  await sw.keyboard.press(keys)
}
// The keys as this computer writes them: one cap on the Mac, one per key elsewhere.
const written = (letter: string): string => (process.platform === 'darwin' ? `⌃⌥${letter}` : `CtrlAlt${letter}`)

test.beforeAll(async () => {
  config = mkdtempSync(join(tmpdir(), 'byggmote-keys-'))
  userData = mkdtempSync(join(tmpdir(), 'byggmote-keys-user-'))
  execFileSync(python, [join(__dirname, 'fixture.py')], { env: { ...process.env, BYGGMOTE_CONFIG: config } })
  await launch()
  // A runner without a desktop is given no shortcut at all, and then none can be chosen: that is said, and not tested here.
  const able = await app.evaluate(({ globalShortcut }) => {
    const ok = globalShortcut.register('Control+Alt+F9', () => {})
    globalShortcut.unregister('Control+Alt+F9')
    return ok
  })
  test.skip(!able, 'the system gives this run no shortcuts')
})

test.afterAll(async () => {
  await app?.close()
  for (const d of [config, userData]) rmSync(d, { recursive: true, force: true })
})

test('a click on a command and new keys change its shortcut', async () => {
  sw = await recordingPane()
  await expect(sw.getByText('Fungerar även när ett annat program ligger överst. Klicka på ett kommando för att byta tangenter.')).toBeVisible()
  await expect(sw.getByRole('button', { name: 'Spela in möte, byt tangenter' })).toHaveCount(0) // the menu's own, listed and not changed
  await choose('Nästa rubrik', 'Control+Alt+K')
  await expect.poll(kept).toEqual({ next: 'Control+Alt+K' })
  await expect(sw.getByRole('button', { name: 'Nästa rubrik, byt tangenter' })).toHaveText(new RegExp(written('K').split('').join('\\s*\\+?\\s*')))
})

test('keys another command has, keys with no modifier and keys the system keeps are refused in words', async () => {
  await choose('Pausa', 'Control+Alt+K')
  await expect(sw.getByRole('alert')).toHaveText(/används redan av Nästa rubrik\. Välj andra tangenter\.$/)
  await choose('Pausa', 'ControlOrMeta+R')
  await expect(sw.getByRole('alert')).toHaveText(/används redan av Spela in möte\. Välj andra tangenter\.$/)
  await choose('Pausa', 'K')
  await expect(sw.getByRole('alert')).toHaveText(/^Ett kortkommando är .+ tillsammans med en bokstav, en siffra eller en funktionstangent\.$/)
  await choose('Sätt märke', 'Control+Alt+9')
  await expect(sw.getByRole('alert')).toHaveText('Märkena har siffrorna 1 till 4. Tryck tangenterna tillsammans med en av dem.')
  // another program has it: here the test takes it first
  await app.evaluate(({ globalShortcut }) => globalShortcut.register('Control+Alt+J', () => {}))
  await choose('Pausa', 'Control+Alt+J')
  await expect(sw.getByRole('alert')).toHaveText(/^Datorn ger inte .+ till Byggmöte, ett annat program använder det\. Välj andra tangenter\.$/)
  await app.evaluate(({ globalShortcut }) => globalShortcut.unregister('Control+Alt+J'))
  expect(await kept()).toEqual({ next: 'Control+Alt+K' }) // nothing that was refused is kept
  await choose('Pausa', 'Escape') // and Esc leaves the keys as they were
  await expect(sw.getByText('Tryck nya tangenter')).toHaveCount(0)
  expect(await kept()).toEqual({ next: 'Control+Alt+K' })
})

test('the chosen keys are kept over a restart, and the recording window, the menu and the system follow them', async () => {
  await app.close()
  await launch()
  expect(await kept()).toEqual({ next: 'Control+Alt+K' })
  await win.getByRole('button', { name: 'Spela in möte' }).click()
  await win.getByRole('checkbox', { name: 'Alla i rummet vet att mötet spelas in' }).check()
  const [rec] = await Promise.all([app.waitForEvent('window'), win.getByRole('button', { name: 'Börja spela in' }).click()])
  await rec.waitForLoadState()
  const marks = rec.getByRole('region', { name: 'Sätt ett märke' })
  await expect(marks.getByRole('button', { name: /Beslut/ })).toBeVisible()
  const shown = (): Promise<string> => rec.locator('kbd').allTextContents().then((k) => k.join(' '))
  // the marks are there with or without a microphone; the next heading's key only once the recording runs
  const std = process.platform === 'darwin' ? '⌃⌥1' : 'Alt+Skift+1'
  await expect.poll(shown).toContain(std)
  const taken = (keys: string): Promise<boolean> => app.evaluate(({ globalShortcut }, k) => globalShortcut.isRegistered(k), keys)
  expect(await taken('Control+Alt+K')).toBe(true)
  const inMenu = (): Promise<string | undefined> => app.evaluate(({ Menu }) => Menu.getApplicationMenu()!.items.flatMap((m) => m.submenu?.items ?? []).find((i) => i.label.startsWith('Nästa rubrik'))?.accelerator as string | undefined)
  expect(await inMenu()).toBe('Control+Alt+K')

  // changed while the meeting goes on: the window that records reads them again, and the system is asked for the new ones
  sw = await recordingPane()
  await choose('Sätt märke', 'Control+Shift+2')
  await expect.poll(kept).toEqual({ next: 'Control+Alt+K', mark: 'Control+Shift+1' })
  await expect.poll(shown).toContain(process.platform === 'darwin' ? '⌃⇧4' : 'Ctrl+Skift+4')
  expect(await taken('Control+Shift+3')).toBe(true)

  await sw.getByRole('button', { name: 'Återställ standard' }).click()
  await expect.poll(kept).toEqual({})
  await expect.poll(shown).toContain(std)
  expect(await taken('Control+Alt+K')).toBe(false)
  expect(await inMenu()).not.toBe('Control+Alt+K')
  await sw.close()
  rec.on('dialog', (d) => void d.accept())
  await Promise.all([rec.waitForEvent('close'), rec.getByRole('button', { name: /Stäng|Avbryt inspelningen/ }).click().catch(() => {})])
})
