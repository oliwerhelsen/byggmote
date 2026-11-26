// A meeting is recorded in a small window of its own that stays over other programs, so whoever leads the meeting
// can have the agenda, a drawing or a spreadsheet on the screen. While it is open there is an icon beside the clock
// with the recording's commands, and shortcuts that work in any program.
import { join } from 'node:path'
import { BrowserWindow, globalShortcut, Menu, nativeImage, Tray, type MenuItemConstructorOptions } from 'electron'
import { accelerators, normal, spell, standard, VALID, type Global } from '../shared/keys'
import type { RecordCommand, RecordSpec, RecordStatus, Shortcuts } from '../shared/types'
import { MAC_TEMPLATE_2X, TILE_32 } from './tray-icons'

const mac = process.platform === 'darwin'

// The shortcuts that work in any program while a meeting is recorded (app/src/shared/keys.ts): the standard ones, or
// the person's own from Inställningar. BYGGMOTE_PLATFORM: a Mac that shows Windows' keys takes those keys.
const keysMac = (process.env['BYGGMOTE_PLATFORM'] || process.platform) === 'darwin'
let chosen: Shortcuts = {}
let taken: string[] = [] // the ones the system has given the app now
const global = (): [Global, string][] => Object.entries(accelerators(chosen, keysMac)) as [Global, string][]
export const shortcut = (c: RecordCommand): string | undefined => (accelerators(chosen, keysMac) as Partial<Record<RecordCommand, string>>)[c]

/** Take the shortcuts from the system while a meeting is recorded, or give them back. */
function take(on: boolean): void {
  for (const keys of taken) globalShortcut.unregister(keys)
  taken = []
  if (!on || !win) return
  for (const [c, keys] of global()) if (globalShortcut.register(keys, () => send(c))) taken.push(keys)
}

/** While the person presses a new combination in Inställningar, a recording does not take the keys as its own. */
export const listen = (on: boolean): void => take(!on)

/** The keys kept from an earlier run, as they were chosen then. */
export function keep(kept: Shortcuts): void {
  chosen = kept
}

const NAMES = { pause: 'Pausa', next: 'Nästa rubrik', mark: 'Sätt märke' } as const

/**
 * The person's own keys, from Inställningar. Refused with a sentence for the person when a combination has no
 * modifier, is another command's, or is one the system does not give the app. Returns what to keep: only what
 * differs from the standard keys. The menus, the icon's menu and a recording that is going on follow at once.
 */
export function choose(wanted: Shortcuts): Shortcuts {
  const std = standard(keysMac)
  const next: Shortcuts = {}
  for (const k of ['pause', 'next', 'mark'] as const) {
    const given = wanted[k]
    if (!given) continue
    let keys = normal(given, keysMac)
    if (!VALID.test(keys) || !/Control|Alt|Command/.test(keys)) {
      throw new Error(`Ett kortkommando är ${keysMac ? '⌃, ⌥ eller ⌘' : 'Ctrl eller Alt'} tillsammans med en bokstav, en siffra eller en funktionstangent.`)
    }
    if (k === 'mark') {
      if (!/\+[1-4]$/.test(keys)) throw new Error('Märkena har siffrorna 1 till 4. Tryck tangenterna tillsammans med en av dem.')
      keys = keys.slice(0, -1) + '1'
    }
    if (keys !== std[k]) next[k] = keys
  }
  const said = (keys: string): string => spell(keys, keysMac)
  const after = accelerators(next, keysMac)
  const row = (c: Global): keyof typeof NAMES => (c === 'pause' || c === 'next' ? c : 'mark')
  const all = Object.entries(after) as [Global, string][]
  for (const [c, keys] of all) {
    const other = all.find(([x, k]) => k === keys && row(x) !== row(c))
    if (other) throw new Error(`${said(keys)} används redan av ${NAMES[row(other[0])]}. Välj andra tangenter.`)
  }
  // The application menu's own: a shortcut that works in any program would take the key from it.
  const walk = (items: Electron.MenuItem[]): Electron.MenuItem[] => items.flatMap((i) => [i, ...(i.submenu ? walk(i.submenu.items) : [])])
  for (const i of walk(Menu.getApplicationMenu()?.items ?? [])) {
    if (!i.accelerator || i.registerAccelerator === false) continue
    const keys = normal(String(i.accelerator), keysMac)
    if (Object.values(after).includes(keys)) throw new Error(`${said(keys)} används redan av ${i.label.replace(/[&…]/g, '')}. Välj andra tangenter.`)
  }
  // Asked of the system only for the ones that are new: it says no to a combination another program has.
  const before = Object.values(accelerators(chosen, keysMac))
  const fresh = Object.values(after).filter((k) => !before.includes(k))
  take(false)
  const refused = fresh.filter((k) => !globalShortcut.register(k, () => {}))
  for (const k of fresh) globalShortcut.unregister(k)
  if (refused.length) {
    take(true)
    throw new Error(`Datorn ger inte ${said(refused[0])} till Byggmöte, ett annat program använder det. Välj andra tangenter.`)
  }
  chosen = next
  take(true)
  drawn = ''
  draw()
  menu()
  return next
}

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
    take(false)
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
  take(true)
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
