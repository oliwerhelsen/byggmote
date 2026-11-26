<script lang="ts">
  // Inställningar in a window of its own (app/src/main/index.ts opens it). What is changed here is kept by the main
  // process, and the other windows are told to read it again. On the Mac the window is named after its pane and is
  // as tall as the pane; on Windows it is Inställningar, with the page's name as its heading.
  import type { Settings as Kept, StommenState } from '../../../shared/types'
  import '../settings.css'
  import Settings from './Settings.svelte'

  let { first, version }: { first: string; version: string } = $props()

  const mac = window.api.platform === 'darwin'
  let settings = $state<Kept | null>(null)
  let stommen = $state<StommenState | null>(null)
  let folder = $state('')
  let root = $state<HTMLElement>()

  const where = (): Promise<void> => window.api.projects().then((p) => { folder = p.folder }).catch(() => {})
  void window.api.settings().then((s) => (settings = s))
  void window.api.stommenState().then((s) => (stommen = s)).catch(() => {})
  void where()
  document.title = 'Inställningar'

  const told = (): Promise<void> => window.api.changed()

  $effect(() => {
    if (!mac || !root) return
    const seen = new ResizeObserver(() => void window.api.settingsFit(Math.ceil(root!.getBoundingClientRect().height)))
    seen.observe(root)
    return () => seen.disconnect()
  })
</script>

<div class="prefs" class:mac class:win={!mac} bind:this={root}>
  {#if settings}
    <Settings {settings} {stommen} {folder} {first} {version}
      shown={(name) => { if (mac) document.title = name }}
      changed={(s) => { settings = s; void told() }}
      moved={async () => { await where(); await told() }}
      connection={(s) => { stommen = s; void told() }}
      fetched={told}
      intro={async () => { await window.api.setUp(false); await told(); window.close() }} />
  {/if}
</div>
