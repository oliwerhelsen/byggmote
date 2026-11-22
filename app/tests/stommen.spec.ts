// The app against a stand-in for Stommen on this computer, answering as Stommen's mobile API does (its ADR-0018):
// sign-in gives a session token in a header, every read carries it, and a Projekt comes with its Roller and Kontakter.
// What is tested is the app's side: what it sends, where the token is and is not, and that what Stommen answers
// reaches the engine. Stommen's own side is tested in Stommen.
import { execFileSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { createServer, type IncomingHttpHeaders, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'

// What the functions handed to `evaluate` see: they run in the app's window, not here.
declare const window: { api: import('../src/shared/types').Api }
declare const document: { documentElement: { innerHTML: string } }
declare const localStorage: Record<string, string>

const here = join(__dirname, '..')
const python = join(here, '..', 'engine', '.venv', ...(process.platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python']))

// Made for this run: nobody's real account.
const EMAIL = 'maria@norrstaden.example'
const PASSWORD = randomBytes(12).toString('hex')
const TOKEN = `${randomBytes(16).toString('hex')}.${randomBytes(16).toString('hex')}`
const LINDEN = '2b0c3f11-8e5d-4f7a-a2c4-91d6e0b7c3f2'

type Seen = { method: string; path: string; headers: IncomingHttpHeaders; body: string }
const seen: Seen[] = []
let ended = false // Stommen has ended the session
let slow = 0 // how long Stommen takes over a Projekt's roles, in milliseconds
let tooOld = false // Stommen wants a newer Byggmöte

let stommen: Server
let address: string
let config: string
let kept: string
let app: ElectronApplication
let win: Page

function answer(method: string, path: string, headers: IncomingHttpHeaders, body: string): [number, unknown, Record<string, string>?] {
  if (method === 'POST' && path === '/api/auth/sign-in/email') {
    const given = JSON.parse(body) as { email?: string; password?: string }
    if (given.email !== EMAIL || given.password !== PASSWORD) return [401, { code: 'INVALID_EMAIL_OR_PASSWORD', message: 'Invalid email or password' }]
    ended = false
    return [200, { redirect: false, user: { id: 'u1', email: EMAIL } }, { 'set-auth-token': TOKEN }]
  }
  if (headers.authorization !== `Bearer ${TOKEN}` || ended) return [401, { error: { code: 'unauthorized', message: 'Inte inloggad' } }]
  if (tooOld && path.startsWith('/api/mobile/v1/')) {
    return [426, { error: { code: 'update_required', message: 'Uppdatera Byggmöte', detail: 'Den här versionen av Byggmöte är för gammal. Hämta den senaste versionen av Byggmöte.' } }]
  }
  if (method === 'POST' && path === '/api/auth/sign-out') {
    ended = true
    return [200, { success: true }]
  }
  if (path === '/api/mobile/v1/me') {
    return [200, { user: { id: 'u1', name: 'Maria Lindqvist', email: EMAIL }, organization: { id: 'o1', name: 'Norrstaden Fastigheter AB', readOnly: false }, roles: ['member'] }]
  }
  if (path === '/api/mobile/v1/projects') {
    return [200, { projects: [{ id: LINDEN, name: 'Kv. Linden', address: null, client: 'Norrstaden Fastigheter AB', phase: 'bygg', contractForm: 'undecided', plannedStart: null }] }]
  }
  if (path === `/api/mobile/v1/projects/${LINDEN}/roles`) {
    return [200, {
      project: { id: LINDEN, name: 'Kv. Linden' },
      // `since` and `title` are fields Stommen might add one day: its v1 only ever adds, and the app must not trip on them.
      roles: [
        { id: 'r1', name: 'Projektledare', holderId: 'k1', substituteId: 'k2', since: '2026-09-01' },
        { id: 'r2', name: 'Platschef', holderId: 'k3', substituteId: null },
        { id: 'r3', name: 'Konstruktör', holderId: null, substituteId: null }
      ],
      contacts: [
        { id: 'k1', name: 'Maria Lindqvist', organization: 'Norrstaden Fastigheter AB', email: EMAIL, title: 'Projektchef' },
        { id: 'k2', name: 'Anders Holm', organization: 'Norrstaden Fastigheter AB', email: null },
        { id: 'k3', name: 'Elin Sjöberg', organization: 'Bergström Bygg AB', email: 'elin@bergstrom.example' }
      ]
    }]
  }
  return [404, { error: { code: 'not_found', message: 'Finns inte' } }]
}

test.beforeAll(async () => {
  stommen = createServer((req, res) => {
    let body = ''
    req.on('data', (d) => (body += d))
    req.on('end', () => {
      seen.push({ method: req.method ?? '', path: req.url ?? '', headers: req.headers, body })
      const [status, json, extra] = answer(req.method ?? '', req.url ?? '', req.headers, body)
      const reply = (): void => void res.writeHead(status, { 'content-type': 'application/json', ...extra }).end(JSON.stringify(json))
      if (slow && req.url?.endsWith('/roles')) setTimeout(reply, slow)
      else reply()
    })
  })
  await new Promise<void>((done) => stommen.listen(0, '127.0.0.1', done))
  address = `http://127.0.0.1:${(stommen.address() as AddressInfo).port}`

  config = mkdtempSync(join(tmpdir(), 'byggmote-app-'))
  kept = mkdtempSync(join(tmpdir(), 'byggmote-kept-'))
  execFileSync(python, [join(__dirname, 'fixture.py')], { env: { ...process.env, BYGGMOTE_CONFIG: config } })
  const args = process.env.CI && process.platform === 'linux' ? ['--no-sandbox', '.'] : ['.']
  const none = { BYGGMOTE_MODELS: join(config, 'no-models'), HF_HUB_CACHE: join(config, 'no-models'), HF_HUB_OFFLINE: '1' }
  // The app keeps what it keeps in a folder of this run's, and no keychain is asked: a test must not put anything in
  // the keychain of whoever runs it, nor wait for them to allow it.
  app = await electron.launch({ args, cwd: here, env: { ...process.env, ...none, BYGGMOTE_CONFIG: config, BYGGMOTE_HIDDEN: '1',
    BYGGMOTE_USER_DATA: kept, BYGGMOTE_NO_KEYCHAIN: '1' } })
  win = await app.firstWindow()
  await expect(win.getByRole('heading', { name: 'Tidigare möten' })).toBeVisible()
})

test.afterAll(async () => {
  await app?.close()
  await new Promise((done) => stommen.close(done))
  for (const d of [config, kept]) rmSync(d, { recursive: true, force: true })
})

async function signIn(password: string, to = address): Promise<void> {
  await win.getByLabel('Adress till Stommen').fill(to)
  await win.getByLabel('E-post').fill(EMAIL)
  await win.getByLabel('Lösenord').fill(password)
  await win.getByRole('button', { name: 'Logga in' }).click()
}

test('the address is Stommen over https, and a wrong password is said plainly', async () => {
  await win.getByRole('button', { name: 'Stommen' }).click()
  await expect(win.getByRole('heading', { name: 'Stommen', level: 1 })).toBeVisible()
  await expect(win.getByText('Stommen är inte kopplat än.')).toBeVisible()

  await signIn(PASSWORD, 'http://stommen.example')
  await expect(win.getByRole('alert')).toHaveText('Adressen till Stommen ska börja med https://.')
  expect(seen).toHaveLength(0) // nothing went anywhere

  await signIn('fel-losenord')
  await expect(win.getByRole('alert')).toHaveText('E-postadressen eller lösenordet stämmer inte.')
  await expect(win.getByRole('heading', { name: 'Logga in i Stommen' })).toBeVisible()
})

test('signing in brings the Projekt with its Roller and Kontakter, and the session stays out of sight', async () => {
  await signIn(PASSWORD)
  await expect(win.getByRole('heading', { name: 'Inloggad som Maria Lindqvist' })).toBeVisible()
  await expect(win.getByText('Norrstaden Fastigheter AB, på ' + address + '.')).toBeVisible()
  await expect(win.getByText('Ett Projekt hämtade, med 3 Kontakter. En Roll är vakant.')).toBeVisible()
  await expect(win.getByText('Kopplad till Stommen som Maria Lindqvist.')).toBeVisible()
  await expect(win.getByText('Du loggar in igen nästa gång appen startar.')).toBeVisible() // this run has no keychain
  await expect(win.getByLabel('Projekt', { exact: true }).locator('option')).toHaveText(['Kv. Eken kontorshus', 'Kv. Linden'])

  // what the engine now has: Stommen's Projekt, the vacant Roll too, and the one person who is in both projects once
  const { projects } = await win.evaluate(() => window.api.projects())
  const linden = projects.find((p) => p.name === 'Kv. Linden')!
  expect(linden.stommen).toBe(LINDEN)
  expect(linden.roles).toEqual(['Projektledare', 'Platschef', 'Konstruktör'])
  expect(linden.people.map((p) => [p.name, p.role])).toEqual([['Maria Lindqvist', 'Projektledare'], ['Anders Holm', undefined], ['Elin Sjöberg', 'Platschef']])
  expect(linden.people[0].id).toBe(projects.find((p) => p.name === 'Kv. Eken kontorshus')!.people[0].id)

  // what the app sent: it names itself, and nothing in it looks like a browser's request. Stommen asks a browser for
  // an Origin at sign-in and withholds the token from one, and Node's own `fetch` sends `sec-fetch-mode` unasked.
  const first = seen.find((r) => r.path === '/api/auth/sign-in/email' && r.body.includes(PASSWORD))!
  expect(first.headers['x-app']).toBe('byggmote')
  expect(first.headers['x-app-version']).toMatch(/^\d+\.\d+\.\d+/)
  for (const r of seen) {
    expect(Object.keys(r.headers).filter((h) => h.startsWith('sec-') || ['origin', 'referer', 'cookie'].includes(h))).toEqual([])
  }
  const reads = seen.filter((r) => r.path.startsWith('/api/mobile/v1/'))
  expect(reads.map((r) => r.path)).toEqual(['/api/mobile/v1/me', '/api/mobile/v1/projects', `/api/mobile/v1/projects/${LINDEN}/roles`])
  expect(reads.every((r) => r.headers.authorization === `Bearer ${TOKEN}` && r.headers['x-app'] === 'byggmote')).toBe(true)
  expect(seen.filter((r) => r.body.includes(PASSWORD)).map((r) => r.path)).toEqual(['/api/auth/sign-in/email'])

  // where the session is not: in the window, or readable on disk
  expect(JSON.stringify(await win.evaluate(() => window.api.stommenState()))).not.toContain(TOKEN)
  expect(await win.evaluate(() => JSON.stringify({ ...localStorage }) + document.documentElement.innerHTML)).not.toContain(TOKEN)
  const onDisk = readFileSync(join(kept, 'stommen.json'), 'utf8')
  expect(onDisk).not.toContain(TOKEN)
  expect(onDisk).not.toContain(PASSWORD)
  await expect(win.getByLabel('Lösenord')).toHaveCount(0)
})

test('a session Stommen has ended shows as signed out, with the address kept', async () => {
  ended = true
  await win.getByRole('button', { name: 'Hämta från Stommen' }).click()
  await expect(win.getByRole('alert')).toHaveText('Inloggningen i Stommen gäller inte längre. Logga in igen.')
  await expect(win.getByRole('heading', { name: 'Logga in i Stommen' })).toBeVisible()
  await expect(win.getByLabel('Adress till Stommen')).toHaveValue(address)
  await expect(win.getByText('Stommen är inte kopplat än.')).toBeVisible()
  await expect(win.getByLabel('Projekt', { exact: true }).locator('option')).toHaveText(['Kv. Eken kontorshus', 'Kv. Linden']) // what was fetched stays
})

test('signing out ends the session in Stommen too', async () => {
  await signIn(PASSWORD)
  await expect(win.getByRole('heading', { name: 'Inloggad som Maria Lindqvist' })).toBeVisible()
  await expect(win.getByText(/hämtade, med/)).toBeVisible()
  await win.getByRole('button', { name: 'Logga ut' }).click()
  await expect(win.getByRole('heading', { name: 'Logga in i Stommen' })).toBeVisible()
  const out = seen.filter((r) => r.path === '/api/auth/sign-out')
  expect(out).toHaveLength(1)
  expect(out[0].headers.authorization).toBe(`Bearer ${TOKEN}`)
  expect(ended).toBe(true)
  expect(await win.evaluate(() => window.api.stommenState())).toMatchObject({ connected: false, server: address })
})

test('signing out while a fetch is still running leaves nothing of the session behind', async () => {
  await signIn(PASSWORD)
  await expect(win.getByText(/hämtade, med/)).toBeVisible()
  slow = 600
  try {
    // as when the app has just started and fetches by itself, and the person signs out before it is done
    const [fetched, out] = await win.evaluate(async () => {
      const running = window.api.stommenSync().then(() => 'fetched', (e: unknown) => String(e))
      await new Promise((r) => setTimeout(r, 150))
      const signedOut = await window.api.stommenSignOut()
      return [await running, signedOut] as const
    })
    expect(fetched).toBe('fetched') // the answer came after the sign-out
    expect(out.connected).toBe(false)
  } finally {
    slow = 0
  }
  expect(JSON.parse(readFileSync(join(kept, 'stommen.json'), 'utf8'))).toEqual({ server: address })
  expect(await win.evaluate(() => window.api.stommenState())).toMatchObject({ connected: false, user: '', syncedAt: null })
})

test('a Byggmöte that Stommen finds too old is told so, and leaves no session behind there', async () => {
  // the test before signed out behind the view's back: the window starts again, as when the app does
  await win.reload()
  await win.getByRole('button', { name: 'Stommen' }).click()
  await expect(win.getByRole('heading', { name: 'Logga in i Stommen' })).toBeVisible()
  tooOld = true
  const before = seen.length
  try {
    await signIn(PASSWORD)
    await expect(win.getByRole('alert')).toHaveText(
      'Stommen svarar: Uppdatera Byggmöte. Den här versionen av Byggmöte är för gammal. Hämta den senaste versionen av Byggmöte.')
  } finally {
    tooOld = false
  }
  await expect(win.getByRole('heading', { name: 'Logga in i Stommen' })).toBeVisible()
  expect(seen.slice(before).map((r) => r.path)).toEqual(['/api/auth/sign-in/email', '/api/mobile/v1/me', '/api/auth/sign-out'])
  expect(ended).toBe(true)
  expect(await win.evaluate(() => window.api.stommenState())).toMatchObject({ connected: false })
})
