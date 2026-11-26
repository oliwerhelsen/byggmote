// The only way from the window to the computer: the calls of `Api`, each one a message to the main process.
import { contextBridge, ipcRenderer } from 'electron'
import type { Api, Command, Job, ModelEvent, Progress, RecordCommand, RecordStatus } from '../shared/types'
import { CHANNELS } from '../shared/types'

const calls = Object.fromEntries(CHANNELS.map((name) => [name, (...args: unknown[]) => ipcRenderer.invoke(name, ...args)]))

const api = {
  ...calls,
  onProgress(listener: (p: Progress) => void) {
    const heard = (_e: unknown, p: Progress): void => listener(p)
    ipcRenderer.on('progress', heard)
    return () => ipcRenderer.removeListener('progress', heard)
  },
  onModels(listener: (e: ModelEvent) => void) {
    const heard = (_e: unknown, m: ModelEvent): void => listener(m)
    ipcRenderer.on('models', heard)
    return () => ipcRenderer.removeListener('models', heard)
  },
  onCommand(listener: (c: Command) => void) {
    const heard = (_e: unknown, c: Command): void => listener(c)
    ipcRenderer.on('command', heard)
    return () => ipcRenderer.removeListener('command', heard)
  },
  onRecording(listener: (s: RecordStatus | null) => void) {
    const heard = (_e: unknown, s: RecordStatus | null): void => listener(s)
    ipcRenderer.on('recording', heard)
    return () => ipcRenderer.removeListener('recording', heard)
  },
  onJob(listener: (job: Job) => void) {
    const heard = (_e: unknown, job: Job): void => listener(job)
    ipcRenderer.on('job', heard)
    return () => ipcRenderer.removeListener('job', heard)
  },
  onRecordCommand(listener: (c: RecordCommand) => void) {
    const heard = (_e: unknown, c: RecordCommand): void => listener(c)
    ipcRenderer.on('recordCommand', heard)
    return () => ipcRenderer.removeListener('recordCommand', heard)
  },
  // BYGGMOTE_PLATFORM: a Mac shows the window as Windows draws it, for a look at the other one.
  platform: process.env['BYGGMOTE_PLATFORM'] || process.platform
} as unknown as Api

contextBridge.exposeInMainWorld('api', api)
