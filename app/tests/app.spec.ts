// The built app against the real engine and a knowledge base the engine wrote (fixture.py). No model runs: what is
// tested is that the window shows what the engine's files say, the way from one view to the next, and that what a
// person corrects in a protocol is there when the engine is asked again. The tests share the knowledge base and run
// in order: the later ones correct the protocol the earlier ones read.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { _electron as electron, expect, test, type ElectronApplication, type Locator, type Page } from '@playwright/test'

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
  await expect(win.getByRole('heading', { name: 'Möten', exact: true })).toBeVisible()
})

test('the meetings of a project, the next one and what is still open', async () => {
  await expect(win.getByRole('heading', { name: 'Nästa möte' })).toBeVisible()
  await expect(win.getByText('En öppen punkt följer med från tidigare möten. En har passerat sitt datum.')).toBeVisible()
  const rows = win.getByRole('region', { name: 'Möten', exact: true }).locator('tbody tr')
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

// The inspector's Punkt tab has the chosen point's properties; the status line is at the window's foot.
const punkt = (): Locator => win.getByRole('tabpanel', { name: 'Punkt' })
const row = (no: string): Locator => win.locator('.point').filter({ hasText: no })
const status = (): Locator => win.locator('footer.status')

test('a protocol: who was there, the points as a table with their checks, and the transcript', async () => {
  await win.getByRole('button', { name: 'Byggmöte 4', exact: true }).click()
  await expect(win.getByRole('heading', { name: 'Protokoll, byggmöte 4' })).toBeVisible()
  await expect(win.locator('.attendees li').first()).toHaveText('Maria Lindqvist, Projektledare')
  await expect(win.locator('.colstrip')).toHaveText('NrTypPunktTidAnsvarigSenast')
  await expect(win.locator('section').filter({ has: win.getByRole('heading', { name: 'Handlingar' }) })).toContainText('Inget noterat')
  await expect(status()).toContainText('3 punkter')
  await expect(status()).toContainText('1 att kontrollera')
  await expect(status()).toContainText('Ljud och utskrift stannar på den här datorn')

  // the formats to save it as are behind one button
  await win.getByRole('button', { name: 'Spara som' }).click()
  await expect(win.getByRole('menuitem')).toHaveText(['Word', 'PDF', 'Markdown', /^Kopiera texten/])
  await win.keyboard.press('Escape')
  await expect(win.getByRole('menu')).toHaveCount(0)
  await expect(win.getByRole('button', { name: 'Spara som' })).toBeFocused()

  const decision = row('4.4.1')
  await expect(decision).toContainText('Beslut')
  await expect(decision).toContainText('Kontrollera beloppet 86 500 kr.')
  await expect(decision).toContainText('åttiosex och fem')

  const carried = row('3.4.1')
  await expect(carried).toContainText('Kvarstår, från byggmöte 3')
  await expect(carried).toContainText('Togs inte upp på mötet.')
  await expect(carried.locator('.due')).toHaveText('2026-11-12förfallen')

  // with nothing chosen the inspector says so; a point's time chooses it, and shows the line it was said in
  await expect(punkt()).toContainText('Ingen punkt är vald.')
  await decision.getByRole('button', { name: 'Lyssna från 17:42' }).click()
  await expect(decision).toHaveAttribute('aria-current', 'true')
  await expect(punkt()).toContainText('Anders Holm')
  await expect(punkt()).toContainText('Ett Beslut är alltid avslutat.')
  await expect(punkt()).toContainText('Modellen skrev punkten')
  await win.getByRole('tab', { name: 'Utskrift' }).click()
  await expect(win.locator('.lines li.active')).toContainText('Beställaren godkänner ÄTA 14')

  await win.getByRole('searchbox').fill('stomresningen')
  await expect(win.locator('.lines li')).toHaveCount(1)
  await expect(win.getByText('Mötet har inget ljud sparat.')).toBeVisible()
  await expect(win.getByRole('button', { name: 'Spela upp' })).toBeDisabled()
  // no project of Stommen's, so nothing to send
  await expect(win.locator('.tools').getByRole('button', { name: 'Skicka till Stommen' })).toBeDisabled()
  await win.getByRole('tab', { name: 'Stommen' }).click()
  await expect(win.getByRole('tabpanel', { name: 'Stommen' })).toContainText('Projektet finns bara på den här datorn')
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
  await expect(win.getByRole('heading', { name: 'Möten', exact: true })).toBeVisible()
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
  const decision = row('4.4.1')
  await decision.getByRole('button', { name: 'Beloppet 86 500 kr i punkt 4.4.1 stämmer' }).click()
  await expect(decision).not.toContainText('Kontrollera beloppet')
  await expect(status()).not.toContainText('att kontrollera')
  await decision.focus()
  await expect(punkt()).toContainText('Beloppet 86 500 kr är kontrollerat mot inspelningen.')

  await toOverview()
  const meeting = win.locator('tbody tr').filter({ hasText: 'Byggmöte 4' })
  await expect(meeting).toContainText('Utkast')
  await expect(meeting).not.toContainText('att kontrollera')

  await protocol4()
  await decision.focus()
  await punkt().getByRole('button', { name: 'Ångra kontrollen av 86 500 kr i punkt 4.4.1' }).click()
  await expect(decision).toContainText('Kontrollera beloppet 86 500 kr.')
})

test('a point is corrected where it stands and in the inspector, and what stays open is on the next agenda', async () => {
  await protocol4()
  const point = row('4.3.1')
  await point.locator('.txt').click()
  const field = win.getByRole('textbox', { name: 'Punkt 4.3.1' })
  await expect(field).toBeFocused()
  await expect(punkt().getByLabel('Återstår efter mötet')).toBeDisabled() // a note is said and done
  await expect(punkt()).toContainText('En Notering är alltid avslutad.')
  await field.fill('Platschefen redovisar läget för stommen på plan tre.')
  await field.press('Enter')
  await expect(point).toContainText('Platschefen redovisar läget för stommen på plan tre.')
  await expect(win.locator('header .edited')).toHaveText('Redigerat')

  // Escape puts the text back, and the key for Ändra punkt opens the field again
  await expect(point).toBeFocused()
  await win.keyboard.press(process.platform === 'darwin' ? 'Enter' : 'F2')
  await expect(field).toBeFocused()
  await field.fill('Något helt annat')
  await field.press('Escape')
  await expect(field).toHaveCount(0)
  await expect(point).toContainText('Platschefen redovisar läget för stommen på plan tre.')

  // each property is saved as it is changed
  await punkt().getByLabel('Typ').selectOption({ label: 'Att göra' })
  await expect(point).toContainText('Att göra')
  await expect(punkt().getByLabel('Återstår efter mötet')).toBeChecked()
  await punkt().getByLabel('Ansvarig').selectOption({ label: 'Platschef' })
  await expect(point.locator('.who')).toHaveText('Platschef')
  await punkt().getByLabel('Senast').fill('2026-11-26')
  await expect(point.locator('.due')).toContainText('2026-11-26')
  // what the engine knows of the point's history, and what the model wrote
  await expect(punkt()).toContainText('Ändrad för hand')
  await expect(punkt()).toContainText('Modellen skrev: ”Stommen på plan tre är klar.”')

  await toOverview()
  await expect(win.getByRole('region', { name: 'Öppna punkter' })).toContainText('4.3.1')
})

test('a point is written on the page where it is said, taken out and put back', async () => {
  await protocol4()
  await win.getByRole('tab', { name: 'Utskrift' }).click()
  await win.locator('.lines').getByRole('button', { name: 'Lyssna från 14:20' }).click()
  await win.getByRole('button', { name: 'Ny punkt under Ekonomi' }).click()
  const field = win.getByRole('textbox', { name: 'Ny punkt' })
  await expect(field).toBeFocused()
  await expect(punkt()).toContainText('Punkten pekar på 14:20 i utskriften, där Maria Lindqvist säger')
  await expect(punkt().getByRole('button', { name: 'Lägg till punkten' })).toBeDisabled()
  await field.fill('Mängdregleringen av schakt tas upp på nästa möte')
  await punkt().getByLabel('Typ').selectOption({ label: 'Notering' })
  await punkt().getByRole('button', { name: 'Lägg till punkten' }).click()

  const point = row('4.4.2')
  await expect(point).toContainText('Mängdregleringen av schakt tas upp på nästa möte.')
  await expect(point).toContainText('Notering')
  await expect(point.getByRole('button', { name: 'Lyssna från 14:20' })).toBeVisible()
  await expect(point).toHaveAttribute('aria-current', 'true') // the new point is the chosen one
  await expect(punkt()).toContainText('Tillagd för hand')

  await punkt().getByRole('button', { name: 'Ta bort punkten' }).click()
  await expect(point).toHaveCount(0)
  await expect(win.getByText('En punkt är borttagen')).toBeVisible()
  await win.getByRole('button', { name: 'Lägg tillbaka punkt 4.4.2' }).click()
  await expect(point).toContainText('Mängdregleringen av schakt tas upp på nästa möte.')
  await expect(win.getByText('En punkt är borttagen')).toHaveCount(0)

  // Escape leaves a new point, and Enter adds one
  await menu('newPoint')
  await field.fill('En punkt som inte blir av')
  await field.press('Escape')
  await expect(field).toHaveCount(0)
  await expect(win.getByText('En punkt som inte blir av')).toHaveCount(0)
  await win.getByRole('button', { name: 'Ny punkt under Tidplan' }).click()
  await field.fill('Taket läggs vecka 49')
  await field.press('Enter')
  const made = row('Taket läggs vecka 49.')
  await expect(made).toContainText('4.3.2')
  await expect(made).toContainText('Att göra')
  await made.focus()
  await win.keyboard.press(process.platform === 'darwin' ? 'Meta+Backspace' : 'Delete') // Ta bort punkt
  await expect(made).toHaveCount(0)
})

test('a model does not write over what a person has set right without a yes', async () => {
  await protocol4()
  const decision = row('4.4.1')
  await decision.getByRole('button', { name: 'Beloppet 86 500 kr i punkt 4.4.1 stämmer' }).click() // a correction of this test's own
  await expect(decision).not.toContainText('Kontrollera beloppet')
  await menu('rewrite')
  await expect(win.getByRole('alert')).toContainText(/Protokollet har (en rättning\. Den|\d+ rättningar\. De) försvinner om modellen skriver om protokollet\./)
  await win.getByRole('button', { name: /^Behåll rättning(en|arna)$/ }).click()
  await expect(win.getByRole('alert')).toHaveCount(0)
  await expect(decision).not.toContainText('Kontrollera beloppet')
})

test('someone who was there and said nothing is added, and taken off again', async () => {
  await protocol4()
  await menu('attend')
  await expect(win.getByLabel('Någon som var med utan att säga något')).toBeFocused()
  await win.getByLabel('Någon som var med utan att säga något').selectOption({ label: 'Sara Nyberg, BAS-U' })
  await win.getByRole('button', { name: 'Lägg till som närvarande' }).click()
  const there = win.locator('.attendees li').filter({ hasText: 'Sara Nyberg' })
  await expect(there).toContainText('Sara Nyberg, BAS-U')
  await expect(there).toContainText('(tillagd för hand)')
  await expect(win.getByLabel('Någon som var med utan att säga något')).toHaveCount(0)
  await expect.poll(() => enabled('attend')).toBe(false) // everyone in the project is there now
  await win.getByRole('button', { name: 'Ta bort Sara Nyberg från närvarande' }).click()
  await expect(there).toHaveCount(0)
})

test('a protocol the next meeting builds on is read, not changed', async () => {
  await win.getByRole('button', { name: 'Byggmöte 3', exact: true }).click()
  await expect(win.getByRole('heading', { name: 'Protokoll, byggmöte 3' })).toBeVisible()
  await expect(win.getByText('Byggmöte 4 bygger på det här protokollet, så punkterna går inte att ändra längre.')).toBeVisible()
  const point = row('3.4.1')
  await point.locator('.txt').click()
  await expect(point).toHaveAttribute('aria-current', 'true')
  await expect(win.getByRole('textbox', { name: /^Punkt / })).toHaveCount(0)
  await expect(punkt().getByLabel('Typ')).toBeDisabled()
  await expect(punkt().getByLabel('Ansvarig')).toBeDisabled()
  await expect(punkt().getByRole('button', { name: 'Ta bort punkten' })).toHaveCount(0)
  await expect(win.getByRole('button', { name: 'Ny punkt', exact: true })).toBeDisabled()
  await expect(win.getByRole('button', { name: /^Ny punkt under/ })).toHaveCount(0)
  for (const c of ['newPoint', 'editPoint', 'removePoint', 'rewrite']) expect(await enabled(c)).toBe(false)
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
  const economy = win.locator('section').filter({ has: win.getByRole('heading', { name: 'Ekonomi' }) })
  await expect(economy.getByRole('textbox', { name: 'Ny punkt' })).toBeFocused()
  await win.keyboard.press('Escape')
  expect(await enabled('saveDocx')).toBe(true)
  expect(await enabled('send')).toBe(false) // not connected to Stommen
  expect(await enabled('play')).toBe(false) // the meeting has no sound
  expect(await enabled('nameSpeakers')).toBe(false) // every speaker has a name
  // what is done to a point is greyed out until one is chosen
  expect(await enabled('editPoint')).toBe(false)
  await row('4.4.1').focus()
  await expect.poll(() => enabled('editPoint')).toBe(true)
  await menu('editPoint')
  await expect(win.getByRole('textbox', { name: 'Punkt 4.4.1' })).toBeFocused()
  await win.keyboard.press('Escape')
  await menu('nextCheck')
  await expect(win.locator('.point[aria-current]')).toHaveCount(1)
  await menu('inspector')
  await expect(win.getByRole('tablist', { name: 'Inspektör' })).toHaveCount(0)
  await menu('find') // brings the inspector back on the transcript, with the search in the toolbar
  await expect(win.getByPlaceholder('Sök i utskriften')).toBeFocused()
  await expect(win.getByRole('tab', { name: 'Utskrift' })).toHaveAttribute('aria-selected', 'true')
  await toOverview()
  await expect.poll(() => enabled('saveDocx')).toBe(false)
})

test('the open points of the project are a list of their own, and one opens in its protocol', async () => {
  const side = win.getByRole('navigation', { name: 'Huvudmeny' })
  await side.getByRole('button', { name: /Öppna punkter/ }).click()
  const rows = win.locator('tbody tr')
  await expect(rows.filter({ hasText: '3.4.1' })).toContainText('Byggmöte 3')
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
  await expect(win.getByRole('heading', { name: 'Möten', exact: true })).toBeVisible()
  await expect(side.getByText('Gick inte att skriva ut')).toBeVisible({ timeout: 45_000 })
  await side.getByRole('button', { name: /Byggmöte 5/ }).click()
  await expect(win.getByText('Det gick inte att skriva ut inspelningen.')).toBeVisible()
  await win.getByRole('button', { name: 'Till översikten' }).click()
  await expect(side.getByText('Skrivs ut', { exact: true })).toHaveCount(0)
})
