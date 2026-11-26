import '@fontsource-variable/inter'
import '@fontsource-variable/josefin-sans'
import '@fontsource-variable/jetbrains-mono'
import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'

// The Mac's measures or Windows' (Linux takes Windows'): app.css reads it.
document.documentElement.dataset.platform = window.api.platform === 'darwin' ? 'mac' : 'win'

export default mount(App, { target: document.getElementById('app')! })
