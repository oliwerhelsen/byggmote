// What the engine's read commands give (engine/src/byggmote/overview.py, series.py, protocol.py) and what the
// window may ask the main process for. One file, so the two sides cannot drift apart.

export type Person = { id: string; name: string; role?: string }
export type SeriesRef = { id: string; name: string; next: number }
export type Project = { id: string; name: string; people: Person[]; series: SeriesRef[] }

export type Kind = 'decision' | 'todo' | 'changeOrder' | 'deviation' | 'question' | 'risk' | 'note'
export type Check = { code: 'amount'; value: string; said: string } | { code: 'role'; said: string }
export type Heading = { no: number; name: string; hint?: string; fill?: string }

/** A point of a protocol. One an earlier meeting left open has `since`, and `raised` says whether this meeting took it up. */
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
  attendees: { name: string; role?: string }[]
  points: Point[]
  dropped: Dropped[]
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
}

export type OpenPoint = { no: string; heading: number; kind: Kind; text: string; role: string | null; due: string | null }
export type Agenda = { series: string; name: string; no: number; headings: (Heading & { open: OpenPoint[] })[] }

/** What was pressed while recording, in seconds of recorded sound. */
export type Marks = { headings: { no: number; at: number }[]; marks: { kind: Kind; at: number }[] }

export type Job = { projectId: string; seriesId: string; file: string; title: string; marks?: Marks }
export type Done = { dir: string; protocolError: string | null }

/** Where a job is: the engine's own step names while it transcribes, then `protocol`. */
export type Progress = { step: string; state: 'start' | 'progress' | 'done'; fraction?: number }

export interface Api {
  projects(): Promise<{ folder: string; projects: Project[] }>
  meetings(projectId: string): Promise<MeetingRow[]>
  agenda(projectId: string, seriesId: string): Promise<Agenda>
  meeting(dir: string): Promise<MeetingDetail>
  audio(dir: string): Promise<Uint8Array | null>
  startSeries(projectId: string, name: string): Promise<SeriesRef>
  pickRecording(): Promise<string | null>
  process(job: Job): Promise<Done>
  writeProtocol(dir: string, seriesId: string): Promise<void>
  nameSpeaker(dir: string, speaker: string, personId: string): Promise<void>
  recordingStart(): Promise<string>
  recordingChunk(id: string, bytes: Uint8Array): Promise<void>
  recordingStop(id: string): Promise<string>
  recordingDiscard(id: string): Promise<void>
  onProgress(listener: (p: Progress) => void): () => void
}

export const CHANNELS = ['projects', 'meetings', 'agenda', 'meeting', 'audio', 'startSeries', 'pickRecording', 'process',
  'writeProtocol', 'nameSpeaker', 'recordingStart', 'recordingChunk', 'recordingStop', 'recordingDiscard'] as const
