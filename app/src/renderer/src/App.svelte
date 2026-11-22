<script lang="ts">
  import type { Project, StommenState } from '../../shared/types'
  import Icon from './lib/Icon.svelte'
  import { failure } from './lib/format'
  import type { View } from './lib/view'
  import Agenda from './views/Agenda.svelte'
  import Meetings from './views/Meetings.svelte'
  import Protocol from './views/Protocol.svelte'
  import Recording from './views/Recording.svelte'
  import Stommen from './views/Stommen.svelte'
  import Working from './views/Working.svelte'

  const TITLES: Record<View['name'], string> = {
    meetings: 'Möten',
    agenda: 'Dagordning',
    recording: 'Inspelning',
    working: 'Mötet bearbetas',
    protocol: 'Protokoll',
    stommen: 'Stommen'
  }

  let projects = $state<Project[]>([])
  let loaded = $state(false)
  let problem = $state('')
  let chosen = $state(localStorage.getItem('project') ?? '')
  let view = $state<View>({ name: 'meetings' })
  let stommen = $state<StommenState | null>(null)

  const project = $derived(projects.find((p) => p.id === chosen) ?? projects[0])
  // A recording or a job in progress is not left by a click in the menu.
  const held = $derived(view.name === 'recording' || view.name === 'working')

  async function load(): Promise<void> {
    try {
      projects = (await window.api.projects()).projects
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
        <button class="item" class:current={view.name !== 'stommen'} aria-current={view.name !== 'stommen' ? 'page' : undefined} disabled={held}
          onclick={() => go({ name: 'meetings' })}>
          <Icon name="list" /> Möten
        </button>
      {/if}
      <button class="item" class:current={view.name === 'stommen'} aria-current={view.name === 'stommen' ? 'page' : undefined} disabled={held}
        onclick={() => go({ name: 'stommen' })}>
        <Icon name="link" /> Stommen
      </button>
    </nav>

    <p class="foot small muted">
      {#if stommen?.connected}
        Kopplad till Stommen som {stommen.user}.
      {:else}
        Stommen är inte kopplat än. Projekt och Roller ligger på den här datorn.
      {/if}
    </p>
  </aside>

  <div class="content">
    <header>
      <p class="crumbs">
        {#if project && view.name !== 'stommen'}<span class="muted">{project.name}</span><span class="muted" aria-hidden="true">/</span>{/if}
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
      {:else if view.name === 'stommen'}
        {#if stommen}
          <Stommen {stommen} changed={(s) => (stommen = s)} refresh={load} />
        {:else}
          <div class="page"><p class="muted">Läser in kopplingen till Stommen.</p></div>
        {/if}
      {:else if !project}
        <div class="page">
          <div class="card">
            <h2>Inga projekt än</h2>
            <p class="muted">Projekt och Roller hämtas från Stommen. Logga in där, så kommer dina Projekt hit.</p>
            <button class="btn primary" style="margin-top: 16px" onclick={() => go({ name: 'stommen' })}>Koppla till Stommen</button>
          </div>
        </div>
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
              <Protocol {project} dir={view.dir} problem={view.problem ?? ''} connected={Boolean(stommen?.connected)} {go} />
            {/key}
          {/if}
        {/key}
      {/if}
    </main>
  </div>
</div>

<style>
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
    .foot { display: none; }
    .promise { display: none; }
  }
</style>
