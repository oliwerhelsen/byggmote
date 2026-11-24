// The only way from the window to the computer: the calls of `Api`, each one a message to the main process.
import { contextBridge, ipcRenderer } from 'electron'
import type { Api, ModelEvent, Progress } from '../shared/types'
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
  }
} as unknown as Api

contextBridge.exposeInMainWorld('api', api)
