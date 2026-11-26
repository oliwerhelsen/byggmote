// What the person sets in the app itself. It lives in the app's own folder, apart from the meetings' knowledge base, so
// moving that folder does not move these.
import { readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { app } from 'electron'
import { VALID } from '../shared/keys'
import type { Settings } from '../shared/types'

// The tests have no first run to click through: BYGGMOTE_SETUP=1 starts them set up.
const fresh = (): Settings => ({ setUp: process.env['BYGGMOTE_SETUP'] === '1', name: '', voices: true, openAtLogin: false, microphone: '', shortcuts: {} })
const file = (): string => join(app.getPath('userData'), 'settings.json')

export async function read(): Promise<Settings> {
  try {
    const got = JSON.parse(await readFile(file(), 'utf8')) as Partial<Settings>
    const d = fresh()
    return {
      setUp: typeof got.setUp === 'boolean' ? got.setUp : d.setUp,
      name: typeof got.name === 'string' ? got.name : d.name,
      voices: typeof got.voices === 'boolean' ? got.voices : d.voices,
      openAtLogin: typeof got.openAtLogin === 'boolean' ? got.openAtLogin : d.openAtLogin,
      microphone: typeof got.microphone === 'string' ? got.microphone : d.microphone,
      shortcuts: Object.fromEntries((['pause', 'next', 'mark'] as const).flatMap((k) => (VALID.test(String(got.shortcuts?.[k] ?? '')) ? [[k, got.shortcuts![k]]] : [])))
    }
  } catch {
    return fresh() // none yet, or one that cannot be read: start over rather than stop
  }
}

export async function write(s: Settings): Promise<Settings> {
  await writeFile(file(), JSON.stringify(s, null, 1) + '\n', 'utf8')
  return s
}
