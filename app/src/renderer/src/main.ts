import '@fontsource-variable/inter'
import '@fontsource-variable/josefin-sans'
import '@fontsource-variable/jetbrains-mono'
import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'
import RecordWindow from './views/RecordWindow.svelte'
import type { RecordSpec } from '../../shared/types'

// The Mac's measures or Windows' (Linux takes Windows'): app.css reads it.
document.documentElement.dataset.platform = window.api.platform === 'darwin' ? 'mac' : 'win'

// The small window a meeting is recorded in is this same page, opened with what to record (app/src/main/recording.ts).
const record = location.hash.startsWith('#record=') ? (JSON.parse(decodeURIComponent(location.hash.slice(8))) as RecordSpec) : null
const target = document.getElementById('app')!

export default record ? mount(RecordWindow, { target, props: { spec: record } }) : mount(App, { target })
