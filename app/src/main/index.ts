import { randomUUID } from 'node:crypto'
import { appendFile, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { app, BrowserWindow, dialog, ipcMain, session, shell } from 'electron'
import type { Agenda, Api, Done, Job, MeetingDetail, MeetingRow, Progress, Project, SeriesRef } from '../shared/types'
import { call, run } from './engine'

// What the window may name. It only ever gets a folder or a file from here, so one it makes up is refused: the
// window shows text a language model wrote, and that text must not become a path.
const meetings = new Set<string>()
const recordings = new Set<string>()
const taping = new Map<string, string>()

const known = (dir: string): string => {
  const d = resolve(dir)
  if (!meetings.has(d)) throw new Error('unknown meeting')
  return d
}

const scratch = (): string => join(app.getPath('temp'), 'byggmote-recordings')

function handlers(tell: (p: Progress) => void): { [K in Exclude<keyof Api, 'onProgress'>]: (...args: Parameters<Api[K]>) => ReturnType<Api[K]> } {
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

    async writeProtocol(dir, seriesId) {
      await call(['protocol', known(dir), '--series', seriesId])
    },

    async nameSpeaker(dir, speaker, personId) {
      await call(['name', known(dir), speaker, `@${personId}`])
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
  for (const [name, fn] of Object.entries(handlers(tell))) {
    ipcMain.handle(name, (_e, ...args: unknown[]) => (fn as (...a: unknown[]) => unknown)(...args))
  }
  open()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) open()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
