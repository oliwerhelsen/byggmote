<script lang="ts">
  // The models the engine needs, what is on this computer and a way to fetch the rest. One list for the first run and
  // for the settings. A download goes on while the person does something else: the window is free to leave.
  import type { ModelEvent, ModelRow } from '../../../shared/types'
  import Icon from './Icon.svelte'
  import { failure } from './format'

  let { changed = () => {} }: { changed?: (missing: number) => void } = $props()

  let rows = $state<ModelRow[]>([])
  let loaded = $state(false)
  let busy = $state(false)
  let problem = $state('')
  /** How far each model has come, from 0 to 1, by the repository the engine names. */
  let fraction = $state<Record<string, number>>({})
  let current = $state('')

  // One language model is enough: the engine lists the other builds for other computers too, and the first is this one's.
  const shown = $derived(rows.filter((m) => m.type !== 'llm' || m.id === rows.find((x) => x.type === 'llm')?.id))
  const missing = $derived(shown.filter((m) => !m.downloaded))

  // Bytes on this computer plus what the running download has fetched, over all bytes: one bar for the whole set.
  const overall = $derived.by(() => {
    const total = shown.reduce((n, m) => n + m.size, 0)
    if (!total) return 0
    const have = shown.reduce((n, m) => n + m.size * (m.downloaded ? 1 : Math.min(fraction[m.model] ?? 0, 1)), 0)
    return have / total
  })

  const bytes = (n: number): string => (n >= 1e9 ? `${(n / 1e9).toFixed(1).replace('.', ',')} GB` : `${Math.round(n / 1e6)} MB`)

  async function load(): Promise<void> {
    try {
      rows = await window.api.models()
    } catch (e) {
      problem = failure(e)
    } finally {
      loaded = true
    }
  }
  void load()

  $effect(() => changed(loaded ? missing.length : -1))

  $effect(() => {
    return window.api.onModels((e: ModelEvent) => {
      if (e.event === 'download' && e.model && e.total) {
        current = e.model
        fraction[e.model] = e.done! / e.total
      } else if (e.event === 'error') {
        problem = e.message ?? 'Hämtningen misslyckades.'
      }
    })
  })

  async function fetchModels(ids: string[]): Promise<void> {
    busy = true
    problem = ''
    fraction = {}
    try {
      await window.api.modelsDownload(ids)
    } catch (e) {
      problem = failure(e)
    } finally {
      busy = false
      current = ''
      await load()
    }
  }

  const stop = (): Promise<void> => window.api.modelsCancel()
</script>

{#if !loaded}
  <p class="muted">Läser in.</p>
{:else}
  {#if problem}
    <div class="note bad" role="alert"><Icon name="alert" /><p>{problem}</p></div>
  {/if}
  <div class="models">
    <p><strong>{shown.length - missing.length} av {shown.length}</strong> modeller installerade</p>
    <progress max="1" value={overall} aria-label="Installerade modeller"></progress>
  </div>
  <div class="row" style="margin-top: 16px">
    {#if busy}
      <button class="btn" onclick={stop}>Avbryt installationen</button>
      <p role="status" class="small muted">{current ? 'Installerar' : 'Förbereder'}. Du kan fortsätta under tiden.</p>
    {:else if missing.length}
      <button class="btn primary" onclick={() => fetchModels(missing.map((m) => m.id))}>
        Installera det som saknas ({bytes(missing.reduce((n, m) => n + m.size, 0))})
      </button>
    {:else}
      <p class="small muted">Allt är installerat. Byggmöte fungerar utan internet.</p>
    {/if}
  </div>
{/if}

<style>
  .models { padding: 12px 0; }
  progress { width: 100%; height: 8px; margin-top: 8px; accent-color: var(--coral-700); }
</style>
