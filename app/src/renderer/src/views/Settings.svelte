<script lang="ts">
  // The app's own settings, as the computer draws a settings window: on the Mac a toolbar of panes and each pane a
  // form, on Windows the pages down the left side and each page a list of rows (lib/Row.svelte, settings.css). Each
  // change is kept as it is made; there is no Save.
  import type { ModelRow, Settings, StommenState } from '../../../shared/types'
  import Glyph from '../lib/Glyph.svelte'
  import Icon from '../lib/Icon.svelte'
  import Microphone from '../lib/Microphone.svelte'
  import Models from '../lib/Models.svelte'
  import Row from '../lib/Row.svelte'
  import Shortcuts from '../lib/Shortcuts.svelte'
  import Stommen from './Stommen.svelte'
  import { failure } from '../lib/format'

  // `first`: the pane to open on. `version`: the app's. `connection`: Stommen's state changed. `fetched`: what Stommen
  // has was fetched. `shown`: the pane that is open, by name.
  let { settings, stommen, folder, first, version, changed, intro, moved, connection, fetched, shown }: {
    settings: Settings
    stommen: StommenState | null
    folder: string
    first: string
    version: string
    changed: (s: Settings) => void
    intro: () => void
    moved: () => Promise<void>
    connection: (s: StommenState) => void
    fetched: () => Promise<void>
    shown: (name: string) => void
  } = $props()

  const mac = window.api.platform === 'darwin'
  // On the Mac what the app is made of is the app menu's Om Byggmöte (views/About.svelte), not a pane.
  const TABS = ([
    { id: 'general', name: 'Allmänt' },
    { id: 'recording', name: 'Inspelning' },
    { id: 'models', name: 'Modeller' },
    { id: 'stommen', name: 'Stommen' },
    { id: 'about', name: 'Om Byggmöte' }
  ] as const).filter((t) => !mac || t.id !== 'about')
  type Tab = (typeof TABS)[number]['id']

  // svelte-ignore state_referenced_locally
  let tab = $state<Tab>(TABS.some((t) => t.id === first) ? (first as Tab) : 'general')
  // svelte-ignore state_referenced_locally
  let name = $state(settings.name)
  let problem = $state('')
  let where = $state('')
  let licences = $state<ModelRow[]>([])
  const title = $derived(TABS.find((t) => t.id === tab)!.name)
  $effect(() => shown(title))

  async function set(patch: Partial<Omit<Settings, 'setUp'>>): Promise<void> {
    problem = ''
    try {
      changed(await window.api.settingsSet(patch))
    } catch (e) {
      problem = failure(e)
    }
  }

  // The name is kept when the field is left or Enter is pressed. An empty one is not a name: the kept one comes back.
  function rename(): void {
    const next = name.trim()
    if (!next) name = settings.name
    else if (next !== settings.name) void set({ name: next })
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

  const KEPT = 'Ljud och utskrift, en mapp per möte. Byggmöte flyttar det som finns om du väljer en annan mapp.'
  const RUNS = 'Modellerna körs på den här datorn. De hämtas en gång, sedan fungerar Byggmöte utan internet.'
</script>

{#snippet panes()}
  {#each TABS as t (t.id)}
    <button id="tab-{t.id}" class="pane" role="tab" aria-selected={tab === t.id} aria-controls="panel" tabindex={tab === t.id ? 0 : -1} onclick={() => (tab = t.id)}>
      <Glyph name={t.id} size={mac ? 22 : 16} /><span>{t.name}</span>
    </button>
  {/each}
{/snippet}

{#snippet folderButtons()}
  <div class="row" style="gap: 8px">
    <button class="btn" onclick={() => window.api.folderShow()}>Visa i mappen</button>
    <button class="btn" onclick={chooseFolder}>Välj mapp…</button>
  </div>
{/snippet}

{#snippet body()}
  {#if problem}
    <div class="note bad wide" role="alert"><Icon name="alert" /><p>{problem}</p></div>
  {/if}

  {#if tab === 'general'}
    <Row label="Ditt namn" for="me" icon="person" desc="Du är med på alla möten. Namnet står i protokollet och används för att känna igen din röst.">
      <input id="me" class="field" style="width: 220px" autocomplete="name" bind:value={name} onchange={rename} />
    </Row>
    {#if mac}
      <span class="lbl">Möten sparas i:</span>
      <div class="val"><p class="mono">{where || folder}</p>{@render folderButtons()}<p class="d">{KEPT}</p></div>
    {:else}
      <div class="srow">
        <span class="ic"><Glyph name="folder" /></span>
        <div class="tx"><span class="t">Där Byggmöte sparar möten</span><span class="d mono">{where || folder}</span><span class="d">{KEPT}</span></div>
        <div class="ctl">{@render folderButtons()}</div>
      </div>
    {/if}
    <Row label="Stommen" icon="stommen" desc={stommen?.connected ? `Kopplad som ${stommen.user}.` : 'Inte kopplad. Projekt och personer ligger på den här datorn.'}>
      <button class="btn" onclick={() => (tab = 'stommen')}>{stommen?.connected ? 'Hantera kopplingen' : 'Koppla till Stommen'}</button>
    </Row>
    <Row label="Introduktion" title="Introduktionen" icon="intro" desc="Gå igenom stegen från första start igen: namn, mikrofon, modeller och Stommen. Inget du har sparat tas bort.">
      <button class="btn" onclick={intro}>Visa introduktionen</button>
    </Row>
  {:else if tab === 'recording'}
    <Row label="Mikrofon" icon="recording" top desc="Vilken mikrofon Byggmöte spelar in med" macDesc="">
      <Microphone bare value={settings.microphone} choose={(microphone) => set({ microphone })} />
    </Row>
    <Row label="Röster" title="Känn igen röster" icon="person" desc="Byggmöte lär sig vem som talar utifrån tidigare möten. Rösterna lämnar inte datorn."
      toggle={{ checked: settings.voices, set: (voices) => set({ voices }) }} />
    <Row label="Start" title="Öppna Byggmöte när jag loggar in" icon="screen" desc="Appen startar när du loggar in på datorn" macDesc=""
      toggle={{ checked: settings.openAtLogin, set: (openAtLogin) => set({ openAtLogin }) }} />
    <Shortcuts {settings} {changed} />
  {:else if tab === 'models'}
    {#if mac}
      <span class="lbl">Modeller:</span>
      <div class="val"><div class="models"><Models /></div><p class="d">{RUNS}</p></div>
    {:else}
      <div class="exp">
        <div class="srow"><span class="ic"><Glyph name="models" /></span><div class="tx"><span class="t">AI-modeller för inspelning och protokoll</span><span class="d">{RUNS}</span></div></div>
        <div class="exp-body"><Models /></div>
      </div>
    {/if}
  {:else if tab === 'stommen'}
    {#if stommen}
      <Stommen bare {stommen} changed={connection} refresh={fetched} />
    {:else}
      <p class="d wide">Läser in kopplingen till Stommen.</p>
    {/if}
  {:else}
    <div class="srow">
      <span class="ic"><Glyph name="about" /></span>
      <div class="tx"><span class="t">Byggmöte</span><span class="d">Spelar in byggmöten, skriver utskriften och protokollet på den här datorn, och skickar det du godkänner vidare till Stommen.</span></div>
      {#if version}<div class="ctl muted">Version {version}</div>{/if}
    </div>
    <div class="exp">
      <div class="srow"><span class="ic"><Glyph name="models" /></span><div class="tx"><span class="t">Modeller</span><span class="d">Villkoren i sin helhet finns i NOTICE.md i appens mapp.</span></div></div>
      {#each licences as m (m.id)}
        <div class="sc-row"><span class="name">{m.name}</span><span class="d">{m.license}</span></div>
      {:else}
        <div class="sc-row d">Läser in.</div>
      {/each}
    </div>
  {/if}
{/snippet}

{#if mac}
  <div class="titlebar">{title}</div>
  <div class="panes" role="tablist" aria-label="Inställningar" tabindex="-1" onkeydown={keys}>{@render panes()}</div>
  <div id="panel" class="form" role="tabpanel" aria-labelledby="tab-{tab}">
    <h1 class="sr">{title}</h1>
    {@render body()}
  </div>
{:else}
  <div class="nav" role="tablist" aria-label="Inställningar" aria-orientation="vertical" tabindex="-1" onkeydown={keys}>{@render panes()}</div>
  <div id="panel" class="content" role="tabpanel" aria-labelledby="tab-{tab}">
    <h1>{title}</h1>
    {@render body()}
  </div>
{/if}

<style>
  .models { width: 100%; max-width: 380px; padding-top: 5px; }
</style>
