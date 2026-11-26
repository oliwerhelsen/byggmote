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
 * Whether a protocol can go to Stommen and what stops it: `local`, the project is not Stommen's; `confirmed`, it is
 * justerat there; `checks`, so many (`about`) are left for a person; `role`, a point is for a Roll (`about`) Stommen no
 * longer has. And when it was last sent, as which version, whether it has changed since, and its Justering as Stommen
 * said it when last asked.
 */
export type Standing = {
  possible: boolean
  why: 'local' | 'confirmed' | 'checks' | 'role' | null
  about: number | string | null
  sent_at: string | null
  version: number | null
  changed: boolean
  confirmed: Confirmation | null
}

/** A Justering the projektledare registered in Stommen: the day, how and who justerade (as written there). */
export type Confirmation = { on: string; method: 'next_meeting' | 'email' | 'signed'; by: string }

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

/** What the person has set in the app itself, kept in the app's own folder. `setUp`: the first-run steps are done. */
export type Settings = { setUp: boolean; name: string; voices: boolean; openAtLogin: boolean; microphone: string; shortcuts: Shortcuts }
/** The person's own keys for the recording's shortcuts, as Electron writes a combination (`Control+Alt+P`). One that is
 * missing is the standard one (app/src/shared/keys.ts). `mark` is the first of the four marks: the others are 2 to 4. */
export type Shortcuts = Partial<Record<'pause' | 'next' | 'mark', string>>
/** A model the engine knows, as `byggmote models --json` lists it. */
export type ModelRow = { id: string; type: 'asr' | 'diarize' | 'llm'; name: string; langs: string[]; model: string; size: number; license: string; downloaded: boolean; min_ram_gb?: number }
/** This computer as far as the models care: its memory and the free space where the models go, in bytes. */
export type Computer = { memory: number; free: number }
/** What a download says as it goes: bytes of one model, one finished, one failed, and the end. */
export type ModelEvent = { event: 'download' | 'downloaded' | 'error' | 'done'; model?: string; id?: string; done?: number; total?: number; message?: string; failed?: string[] }

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
  /** The meeting's title, as the person words it. */
  setTitle(dir: string, title: string): Promise<void>
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
  /** Whether Stommen has the meeting's sent protocol as justerat, kept with the protocol. Null while it is not. */
  stommenConfirmation(dir: string): Promise<Confirmation | null>
  /** A project of this computer's own, with its first mötesserie, so a meeting can be recorded at once. Returns its id. */
  projectAdd(name: string): Promise<string>
  projectRename(id: string, name: string): Promise<void>
  /** Refused for one of Stommen's. Its meetings' folders stay. */
  projectDelete(id: string): Promise<void>
  /** A person at the project's meetings, with their Roll if they have one. Refused in one of Stommen's. */
  personAdd(projectId: string, name: string, role: string): Promise<void>
  personRemove(projectId: string, personId: string): Promise<void>
  /** The meeting's protocol as a Word, PDF or Markdown file the person chooses where to keep; false when they cancelled. */
  protocolSave(dir: string, format: 'docx' | 'pdf' | 'md'): Promise<boolean>
  protocolCopy(dir: string): Promise<void>
  recordingStart(): Promise<string>
  recordingChunk(id: string, bytes: Uint8Array): Promise<void>
  recordingStop(id: string): Promise<string>
  recordingDiscard(id: string): Promise<void>
  settings(): Promise<Settings>
  /** Any of the settings but `setUp`. The name and Recognise Voices go on to the engine; opening at login to the system.
   * Of `shortcuts`, the ones named: an empty one goes back to the standard keys. Keys another command has, or that the
   * system does not give the app, are refused with a sentence for the person. */
  settingsSet(patch: Partial<Omit<Settings, 'setUp'>>): Promise<Settings>
  /** The first-run steps are done, or (`false`) are to be shown again. */
  setUp(done: boolean): Promise<Settings>
  models(): Promise<ModelRow[]>
  /** Resolves when the download has ended; `ids` empty means every model the app needs. Progress comes through `onModels`. */
  modelsDownload(ids: string[]): Promise<void>
  modelsCancel(): Promise<void>
  computer(): Promise<Computer>
  /** Where the meetings are kept now, and a way to show or change it. `folderChoose` resolves null when cancelled. */
  folderShow(): Promise<void>
  folderChoose(): Promise<string | null>
  /** A meeting is recorded in a small window of its own, which stays over other programs. One at a time. */
  recordOpen(spec: RecordSpec): Promise<void>
  /** From the recording window: where the recording stands, for the menu, the icon beside the clock and the main window. */
  recordStatus(status: RecordStatus): Promise<void>
  /** From the recording window: the recording is saved. The main window writes it out, and the recording window closes. */
  recordDone(job: Job): Promise<void>
  /** From the recording window: close it (the recording is thrown away, or never began). */
  recordClose(): Promise<void>
  /** Bring the recording window forward. */
  recordShow(): Promise<void>
  /** Inställningar, in a window of its own, on the tab named (general, recording, models, stommen, about). */
  settingsOpen(tab?: string): Promise<void>
  /** From the settings window: something the other windows show was changed, so they read it again. */
  changed(): Promise<void>
  /** From the settings window: the next keys pressed are a shortcut being chosen, so no menu and no recording takes them. */
  shortcutListen(on: boolean): Promise<void>
  /** From the settings window on the Mac: how tall its pane is, so the window is as tall. */
  settingsFit(height: number): Promise<void>
  /** What the window can do now, so the application menu greys out the rest. */
  menuState(state: MenuState): Promise<void>
  onProgress(listener: (p: Progress) => void): () => void
  onModels(listener: (e: ModelEvent) => void): () => void
  /** A choice in the application menu, or its shortcut. */
  onCommand(listener: (c: Command) => void): () => void
  /** In the main window: the recording in the other window, or null when there is none. */
  onRecording(listener: (s: RecordStatus | null) => void): () => void
  /** In the main and the recording window: the settings, the connection to Stommen or the projects were changed in another window. */
  onChanged(listener: () => void): () => void
  /** In the main window: a recording to write out. */
  onJob(listener: (job: Job) => void): () => void
  /** In the recording window: a choice in the menu, by the icon beside the clock, or a shortcut pressed in any program. */
  onRecordCommand(listener: (c: RecordCommand) => void): () => void
  /** The computer's kind (`process.platform`): the window keeps to its conventions. */
  platform: string
}

/** What a recording window is opened for. */
export type RecordSpec = { projectId: string; projectName: string; series: SeriesRef; agenda: boolean }
/** Where a recording stands. `seconds`: of recorded sound. `heading` and `next`: the agenda's, as "3. Tidplan". */
export type RecordStatus = { title: string; phase: 'idle' | 'recording' | 'paused' | 'saving'; seconds: number; heading: string | null; next: string | null }
/** What is done to a recording from outside its window. `cancel` asks first. */
export const RECORD_COMMANDS = ['pause', 'next', 'decision', 'todo', 'changeOrder', 'question', 'finish', 'cancel'] as const
export type RecordCommand = (typeof RECORD_COMMANDS)[number]

/** What the application menu asks the window to do. Each is also a shortcut (app/src/main/menu.ts). */
export const COMMANDS = ['settings', 'newProject', 'addRecording', 'sync', 'overview', 'points', 'agenda', 'record', 'sidebar', 'intro', 'palette',
  // about the protocol in the window
  'saveDocx', 'savePdf', 'saveMd', 'copyText', 'find', 'inspector', 'newPoint', 'nextCheck', 'rename', 'rewrite', 'send'] as const
export type Command = (typeof COMMANDS)[number]
/** `ready`: past the first run. `held`: a recording or a job is in the window. `sidebar`: it is shown. `meeting`: one is
 * open; `protocol`: it has one; `free`: that can be corrected; `sendable`: it can go to Stommen; `inspector`: the transcript is shown. */
export type MenuState = { ready: boolean; held: boolean; project: boolean; series: boolean; connected: boolean; sidebar: boolean
  meeting: boolean; protocol: boolean; free: boolean; sendable: boolean; inspector: boolean }

export const CHANNELS = ['projects', 'meetings', 'agenda', 'meeting', 'audio', 'startSeries', 'pickRecording', 'process',
  'writeProtocol', 'nameSpeaker', 'setTitle', 'changePoint', 'addPoint', 'removePoint', 'restorePoint', 'confirmCheck', 'attend', 'stommenState', 'stommenSignIn', 'stommenSync', 'stommenSignOut', 'stommenSend', 'stommenConfirmation', 'projectAdd', 'projectRename', 'projectDelete', 'personAdd', 'personRemove', 'protocolSave', 'protocolCopy', 'recordingStart', 'recordingChunk', 'recordingStop', 'recordingDiscard', 'settings', 'settingsSet', 'setUp', 'models', 'modelsDownload', 'modelsCancel', 'computer', 'folderShow', 'folderChoose', 'menuState', 'recordOpen', 'recordStatus', 'recordDone', 'recordClose', 'recordShow', 'settingsOpen', 'changed', 'shortcutListen', 'settingsFit'] as const
