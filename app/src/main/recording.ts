// A meeting is recorded in a small window of its own that stays over other programs, so whoever leads the meeting
// can have the agenda, a drawing or a spreadsheet on the screen. While it is open there is an icon beside the clock
// with the recording's commands, and shortcuts that work in any program.
import { join } from 'node:path'
import { BrowserWindow, globalShortcut, Menu, nativeImage, Tray, type MenuItemConstructorOptions } from 'electron'
import type { RecordCommand, RecordSpec, RecordStatus } from '../shared/types'
import { MAC_TEMPLATE_2X, TILE_32 } from './tray-icons'

const mac = process.platform === 'darwin'

/** The shortcuts that work in any program while a meeting is recorded. Ctrl+Alt on the Mac and Alt+Shift elsewhere:
 * Alt with a digit is a spreadsheet's, and Ctrl+Alt with a digit types a character on a Swedish keyboard on Windows. */
const GLOBAL: [RecordCommand, string][] = (
  [['pause', 'P'], ['next', 'N'], ['decision', '1'], ['todo', '2'], ['changeOrder', '3'], ['question', '4']] as const
).map(([c, key]) => [c, `${mac ? 'Control+Alt' : 'Alt+Shift'}+${key}`])
export const shortcut = (c: RecordCommand): string | undefined => GLOBAL.find(([x]) => x === c)?.[1]

let win: BrowserWindow | null = null
let tray: Tray | null = null
let status: RecordStatus | null = null
let drawn = '' // what the icon's menu was built from, so it is not rebuilt every second
let tell: (s: RecordStatus | null) => void = () => {}
let menu: () => void = () => {}

export const recording = (): RecordStatus | null => status
export const recordingWindow = (): BrowserWindow | null => win

/** `tell`: the main window hears where the recording stands. `menu`: the application menu follows it. */
export function setUp(hear: (s: RecordStatus | null) => void, redraw: () => void): void {
  tell = hear
  menu = redraw
}

export function send(c: RecordCommand): void {
  if (!win) return
  if (c === 'cancel') show() // it asks first, and the question is in the window
  win.webContents.send('recordCommand', c)
}

export function show(): void {
  if (!win) return
  if (win.isMinimized()) win.restore()
  win.show()
  win.focus()
}

const clock = (seconds: number): string => {
  const t = Math.floor(seconds)
  const h = Math.floor(t / 3600)
  const m = String(Math.floor((t % 3600) / 60)).padStart(2, '0')
  const s = String(t % 60).padStart(2, '0')
  return h ? `${h}:${m}:${s}` : `${m}:${s}`
}

const LABELS = { idle: 'Inte igång', recording: 'Spelar in', paused: 'Pausad', saving: 'Sparar inspelningen' } as const

/** The recording's commands, for the icon beside the clock and for the application menu's Möte. */
export function commands(): MenuItemConstructorOptions[] {
  const s = status
  const live = s?.phase === 'recording'
  const on = live || s?.phase === 'paused'
  // The shortcut is shown, not taken by the menu: it is registered for every program below.
  const item = (c: RecordCommand, label: string, enabled: boolean, accelerator = shortcut(c)): MenuItemConstructorOptions =>
    ({ label, enabled, accelerator, registerAccelerator: !shortcut(c), click: () => send(c) })
  return [
    item('pause', s?.phase === 'paused' ? 'Fortsätt' : 'Pausa', Boolean(on)),
    item('next', s?.next ? `Nästa rubrik: ${s.next}` : 'Nästa rubrik', Boolean(on && s?.next)),
    { type: 'separator' },
    item('decision', 'Sätt märke: Beslut', Boolean(live)),
    item('todo', 'Sätt märke: Att göra', Boolean(live)),
    item('changeOrder', 'Sätt märke: ÄTA', Boolean(live)),
    item('question', 'Sätt märke: Fråga', Boolean(live)),
    { type: 'separator' },
    { label: 'Visa inspelningsfönstret', enabled: Boolean(s), click: show },
    item('finish', 'Avsluta mötet', Boolean(on), 'CmdOrCtrl+Shift+R'),
    item('cancel', 'Avbryt inspelningen…', Boolean(on))
  ]
}

function draw(): void {
  if (!tray || !status) return
  if (mac) tray.setTitle(status.phase === 'idle' ? '' : ` ${clock(status.seconds)}`, { fontType: 'monospacedDigit' })
  tray.setToolTip(`${status.title} · ${LABELS[status.phase]}${mac ? '' : ` · ${clock(status.seconds)}`}`)
  const key = [status.title, status.phase, status.heading, status.next].join('|')
  if (key === drawn) return
  drawn = key
  const head = [status.title, LABELS[status.phase], status.heading].filter(Boolean).join(' · ')
  tray.setContextMenu(Menu.buildFromTemplate([{ label: head, enabled: false }, { type: 'separator' }, ...commands()]))
}

export function open(spec: RecordSpec, preload: string, hidden: boolean): void {
  if (win) return show()
  win = new BrowserWindow({
    width: 380,
    height: spec.agenda ? 640 : 470,
    minWidth: 340,
    minHeight: 360,
    show: false,
    alwaysOnTop: true,
    fullscreenable: false,
    maximizable: false,
    title: 'Byggmöte',
    backgroundColor: '#ffffff',
    autoHideMenuBar: true, // Windows and Linux: the small window has no menu bar of its own
    webPreferences: { preload, sandbox: true, contextIsolation: true, nodeIntegration: false, backgroundThrottling: false }
  })
  const w = win
  w.setAlwaysOnTop(true, 'floating')
  w.once('ready-to-show', () => {
    if (!hidden) w.show()
  })
  w.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  w.webContents.on('will-navigate', (e) => e.preventDefault())
  // The window's own close button asks first, as Avbryt inspelningen does: the recording is not lost by a stray click.
  let closing = false
  w.on('close', (e) => {
    if (closing || !status || status.phase === 'idle') return
    e.preventDefault()
    send('cancel')
  })
  w.on('closed', () => {
    win = null
    status = null
    drawn = ''
    tray?.destroy()
    tray = null
    for (const [, keys] of GLOBAL) globalShortcut.unregister(keys)
    tell(null)
    menu()
  })
  allow = () => {
    closing = true
  }
  const hash = `record=${encodeURIComponent(JSON.stringify(spec))}`
  if (process.env['ELECTRON_RENDERER_URL']) void w.loadURL(`${process.env['ELECTRON_RENDERER_URL']}#${hash}`)
  else void w.loadFile(join(__dirname, '../renderer/index.html'), { hash })

  const image = mac ? nativeImage.createFromBuffer(Buffer.from(MAC_TEMPLATE_2X, 'base64'), { scaleFactor: 2 }) : nativeImage.createFromBuffer(Buffer.from(TILE_32, 'base64'))
  if (mac) image.setTemplateImage(true)
  tray = new Tray(image)
  tray.on('click', () => (mac ? undefined : show())) // on the Mac a click opens the menu
  for (const [c, keys] of GLOBAL) globalShortcut.register(keys, () => send(c))
}

let allow: () => void = () => {}

/** From the recording window: where it stands now. */
export function heard(next: RecordStatus): void {
  if (!win) return
  const before = [status?.phase, status?.next].join('|')
  status = { title: String(next.title).slice(0, 200), phase: next.phase, seconds: Number(next.seconds) || 0, heading: next.heading ? String(next.heading).slice(0, 200) : null, next: next.next ? String(next.next).slice(0, 200) : null }
  draw()
  tell(status)
  if ([status.phase, status.next].join('|') !== before) menu() // its labels follow the recording, not the clock
}

/** From the recording window: it is done with, one way or the other. */
export function close(): void {
  allow()
  win?.close()
}
