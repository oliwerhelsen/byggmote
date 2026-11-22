// The engine is a command line program (engine/). The app starts it for each thing it wants and reads JSON back:
// one object from most commands, a line per event from `run`.
import { spawn, type ChildProcess } from 'node:child_process'
import { join } from 'node:path'
import { app } from 'electron'

export class EngineError extends Error {}

/** BYGGMOTE_ENGINE, else the development checkout's engine next to the app. */
export function enginePath(): string {
  if (process.env.BYGGMOTE_ENGINE) return process.env.BYGGMOTE_ENGINE
  const bin = process.platform === 'win32' ? ['Scripts', 'byggmote.exe'] : ['bin', 'byggmote']
  return join(app.getAppPath(), '..', 'engine', '.venv', ...bin)
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
  const child = spawn(enginePath(), args, { env: process.env, windowsHide: true })
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
