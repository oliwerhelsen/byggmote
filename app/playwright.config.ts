import { defineConfig } from '@playwright/test'

// One app, one window, the tests in order: they share the window as a person would.
// The first assertion of a file runs right after a cold Electron launch, which on a Windows runner takes more than the
// default 5s to render its first view; 15s covers that without slowing a passing run.
export default defineConfig({ testDir: 'tests', workers: 1, timeout: 60_000, expect: { timeout: 15_000 }, reporter: 'list' })
