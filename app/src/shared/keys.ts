// The recording's shortcuts: which keys each has, the person's own choice over the standard ones, and how a
// combination is written on each computer. One file, so the main process registers what the windows show.
import type { RecordCommand, Shortcuts } from './types'

/** The commands that work in any program while a meeting is recorded. */
export type Global = Extract<RecordCommand, 'pause' | 'next' | 'decision' | 'todo' | 'changeOrder' | 'question'>
const MARKS = ['decision', 'todo', 'changeOrder', 'question'] as const

/** Ctrl+Alt on the Mac and Alt+Shift elsewhere: Alt with a digit is a spreadsheet's, and Ctrl+Alt with a digit types
 * a character on a Swedish keyboard on Windows. */
export function standard(mac: boolean): Required<Shortcuts> {
  const m = mac ? 'Control+Alt' : 'Alt+Shift'
  return { pause: `${m}+P`, next: `${m}+N`, mark: `${m}+1` }
}

/** The two that are the application menu's own, and only work in the app. */
export const FIXED = { record: 'CmdOrCtrl+R', finish: 'CmdOrCtrl+Shift+R' } as const

const MODIFIERS = ['Control', 'Alt', 'Shift', 'Command'] as const
/** A combination as Electron reads it: modifiers in one order, then a letter, a digit or a function key. */
export const VALID = /^(Control\+)?(Alt\+)?(Shift\+)?(Command\+)?([A-Z0-9]|F([1-9]|1[0-9]|2[0-4]))$/

/** The same combination written the same way, whatever order it came in and whichever of Cmd and Ctrl CmdOrCtrl is here. */
export function normal(accelerator: string, mac: boolean): string {
  const parts = accelerator.split('+').map((p) => {
    const l = p.toLowerCase()
    if (l === 'cmdorctrl' || l === 'commandorcontrol') return mac ? 'Command' : 'Control'
    if (l === 'ctrl' || l === 'control') return 'Control'
    if (l === 'cmd' || l === 'command' || l === 'super' || l === 'meta') return 'Command'
    if (l === 'alt' || l === 'option') return 'Alt'
    if (l === 'shift') return 'Shift'
    return p.length === 1 ? p.toUpperCase() : p
  })
  const key = parts.filter((p) => !(MODIFIERS as readonly string[]).includes(p)).join('+')
  return [...MODIFIERS.filter((m) => parts.includes(m)), key].join('+')
}

/** Each command's keys: the person's own where they chose, else the standard. The marks are one choice, 1 to 4. */
export function accelerators(chosen: Shortcuts, mac: boolean): Record<Global, string> {
  const s = { ...standard(mac), ...Object.fromEntries(Object.entries(chosen).filter(([, v]) => v && VALID.test(v))) } as Required<Shortcuts>
  const base = s.mark.slice(0, -1)
  return { pause: s.pause, next: s.next, ...(Object.fromEntries(MARKS.map((c, i) => [c, `${base}${i + 1}`])) as Record<(typeof MARKS)[number], string>) }
}

const MAC = { Control: '⌃', Alt: '⌥', Shift: '⇧', Command: '⌘' } as const
const WIN = { Control: 'Ctrl', Alt: 'Alt', Shift: 'Skift', Command: 'Win' } as const

/** The key caps a combination is drawn with: one on the Mac (⌃⌥P), one per key elsewhere (Alt, Skift, P). */
export function caps(accelerator: string, mac: boolean): string[] {
  const parts = normal(accelerator, mac).split('+')
  const key = parts.pop()!
  const mods = parts as (keyof typeof MAC)[]
  return mac ? [mods.map((m) => MAC[m]).join('') + key] : [...(['Control', 'Alt', 'Shift', 'Command'] as const).filter((m) => mods.includes(m)).map((m) => WIN[m]), key]
}

/** A combination in running text: ⌃⌥P, Alt+Skift+P. */
export const spell = (accelerator: string, mac: boolean): string => caps(accelerator, mac).join('+')
