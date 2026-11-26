import type { Kind, MeetingRow } from '../../../shared/types'

/** What the protocol calls each kind: the engine's code names are Stommen's. */
export const KINDS: Record<Kind, string> = {
  decision: 'Beslut',
  todo: 'Att göra',
  changeOrder: 'ÄTA',
  deviation: 'Avvikelse',
  question: 'Fråga',
  risk: 'Risk',
  note: 'Notering'
}

/** 1062 as 17:42, an hour and more as 1:02:03: the same as the engine writes in a transcript. */
export function clock(seconds: number): string {
  const t = Math.floor(seconds)
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const s = String(t % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${String(m).padStart(2, '0')}:${s}`
}

export function minutes(seconds: number): string {
  const m = Math.max(1, Math.round(seconds / 60))
  return m === 1 ? '1 minut' : `${m} minuter`
}

/** `52 min`, `1 tim 4 min`: a meeting's length in a narrow list. */
export function brief(seconds: number): string {
  const m = Math.max(1, Math.round(seconds / 60))
  return m < 60 ? `${m} min` : m % 60 ? `${Math.floor(m / 60)} tim ${m % 60} min` : `${m / 60} tim`
}

const DAY = new Intl.DateTimeFormat('sv-SE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

/** `Torsdag 19 november 2026` from the engine's timestamp. */
export function day(iso: string | null): string {
  if (!iso) return ''
  const text = DAY.format(new Date(iso))
  return text[0].toUpperCase() + text.slice(1)
}

export const date = (iso: string | null): string => (iso ? iso.slice(0, 10) : '')

/** A date that has passed, by the computer's own day. */
export function overdue(due: string | null): boolean {
  if (!due) return false
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  return due < today
}

/** `1 öppen punkt`, `7 öppna punkter`. */
export const count = (n: number, one: string, many: string): string => `${n} ${n === 1 ? one : many}`

/** What went wrong, for a person: the engine's own words are a developer's, so they come after a plain sentence. */
export const failure = (e: unknown): string => (e instanceof Error ? e.message : String(e)).replace(/^Error invoking remote method '[^']+': (Error: )?/, '')

type Tone = '' | 'ok' | 'warn' | 'bad'
/** Where a meeting stands, as the list of meetings and the sidebar say it. */
export function standing(r: MeetingRow): { tone: Tone; icon: 'clock' | 'alert' | 'file' | 'check'; text: string } {
  if (r.status === 'processing') return { tone: '', icon: 'clock', text: 'Skrivs ut' }
  if (r.status === 'failed') return { tone: 'bad', icon: 'alert', text: 'Gick inte att skriva ut' }
  if (!r.protocol) return { tone: '', icon: 'file', text: 'Utskrift utan protokoll' }
  if (r.protocol.status === 'unreadable') return { tone: 'bad', icon: 'alert', text: 'Protokollet går inte att läsa' }
  if (r.protocol.status !== 'draft') return { tone: 'ok', icon: 'check', text: 'Justerat' }
  return r.protocol.checks ? { tone: 'warn', icon: 'alert', text: `Utkast, ${r.protocol.checks} att kontrollera` } : { tone: '', icon: 'file', text: 'Utkast' }
}

const SHORT = new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'short' })
/** `5 nov.`, for a narrow list. */
export const shortDate = (iso: string | null): string => (iso ? SHORT.format(new Date(iso)) : '')
