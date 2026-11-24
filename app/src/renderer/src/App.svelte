<script lang="ts">
  import type { Project, Settings as Kept, StommenState } from '../../shared/types'
  import Icon from './lib/Icon.svelte'
  import { failure } from './lib/format'
  import type { View } from './lib/view'
  import Agenda from './views/Agenda.svelte'
  import Meetings from './views/Meetings.svelte'
  import Projects from './views/Projects.svelte'
  import Protocol from './views/Protocol.svelte'
  import Onboarding from './views/Onboarding.svelte'
  import Recording from './views/Recording.svelte'
  import Settings from './views/Settings.svelte'
  import Stommen from './views/Stommen.svelte'
  import Working from './views/Working.svelte'

  const TITLES: Record<View['name'], string> = {
    meetings: 'Möten',
    agenda: 'Dagordning',
    recording: 'Inspelning',
    working: 'Mötet bearbetas',
    protocol: 'Protokoll',
    projects: 'Projekt',
    stommen: 'Stommen',
    settings: 'Inställningar'
  }

  let projects = $state<Project[]>([])
  let loaded = $state(false)
  let problem = $state('')
  let chosen = $state(localStorage.getItem('project') ?? '')
  let view = $state<View>({ name: 'meetings' })
  let stommen = $state<StommenState | null>(null)
  let settings = $state<Kept | null>(null)
  let folder = $state('')
  void window.api.settings().then((s) => (settings = s))

  const project = $derived(projects.find((p) => p.id === chosen) ?? projects[0])
  // A recording or a job in progress is not left by a click in the menu.
  // The views that are not about the chosen project's meetings.
  const elsewhere = $derived(view.name === 'stommen' || view.name === 'projects' || view.name === 'settings')
  const held = $derived(view.name === 'recording' || view.name === 'working')

  async function load(): Promise<void> {
    try {
      const got = await window.api.projects()
      projects = got.projects
      folder = got.folder
      problem = ''
    } catch (e) {
      problem = failure(e)
    } finally {
      loaded = true
    }
  }
  void load()

  /** Where the app stands with Stommen, and when it is signed in, what Stommen has now: Stommen wins. */
  async function connect(): Promise<void> {
    try {
      stommen = await window.api.stommenState()
      if (!stommen.connected) return
      await window.api.stommenSync()
      await load()
    } catch {
      // Stommen out of reach stops nothing here: the projects are on this computer, and the Stommen view says what is wrong.
    } finally {
      stommen = await window.api.stommenState().catch(() => stommen)
    }
  }
  void connect()

  function choose(id: string): void {
    chosen = id
    localStorage.setItem('project', id)
    view = { name: 'meetings' }
  }

  const go = (to: View): void => {
    view = to
  }
</script>

{#if settings && !settings.setUp}
  <Onboarding {settings} {stommen} changed={(s) => (settings = s)} stommenChanged={(s) => (stommen = s)} refresh={load} done={() => (view = { name: 'meetings' })} />
{:else}
<div class="shell">
  <aside>
    <div class="brand"><Icon name="wave" size={22} /><span><b>B</b>YGGMÖTE</span></div>

    {#if projects.length}
      <label class="small muted" for="project">Projekt</label>
      <select id="project" class="field" value={project?.id} disabled={held} onchange={(e) => choose(e.currentTarget.value)}>
        {#each projects as p (p.id)}
          <option value={p.id}>{p.name}</option>
        {/each}
      </select>
    {/if}

    <nav aria-label="Huvudmeny">
      {#if projects.length}
        <button class="item" class:current={!elsewhere} aria-current={!elsewhere ? 'page' : undefined}
          disabled={held} onclick={() => go({ name: 'meetings' })}>
          <Icon name="list" /> Möten
        </button>
      {/if}
      <button class="item" class:current={view.name === 'projects'} aria-current={view.name === 'projects' ? 'page' : undefined} disabled={held}
        onclick={() => go({ name: 'projects' })}>
        <Icon name="person" /> Projekt
      </button>
      <button class="item" class:current={view.name === 'stommen'} aria-current={view.name === 'stommen' ? 'page' : undefined} disabled={held}
        onclick={() => go({ name: 'stommen' })}>
        <Icon name="link" /> Stommen
      </button>
      <button class="item" class:current={view.name === 'settings'} aria-current={view.name === 'settings' ? 'page' : undefined} disabled={held}
        onclick={() => go({ name: 'settings' })}>
        <Icon name="gear" /> Inställningar
      </button>
    </nav>

    <p class="foot small muted">
      {#if stommen?.connected}
        Kopplad till Stommen som {stommen.user}.
      {:else}
        Stommen är inte kopplat än. Projekt och personer ligger på den här datorn.
      {/if}
    </p>
    {#if stommen && !stommen.connected && view.name !== 'stommen'}
      <button class="btn primary login" disabled={held} onclick={() => go({ name: 'stommen' })}>Logga in</button>
    {/if}
  </aside>

  <div class="content">
    <header>
      <p class="crumbs">
        {#if project && !elsewhere}<span class="muted">{project.name}</span><span class="muted" aria-hidden="true">/</span>{/if}
        <span>{TITLES[view.name]}</span>
      </p>
      <p class="promise small"><Icon name="lock" size={16} /> Ljud och utskrift stannar på den här datorn</p>
    </header>

    <main>
      {#if !loaded}
        <div class="page"><p class="muted">Läser in projekten.</p></div>
      {:else if problem}
        <div class="page">
          <div class="note bad" role="alert">
            <Icon name="alert" />
            <div>
              <p><strong>Byggmöte når inte sin motor.</strong> Utan den går det varken att läsa möten eller skriva ut nya.</p>
              <p class="small mono">{problem}</p>
              <button class="btn" style="margin-top: 12px" onclick={load}>Försök igen</button>
            </div>
          </div>
        </div>
      {:else if view.name === 'settings'}
        {#if settings}
          <Settings {settings} {stommen} {folder} {go} changed={(s) => (settings = s)} moved={load}
            intro={async () => (settings = await window.api.setUp(false))} />
        {/if}
      {:else if view.name === 'stommen'}
        {#if stommen}
          <Stommen {stommen} changed={(s) => (stommen = s)} refresh={load} />
        {:else}
          <div class="page"><p class="muted">Läser in kopplingen till Stommen.</p></div>
        {/if}
      {:else if view.name === 'projects' || !project}
        <Projects {projects} chosen={project?.id ?? ''} refresh={load} {choose} first={!projects.length} />
        {#if !projects.length}
          <div class="page" style="padding-top: 0">
            <p class="small muted">Har du Stommen? <button class="link" onclick={() => go({ name: 'stommen' })}>Koppla dit</button> så hämtas dina Projekt, Roller och Kontakter hit.</p>
          </div>
        {/if}
      {:else}
        {#key project.id}
          {#if view.name === 'meetings'}
            <Meetings {project} {go} refresh={load} />
          {:else if view.name === 'agenda'}
            <Agenda {project} series={view.series} {go} />
          {:else if view.name === 'recording'}
            <Recording {project} series={view.series} {go} />
          {:else if view.name === 'working'}
            <Working job={view.job} {go} />
          {:else if view.name === 'protocol'}
            {#key view.dir}
              <Protocol {project} dir={view.dir} problem={view.problem ?? ''} connected={Boolean(stommen?.connected)} {go} refresh={load} />
            {/key}
          {/if}
        {/key}
      {/if}
    </main>
  </div>
</div>
{/if}

<style>
  .login { width: 100%; }
  .shell { display: flex; height: 100%; }
  aside { flex: 0 0 248px; display: flex; flex-direction: column; gap: 8px; padding: 20px 16px; background: var(--surface); border-right: 1px solid var(--line); }
  .brand { display: flex; align-items: center; gap: 10px; height: 24px; margin-bottom: 20px; color: var(--coral-500); }
  .brand span { font: 300 17px var(--font-display); letter-spacing: 0.24em; color: var(--coral-700); padding-top: 3px; }
  .brand b { font-weight: 600; }
  select { width: 100%; margin-bottom: 12px; }
  nav { display: flex; flex-direction: column; gap: 2px; }
  .item { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 12px; border: 0; border-radius: var(--radius-sm); background: transparent; text-align: left; font-weight: 500; }
  .item.current { background: var(--coral-50); }
  .item :global(svg) { color: var(--coral-700); }
  .foot { margin-top: auto; }
  .link { padding: 0; border: 0; background: transparent; color: var(--coral-700); text-decoration: underline; }
  .content { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
  header { flex: none; display: flex; align-items: center; justify-content: space-between; gap: 16px; height: 64px; padding: 0 clamp(16px, 4vw, 40px);
    background: var(--surface); border-bottom: 1px solid var(--line); }
  .crumbs { display: flex; gap: 8px; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .promise { display: flex; align-items: center; gap: 8px; color: var(--ink-700); white-space: nowrap; }
  .promise :global(svg) { color: var(--ok); }
  main { flex: 1 1 auto; overflow: auto; }
  @media (max-width: 760px) {
    .shell { flex-direction: column; }
    aside { flex: none; border-right: 0; border-bottom: 1px solid var(--line); }
    .foot, .login { display: none; }
    .promise { display: none; }
  }
</style>
