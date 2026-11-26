// The built app against the real engine and a knowledge base the engine wrote (fixture.py). No model runs: what is
// tested is that the window shows what the engine's files say, the way from one view to the next, and that what a
// person corrects in a protocol is there when the engine is asked again. The tests share the knowledge base and run
// in order: the later ones correct the protocol the earlier ones read.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
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
  // No model can run from a test: the engine is shown folders that have none, and may not fetch one. A test that
  // asks for a protocol to be written, by mistake or after another test failed, gets an error and not minutes of work.
  const none = { BYGGMOTE_MODELS: join(config, 'no-models'), HF_HUB_CACHE: join(config, 'no-models'), HF_HUB_OFFLINE: '1' }
  // Hidden: a test run does not take the screen, and whoever sits at the computer cannot click in it.
  app = await electron.launch({ args, cwd: here, env: { ...process.env, ...none, BYGGMOTE_CONFIG: config, BYGGMOTE_HIDDEN: '1',
    BYGGMOTE_USER_DATA: mkdtempSync(join(tmpdir(), 'byggmote-app-user-')), BYGGMOTE_SETUP: '1' } })
  win = await app.firstWindow()
})

test.afterAll(async () => {
  await app?.close()
  rmSync(config, { recursive: true, force: true })
})

// The application menu is the Mac's menu bar and the window's own on Windows and Linux: a choice in it, or its
// shortcut, reaches the window as a command.
const menu = (id: string): Promise<void> => app.evaluate(({ Menu }, item) => Menu.getApplicationMenu()!.getMenuItemById(item)!.click(), id)
const enabled = (id: string): Promise<boolean> => app.evaluate(({ Menu }, item) => Menu.getApplicationMenu()!.getMenuItemById(item)!.enabled, id)

// Every test starts on the project's overview, reached through the sidebar; a recording has its own way back.
const toOverview = (): Promise<void> => win.getByRole('navigation', { name: 'Huvudmeny' }).getByRole('button', { name: 'Översikt' }).click()

test.beforeEach(async () => {
  if (await win.getByRole('button', { name: 'Till översikten' }).count()) await win.getByRole('button', { name: 'Till översikten' }).click()
  else await toOverview()
  await expect(win.getByRole('heading', { name: 'Senaste möten' })).toBeVisible()
})

test('the meetings of a project, the next one and what is still open', async () => {
  await expect(win.getByRole('heading', { name: 'Nästa möte' })).toBeVisible()
  await expect(win.getByText('En öppen punkt följer med från tidigare möten. En har passerat sitt datum.')).toBeVisible()
  const rows = win.getByRole('region', { name: 'Senaste möten' }).locator('tbody tr')
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
  await expect(economy).toContainText('1 öppen punkt')
  await expect(economy.locator('.point')).toHaveText(/3\.4\.1\s*Att göra\s*Platschefen lämnar underlag.*Platschef\s*Förfallen 2026-11-12/)
  await expect(win.locator('.headings > li')).toHaveCount(11)
  // the points under a heading can be put away, and what follows along is counted beside the list
  await economy.getByRole('button', { name: 'Dölj punkterna under Ekonomi' }).click()
  await expect(economy.locator('.point')).toHaveCount(0)
  await economy.getByRole('button', { name: 'Visa punkterna under Ekonomi' }).click()
  const about = win.getByRole('complementary', { name: 'Om dagordningen' })
  await expect(about).toContainText('1 öppen punkt')
  await expect(about).toContainText('En har passerat sitt datum.')
  await expect(about).toContainText('Från byggmöte 31')
  // from an agenda the meeting is recorded with it: the dialog does not ask
  await win.getByRole('button', { name: 'Spela in', exact: true }).click()
  const dialog = win.getByRole('dialog', { name: 'Nytt möte' })
  await expect(dialog).toContainText('Byggmöte 5 · Kv. Eken kontorshus')
  await expect(dialog.getByText('Mikrofon:')).toBeVisible()
  await expect(dialog.getByRole('radio')).toHaveCount(0)
  await dialog.getByRole('button', { name: 'Avbryt' }).click()
  // opened again at once, from elsewhere, it asks
  await menu('overview')
  await menu('record')
  await expect(dialog.getByRole('radio')).toHaveCount(2)
  await dialog.getByRole('button', { name: 'Avbryt' }).click()
  await expect(dialog).toBeHidden()
})

test('a protocol: who was there, the points with their checks, and the transcript', async () => {
  await win.getByRole('button', { name: 'Byggmöte 4', exact: true }).click()
  await expect(win.getByRole('heading', { name: 'Protokoll, byggmöte 4' })).toBeVisible()
  await expect(win.locator('.attendees li').first()).toHaveText('Maria Lindqvist, Projektledare')

  // the formats to save it as are behind one button
  await win.getByRole('button', { name: 'Spara som' }).click()
  await expect(win.getByRole('menuitem')).toHaveText(['Word', 'PDF', 'Markdown', 'Kopiera texten'])
  await win.keyboard.press('Escape')
  await expect(win.getByRole('menu')).toHaveCount(0)
  await expect(win.getByRole('button', { name: 'Spara som' })).toBeFocused()

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

/** The small window a meeting is recorded in, opened by the dialog. It closes again whether or not this computer has a microphone. */
async function recordingWindow(): Promise<Page> {
  const [rec] = await Promise.all([app.waitForEvent('window'), win.getByRole('button', { name: 'Börja spela in' }).click()])
  await rec.waitForLoadState()
  return rec
}
async function closeRecording(rec: Page): Promise<void> {
  rec.on('dialog', (d) => void d.accept()) // "Avbryta inspelningen?"
  // The window can be gone before the click has been told it landed: that is the click doing its work, not failing.
  await Promise.all([rec.waitForEvent('close'), rec.getByRole('button', { name: /Stäng|Avbryt inspelningen/ }).click().catch(() => {})])
}

test('nothing is recorded before everyone knows, and the meeting is recorded in a window of its own', async () => {
  await win.getByRole('button', { name: 'Spela in möte' }).click()
  const start = win.getByRole('button', { name: 'Börja spela in' })
  await expect(win.getByRole('radio', { name: /Med dagordning/ })).toBeChecked()
  await expect(start).toBeDisabled()
  await win.getByRole('checkbox', { name: 'Alla i rummet vet att mötet spelas in' }).check()
  await expect(start).toBeEnabled()
  const rec = await recordingWindow()
  await expect(rec.getByRole('heading', { name: 'Byggmöte 5' })).toHaveCount(1)
  await rec.getByRole('button', { name: 'Alla rubriker' }).click()
  await expect(rec.locator('.heading')).toHaveCount(11)
  // the main window is free, shows the recording, and does not offer a second one
  const side = win.getByRole('navigation', { name: 'Huvudmeny' })
  await expect(side.getByText('Spelas in', { exact: true })).toBeVisible()
  await expect(win.getByRole('heading', { name: 'Senaste möten' })).toBeVisible()
  expect(await enabled('record')).toBe(false)
  // its shortcuts work in any program while it is open (asked of the Mac only: a runner without a desktop has none to give)
  const taken = (): Promise<boolean> => app.evaluate(({ globalShortcut }) => globalShortcut.isRegistered('Control+Alt+N'))
  if (process.platform === 'darwin') expect(await taken()).toBe(true)
  await closeRecording(rec)
  if (process.platform === 'darwin') await expect.poll(taken).toBe(false) // given back once the window is gone
  await expect(side.getByText('Spelas in', { exact: true })).toHaveCount(0)
  expect(await enabled('record')).toBe(true)
})

test('a meeting can be recorded without an agenda', async () => {
  await win.getByRole('button', { name: 'Spela in möte' }).click()
  await win.getByLabel('Utan dagordning').check()
  await win.getByRole('checkbox', { name: 'Alla i rummet vet att mötet spelas in' }).check()
  const rec = await recordingWindow()
  await expect(rec.getByRole('heading', { name: 'Byggmöte 5' })).toHaveCount(1)
  await expect(rec.getByRole('button', { name: 'Alla rubriker' })).toHaveCount(0)
  await expect(rec.getByRole('heading', { name: 'Dagordning' })).toHaveCount(0)
  await closeRecording(rec)
})

const protocol4 = async (): Promise<void> => {
  await win.getByRole('button', { name: 'Byggmöte 4', exact: true }).click()
  await expect(win.getByRole('heading', { name: 'Protokoll, byggmöte 4' })).toBeVisible()
}

test('a person says an amount is right, and takes it back', async () => {
  await protocol4()
  const decision = win.locator('.point').filter({ hasText: '4.4.1' })
  await decision.getByRole('button', { name: 'Beloppet 86 500 kr i punkt 4.4.1 stämmer' }).click()
  await expect(decision).toContainText('Beloppet 86 500 kr är kontrollerat mot inspelningen.')
  await expect(win.getByText('En sak ska kontrolleras')).toHaveCount(0)

  await toOverview()
  const row = win.locator('tbody tr').filter({ hasText: 'Byggmöte 4' })
  await expect(row).toContainText('Utkast')
  await expect(row).not.toContainText('att kontrollera')

  await protocol4()
  await decision.getByRole('button', { name: 'Ångra kontrollen av 86 500 kr i punkt 4.4.1' }).click()
  await expect(decision).toContainText('Kontrollera beloppet 86 500 kr.')
})

test('a point is changed in its form, and what stays open is on the next agenda', async () => {
  await protocol4()
  await win.getByRole('button', { name: 'Ändra punkt 4.3.1' }).click()
  const form = win.getByRole('form', { name: 'Ändra punkt 4.3.1' })
  await expect(form.getByLabel('Punkten')).toBeFocused()
  await expect(form.getByLabel('Återstår efter mötet')).toHaveCount(0) // a note is said and done
  await form.getByLabel('Punkten').fill('Platschefen redovisar läget för stommen på plan tre.')
  await form.getByLabel('Typ').selectOption({ label: 'Att göra' })
  await expect(form.getByLabel('Återstår efter mötet')).toBeChecked()
  await form.getByLabel('Ansvarig').selectOption({ label: 'Platschef' })
  await form.getByLabel('Senast').fill('2026-11-26')
  await form.getByRole('button', { name: 'Spara' }).click()

  const point = win.locator('.point').filter({ hasText: '4.3.1' })
  await expect(point).toContainText('Platschefen redovisar läget för stommen på plan tre.')
  await expect(point).toContainText('Att göra')
  await expect(point).toContainText('Ändrad för hand')
  await expect(point).toContainText('Ansvarig: Platschef. Senast 2026-11-26')
  await expect(win.getByRole('button', { name: 'Ändra punkt 4.3.1' })).toBeFocused()

  // the form remembers what the model wrote
  await win.getByRole('button', { name: 'Ändra punkt 4.3.1' }).click()
  await expect(form).toContainText('Modellen skrev: ”Stommen på plan tre är klar.”')
  await form.getByRole('button', { name: 'Avbryt' }).click()

  await toOverview()
  await expect(win.getByRole('region', { name: 'Öppna punkter' })).toContainText('4.3.1')
})

test('a point is added where it is said, taken out and put back', async () => {
  await protocol4()
  await win.locator('.lines').getByRole('button', { name: 'Lyssna från 14:20' }).click()
  await win.getByRole('button', { name: 'Lägg till punkt under Ekonomi' }).click()
  const form = win.getByRole('form', { name: 'Ny punkt' })
  await expect(form).toContainText('Punkten pekar på 14:20 i utskriften, där Maria Lindqvist säger')
  await expect(form.getByRole('button', { name: 'Lägg till punkten' })).toBeDisabled()
  await form.getByLabel('Punkten', { exact: true }).fill('Mängdregleringen av schakt tas upp på nästa möte')
  await form.getByLabel('Typ').selectOption({ label: 'Notering' })
  await form.getByRole('button', { name: 'Lägg till punkten' }).click()

  const point = win.locator('.point').filter({ hasText: '4.4.2' })
  await expect(point).toContainText('Mängdregleringen av schakt tas upp på nästa möte.')
  await expect(point).toContainText('Tillagd för hand')
  await expect(point.getByRole('button', { name: 'Lyssna från 14:20' })).toBeVisible()

  await win.getByRole('button', { name: 'Ändra punkt 4.4.2' }).click()
  await win.getByRole('button', { name: 'Ta bort punkten' }).click()
  await expect(point).toHaveCount(0)
  await expect(win.getByText('En punkt är borttagen')).toBeVisible()
  await win.getByRole('button', { name: 'Lägg tillbaka punkt 4.4.2' }).click()
  await expect(point).toContainText('Mängdregleringen av schakt tas upp på nästa möte.')
  await expect(win.getByText('En punkt är borttagen')).toHaveCount(0)
})

test('a model does not write over what a person has set right without a yes', async () => {
  await protocol4()
  const decision = win.locator('.point').filter({ hasText: '4.4.1' })
  await decision.getByRole('button', { name: 'Beloppet 86 500 kr i punkt 4.4.1 stämmer' }).click() // a correction of this test's own
  await expect(decision).toContainText('är kontrollerat mot inspelningen')
  await win.getByRole('button', { name: 'Skriv om protokollet' }).click()
  await expect(win.getByRole('alert')).toContainText(/Protokollet har (en rättning\. Den|\d+ rättningar\. De) försvinner om modellen skriver om protokollet\./)
  await win.getByRole('button', { name: /^Behåll rättning(en|arna)$/ }).click()
  await expect(win.getByRole('alert')).toHaveCount(0)
  await expect(decision).toContainText('är kontrollerat mot inspelningen')
})

test('someone who was there and said nothing is added, and taken off again', async () => {
  await protocol4()
  await win.getByLabel('Någon som var med utan att säga något').selectOption({ label: 'Sara Nyberg, BAS-U' })
  await win.getByRole('button', { name: 'Lägg till som närvarande' }).click()
  const there = win.locator('.attendees li').filter({ hasText: 'Sara Nyberg' })
  await expect(there).toContainText('Sara Nyberg, BAS-U')
  await expect(there).toContainText('Tillagd för hand')
  await expect(win.getByLabel('Någon som var med utan att säga något')).toHaveCount(0) // everyone in the project is there now
  await win.getByRole('button', { name: 'Ta bort Sara Nyberg från närvarande' }).click()
  await expect(there).toHaveCount(0)
})

test('a protocol the next meeting builds on is read, not changed', async () => {
  await win.getByRole('button', { name: 'Byggmöte 3', exact: true }).click()
  await expect(win.getByRole('heading', { name: 'Protokoll, byggmöte 3' })).toBeVisible()
  await expect(win.getByText('Byggmöte 4 bygger på det här protokollet, så punkterna går inte att ändra längre.')).toBeVisible()
  await expect(win.locator('.point').filter({ hasText: '3.4.1' })).toBeVisible()
  await expect(win.getByRole('button', { name: /^Ändra punkt/ })).toHaveCount(0)
  await expect(win.getByRole('button', { name: /^Lägg till punkt under/ })).toHaveCount(0)
  await expect(win.getByRole('button', { name: 'Skriv om protokollet' })).toHaveCount(0)
})

test('the application menu opens the views, and greys out what cannot run', async () => {
  await menu('overview')
  await expect(win.getByRole('heading', { name: 'Kv. Eken kontorshus', level: 1 })).toBeVisible()
  await menu('agenda')
  await expect(win.getByRole('heading', { name: 'Dagordning, byggmöte 5' })).toBeVisible()
  await menu('record')
  await expect(win.getByRole('heading', { name: 'Nytt möte' })).toBeVisible()
  await win.getByRole('button', { name: 'Avbryt', exact: true }).click()
  const [sw] = await Promise.all([app.waitForEvent('window'), menu('settings')]) // Inställningar is a window of its own
  await expect(sw.getByRole('heading', { name: 'Inställningar', level: 1 })).toBeVisible()
  await sw.close()
  expect(await enabled('sync')).toBe(false) // nothing to fetch from: Stommen is not connected
  expect(await enabled('record')).toBe(true)
  await menu('points')
  await expect(win.getByRole('button', { name: 'Öppna i protokollet' })).toBeVisible()
})

test('the sidebar lists the meetings of the project, opens one, and can be put away', async () => {
  const side = win.getByRole('navigation', { name: 'Huvudmeny' })
  await expect(side.getByText('2 möten')).toBeVisible()
  await side.getByRole('button', { name: /Byggmöte 4/ }).click()
  await expect(win.getByRole('heading', { name: 'Protokoll, byggmöte 4' })).toBeVisible()
  await expect(side.getByRole('button', { name: /Byggmöte 4/ })).toHaveAttribute('aria-current', 'page')
  await menu('sidebar')
  await expect(side).toHaveCount(0)
  await win.getByRole('button', { name: 'Visa sidopanelen' }).click()
  await expect(side).toBeVisible()
})

test('a protocol is a document: an outline to its headings, and its commands in the menu', async () => {
  await protocol4()
  const outline = win.getByRole('navigation', { name: 'Rubriker' })
  await expect(outline.getByRole('button')).toHaveCount(11)
  await outline.getByRole('button', { name: /Ekonomi/ }).click()
  await menu('newPoint') // under the heading chosen in the outline
  await expect(win.getByRole('group', { name: 'Ny punkt' }).or(win.getByLabel('Ny punkt'))).toBeVisible()
  await win.getByRole('button', { name: 'Avbryt' }).click()
  expect(await enabled('saveDocx')).toBe(true)
  expect(await enabled('send')).toBe(false) // not connected to Stommen
  await menu('inspector')
  await expect(win.getByRole('heading', { name: 'Utskrift' })).toHaveCount(0)
  await menu('find') // brings the transcript back, with its search
  await expect(win.getByPlaceholder('Sök i utskriften')).toBeFocused()
  await toOverview()
  expect(await enabled('saveDocx')).toBe(false)
})

test('the open points of the project are a list of their own, and one opens in its protocol', async () => {
  const side = win.getByRole('navigation', { name: 'Huvudmeny' })
  await side.getByRole('button', { name: /Öppna punkter/ }).click()
  const rows = win.locator('tbody tr')
  await expect(rows.filter({ hasText: '3.4.1' })).toContainText('Byggmöte 3')
  // beside the list: what the latest meeting said of the point, and where it was first said
  const chosen = win.getByRole('complementary', { name: 'Vald punkt' })
  await expect(chosen.getByRole('heading', { name: 'På byggmöte 4' })).toBeVisible()
  await expect(chosen.getByRole('heading', { name: 'I inspelningen' })).toBeVisible()
  await expect(chosen).toContainText('21:05')
  await expect(chosen).toContainText('Jonas Bergström')
  await win.getByPlaceholder('Sök bland punkterna').fill('finns inte')
  await expect(win.getByText('Ingen punkt stämmer med urvalet.')).toBeVisible()
  await win.getByPlaceholder('Sök bland punkterna').fill('')
  await win.getByRole('button', { name: 'Förfallna' }).click()
  await expect(rows.filter({ hasText: '3.4.1' })).toBeVisible()
  await win.getByRole('button', { name: 'Öppna i protokollet' }).click()
  await expect(win.getByRole('heading', { name: 'Protokoll, byggmöte 3' })).toBeVisible()
  await side.getByRole('button', { name: /Dagordning inför byggmöte 5/ }).click()
  await expect(win.getByRole('heading', { name: 'Dagordning, byggmöte 5' })).toBeVisible()
})

test('the palette runs a command and opens a meeting or a point from a few letters', async () => {
  await menu('palette')
  const ask = win.getByRole('combobox', { name: 'Sök kommando, möte eller punkt' })
  await expect(ask).toBeFocused()
  await ask.fill('öppna p')
  await expect(win.getByRole('listbox', { name: 'Träffar' }).getByRole('option').first()).toContainText('Öppna punkter')
  await ask.press('Enter')
  await expect(win.getByRole('button', { name: 'Öppna i protokollet' })).toBeVisible()
  await menu('palette')
  await ask.fill('byggmöte 4')
  await ask.press('Enter')
  await expect(win.getByRole('heading', { name: 'Protokoll, byggmöte 4' })).toBeVisible()
  await menu('palette')
  await ask.fill('finns inte alls')
  await expect(win.getByText('Inget stämmer med det du skrev.')).toBeVisible()
  await ask.press('Escape')
  await expect(ask).toBeHidden()
})

// Last: it leaves a recording that could not be written out among the project's meetings.
test('a recording is written out behind the window, and one that fails says so until it is seen', async () => {
  const file = join(config, 'not-sound.m4a')
  writeFileSync(file, 'not sound')
  await app.evaluate(({ dialog }, picked) => {
    dialog.showOpenDialog = (async () => ({ canceled: false, filePaths: [picked] })) as unknown as typeof dialog.showOpenDialog
  }, file)
  await menu('addRecording')
  await expect(win.getByRole('heading', { name: 'Byggmöte 5', level: 1 })).toBeVisible()
  const side = win.getByRole('navigation', { name: 'Huvudmeny' })
  await expect(side.getByText('Skrivs ut', { exact: true })).toBeVisible()
  await toOverview() // the window is free meanwhile
  await expect(win.getByRole('heading', { name: 'Senaste möten' })).toBeVisible()
  await expect(side.getByText('Gick inte att skriva ut')).toBeVisible({ timeout: 45_000 })
  await side.getByRole('button', { name: /Byggmöte 5/ }).click()
  await expect(win.getByText('Det gick inte att skriva ut inspelningen.')).toBeVisible()
  await win.getByRole('button', { name: 'Till översikten' }).click()
  await expect(side.getByText('Skrivs ut', { exact: true })).toHaveCount(0)
})
