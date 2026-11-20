import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'electron-vite'

export default defineConfig({
  main: {},
  preload: {},
  // No file is inlined as a data: address: the window's content policy allows fonts and images from the app only.
  renderer: { plugins: [svelte()], build: { assetsInlineLimit: 0 } }
})
