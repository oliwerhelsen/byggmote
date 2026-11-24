// Stommen is where the Projekt, their Roller and their Kontakter are kept. The app signs in as a person, the way
// Stommen's phone app does (ADR-0018 there): a session token comes back, every read carries it, and the engine is
// handed what Stommen answers. The token never reaches the window. On disk it is encrypted by the operating system's
// keychain; where the computer has none, it lives until the app quits and the person signs in again.
//
// What goes to Stommen is the sign-in and, when the person sends it, a meeting's protocol: its points, and for each
// how far into the recording it was said, the line said there and who said it. Sound and the rest of the transcript
// never do.
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { request as overHttp } from 'node:http'
import { request as overHttps } from 'node:https'
import { dirname, join } from 'node:path'
import { app, safeStorage } from 'electron'
import type { StommenState, StommenSync } from '../shared/types'
import { call } from './engine'

type Saved = { server: string; token?: string; user?: string; organization?: string; syncedAt?: string }
type Me = { user: { id: string; name?: string; email?: string }; organization: { id: string; name: string } }
type Roles = {
  project: { id: string; name: string }
  roles: { id: string; name: string; holderId?: string | null; substituteId?: string | null }[]
  contacts: { id: string; name: string; organization?: string | null; email?: string | null }[]
}

/** What went wrong, in words for the person. */
export class StommenError extends Error {}

const WAIT = 20_000
const LARGEST = 8 * 1024 * 1024 // an answer larger than this is not Stommen's

/** What came back: enough of a `Response` for what is read here. */
type Answer = { status: number; ok: boolean; header(name: string): string | null; json(): Promise<unknown> }

/**
 * One request, with the headers given and no others. Not `fetch`: Node's adds `sec-fetch-mode`, which makes Stommen
 * take the sign-in for a browser's and refuse it for having no Origin. Nor is a redirect followed here.
 */
function ask(url: URL, method: string, headers: Record<string, string>, body?: string): Promise<Answer> {
  return new Promise((resolve, reject) => {
    const req = (url.protocol === 'https:' ? overHttps : overHttp)(url, { method, headers, timeout: WAIT }, (res) => {
      const parts: Buffer[] = []
      let size = 0
      res.on('data', (part: Buffer) => {
        size += part.length
        if (size > LARGEST) req.destroy(new Error('too large'))
        else parts.push(part)
      })
      res.on('error', reject)
      res.on('end', () => {
        const status = res.statusCode ?? 0
        const text = Buffer.concat(parts).toString('utf8')
        resolve({
          status,
          ok: status >= 200 && status < 300,
          header: (name) => {
            const value = res.headers[name.toLowerCase()]
            return (Array.isArray(value) ? value[0] : value) ?? null
          },
          json: async () => JSON.parse(text) as unknown
        })
      })
    })
    req.on('timeout', () => req.destroy(new Error('timeout')))
    req.on('error', reject)
    if (body !== undefined) req.setHeader('content-length', Buffer.byteLength(body))
    req.end(body)
  })
}
const file = (): string => join(app.getPath('userData'), 'stommen.json')

// A session the computer cannot keep safely: here until the app quits.
let unkept: string | null = null

/** Whether the operating system encrypts for us. On Linux without a keyring Electron falls back to a fixed key: that is not keeping it safe. */
function keeps(): boolean {
  if (process.env['BYGGMOTE_NO_KEYCHAIN'] === '1') return false
  if (!safeStorage.isEncryptionAvailable()) return false
  return !(process.platform === 'linux' && safeStorage.getSelectedStorageBackend() === 'basic_text')
}

async function read(): Promise<Saved | null> {
  try {
    const saved = JSON.parse(await readFile(file(), 'utf8')) as Saved
    return typeof saved?.server === 'string' ? saved : null
  } catch {
    return null
  }
}

async function write(saved: Saved): Promise<void> {
  await mkdir(dirname(file()), { recursive: true })
  await writeFile(file(), JSON.stringify(saved, null, 1) + '\n', { encoding: 'utf8', mode: 0o600 })
}

function token(saved: Saved | null): string | null {
  if (unkept) return unkept
  if (!saved?.token || !keeps()) return null
  try {
    return safeStorage.decryptString(Buffer.from(saved.token, 'base64'))
  } catch {
    return null // the keychain no longer opens it: the person signs in again
  }
}

/** Where Stommen runs unless the person has chosen another address under Avancerat. */
export const DEFAULT_SERVER = 'https://app.stommen.io'

/** The address as the person wrote it, as an origin. Stommen is reached over https; only this computer's own over http. */
function address(given: string): string {
  let url: URL
  try {
    url = new URL(/^[a-z]+:\/\//i.test(given.trim()) ? given.trim() : `https://${given.trim()}`)
  } catch {
    throw new StommenError('Adressen till Stommen går inte att läsa.')
  }
  const own = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || url.hostname.endsWith('.localhost')
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && own)) throw new StommenError('Adressen till Stommen ska börja med https://.')
  if (url.username || url.password) throw new StommenError('Adressen till Stommen ska inte ha namn eller lösenord i sig.')
  return url.origin
}

async function send(server: string, path: string, init: { method?: string; body?: string; token?: string; key?: string } = {}): Promise<Answer> {
  const headers: Record<string, string> = { accept: 'application/json', 'x-app': 'byggmote', 'x-app-version': app.getVersion() }
  if (init.body !== undefined) headers['content-type'] = 'application/json'
  if (init.token) headers['authorization'] = `Bearer ${init.token}`
  if (init.key) headers['idempotency-key'] = init.key // the same protocol sent twice is one send in Stommen
  try {
    // The token and the password go to the address the person gave and nowhere else.
    return await ask(new URL(server + path), init.method ?? 'GET', headers, init.body)
  } catch {
    throw new StommenError(`Det gick inte att nå Stommen på ${server}.`)
  }
}

/** Stommen's own words for a refusal, when it gave any: its API answers `{error: {message, detail}}`, its sign-in `{message}`. */
async function refusal(res: Answer): Promise<StommenError> {
  const body = (await res.json().catch(() => null)) as { error?: { message?: string; detail?: string }; message?: string } | null
  const said = [body?.error?.message, body?.error?.detail].filter(Boolean).join('. ') || body?.message
  return new StommenError(said ? `Stommen svarar: ${said}` : `Stommen svarar med fel ${res.status}.`)
}

async function get<T>(server: string, bearer: string, path: string): Promise<T> {
  const res = await send(server, `/api/mobile/v1${path}`, { token: bearer })
  if (res.status === 401) {
    await forget()
    throw new StommenError('Inloggningen i Stommen gäller inte längre. Logga in igen.')
  }
  if (!res.ok) throw await refusal(res)
  return (await res.json()) as T
}

/** The session is gone from this computer. The address stays, for the next sign-in. */
async function forget(): Promise<void> {
  unkept = null
  const saved = await read()
  if (saved) await write({ server: saved.server })
}

export async function state(): Promise<StommenState> {
  const saved = await read()
  const connected = token(saved) !== null
  return { server: saved?.server || DEFAULT_SERVER, connected, user: connected ? (saved?.user ?? '') : '', organization: connected ? (saved?.organization ?? '') : '',
    syncedAt: connected ? (saved?.syncedAt ?? null) : null, kept: keeps() }
}

export async function signIn(server: string, email: string, password: string): Promise<StommenState> {
  const base = address(server.trim() || DEFAULT_SERVER)
  const res = await send(base, '/api/auth/sign-in/email', { method: 'POST', body: JSON.stringify({ email: email.trim(), password }) })
  if (res.status === 400 || res.status === 401) throw new StommenError('E-postadressen eller lösenordet stämmer inte.')
  if (!res.ok) throw await refusal(res)
  const bearer = res.header('set-auth-token')
  if (!bearer) {
    const body = (await res.json().catch(() => null)) as { twoFactorRedirect?: boolean } | null
    throw new StommenError(body?.twoFactorRedirect ? 'Kontot har tvåstegsinloggning, och den klarar Byggmöte inte än.' : 'Inloggningen gav ingen session. Försök igen.')
  }
  let me: Me
  try {
    me = await get<Me>(base, bearer, '/me')
  } catch (e) {
    // Signed in, and then refused (a Byggmöte too old for Stommen, an organization that is closed): the session that
    // was just made is ended again, so none is left in Stommen that nobody holds.
    await send(base, '/api/auth/sign-out', { method: 'POST', body: '{}', token: bearer }).catch(() => {})
    throw e
  }
  const saved: Saved = { server: base, user: me.user.name || me.user.email || '', organization: me.organization.name }
  unkept = null
  if (keeps()) saved.token = safeStorage.encryptString(bearer).toString('base64')
  else unkept = bearer
  await write(saved)
  return state()
}

/** Every Projekt the person sees in Stommen, with its Roller and Kontakter, into the engine's knowledge base. Stommen wins there. */
export async function sync(): Promise<StommenSync> {
  const saved = await read()
  const bearer = token(saved)
  if (!saved || !bearer) throw new StommenError('Byggmöte är inte inloggat i Stommen.')
  const { projects } = await get<{ projects: { id: string; name: string }[] }>(saved.server, bearer, '/projects')
  const sum: StommenSync = { projects: 0, people: 0, vacant: 0 }
  for (const p of projects) {
    const r = await get<Roles>(saved.server, bearer, `/projects/${encodeURIComponent(p.id)}/roles`)
    // Only the fields Byggmöte uses: Stommen may add to its answers (its v1 is additive), and the engine refuses a
    // field it does not know. The engine checks the rest before anything is written.
    const took = await call<{ people: number; vacant: number }>(['stommen', 'project'], {
      project: { id: r.project.id, name: r.project.name },
      roles: r.roles.map((x) => ({ id: x.id, name: x.name, holderId: x.holderId ?? null, substituteId: x.substituteId ?? null })),
      contacts: r.contacts.map((c) => ({ id: c.id, name: c.name, organization: c.organization ?? null, email: c.email ?? null }))
    })
    sum.projects += 1
    sum.people += took.people
    sum.vacant += took.vacant
  }
  // The fetch took a while, and the person may have signed out meanwhile: what is on disk now is what counts, and a
  // session that was forgotten is not written back.
  const now = await read()
  if (now && token(now) === bearer) await write({ ...now, syncedAt: new Date().toISOString() })
  return sum
}

/** Stommen ends the session, and this computer forgets it whether Stommen could be reached or not. */
export async function signOut(): Promise<StommenState> {
  const saved = await read()
  const bearer = token(saved)
  if (saved && bearer) await send(saved.server, '/api/auth/sign-out', { method: 'POST', body: '{}', token: bearer }).catch(() => {})
  await forget()
  return state()
}

/**
 * The meeting's protocol to Stommen, as the engine gives it (`byggmote stommen minutes`), and the engine is told what
 * Stommen answered. The engine refuses while a check is left, so nothing unread goes.
 */
export async function sendMinutes(dir: string): Promise<{ version: number; replaced: boolean }> {
  const saved = await read()
  const bearer = token(saved)
  if (!saved || !bearer) throw new StommenError('Byggmöte är inte inloggat i Stommen.')
  const out = await call<{ project: string; minutes: unknown; digest: string }>(['stommen', 'minutes', dir])
  const res = await send(saved.server, `/api/mobile/v1/projects/${encodeURIComponent(out.project)}/minutes`, {
    method: 'POST', body: JSON.stringify(out.minutes), token: bearer, key: out.digest
  })
  if (res.status === 401) {
    await forget()
    throw new StommenError('Inloggningen i Stommen gäller inte längre. Logga in igen.')
  }
  if (res.status === 404) throw new StommenError('Projektet finns inte i Stommen längre, eller så ser du det inte där.')
  if (res.status === 409) throw new StommenError('Protokollet är justerat i Stommen och kan inte ersättas.')
  if (!res.ok) throw await refusal(res)
  const took = (await res.json()) as { version?: number; replaced?: boolean }
  if (typeof took.version !== 'number') throw new StommenError('Stommen svarade inte som väntat. Protokollet kan ha kommit fram: öppna Stommen och se efter.')
  await call(['stommen', 'sent', dir], { version: took.version, digest: out.digest })
  return { version: took.version, replaced: Boolean(took.replaced) }
}
