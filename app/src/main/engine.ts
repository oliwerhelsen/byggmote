// The engine is a command line program (engine/). The app starts it for each thing it wants and reads JSON back:
// one object from most commands, a line per event from `run`.
import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync, readdirSync } from 'node:fs'
import { basename, delimiter, join } from 'node:path'
import { app } from 'electron'

export class EngineError extends Error {}

/** The engine an installed app carries (scripts/bundle-engine.sh): its own Python, ffmpeg and llama-server. */
export const bundled = (): string => join(process.resourcesPath, 'engine')

/** The command and its first arguments: BYGGMOTE_ENGINE, else the installed app's Python, else the development checkout's engine. */
export function enginePath(): string[] {
  if (process.env.BYGGMOTE_ENGINE) return [process.env.BYGGMOTE_ENGINE]
  if (app.isPackaged) {
    const python = process.platform === 'win32' ? ['python', 'python.exe'] : ['python', 'bin', 'python3']
    return [join(bundled(), ...python), '-m', 'byggmote']
  }
  const bin = process.platform === 'win32' ? ['Scripts', 'byggmote.exe'] : ['bin', 'byggmote']
  return [join(app.getAppPath(), '..', 'engine', '.venv', ...bin)]
}

/** An installed app's engine finds ffmpeg, llama-server and the shipped models in the app, never on the person's path. */
export function engineEnv(): NodeJS.ProcessEnv {
  if (!app.isPackaged || process.env.BYGGMOTE_ENGINE) return process.env
  const root = bundled()
  const env: NodeJS.ProcessEnv = { ...process.env, PYTHONNOUSERSITE: '1', PYTHONDONTWRITEBYTECODE: '1' }
  const key = Object.keys(env).find((k) => k.toUpperCase() === 'PATH') ?? 'PATH'
  env[key] = [join(root, 'bin'), env[key]].filter(Boolean).join(delimiter)
  const server = process.platform === 'win32' ? 'llama-server.exe' : 'llama-server'
  const llama = join(root, 'bin', 'llama')
  if (existsSync(llama)) {
    const found = readdirSync(llama, { recursive: true, encoding: 'utf8' }).find((f) => basename(f) === server)
    if (found) env.BYGGMOTE_LLAMA_SERVER ??= join(llama, found)
  }
  if (existsSync(join(root, 'models'))) env.BYGGMOTE_MODELS ??= join(root, 'models')
  return env
}

// The engines at work. One that writes a protocol runs a language model for minutes: it does not outlive the app.
const running = new Set<ChildProcess>()

export function stopAll(): void {
  for (const child of running) {
    // On Windows the command is a launcher with Python under it, and stopping the launcher leaves Python running.
    if (process.platform === 'win32' && child.pid) spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true }).on('error', () => {})
    else child.kill()
  }
}

function start(args: string[], input?: unknown) {
  const [command, ...first] = enginePath()
  const child = spawn(command, [...first, ...args], { env: engineEnv(), windowsHide: true })
  running.add(child)
  child.on('close', () => running.delete(child)).on('error', () => running.delete(child))
  let err = ''
  child.stderr.setEncoding('utf8').on('data', (d: string) => (err = (err + d).slice(-4000)))
  child.stdin.on('error', () => {}) // the engine may be gone before it has read: `close` says why
  child.stdin.end(input === undefined ? '' : JSON.stringify(input))
  return { child, last: () => err.trim().split('\n').pop() || '' }
}

/** A command that prints one JSON value. The engine's own `{"error"}` is the message when it fails. */
export function call<T>(args: string[], input?: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    const { child, last } = start(args, input)
    let out = ''
    child.stdout.setEncoding('utf8').on('data', (d: string) => (out += d))
    child.on('error', (e) => reject(new EngineError(`the engine did not start: ${e.message}`)))
    child.on('close', (code) => {
      let value: unknown
      try {
        value = out.trim() ? JSON.parse(out) : null
      } catch {
        return reject(new EngineError(last() || `the engine answered something that is not JSON (exit ${code})`))
      }
      const said = (value as { error?: unknown } | null)?.error
      if (code === 0) resolve(value as T)
      else reject(new EngineError(typeof said === 'string' ? said : last() || `the engine stopped (exit ${code})`))
    })
  })
}

export type RunEvent = { event: string; step?: string; status?: string; fraction?: number; dir?: string; message?: string }

/** `byggmote run`: every event to `on`, and the folder of the meeting once it is done. */
export function run(args: string[], on: (e: RunEvent) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const { child, last } = start(['run', ...args])
    let rest = '', dir = '', failed = ''
    child.stdout.setEncoding('utf8').on('data', (d: string) => {
      const lines = (rest + d).split('\n')
      rest = lines.pop() ?? ''
      for (const line of lines) {
        let e: RunEvent
        try {
          e = JSON.parse(line)
        } catch {
          continue
        }
        if (e.event === 'done' && e.dir) dir = e.dir
        if (e.event === 'error') failed = [e.step, e.message].filter(Boolean).join(': ')
        on(e)
      }
    })
    child.on('error', (e) => reject(new EngineError(`the engine did not start: ${e.message}`)))
    child.on('close', (code) => {
      if (code === 0 && dir) resolve(dir)
      else reject(new EngineError(failed || last() || `the engine stopped (exit ${code})`))
    })
  })
}

/** A command that prints a JSON event a line, with a way to stop it: `byggmote models download`. Resolves with its exit code. */
export function stream(args: string[], on: (e: Record<string, unknown>) => void): { done: Promise<number>; stop: () => void } {
  const { child } = start(args)
  const done = new Promise<number>((resolve, reject) => {
    let rest = ''
    child.stdout.setEncoding('utf8').on('data', (d: string) => {
      const lines = (rest + d).split('\n')
      rest = lines.pop() ?? ''
      for (const line of lines) {
        try {
          on(JSON.parse(line))
        } catch {
          // a line that is not an event is not for the window
        }
      }
    })
    child.on('error', (e) => reject(new EngineError(`the engine did not start: ${e.message}`)))
    child.on('close', (code) => resolve(code ?? 1))
  })
  return { done, stop: () => child.kill() }
}
