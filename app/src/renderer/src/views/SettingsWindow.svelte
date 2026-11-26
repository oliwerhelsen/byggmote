<script lang="ts">
  // Inställningar in a window of its own (app/src/main/index.ts opens it). What is changed here is kept by the main
  // process, and the main window is told to read it again.
  import type { Settings as Kept, StommenState } from '../../../shared/types'
  import Settings from './Settings.svelte'

  let { first }: { first: string } = $props()

  let settings = $state<Kept | null>(null)
  let stommen = $state<StommenState | null>(null)
  let folder = $state('')

  const where = (): Promise<void> => window.api.projects().then((p) => { folder = p.folder }).catch(() => {})
  void window.api.settings().then((s) => (settings = s))
  void window.api.stommenState().then((s) => (stommen = s)).catch(() => {})
  void where()
  document.title = 'Inställningar'

  const told = (): Promise<void> => window.api.changed()
</script>

{#if settings}
  <Settings {settings} {stommen} {folder} {first}
    changed={(s) => { settings = s; void told() }}
    moved={async () => { await where(); await told() }}
    connection={(s) => { stommen = s; void told() }}
    fetched={told}
    intro={async () => { await window.api.setUp(false); await told(); window.close() }} />
{/if}
