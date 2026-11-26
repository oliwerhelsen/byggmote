// The application menu: the Mac's menu bar, the menu bar in the window on Windows and Linux. A command is a message
// to the window (`Command`), which does it the same way as its own button would. Each has the platform's shortcut.
import { app, Menu, type BrowserWindow, type MenuItemConstructorOptions } from 'electron'
import { COMMANDS, NO_DOC, type Command, type MenuState } from '../shared/types'
import { commands as recordCommands, recording, show as showRecording } from './recording'

const mac = process.platform === 'darwin'

let state: MenuState = { ready: false, held: false, project: false, series: false, connected: false, sidebar: true, meeting: false, typing: true, view: '', ...NO_DOC }

/** Whether the window can do it now. A recording or a job in the window is not left by a shortcut. */
function can(c: Command): boolean {
  if (!state.ready) return false
  if (c === 'sidebar') return true
  if (state.held) return false
  if (c === 'find') return state.meeting || state.view === 'points'
  if (c === 'inspector' || c === 'reveal') return state.meeting
  if (c === 'saveDocx' || c === 'savePdf' || c === 'saveMd' || c === 'copyText' || c === 'nextCheck' || c === 'rename') return state.protocol
  if (c === 'newPoint' || c === 'rewrite') return state.free
  if (c === 'send') return state.sendable
  if (c === 'editPoint') return state.point
  if (c === 'removePoint') return state.own
  if (c === 'listen') return state.said
  if (c === 'play' || c === 'back' || c === 'forward') return state.sound
  if (c === 'nameSpeakers') return state.unnamed
  if (c === 'attend') return state.absent
  if (c === 'confirmation') return state.sent
  if (c === 'sync') return state.connected
  if (c === 'overview' || c === 'points' || c === 'switchProject') return state.project
  if (c === 'record') return state.project && state.series && !recording() // one meeting is recorded at a time
  if (c === 'agenda' || c === 'addRecording') return state.project && state.series
  return true
}

let reopen: () => void = () => {}
let mains: () => BrowserWindow[] = () => []
let settingsWindow: (tab?: string) => void = () => {}

/** Draw the menu again: the recording's commands in Möte follow where the recording stands. */
export function buildMenu(open: () => void = reopen, mainWindows: () => BrowserWindow[] = mains, openSettings: (tab?: string) => void = settingsWindow): void {
  reopen = open
  mains = mainWindows
  settingsWindow = openSettings
  const send = (c: Command): void => {
    if (c === 'settings') return settingsWindow() // a window of its own, whatever else is open
    const win = mains()[0] // the main window, not the recording's or Inställningar
    if (!win) return reopen() // the Mac keeps the app when its window is closed: the choice brings the window back
    if (win.isMinimized()) win.restore()
    win.webContents.send('command', c)
  }
  const item = (c: Command, label: string, accelerator?: string): MenuItemConstructorOptions => ({ id: c, label, accelerator, enabled: can(c), click: () => send(c) })
  // The view in the window has the tick.
  const view = (c: 'overview' | 'points' | 'agenda', label: string, n: number): MenuItemConstructorOptions => ({ ...item(c, label, `CmdOrCtrl+${n}`), type: 'checkbox', checked: state.view === c })
  // A key a field needs for itself (Enter, the space bar, the arrows): the window takes it (Protocol.svelte), which
  // knows where the keys go. Windows shows it without taking it. The Mac shows only what the menu takes, so there
  // it is the menu's too, except while something is typed.
  const key = (c: Command, label: string, onMac: string, elsewhere: string): MenuItemConstructorOptions =>
    mac ? item(c, label, state.typing ? undefined : onMac) : { ...item(c, label, elsewhere), registerAccelerator: false }
  const line: MenuItemConstructorOptions = { type: 'separator' }
  const settings = item('settings', 'Inställningar…', 'CmdOrCtrl+,')
  // What the app is and what it is made of: a small window on the Mac, a page of Inställningar elsewhere.
  const about: MenuItemConstructorOptions = { id: 'about', label: 'Om Byggmöte', click: () => settingsWindow('about') }

  const template: MenuItemConstructorOptions[] = [
    ...(mac
      ? [{
          label: app.name,
          submenu: [
            about, line, settings, line,
            { role: 'services', label: 'Tjänster' }, line,
            { role: 'hide', label: 'Göm Byggmöte' }, { role: 'hideOthers', label: 'Göm övriga' }, { role: 'unhide', label: 'Visa alla' }, line,
            { role: 'quit', label: 'Avsluta Byggmöte' }
          ]
        } satisfies MenuItemConstructorOptions]
      : []),
    {
      label: mac ? 'Arkiv' : '&Arkiv',
      submenu: [
        item('newProject', 'Nytt projekt…', 'CmdOrCtrl+Shift+N'),
        item('switchProject', 'Byt projekt…', 'CmdOrCtrl+Shift+O'),
        item('addRecording', 'Lägg till en inspelning…', 'CmdOrCtrl+O'),
        line,
        { label: 'Spara som', submenu: [item('saveDocx', 'Word…', 'CmdOrCtrl+Shift+S'), item('savePdf', 'PDF…'), item('saveMd', 'Markdown…')] },
        item('copyText', 'Kopiera texten', 'CmdOrCtrl+Shift+C'),
        item('reveal', mac ? 'Visa i Finder' : process.platform === 'win32' ? 'Visa i Utforskaren' : 'Visa i mappen'),
        line,
        item('sync', 'Hämta från Stommen', mac ? 'Cmd+Shift+U' : 'F5'),
        line,
        ...(mac ? [] : [settings, line]),
        { role: 'close', label: 'Stäng fönstret' },
        // Alt+F4 is the system's own: the menu shows it and does not take it.
        ...(mac ? [] : [{ role: 'quit', label: 'Avsluta', accelerator: 'Alt+F4', registerAccelerator: false } satisfies MenuItemConstructorOptions])
      ]
    },
    {
      label: mac ? 'Redigera' : '&Redigera',
      submenu: [
        { role: 'undo', label: 'Ångra' }, { role: 'redo', label: 'Gör om' }, line,
        { role: 'cut', label: 'Klipp ut' }, { role: 'copy', label: 'Kopiera' }, { role: 'paste', label: 'Klistra in' }, { role: 'selectAll', label: 'Markera allt' },
        line, item('find', state.view === 'points' ? 'Sök bland punkterna' : 'Sök i utskriften', 'CmdOrCtrl+F')
      ]
    },
    {
      label: mac ? 'Visa' : '&Visa',
      submenu: [
        view('overview', 'Översikt', 1),
        view('points', 'Öppna punkter', 2),
        view('agenda', 'Dagordning', 3),
        line,
        item('sidebar', state.sidebar ? 'Dölj sidopanelen' : 'Visa sidopanelen', mac ? 'Ctrl+Cmd+S' : 'Ctrl+B'),
        item('inspector', state.inspector && state.meeting ? 'Dölj utskriften' : 'Visa utskriften', mac ? 'Alt+Cmd+I' : 'Ctrl+I'),
        line,
        item('palette', 'Kommandopalett…', 'CmdOrCtrl+K'),
        line,
        { role: 'togglefullscreen', label: mac ? 'Starta helskärmsläge' : 'Helskärm' },
        // A checkout run from a terminal, never the installed app.
        ...(app.isPackaged ? [] : [line, { role: 'reload', label: 'Läs in fönstret igen', accelerator: 'CmdOrCtrl+Alt+R' }, { role: 'toggleDevTools', label: 'Utvecklarverktyg' }] satisfies MenuItemConstructorOptions[])
      ]
    },
    { label: mac ? 'Möte' : '&Möte', submenu: [item('record', 'Spela in möte…', 'CmdOrCtrl+R'), ...recordCommands(true), line, item('rename', 'Byt namn på mötet…')] },
    {
      label: mac ? 'Protokoll' : '&Protokoll',
      submenu: [
        item('newPoint', 'Ny punkt', 'CmdOrCtrl+N'),
        key('editPoint', 'Ändra punkt', 'Enter', 'F2'),
        key('removePoint', 'Ta bort punkt', 'Cmd+Backspace', 'Delete'),
        line,
        item('nextCheck', 'Nästa att kontrollera', 'CmdOrCtrl+J'),
        item('nameSpeakers', 'Sätt namn på talare…'),
        item('attend', 'Lägg till som närvarande…'),
        line,
        key('play', 'Spela upp', 'Space', 'Space'),
        key('listen', 'Lyssna från punkten', 'Alt+Space', 'Ctrl+L'),
        key('back', 'Hoppa 10 s bakåt', 'Alt+Left', 'Ctrl+Left'),
        key('forward', 'Hoppa 10 s framåt', 'Alt+Right', 'Ctrl+Right'),
        line,
        item('rewrite', 'Skriv om protokollet…'),
        line,
        item('send', 'Skicka till Stommen…', 'CmdOrCtrl+Enter'),
        item('confirmation', 'Se efter om det är justerat')
      ]
    },
    ...(mac
      ? [{ role: 'windowMenu', label: 'Fönster', submenu: [{ role: 'minimize', label: 'Minimera' }, { role: 'zoom', label: 'Zooma' }, line,
          { id: 'recording', label: 'Inspelning', enabled: Boolean(recording()), click: showRecording }, line, { role: 'front', label: 'Lägg alla överst' }] } satisfies MenuItemConstructorOptions]
      : []),
    {
      role: 'help',
      label: mac ? 'Hjälp' : '&Hjälp',
      submenu: [item('shortcuts', 'Kortkommandon', 'CmdOrCtrl+/'), item('intro', 'Visa introduktionen'), ...(mac ? [] : [line, about])]
    }
  ]
  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

// What the menu's labels and ticks are drawn from: when one of these changes, the menu is drawn again.
const drawn = (): string => [state.sidebar, state.inspector && state.meeting, state.view, mac && state.typing].join('|')

/** The window says what it can do now: the commands that cannot run are greyed out, and their shortcuts do nothing. */
export function setMenuState(next: MenuState): void {
  const before = drawn()
  const view = (['overview', 'points', 'agenda'] as const).find((v) => v === next.view) ?? ''
  state = { ...(Object.fromEntries(Object.keys(state).map((k) => [k, Boolean(next[k as keyof MenuState])])) as unknown as MenuState), view }
  if (drawn() !== before) return buildMenu() // the keys a field needs are the Mac menu's only while nothing is typed
  const menu = Menu.getApplicationMenu()
  if (!menu) return
  for (const c of COMMANDS) {
    const it = menu.getMenuItemById(c)
    if (it) it.enabled = can(c)
  }
}
