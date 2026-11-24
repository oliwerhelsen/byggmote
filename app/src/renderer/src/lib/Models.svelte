<script lang="ts">
  // The models the engine needs, what is on this computer and a way to fetch the rest. One list for the first run and
  // for the settings. A download goes on while the person does something else: the window is free to leave.
  import type { ModelEvent, ModelRow } from '../../../shared/types'
  import Icon from './Icon.svelte'
  import { failure } from './format'

  let { changed = () => {} }: { changed?: (missing: number) => void } = $props()

  const KINDS: Record<ModelRow['type'], string> = { asr: 'Tal till text', diarize: 'Vem som talar', llm: 'Skriver protokollet' }

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
  <p class="muted">Läser in modellerna.</p>
{:else}
  {#if problem}
    <div class="note bad" role="alert"><Icon name="alert" /><p>{problem}</p></div>
  {/if}
  <ul class="models" aria-label="Modeller">
    {#each shown as m (m.id)}
      {@const f = fraction[m.model]}
      <li>
        <div class="grow">
          <p><strong>{m.name}</strong> <span class="muted small">{KINDS[m.type]}{m.langs.length ? `, ${m.langs.join(' och ')}` : ''}</span></p>
          <p class="small muted">{bytes(m.size)}. {m.license}.</p>
          {#if busy && f !== undefined && f < 1}
            <progress max="1" value={f} aria-label="Hämtar {m.name}"></progress>
          {/if}
        </div>
        {#if m.downloaded}
          <span class="badge ok"><Icon name="check" size={14} /> På den här datorn</span>
        {:else if busy}
          <span class="badge">Väntar</span>
        {:else}
          <button class="btn" onclick={() => fetchModels([m.id])}>Hämta</button>
        {/if}
      </li>
    {/each}
  </ul>
  <div class="row" style="margin-top: 16px">
    {#if busy}
      <button class="btn" onclick={stop}>Avbryt hämtningen</button>
      <p role="status" class="small muted">{current ? 'Hämtar' : 'Förbereder'}. Du kan fortsätta under tiden.</p>
    {:else if missing.length}
      <button class="btn primary" onclick={() => fetchModels(missing.map((m) => m.id))}>
        Hämta det som saknas ({bytes(missing.reduce((n, m) => n + m.size, 0))})
      </button>
    {:else}
      <p class="small muted">Allt finns på den här datorn. Byggmöte fungerar utan internet.</p>
    {/if}
  </div>
{/if}

<style>
  .models { display: flex; flex-direction: column; }
  .models li { display: flex; align-items: center; gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--line); }
  .models li:last-child { border-bottom: 0; }
  progress { width: 100%; height: 6px; margin-top: 6px; accent-color: var(--coral-700); }
</style>
