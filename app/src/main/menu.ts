// The application menu: the Mac's menu bar, the menu bar in the window on Windows and Linux. A command is a message
// to the window (`Command`), which does it the same way as its own button would. Each has the platform's shortcut.
import { app, BrowserWindow, Menu, type MenuItemConstructorOptions } from 'electron'
import { COMMANDS, type Command, type MenuState } from '../shared/types'

const mac = process.platform === 'darwin'

let state: MenuState = { ready: false, held: false, project: false, series: false, connected: false, sidebar: true, meeting: false, protocol: false, free: false, sendable: false, inspector: true }

/** Whether the window can do it now. A recording or a job in the window is not left by a shortcut. */
function can(c: Command): boolean {
  if (!state.ready) return false
  if (c === 'sidebar') return true
  if (state.held) return false
  if (c === 'find' || c === 'inspector') return state.meeting
  if (c === 'saveDocx' || c === 'savePdf' || c === 'saveMd' || c === 'copyText' || c === 'nextCheck' || c === 'rename') return state.protocol
  if (c === 'newPoint' || c === 'rewrite') return state.free
  if (c === 'send') return state.sendable
  if (c === 'sync') return state.connected
  if (c === 'overview' || c === 'meetings') return state.project
  if (c === 'agenda' || c === 'record' || c === 'addRecording') return state.project && state.series
  return true
}

export function buildMenu(reopen: () => void): void {
  const send = (c: Command): void => {
    const win = BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0]
    if (!win) return reopen() // the Mac keeps the app when its window is closed: the choice brings the window back
    if (win.isMinimized()) win.restore()
    win.webContents.send('command', c)
  }
  const item = (c: Command, label: string, accelerator?: string): MenuItemConstructorOptions => ({ id: c, label, accelerator, enabled: can(c), click: () => send(c) })
  const line: MenuItemConstructorOptions = { type: 'separator' }
  const settings = item('settings', 'Inställningar…', 'CmdOrCtrl+,')

  const template: MenuItemConstructorOptions[] = [
    ...(mac
      ? [{
          label: app.name,
          submenu: [
            { role: 'about', label: 'Om Byggmöte' }, line, settings, line,
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
        item('addRecording', 'Lägg till en inspelning…', 'CmdOrCtrl+O'),
        line,
        { label: 'Spara som', submenu: [item('saveDocx', 'Word…', 'CmdOrCtrl+Shift+S'), item('savePdf', 'PDF…'), item('saveMd', 'Markdown…')] },
        item('copyText', 'Kopiera texten', 'CmdOrCtrl+Shift+C'),
        line,
        item('sync', 'Hämta från Stommen', mac ? 'Cmd+Shift+U' : 'F5'),
        line,
        ...(mac ? [] : [settings, line]),
        { role: 'close', label: 'Stäng fönstret' },
        ...(mac ? [] : [{ role: 'quit', label: 'Avsluta' } satisfies MenuItemConstructorOptions])
      ]
    },
    {
      label: mac ? 'Redigera' : '&Redigera',
      submenu: [
        { role: 'undo', label: 'Ångra' }, { role: 'redo', label: 'Gör om' }, line,
        { role: 'cut', label: 'Klipp ut' }, { role: 'copy', label: 'Kopiera' }, { role: 'paste', label: 'Klistra in' }, { role: 'selectAll', label: 'Markera allt' },
        line, item('find', 'Sök i utskriften', 'CmdOrCtrl+F')
      ]
    },
    {
      label: mac ? 'Visa' : '&Visa',
      submenu: [
        item('overview', 'Översikt', 'CmdOrCtrl+1'),
        item('meetings', 'Möten', 'CmdOrCtrl+2'),
        item('agenda', 'Dagordning', 'CmdOrCtrl+4'),
        line,
        { ...item('sidebar', 'Visa sidopanelen', mac ? 'Ctrl+Cmd+S' : 'Ctrl+B'), type: 'checkbox', checked: state.sidebar },
        { ...item('inspector', 'Visa utskriften', mac ? 'Alt+Cmd+I' : 'Ctrl+I'), type: 'checkbox', checked: state.inspector },
        line,
        { role: 'togglefullscreen', label: 'Helskärm' },
        // A checkout run from a terminal, never the installed app.
        ...(app.isPackaged ? [] : [line, { role: 'reload', label: 'Läs in fönstret igen', accelerator: 'CmdOrCtrl+Alt+R' }, { role: 'toggleDevTools', label: 'Utvecklarverktyg' }] satisfies MenuItemConstructorOptions[])
      ]
    },
    { label: mac ? 'Möte' : '&Möte', submenu: [item('record', 'Spela in möte…', 'CmdOrCtrl+R'), line, item('rename', 'Byt namn på mötet…')] },
    {
      label: mac ? 'Protokoll' : '&Protokoll',
      submenu: [
        item('newPoint', 'Ny punkt', 'CmdOrCtrl+N'),
        item('nextCheck', 'Nästa att kontrollera', 'CmdOrCtrl+J'),
        line,
        item('rewrite', 'Skriv om protokollet…'),
        line,
        item('send', 'Skicka till Stommen…', 'CmdOrCtrl+Enter')
      ]
    },
    ...(mac
      ? [{ role: 'windowMenu', label: 'Fönster', submenu: [{ role: 'minimize', label: 'Minimera' }, { role: 'zoom', label: 'Zooma' }, line, { role: 'front', label: 'Lägg alla överst' }] } satisfies MenuItemConstructorOptions]
      : []),
    {
      role: 'help',
      label: mac ? 'Hjälp' : '&Hjälp',
      submenu: [item('intro', 'Visa introduktionen'), ...(mac ? [] : [line, { role: 'about', label: 'Om Byggmöte' } satisfies MenuItemConstructorOptions])]
    }
  ]
  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

/** The window says what it can do now: the commands that cannot run are greyed out, and their shortcuts do nothing. */
export function setMenuState(next: MenuState): void {
  state = {
    ready: Boolean(next.ready), held: Boolean(next.held), project: Boolean(next.project),
    series: Boolean(next.series), connected: Boolean(next.connected), sidebar: Boolean(next.sidebar),
    meeting: Boolean(next.meeting), protocol: Boolean(next.protocol), free: Boolean(next.free), sendable: Boolean(next.sendable), inspector: Boolean(next.inspector)
  }
  const menu = Menu.getApplicationMenu()
  if (!menu) return
  for (const c of COMMANDS) {
    const it = menu.getMenuItemById(c)
    if (it) it.enabled = can(c)
  }
  const side = menu.getMenuItemById('sidebar')
  if (side) side.checked = state.sidebar
  const insp = menu.getMenuItemById('inspector')
  if (insp) insp.checked = state.inspector
}
