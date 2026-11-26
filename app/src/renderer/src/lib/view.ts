import type { Job, SeriesRef } from '../../../shared/types'

/** Where the window is. A meeting is recorded in a window of its own (views/RecordWindow.svelte), not in a view here. */
export type View =
  | { name: 'points' }
  | { name: 'agenda'; series: SeriesRef }
  | { name: 'working'; job: Job }
  | { name: 'protocol'; dir: string; problem?: string }
  | { name: 'overview' }
  | { name: 'stommen' }
  | { name: 'settings' }

export type Go = (to: View) => void
