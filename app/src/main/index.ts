import { randomUUID } from 'node:crypto'
import { appendFile, copyFile, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { basename, extname, join, resolve } from 'node:path'
import { app, BrowserWindow, clipboard, dialog, ipcMain, session, shell } from 'electron'
import type { Agenda, Api, Done, Job, MeetingDetail, MeetingRow, ModelEvent, ModelRow, NewPoint, PointFields, Progress, Project, SeriesRef } from '../shared/types'
import { call, run, stopAll, stream } from './engine'
import * as kept from './settings'
import { toDocx, toPdf } from './export'
import * as stommen from './stommen'

// The tests give the app a folder of its own for what it keeps, so a run never reads or writes the person's.
if (process.env['BYGGMOTE_USER_DATA']) app.setPath('userData', process.env['BYGGMOTE_USER_DATA'])

// What the window may name. It only ever gets a folder or a file from here, so one it makes up is refused: the
// window shows text a language model wrote, and that text must not become a path.
const meetings = new Set<string>()
const recordings = new Set<string>()
const taping = new Map<string, string>()
// The model download at work. There is one at a time, and it does not outlive the app.
let fetching: { done: Promise<number>; stop: () => void } | null = null

const known = (dir: string): string => {
  const d = resolve(dir)
  if (!meetings.has(d)) throw new Error('unknown meeting')
  return d
}

const scratch = (): string => join(app.getPath('temp'), 'byggmote-recordings')

// A point's number and a person's id go to the engine as arguments. Neither may be read as an option.
const point = (no: string): string => {
  if (!/^\d+\.\d+\.\d+$/.test(no)) throw new Error('unknown point')
  return no
}
const personKey = (id: string): string => {
  if (!/^[^\s@-][^\s@]*$/.test(id)) throw new Error('unknown person')
  return id
}
const person = (id: string): string => `@${personKey(id)}`

// A project's id goes to the engine as an argument, so it may not be read as an option either.
const projectId = (id: string): string => {
  if (!/^[a-z0-9][a-z0-9-]*$/.test(id)) throw new Error('unknown project')
  return id
}
const words = (s: unknown, what: string): string => {
  const t = String(s ?? '').split(/\s+/).filter(Boolean).join(' ')
  if (!t) throw new Error(`${what} saknas`)
  return t
}

/** A project of this computer's own. One of Stommen's is Stommen's to name, remove and staff: the window hides those
 * buttons, and this refuses them too, so a call from the window cannot do what the window does not offer. */
async function own(id: string): Promise<Project> {
  const p = (await call<{ projects: Project[] }>(['projects'])).projects.find((x) => x.id === projectId(id))
  if (!p) throw new Error('unknown project')
  if (p.stommen) throw new Error('Projektet kommer från Stommen. Ändra det där och hämta det igen.')
  return p
}

/** The project's people as the engine keeps them (a person and a Roll each), for a change to write back whole. */
async function members(id: string): Promise<{ person: string; role?: string }[]> {
  const p = await own(id)
  return p.people.map((x) => (x.role ? { person: x.id, role: x.role } : { person: x.id }))
}

const setMembers = (id: string, people: { person: string; role?: string }[]): Promise<unknown> => call(['areas', 'set', projectId(id)], { people })

/** One correction of a protocol: `byggmote correct`, the fields on its stdin. */
const correct = async (args: string[], fields?: PointFields | NewPoint): Promise<void> => {
  await call(['correct', ...args], fields)
}

function handlers(tell: (p: Progress) => void, tellModels: (e: ModelEvent) => void): { [K in Exclude<keyof Api, 'onProgress' | 'onModels'>]: (...args: Parameters<Api[K]>) => ReturnType<Api[K]> } {
  return {
    projects: () => call<{ folder: string; projects: Project[] }>(['projects']),

    async meetings(projectId) {
      const rows = await call<MeetingRow[]>(['meetings', projectId])
      for (const r of rows) meetings.add(resolve(r.dir))
      return rows
    },

    agenda: (projectId, seriesId) => call<Agenda>(['agenda', projectId, seriesId]),

    meeting: (dir) => call<MeetingDetail>(['meeting', known(dir)]),

    async audio(dir) {
      try {
        return new Uint8Array(await readFile(join(known(dir), 'audio.m4a')))
      } catch (e) {
        if ((e as NodeJS.ErrnoException).code === 'ENOENT') return null
        throw e
      }
    },

    startSeries: (projectId, name) => call<SeriesRef>(['series', 'start', projectId], { name }),

    async pickRecording() {
      const win = BrowserWindow.getFocusedWindow()
      const options: Electron.OpenDialogOptions = {
        title: 'Lägg till en inspelning',
        properties: ['openFile'],
        filters: [{ name: 'Ljud och video', extensions: ['m4a', 'mp3', 'wav', 'aac', 'ogg', 'opus', 'flac', 'webm', 'mp4', 'mov', 'mkv'] }]
      }
      const got = win ? await dialog.showOpenDialog(win, options) : await dialog.showOpenDialog(options)
      if (got.canceled || !got.filePaths[0]) return null
      recordings.add(got.filePaths[0])
      return got.filePaths[0]
    },

    async process(job: Job): Promise<Done> {
      if (!recordings.has(job.file)) throw new Error('unknown recording')
      const dir = await run([job.file, '--area', job.projectId, '--title', job.title], (e) => {
        if (e.event === 'step' && e.step) tell({ step: e.step, state: e.status === 'done' ? 'done' : 'start' })
        if (e.event === 'progress' && e.step) tell({ step: e.step, state: 'progress', fraction: e.fraction })
      })
      meetings.add(resolve(dir))
      if (job.file.startsWith(scratch())) await rm(job.file, { force: true }) // the meeting has its own copy now
      recordings.delete(job.file)
      if (job.marks) await writeFile(join(dir, 'marks.json'), JSON.stringify(job.marks, null, 1) + '\n', 'utf8')
      tell({ step: 'protocol', state: 'start' })
      try {
        await call(['protocol', dir, '--series', job.seriesId])
        return { dir, protocolError: null }
      } catch (e) {
        return { dir, protocolError: (e as Error).message } // the transcript is there: the protocol can be written again
      } finally {
        tell({ step: 'protocol', state: 'done' })
      }
    },

    async writeProtocol(dir, seriesId, discard) {
      await call(['protocol', known(dir), '--series', seriesId, ...(discard ? ['--discard'] : [])])
    },

    async nameSpeaker(dir, speaker, personId) {
      if (!/^\w+$/.test(speaker)) throw new Error('unknown speaker')
      await call(['name', known(dir), speaker, person(personId)])
    },

    async setTitle(dir, title) {
      const text = String(title).replace(/\s+/g, ' ').trim()
      if (!text) throw new Error('Mötet behöver ett namn')
      await call(['title', known(dir), text])
    },

    changePoint: (dir, no, fields) => correct(['change', known(dir), point(no)], fields),
    addPoint: (dir, fields) => correct(['add', known(dir)], fields),
    removePoint: (dir, no) => correct(['remove', known(dir), point(no)]),
    restorePoint: (dir, no) => correct(['restore', known(dir), point(no)]),
    confirmCheck: (dir, no, n, undo) => correct(['check', known(dir), point(no), String(Math.trunc(n)), ...(undo ? ['--undo'] : [])]),
    attend: (dir, personId, gone) => correct(['attend', known(dir), person(personId), ...(gone ? ['--remove'] : [])]),

    stommenState: () => stommen.state(),
    stommenSignIn: (server, email, password) => stommen.signIn(String(server), String(email), String(password)),
    stommenSync: () => stommen.sync(),
    stommenSignOut: () => stommen.signOut(),
    stommenSend: (dir) => stommen.sendMinutes(known(dir)),

    async projectAdd(name) {
      const a = await call<{ id: string }>(['areas', 'add'], { name: words(name, 'Namn') })
      try {
        await call(['series', 'start', a.id], { name: 'Byggmöte' })
      } catch (e) {
        await call(['areas', 'delete', a.id]).catch(() => {}) // no half-made project, so trying again is not a second one
        throw e
      }
      return a.id
    },
    async projectRename(id, name) {
      await own(id)
      await call(['areas', 'set', projectId(id)], { name: words(name, 'Namn') })
    },
    async projectDelete(id) {
      await own(id)
      await call(['areas', 'delete', projectId(id)])
    },
    async personAdd(id, name, role) {
      const cur = await members(id)
      const p = await call<{ id: string }>(['people', 'add'], { name: words(name, 'Namn') })
      if (cur.some((x) => x.person === p.id)) throw new Error('Personen finns redan i projektet')
      const r = String(role ?? '').trim()
      await setMembers(id, [...cur, r ? { person: p.id, role: r } : { person: p.id }])
      // The engine leaves out the person who is using the app (they are at every meeting): say so, not nothing.
      if (!(await members(id)).some((x) => x.person === p.id)) throw new Error('Det är du själv. Du är med på alla möten och behöver inte läggas till.')
    },
    async personRemove(id, personId) {
      const who = personKey(personId)
      await setMembers(id, (await members(id)).filter((x) => x.person !== who))
    },

    async protocolSave(dir) {
      const d = known(dir)
      const win = BrowserWindow.getFocusedWindow()
      const options: Electron.SaveDialogOptions = {
        title: 'Spara protokollet',
        defaultPath: `${basename(d)}.docx`,
        filters: [
          { name: 'Word', extensions: ['docx'] },
          { name: 'PDF', extensions: ['pdf'] },
          { name: 'Markdown', extensions: ['md'] }
        ]
      }
      const got = win ? await dialog.showSaveDialog(win, options) : await dialog.showSaveDialog(options)
      if (got.canceled || !got.filePath) return false
      const file = join(d, 'protocol.md')
      const ext = extname(got.filePath).toLowerCase()
      if (ext === '.docx') await writeFile(got.filePath, await toDocx(await readFile(file, 'utf8')))
      else if (ext === '.pdf') await writeFile(got.filePath, await toPdf(await readFile(file, 'utf8')))
      else await copyFile(file, got.filePath)
      return true
    },
    async protocolCopy(dir) {
      clipboard.writeText(await readFile(join(known(dir), 'protocol.md'), 'utf8'))
    },

    // A recording goes to disk a second at a time, so a crash an hour in loses a second, not the hour.
    async recordingStart() {
      await mkdir(scratch(), { recursive: true })
      const id = randomUUID()
      taping.set(id, join(scratch(), `${id}.webm`))
      await writeFile(taping.get(id)!, new Uint8Array())
      return id
    },

    async recordingChunk(id, bytes) {
      const file = taping.get(id)
      if (!file) throw new Error('unknown recording')
      await appendFile(file, bytes)
    },

    async recordingStop(id) {
      const file = taping.get(id)
      if (!file) throw new Error('unknown recording')
      taping.delete(id)
      recordings.add(file)
      return file
    },

    async recordingDiscard(id) {
      const file = taping.get(id)
      taping.delete(id)
      if (file) await rm(file, { force: true })
    },

    settings: () => kept.read(),

    async settingsSet(patch) {
      const cur = await kept.read()
      const next = { ...cur }
      if (typeof patch.name === 'string' && patch.name.trim() !== cur.name) {
        const name = patch.name.trim().split(/\s+/).join(' ')
        if (name) await call(['me', name]) // the engine knows who is using the app: they are at every meeting
        next.name = name
      }
      if (typeof patch.voices === 'boolean' && patch.voices !== cur.voices) {
        await call(['voices', patch.voices ? 'on' : 'off'])
        next.voices = patch.voices
      }
      if (typeof patch.openAtLogin === 'boolean' && patch.openAtLogin !== cur.openAtLogin) {
        if (app.isPackaged) app.setLoginItemSettings({ openAtLogin: patch.openAtLogin }) // a dev run would register Electron itself
        next.openAtLogin = patch.openAtLogin
      }
      if (typeof patch.microphone === 'string') next.microphone = patch.microphone.slice(0, 500)
      return kept.write(next)
    },

    async setUp(done) {
      return kept.write({ ...(await kept.read()), setUp: Boolean(done) })
    },

    models: () => call<ModelRow[]>(['models', '--json']),

    async modelsDownload(ids) {
      if (fetching) throw new Error('En hämtning pågår redan.')
      const known = (await call<ModelRow[]>(['models', '--json'])).map((m) => m.id)
      if (ids.some((i) => !known.includes(String(i)))) throw new Error('unknown model')
      const job = (fetching = stream(['models', 'download', ...ids.map(String)], (e) => tellModels(e as ModelEvent)))
      try {
        await job.done
      } finally {
        fetching = null
      }
    },

    async modelsCancel() {
      fetching?.stop()
    },

    async folderShow() {
      shell.showItemInFolder((await call<{ folder: string }>(['projects'])).folder)
    },

    async folderChoose() {
      const win = BrowserWindow.getFocusedWindow()
      const options: Electron.OpenDialogOptions = { title: 'Välj mapp för Byggmöte', properties: ['openDirectory', 'createDirectory'] }
      const got = win ? await dialog.showOpenDialog(win, options) : await dialog.showOpenDialog(options)
      if (got.canceled || !got.filePaths[0]) return null
      return (await call<{ folder: string }>(['folder', got.filePaths[0]])).folder
    }
  }
}

function open(): void {
  // BYGGMOTE_HIDDEN=1: the tests drive the window without showing it, so a run neither takes the screen nor gets a
  // stray click from whoever sits at the computer.
  const hidden = process.env['BYGGMOTE_HIDDEN'] === '1'
  const win = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    show: false,
    title: 'Byggmöte',
    backgroundColor: '#faf9fb',
    autoHideMenuBar: true,
    webPreferences: { preload: join(__dirname, '../preload/index.js'), sandbox: true, contextIsolation: true, nodeIntegration: false, backgroundThrottling: !hidden }
  })
  win.once('ready-to-show', () => {
    if (!hidden) win.show()
  })
  // The window is the app and nothing else: a link opens in the browser, and nothing navigates away.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) void shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (e) => e.preventDefault())
  if (process.env['ELECTRON_RENDERER_URL']) void win.loadURL(process.env['ELECTRON_RENDERER_URL'])
  else void win.loadFile(join(__dirname, '../renderer/index.html'))
}

void app.whenReady().then(() => {
  // The microphone, for recording a meeting, and nothing else a page can ask for.
  session.defaultSession.setPermissionRequestHandler((_wc, permission, allow) => allow(permission === 'media'))
  const tell = (p: Progress): void => {
    for (const w of BrowserWindow.getAllWindows()) w.webContents.send('progress', p)
  }
  const tellModels = (e: ModelEvent): void => {
    for (const w of BrowserWindow.getAllWindows()) w.webContents.send('models', e)
  }
  for (const [name, fn] of Object.entries(handlers(tell, tellModels))) {
    ipcMain.handle(name, (_e, ...args: unknown[]) => (fn as (...a: unknown[]) => unknown)(...args))
  }
  open()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) open()
  })
})

app.on('will-quit', () => {
  fetching?.stop()
  stopAll()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
