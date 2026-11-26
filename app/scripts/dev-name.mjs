// In dev the app runs inside Electron's own bundle, so the Mac's menu bar says Electron. This names that bundle
// Byggmöte, in node_modules only; the installed app gets its name from electron-builder.yml.
import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'

const plist = 'node_modules/electron/dist/Electron.app/Contents/Info.plist'
if (process.platform === 'darwin' && existsSync(plist)) {
  for (const key of ['CFBundleName', 'CFBundleDisplayName']) {
    execFileSync('/usr/libexec/PlistBuddy', ['-c', `Set :${key} Byggmöte`, plist])
  }
}
