import type { Job, SeriesRef } from '../../../shared/types'

/** Where the window is. A meeting is recorded in a window of its own (views/RecordWindow.svelte), not in a view here. */
export type View =
  | { name: 'points' }
  | { name: 'agenda'; series: SeriesRef }
  | { name: 'working'; job: Job }
  | { name: 'protocol'; dir: string; problem?: string }
  | { name: 'overview' }

export type Go = (to: View) => void

/** What the toolbar says of the meeting in the window: its title, whether a person has corrected its protocol, and
 * whether that is a draft or justerat (nothing without a protocol). */
export type About = { title: string; edited: boolean; standing: '' | 'draft' | 'done' }
