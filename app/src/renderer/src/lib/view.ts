import type { Job, SeriesRef } from '../../../shared/types'

/** Where the window is. A recording and a job in progress are views of their own, so nothing else can be opened over them. */
export type View =
  | { name: 'points' }
  | { name: 'agenda'; series: SeriesRef }
  | { name: 'recording'; series: SeriesRef; agenda: boolean }
  | { name: 'working'; job: Job }
  | { name: 'protocol'; dir: string; problem?: string }
  | { name: 'overview' }
  | { name: 'stommen' }
  | { name: 'settings' }

export type Go = (to: View) => void
