<script lang="ts">
  // The app's own settings, in tabs like a settings window: who is using it, where meetings are kept, what records,
  // the models and what the app is made of. Each change is kept as it is made; there is no Save.
  import type { ModelRow, Settings, StommenState } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import Microphone from '../lib/Microphone.svelte'
  import Models from '../lib/Models.svelte'
  import { failure } from '../lib/format'
  import type { Go } from '../lib/view'

  let { settings, stommen, folder, changed, intro, go, moved }: {
    settings: Settings
    stommen: StommenState | null
    folder: string
    changed: (s: Settings) => void
    intro: () => void
    go: Go
    moved: () => Promise<void>
  } = $props()

  const TABS = [
    { id: 'general', name: 'Allmänt' },
    { id: 'recording', name: 'Inspelning' },
    { id: 'models', name: 'Modeller' },
    { id: 'about', name: 'Om Byggmöte' }
  ] as const
  type Tab = (typeof TABS)[number]['id']

  let tab = $state<Tab>('general')
  // svelte-ignore state_referenced_locally
  let name = $state(settings.name)
  let problem = $state('')
  let saved = $state(false)
  let where = $state('')
  let licences = $state<ModelRow[]>([])

  async function set(patch: Partial<Omit<Settings, 'setUp'>>): Promise<void> {
    problem = ''
    try {
      changed(await window.api.settingsSet(patch))
      saved = true
      setTimeout(() => (saved = false), 2000)
    } catch (e) {
      problem = failure(e)
    }
  }

  async function chooseFolder(): Promise<void> {
    problem = ''
    try {
      const to = await window.api.folderChoose()
      if (to) {
        where = to
        await moved()
      }
    } catch (e) {
      problem = failure(e)
    }
  }

  $effect(() => {
    if (tab === 'about' && !licences.length) void window.api.models().then((m) => (licences = m)).catch(() => {})
  })

  const keys = (e: KeyboardEvent): void => {
    const i = TABS.findIndex((t) => t.id === tab)
    const next = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? i - 1 : i
    if (next === i) return
    e.preventDefault()
    tab = TABS[(next + TABS.length) % TABS.length].id
    document.getElementById(`tab-${tab}`)?.focus()
  }
</script>

<div class="page">
  <div class="page-head">
    <div>
      <h1>Inställningar</h1>
      <p class="muted">Det som gäller för Byggmöte på den här datorn.</p>
    </div>
    <p class="small muted" role="status">{saved ? 'Sparat.' : ''}</p>
  </div>

  <div class="settings">
    <div class="tabs" role="tablist" aria-label="Inställningar" aria-orientation="vertical" tabindex="-1" onkeydown={keys}>
      {#each TABS as t (t.id)}
        <button id="tab-{t.id}" class="tab" role="tab" aria-selected={tab === t.id} aria-controls="panel" tabindex={tab === t.id ? 0 : -1}
          onclick={() => (tab = t.id)}>{t.name}</button>
      {/each}
    </div>

    <div id="panel" class="panel stack" role="tabpanel" aria-labelledby="tab-{tab}">
      {#if problem}
        <div class="note bad" role="alert"><Icon name="alert" /><p>{problem}</p></div>
      {/if}

      {#if tab === 'general'}
        <section class="card">
          <h2>Du</h2>
          <form class="line" onsubmit={(e) => { e.preventDefault(); void set({ name }) }}>
            <div class="grow">
              <label class="label" for="me">Ditt namn</label>
              <input id="me" class="field" style="width: 100%" autocomplete="name" bind:value={name} />
              <p class="small muted" style="margin-top: 4px">Du är med på alla möten. Namnet står i protokollet och används för att känna igen din röst.</p>
            </div>
            <button class="btn" type="submit" disabled={!name.trim() || name.trim() === settings.name}>Spara namn</button>
          </form>
        </section>

        <section class="card">
          <h2>Där Byggmöte sparar möten</h2>
          <p class="mono" style="overflow-wrap: anywhere">{where || folder}</p>
          <p class="small muted" style="margin: 4px 0 12px">Ljud och utskrift, en mapp per möte. Byggmöte flyttar det som finns om du väljer en annan mapp.</p>
          <div class="row">
            <button class="btn" onclick={() => window.api.folderShow()}>Visa i mappen</button>
            <button class="btn" onclick={chooseFolder}>Välj mapp…</button>
          </div>
        </section>

        <section class="card">
          <h2>Stommen</h2>
          <p>{stommen?.connected ? `Kopplad som ${stommen.user}.` : 'Inte kopplad. Projekt och personer ligger på den här datorn.'}</p>
          <div class="row" style="margin-top: 12px">
            <button class="btn" onclick={() => go({ name: 'stommen' })}><Icon name="link" /> {stommen?.connected ? 'Hantera kopplingen' : 'Koppla till Stommen'}</button>
          </div>
        </section>

        <section class="card">
          <h2>Introduktionen</h2>
          <p class="muted" style="margin-bottom: 12px">Gå igenom stegen från första start igen: namn, mikrofon, modeller och Stommen. Inget du har sparat tas bort.</p>
          <button class="btn" onclick={intro}>Visa introduktionen</button>
        </section>
      {:else if tab === 'recording'}
        <section class="card">
          <h2>Mikrofon</h2>
          <Microphone value={settings.microphone} choose={(microphone) => set({ microphone })} />
          <p class="small muted" style="margin-top: 8px">Är den inte inkopplad används datorns egen. Datorns ljud spelas inte in.</p>
        </section>
        <section class="card">
          <h2>Röster</h2>
          <label class="tick">
            <input type="checkbox" checked={settings.voices} onchange={(e) => set({ voices: e.currentTarget.checked })} />
            <span>Känn igen röster</span>
          </label>
          <p class="small muted">Byggmöte kommer ihåg hur namngivna personer låter, så nästa möte vet vem som talar. Rösterna stannar på den här datorn. Avstängt sparas inga nya röster och ingen känns igen.</p>
        </section>
        <section class="card">
          <h2>Start</h2>
          <label class="tick">
            <input type="checkbox" checked={settings.openAtLogin} onchange={(e) => set({ openAtLogin: e.currentTarget.checked })} />
            <span>Öppna Byggmöte när jag loggar in</span>
          </label>
        </section>
      {:else if tab === 'models'}
        <section class="card">
          <h2>Taligenkänning och protokoll</h2>
          <p class="muted" style="margin-bottom: 12px">Modellerna körs på den här datorn. De hämtas en gång, sedan fungerar Byggmöte utan internet.</p>
          <Models />
        </section>
      {:else}
        <section class="card">
          <h2>Byggmöte</h2>
          <p>Spelar in byggmöten, skriver utskriften och protokollet på den här datorn, och skickar det du godkänner vidare till Stommen.</p>
        </section>
        <section class="card">
          <h2>Modeller</h2>
          {#if licences.length}
            <ul class="credits">
              {#each licences as m (m.id)}
                <li><span>{m.name}</span><span class="muted">{m.license}</span></li>
              {/each}
            </ul>
          {:else}
            <p class="muted">Läser in.</p>
          {/if}
          <p class="small muted" style="margin-top: 12px">Villkoren i sin helhet finns i NOTICE.md i appens mapp.</p>
        </section>
      {/if}
    </div>
  </div>
</div>

<style>
  .settings { display: flex; gap: 32px; align-items: flex-start; }
  .tabs { flex: 0 0 200px; display: flex; flex-direction: column; gap: 2px; }
  .tab { min-height: 44px; padding: 0 14px; border: 0; border-radius: var(--radius-sm); background: transparent; text-align: left; font-weight: 500; }
  .tab:hover { background: var(--sunken); }
  .tab[aria-selected='true'] { background: var(--coral-50); color: var(--coral-800); }
  .panel { flex: 1 1 auto; min-width: 0; max-width: 680px; }
  .line { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
  .credits li { display: flex; justify-content: space-between; gap: 16px; padding: 8px 0; border-bottom: 1px solid var(--line); }
  @media (max-width: 760px) {
    .settings { flex-direction: column; gap: 16px; }
    .tabs { flex: none; flex-direction: row; flex-wrap: wrap; }
  }
</style>
