// Naming the speakers nobody has named, against the real engine: who a voice sounds like is a name to click, and a
// name written and Enter is saved. Two unnamed speakers are added to the fixture's Byggmöte 4, one whose voice the
// run matched to Sara Nyberg, as `byggmote run` leaves a meeting with Känn igen röster on.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'

const here = join(__dirname, '..')
const python = join(here, '..', 'engine', '.venv', ...(process.platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python']))

const UNNAMED = `
from byggmote import areas, meeting, people, voice
voice.turn(True)
a = next(a for a in areas.load()["areas"] if a["name"] == "Kv. Eken kontorshus")
d = areas.transcripts(a) / "Byggmöte 4"
m = meeting.load(d)
sara = next(p["id"] for p in people.load() if p["name"] == "Sara Nyberg")
for n, (sid, said, heard) in enumerate([("S8", "Skyddsronden i fredags gick bra.", sara), ("S9", "Vi från elfirman har en fråga om schaktet.", None)], 1):
    m["speakers"].append({"id": sid, "name": f"Talare {n}", "person": None, "track": "1", "cluster": None, "embedding": None}
                         | ({"voice": {"person": heard, "score": 0.8}} if heard else {}))
    m["segments"].append({"id": 80 + n, "start": 1400.0 + 20 * n, "end": 1415.0 + 20 * n, "speaker": sid, "text": said, "words": []})
meeting.save(d, m)
`

let config: string
let app: ElectronApplication
let win: Page

test.beforeAll(async () => {
  config = mkdtempSync(join(tmpdir(), 'byggmote-speakers-'))
  const env = { ...process.env, BYGGMOTE_CONFIG: config }
  execFileSync(python, [join(__dirname, 'fixture.py')], { env })
  execFileSync(python, ['-c', UNNAMED], { env })
  const args = process.env.CI && process.platform === 'linux' ? ['--no-sandbox', '.'] : ['.']
  const none = { BYGGMOTE_MODELS: join(config, 'no-models'), HF_HUB_CACHE: join(config, 'no-models'), HF_HUB_OFFLINE: '1' }
  app = await electron.launch({ args, cwd: here, env: { ...process.env, ...none, BYGGMOTE_CONFIG: config, BYGGMOTE_HIDDEN: '1',
    BYGGMOTE_USER_DATA: mkdtempSync(join(tmpdir(), 'byggmote-speakers-user-')), BYGGMOTE_SETUP: '1' } })
  win = await app.firstWindow()
})

test.afterAll(async () => {
  await app?.close()
  rmSync(config, { recursive: true, force: true })
})

test('a recognised voice is a name to click, and a written name is saved with Enter', async () => {
  await win.getByRole('button', { name: 'Byggmöte 4', exact: true }).first().click()
  await win.getByRole('button', { name: 'Sätt namn på talare' }).click()
  const card = win.getByRole('dialog', { name: 'Sätt namn på talare' })
  await expect(card).toContainText('2 talare har inget namn.')

  // Talare 1 sounds like Sara Nyberg, who is offered on her own and not again among the project's people
  const heard = card.getByRole('group', { name: 'Rösten känns igen från ett tidigare möte' })
  await expect(heard.getByRole('button')).toHaveText('Sara Nyberg')
  const people = card.getByRole('group', { name: 'I projektet' }).first()
  await expect(people.getByRole('button')).toHaveText(['Maria Lindqvist', 'Anders Holm', 'Jonas Bergström'])
  await heard.getByRole('button', { name: 'Sara Nyberg' }).click()
  await expect(card.getByRole('textbox', { name: 'Vem är Talare 1?' })).toHaveCount(0)
  await expect(card).toContainText('En talare har inget namn.')

  // the next one without a name has the focus: a name nobody has is written, and Enter saves it
  const left = card
  await expect(left).toContainText('En talare har inget namn.')
  const who = left.getByRole('textbox', { name: 'Vem är Talare 2?' })
  await expect(who).toBeFocused()
  await who.fill('Erik Ek')
  await expect(left).toContainText('Enter sparar ”Erik Ek” som en ny person i projektet.')
  await expect(left.getByRole('group', { name: 'I projektet' })).toHaveCount(0) // nobody in the project is called that
  await who.press('Enter')
  await expect(card).toBeHidden() // the last name closes the sheet
  await win.getByRole('tab', { name: 'Utskrift' }).click()
  await expect(win.locator('#line-82')).toContainText('Erik Vi från elfirman har en fråga om schaktet.')
  await expect(win.locator('#line-81')).toContainText('Sara Skyddsronden i fredags gick bra.')
})
