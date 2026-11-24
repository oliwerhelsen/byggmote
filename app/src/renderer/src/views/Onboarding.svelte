<script lang="ts">
  // The first run: who is using the app, the microphone, the models, and Stommen if the person has it. Every step but
  // the name can be left for later, and the models download while the person goes on. It is shown until it is done,
  // and from the settings it can be shown again.
  import type { Settings, StommenState } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import Microphone from '../lib/Microphone.svelte'
  import Models from '../lib/Models.svelte'
  import { failure } from '../lib/format'
  import Stommen from './Stommen.svelte'

  let { settings, stommen, changed, stommenChanged, refresh, done }: {
    settings: Settings
    stommen: StommenState | null
    changed: (s: Settings) => void
    stommenChanged: (s: StommenState) => void
    refresh: () => Promise<void>
    done: () => void
  } = $props()

  const STEPS = ['Välkommen', 'Mikrofon', 'Modeller', 'Stommen', 'Klart'] as const

  let step = $state(0)
  // svelte-ignore state_referenced_locally
  let name = $state(settings.name)
  let problem = $state('')
  let busy = $state(false)
  let missing = $state(-1)

  async function begin(e: SubmitEvent): Promise<void> {
    e.preventDefault()
    busy = true
    problem = ''
    try {
      changed(await window.api.settingsSet({ name }))
      step = 1
    } catch (x) {
      problem = failure(x)
    } finally {
      busy = false
    }
  }

  async function finish(): Promise<void> {
    busy = true
    try {
      changed(await window.api.setUp(true))
      done()
    } catch (x) {
      problem = failure(x)
      busy = false
    }
  }

  const next = (): void => {
    step += 1
  }
</script>

<div class="first">
  <div class="sheet">
    <div class="brand"><Icon name="wave" size={22} /><span><b>B</b>YGGMÖTE</span></div>

    <ol class="steps" aria-label="Steg">
      {#each STEPS as s, i (s)}
        <li aria-current={i === step ? 'step' : undefined} class:past={i < step}>
          <span class="n">{i < step ? '✓' : i + 1}</span><span class="t">{s}</span>
        </li>
      {/each}
    </ol>

    {#if problem}
      <div class="note bad" role="alert"><Icon name="alert" /><p>{problem}</p></div>
    {/if}

    {#if step === 0}
      <form class="stack" onsubmit={begin} aria-labelledby="h0">
        <h1 id="h0">Välkommen till Byggmöte</h1>
        <p class="muted">Byggmöte spelar in byggmötet, skriver ut det och föreslår protokollet. Allt sker på den här datorn: ljud och utskrift lämnar den inte.</p>
        <div>
          <label class="label" for="name">Ditt namn</label>
          <input id="name" class="field" style="width: 100%" autocomplete="name" required bind:value={name} />
          <p class="small muted" style="margin-top: 4px">Du är med på alla möten. Namnet står i protokollet.</p>
        </div>
        <div class="row">
          <button class="btn primary" type="submit" disabled={busy || !name.trim()}>Fortsätt</button>
        </div>
      </form>
    {:else if step === 1}
      <div class="stack" aria-labelledby="h1">
        <h1 id="h1">Mikrofon</h1>
        <p class="muted">Tillåt mikrofonen nu, så frågar datorn inte mitt i ett möte. Du kan också göra det vid första inspelningen.</p>
        <Microphone value={settings.microphone} choose={async (microphone) => changed(await window.api.settingsSet({ microphone }))} />
        <div class="row">
          <button class="btn primary" onclick={next}>Fortsätt</button>
        </div>
      </div>
    {:else if step === 2}
      <div class="stack" aria-labelledby="h2">
        <h1 id="h2">Taligenkänning och protokoll</h1>
        <p class="muted">Byggmöte hämtar modellerna en gång, sedan fungerar det utan internet. Du kan gå vidare medan de hämtas.</p>
        <Models changed={(n) => (missing = n)} />
        <div class="row">
          <button class="btn primary" onclick={next}>{missing === 0 ? 'Fortsätt' : 'Fortsätt, hämta senare'}</button>
        </div>
      </div>
    {:else if step === 3}
      <div class="stack">
        {#if stommen}
          <Stommen {stommen} changed={stommenChanged} {refresh} />
        {/if}
        <div class="row">
          <button class="btn primary" onclick={next}>{stommen?.connected ? 'Fortsätt' : 'Hoppa över'}</button>
        </div>
      </div>
    {:else}
      <div class="stack" aria-labelledby="h4">
        <h1 id="h4">Klart{settings.name ? `, ${settings.name.split(' ')[0]}` : ''}</h1>
        <ul class="sum">
          <li><Icon name="check" size={16} /> Du är med på alla möten</li>
          <li><Icon name={missing === 0 ? 'check' : 'clock'} size={16} /> {missing === 0 ? 'Modellerna finns på datorn' : 'Modellerna hämtas, du kan börja ändå'}</li>
          <li><Icon name={stommen?.connected ? 'check' : 'link'} size={16} /> {stommen?.connected ? `Kopplad till Stommen som ${stommen.user}` : 'Stommen kopplar du när du vill, under Inställningar'}</li>
        </ul>
        <p class="small muted">Allt här går att ändra under Inställningar.</p>
        <div class="row">
          <button class="btn primary" disabled={busy} onclick={finish}>Börja använda Byggmöte</button>
        </div>
      </div>
    {/if}

    {#if step > 0}
      <div class="row"><button class="btn quiet" onclick={() => (step -= 1)}><Icon name="back" size={16} /> Tillbaka</button></div>
    {/if}
  </div>
</div>

<style>
  .first { min-height: 100%; display: flex; justify-content: center; align-items: flex-start; padding: 40px 16px; background: var(--canvas); overflow: auto; height: 100%; }
  .sheet { width: 100%; max-width: 640px; display: flex; flex-direction: column; gap: 24px; }
  .brand { display: flex; align-items: center; gap: 10px; color: var(--coral-500); }
  .brand span { font: 300 17px var(--font-display); letter-spacing: 0.24em; color: var(--coral-700); padding-top: 3px; }
  .brand b { font-weight: 600; }
  .steps { display: flex; gap: 8px; flex-wrap: wrap; }
  .steps li { display: flex; align-items: center; gap: 8px; color: var(--ink-500); font-size: 13px; }
  .steps li[aria-current='step'] { color: var(--ink-900); font-weight: 600; }
  .n { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: var(--radius-pill); background: var(--sunken); font-size: 12px; }
  li[aria-current='step'] .n { background: var(--coral-700); color: #fff; }
  .past .n { background: var(--ok-bg); color: var(--ok); }
  .sum { display: flex; flex-direction: column; gap: 8px; }
  .sum li { display: flex; align-items: center; gap: 10px; }
  .sum :global(svg) { color: var(--ok); }
  .sheet :global(.page) { padding: 0; }
  @media (max-width: 520px) { .steps .t { display: none; } .steps li[aria-current='step'] .t { display: inline; } }
</style>
