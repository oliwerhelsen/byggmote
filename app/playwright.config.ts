import { defineConfig } from '@playwright/test'

// One app, one window, the tests in order: they share the window as a person would.
export default defineConfig({ testDir: 'tests', workers: 1, timeout: 60_000, reporter: 'list' })
