// What the engine's read commands give (engine/src/byggmote/overview.py, series.py, protocol.py) and what the
// window may ask the main process for. One file, so the two sides cannot drift apart.

export type Person = { id: string; name: string; role?: string }
export type SeriesRef = { id: string; name: string; next: number }
/** `roles`: the Roller a point can be given, a vacant one too. `stommen`: the Projekt's id there, when it is Stommen's. */
export type Project = { id: string; name: string; stommen: string | null; roles: string[]; people: Person[]; series: SeriesRef[] }

export type Kind = 'decision' | 'todo' | 'changeOrder' | 'deviation' | 'question' | 'risk' | 'note'
/** Something for a person to read against the recording. `confirmed`: when a person said the amount is right. */
export type Check = { code: 'amount'; value: string; said: string; confirmed?: string } | { code: 'role'; said: string }
export type Heading = { no: number; name: string; hint?: string; fill?: string }

/** What a person may set on a point: the first six on the meeting's own, `follow` and the last three on an earlier meeting's. */
export type PointFields = Partial<{ text: string; kind: Kind; heading: number; role: string | null; due: string | null; open: boolean; follow: string | null }>
/** A point a person writes. `line` is the transcript line where it is said, when the person points at one. */
export type NewPoint = { heading: number; kind: Kind; text: string; open: boolean; role: string | null; due: string | null; line: number | null }

/** A point of a protocol. One an earlier meeting left open has `since`, and `raised` says whether this meeting took it up.
 * `edited`: a person changed it, and `proposed` is what the model wrote. `added`: a person wrote it. */
export type Point = {
  no: string
  heading: number
  kind: Kind
  text: string
  role: string | null
  due: string | null
  open: boolean
  at: number | null
  line: number | null
  quote: string | null
  checks: Check[]
  since?: number
  raised?: boolean
  follow?: string | null
  said?: string | null
  edited?: string
  added?: string
  proposed?: PointFields
}

export type Dropped = { reason: string; text: string; time: string | null; quote: string | null; no?: string }

export type Protocol = {
  series: string
  name: string
  no: number
  status: string
  model: string | null
  written_at: string
  headings: Heading[]
  /** `added`: a person put them there, as someone who was at the meeting and said nothing. */
  attendees: { name: string; role?: string; person?: string; added?: string }[]
  points: Point[]
  dropped: Dropped[]
  /** Points a person took out, kept to put back. */
  removed?: Point[]
}

export type ProtocolAbout = { status: string; points?: number; carried?: number; open?: number; checks?: number }

export type MeetingRow = {
  dir: string
  title: string
  recorded_at: string | null
  duration: number
  status: string
  error?: string | null
  series: string | null
  no: number | null
  unnamed: number
  protocol: ProtocolAbout | null
}

export type Line = { id: number; at: number; speaker: string; who: string; text: string }

export type MeetingDetail = Omit<MeetingRow, 'protocol'> & {
  project: string
  audio: boolean
  speakers: { id: string; name: string; person: string | null }[]
  lines: Line[]
  protocol: Protocol | null
  /** How much of the protocol a person has set right: lost if it is written again. */
  corrections: number
  /** The number of the meeting that builds on this protocol, when one does: then it is not changed. */
  later: number | null
  /** Where the protocol stands with Stommen; null without a protocol. */
  stommen: Standing | null
}

/**
 * Whether a protocol can go to Stommen and what stops it: `local`, the project is not Stommen's; `checks`, so many
 * (`about`) are left for a person; `role`, a point is for a Roll (`about`) Stommen no longer has. And when it was last
 * sent, as which version, and whether it has changed since.
 */
export type Standing = {
  possible: boolean
  why: 'local' | 'checks' | 'role' | null
  about: number | string | null
  sent_at: string | null
  version: number | null
  changed: boolean
}

export type OpenPoint = { no: string; heading: number; kind: Kind; text: string; role: string | null; due: string | null }
export type Agenda = { series: string; name: string; no: number; headings: (Heading & { open: OpenPoint[] })[] }

/** What was pressed while recording, in seconds of recorded sound. */
export type Marks = { headings: { no: number; at: number }[]; marks: { kind: Kind; at: number }[] }

export type Job = { projectId: string; seriesId: string; file: string; title: string; marks?: Marks }
export type Done = { dir: string; protocolError: string | null }

/** Where a job is: the engine's own step names while it transcribes, then `protocol`. */
export type Progress = { step: string; state: 'start' | 'progress' | 'done'; fraction?: number }

/** Where the app stands with Stommen. `kept`: the computer can keep the session safely, so it lasts over a restart. */
export type StommenState = { server: string; connected: boolean; user: string; organization: string; syncedAt: string | null; kept: boolean }
/** What a fetch from Stommen brought: the Projekt, the Kontakter in them, and the Roller nobody holds. */
export type StommenSync = { projects: number; people: number; vacant: number }

export interface Api {
  projects(): Promise<{ folder: string; projects: Project[] }>
  meetings(projectId: string): Promise<MeetingRow[]>
  agenda(projectId: string, seriesId: string): Promise<Agenda>
  meeting(dir: string): Promise<MeetingDetail>
  audio(dir: string): Promise<Uint8Array | null>
  startSeries(projectId: string, name: string): Promise<SeriesRef>
  pickRecording(): Promise<string | null>
  process(job: Job): Promise<Done>
  /** `discard`: the protocol has a person's corrections, and they may go. */
  writeProtocol(dir: string, seriesId: string, discard?: boolean): Promise<void>
  nameSpeaker(dir: string, speaker: string, personId: string): Promise<void>
  changePoint(dir: string, no: string, fields: PointFields): Promise<void>
  addPoint(dir: string, fields: NewPoint): Promise<void>
  removePoint(dir: string, no: string): Promise<void>
  restorePoint(dir: string, no: string): Promise<void>
  /** Check `n` (from 1) of a point is right, or with `undo`, not confirmed after all. */
  confirmCheck(dir: string, no: string, n: number, undo: boolean): Promise<void>
  /** A person of the project was at the meeting and said nothing; `gone`: was not there after all. */
  attend(dir: string, personId: string, gone: boolean): Promise<void>
  stommenState(): Promise<StommenState>
  /** The password goes to the main process and from there to Stommen. It is not kept. */
  stommenSignIn(server: string, email: string, password: string): Promise<StommenState>
  /** The person's Projekt with Roller and Kontakter, from Stommen into the engine. */
  stommenSync(): Promise<StommenSync>
  stommenSignOut(): Promise<StommenState>
  /** The meeting's protocol to Stommen: its points, and for each the time, the line said there and who said it. */
  stommenSend(dir: string): Promise<{ version: number; replaced: boolean }>
  /** A project of this computer's own, with its first mötesserie, so a meeting can be recorded at once. Returns its id. */
  projectAdd(name: string): Promise<string>
  projectRename(id: string, name: string): Promise<void>
  /** Refused for one of Stommen's. Its meetings' folders stay. */
  projectDelete(id: string): Promise<void>
  /** A person at the project's meetings, with their Roll if they have one. Refused in one of Stommen's. */
  personAdd(projectId: string, name: string, role: string): Promise<void>
  personRemove(projectId: string, personId: string): Promise<void>
  /** The meeting's protocol as a Markdown file the person chooses where to keep; false when they cancelled. */
  protocolSave(dir: string): Promise<boolean>
  protocolCopy(dir: string): Promise<void>
  recordingStart(): Promise<string>
  recordingChunk(id: string, bytes: Uint8Array): Promise<void>
  recordingStop(id: string): Promise<string>
  recordingDiscard(id: string): Promise<void>
  onProgress(listener: (p: Progress) => void): () => void
}

export const CHANNELS = ['projects', 'meetings', 'agenda', 'meeting', 'audio', 'startSeries', 'pickRecording', 'process',
  'writeProtocol', 'nameSpeaker', 'changePoint', 'addPoint', 'removePoint', 'restorePoint', 'confirmCheck', 'attend', 'stommenState', 'stommenSignIn', 'stommenSync', 'stommenSignOut', 'stommenSend', 'projectAdd', 'projectRename', 'projectDelete', 'personAdd', 'personRemove', 'protocolSave', 'protocolCopy', 'recordingStart', 'recordingChunk', 'recordingStop', 'recordingDiscard'] as const
