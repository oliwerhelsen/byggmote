// The built app against the real engine and a knowledge base the engine wrote (fixture.py). No model runs: what is
// tested is that the window shows what the engine's files say, the way from one view to the next, and that what a
// person corrects in a protocol is there when the engine is asked again. The tests share the knowledge base and run
// in order: the later ones correct the protocol the earlier ones read.
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
  // No model can run from a test: the engine is shown folders that have none, and may not fetch one. A test that
  // asks for a protocol to be written, by mistake or after another test failed, gets an error and not minutes of work.
  const none = { BYGGMOTE_MODELS: join(config, 'no-models'), HF_HUB_CACHE: join(config, 'no-models'), HF_HUB_OFFLINE: '1' }
  // Hidden: a test run does not take the screen, and whoever sits at the computer cannot click in it.
  app = await electron.launch({ args, cwd: here, env: { ...process.env, ...none, BYGGMOTE_CONFIG: config, BYGGMOTE_HIDDEN: '1' } })
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

const protocol4 = async (): Promise<void> => {
  await win.getByRole('button', { name: 'Byggmöte 4' }).click()
  await expect(win.getByRole('heading', { name: 'Protokoll, byggmöte 4' })).toBeVisible()
}

test('a person says an amount is right, and takes it back', async () => {
  await protocol4()
  const decision = win.locator('.point').filter({ hasText: '4.4.1' })
  await decision.getByRole('button', { name: 'Beloppet 86 500 kr i punkt 4.4.1 stämmer' }).click()
  await expect(decision).toContainText('Beloppet 86 500 kr är kontrollerat mot inspelningen.')
  await expect(win.getByText('En sak ska kontrolleras')).toHaveCount(0)

  await win.getByRole('button', { name: 'Till möten' }).click()
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

  await win.getByRole('button', { name: 'Till möten' }).click()
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
  await win.getByRole('button', { name: 'Byggmöte 3' }).click()
  await expect(win.getByRole('heading', { name: 'Protokoll, byggmöte 3' })).toBeVisible()
  await expect(win.getByText('Byggmöte 4 bygger på det här protokollet, så punkterna går inte att ändra längre.')).toBeVisible()
  await expect(win.locator('.point').filter({ hasText: '3.4.1' })).toBeVisible()
  await expect(win.getByRole('button', { name: /^Ändra punkt/ })).toHaveCount(0)
  await expect(win.getByRole('button', { name: /^Lägg till punkt under/ })).toHaveCount(0)
  await expect(win.getByRole('button', { name: 'Skriv om protokollet' })).toHaveCount(0)
})
