<script lang="ts">
  import type { Agenda as Headings, Command, Job, MeetingRow, Progress, Project, RecordStatus, SeriesRef, Settings as Kept, StommenState } from '../../shared/types'
  import Icon from './lib/Icon.svelte'
  import { clock, failure, minutes, shortDate, standing } from './lib/format'
  import type { View } from './lib/view'
  import Agenda from './views/Agenda.svelte'
  import OpenPoints from './views/OpenPoints.svelte'
  import NewProject from './lib/NewProject.svelte'
  import RecordDialog from './lib/RecordDialog.svelte'
  import Overview from './views/Overview.svelte'
  import Protocol from './views/Protocol.svelte'
  import Onboarding from './views/Onboarding.svelte'
  import Palette, { type Entry } from './lib/Palette.svelte'
  import Working, { STEPS, type Run } from './views/Working.svelte'

  const TITLES: Record<View['name'], string> = {
    points: 'Öppna punkter',
    agenda: 'Dagordning',
    working: 'Mötet bearbetas',
    protocol: 'Protokoll',
    overview: 'Översikt'
  }

  // The select's last option opens a dialog where a project is named and made.
  const NEW = '__new'

  let projects = $state<Project[]>([])
  let loaded = $state(false)
  let problem = $state('')
  let chosen = $state(localStorage.getItem('project') ?? '')
  let view = $state<View>({ name: 'overview' })
  let stommen = $state<StommenState | null>(null)
  let settings = $state<Kept | null>(null)
  let folder = $state('')
  let naming = $state(false)
  let dialog = $state<HTMLDialogElement>()
  let recorder = $state<{ show: (s: SeriesRef, agenda?: boolean) => void }>()
  // The sidebar is the project's library: its meetings, read again when something in them may have changed.
  let rows = $state<MeetingRow[]>([])
  let read = $state(false) // whether the meetings below are the chosen project's yet
  let agendas = $state<Headings[] | null>(null) // each mötesserie's, with what earlier meetings left open
  let stale = $state(0)
  let sidebar = $state(localStorage.getItem('sidebar') !== 'hidden')
  // The meeting in the window: what the toolbar says of it, what the menu can do with it, and the view to tell.
  let protocol = $state<{ command: (c: Command) => void }>()
  let meeting = $state({ title: '', sub: '' })
  let doc = $state({ protocol: false, free: false, sendable: false, inspector: localStorage.getItem('inspector') !== 'hidden' })
  void window.api.settings().then((s) => (settings = s))

  const project = $derived(projects.find((p) => p.id === chosen) ?? projects[0])
  // The views that are not about the chosen project's meetings.
  // The meeting being recorded in its own window, as that window says it stands. One at a time.
  let live = $state<RecordStatus | null>(null)
  $effect(() => window.api.onRecording((r) => (live = r)))

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
      stale++
    }
  }
  void load()

  $effect(() => {
    const id = project?.id
    void stale
    const series = project?.series.map((x) => x.id) ?? []
    if (!id) {
      rows = []
      agendas = null
      return
    }
    void window.api.meetings(id).then((r) => { if (project?.id === id) { rows = r; read = true } }).catch(() => { read = true })
    void Promise.all(series.map((x) => window.api.agenda(id, x))).then((a) => { if (project?.id === id) agendas = a }).catch(() => { agendas = [] })
  })
  const open = $derived((agendas ?? []).reduce((n, a) => n + a.headings.reduce((k, h) => k + h.open.length, 0), 0))
  // A meeting with no series of the project's (one removed, or a recording from before there were series) comes last.
  const groups = $derived.by(() => {
    if (!project) return []
    const named = project.series.map((s) => ({ id: s.id, name: s.name, rows: rows.filter((r) => r.series === s.id) }))
    const rest = rows.filter((r) => !project.series.some((s) => s.id === r.series))
    return rest.length ? [...named, { id: '', name: 'Övriga möten', rows: rest }] : named
  })

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
    read = false
    agendas = null
    rows = []
    localStorage.setItem('project', id)
    view = { name: 'overview' }
  }

  function openNew(): void {
    naming = true
    dialog?.showModal()
  }
  function closeNew(): void {
    naming = false
    dialog?.close()
  }
  async function made(id: string): Promise<void> {
    await load()
    closeNew()
    choose(id)
  }

  // The recordings being written out, in the order they came. One is worked on at a time, and the window is free
  // meanwhile; one that failed stays in the list, saying so, until the person has seen it.
  let runs = $state<Run[]>([])
  let shown = $state(0) // the run the job view shows
  let last = 0
  let working = false
  const AT: Record<string, number> = { extract: 0, asr: 1, diarize: 2, merge: 3, write: 3, protocol: 4 }

  function start(job: Job): void {
    runs.push({ id: ++last, job, at: 0, fraction: 0, problem: '' })
    shown = last
    view = { name: 'working', job }
    void work()
  }

  async function work(): Promise<void> {
    if (working) return
    working = true
    try {
      for (;;) {
        const run = runs.find((r) => !r.problem)
        if (!run) return
        try {
          const done = await window.api.process($state.snapshot(run.job))
          runs = runs.filter((r) => r.id !== run.id)
          stale++
          // Whoever is watching the job is taken to its protocol; anyone else finds the meeting in the sidebar.
          if (view.name === 'working' && shown === run.id && project?.id === run.job.projectId) view = { name: 'protocol', dir: done.dir, problem: done.protocolError ?? undefined }
        } catch (e) {
          run.problem = failure(e)
        }
      }
    } finally {
      working = false
    }
  }

  /** The engine's steps, as the job view counts them. It loads a model before the second and the third. */
  function heard(p: Progress): void {
    const run = runs.find((r) => !r.problem)
    if (!run) return
    const i = AT[p.step.split(':')[0]]
    if (i === undefined) {
      if (p.step === 'load' && p.state === 'start' && run.at < 2) (run.at += 1), (run.fraction = 0)
      return
    }
    if (i > run.at) (run.at = i), (run.fraction = 0)
    if (i === run.at) run.fraction = p.state === 'done' ? 1 : p.state === 'progress' ? (p.fraction ?? 0) : run.fraction
  }
  $effect(() => window.api.onProgress(heard))
  // Inställningar is a window of its own: what is changed there is read again here.
  $effect(() => window.api.onChanged(() => {
    void window.api.settings().then((x) => (settings = x))
    void window.api.stommenState().then((x) => (stommen = x)).catch(() => {})
    void load()
  }))
  // A meeting recorded in its own window comes here to be written out.
  $effect(() => window.api.onJob(start))

  function dismiss(id: number): void {
    runs = runs.filter((r) => r.id !== id)
    view = { name: 'overview' }
  }

  const go = (to: View): void => {
    if (to.name === 'working') return start(to.job)
    if (view.name === 'protocol') stale++ // a protocol was corrected
    if (to.name === 'protocol') meeting = { title: '', sub: '' }
    view = to
  }

  function showSidebar(on: boolean): void {
    sidebar = on
    localStorage.setItem('sidebar', on ? 'shown' : 'hidden')
  }

  async function addRecording(s: SeriesRef): Promise<void> {
    const file = await window.api.pickRecording()
    if (file && project) go({ name: 'working', job: { projectId: project.id, seriesId: s.id, file, title: `${s.name} ${s.next}` } })
  }

  /** Nytt möte, or the recording window when a meeting is being recorded. From an agenda it is that agenda's meeting. */
  function record(): void {
    if (live) void window.api.recordShow()
    else if (view.name === 'agenda') recorder?.show(view.series, true)
    else if (project?.series.length) recorder?.show(project.series[0])
  }

  const PROTOCOL: Command[] = ['saveDocx', 'savePdf', 'saveMd', 'copyText', 'find', 'inspector', 'newPoint', 'nextCheck', 'rename', 'rewrite', 'send']

  /** A choice in the application menu, or its shortcut. The menu greys out what cannot run; this refuses it too. */
  function command(c: Command): void {
    if (c === 'sidebar') return showSidebar(!sidebar)
    if (!settings?.setUp) return
    if (PROTOCOL.includes(c)) return view.name === 'protocol' ? protocol?.command(c) : undefined
    const first = project?.series[0]
    if (c === 'settings') void window.api.settingsOpen()
    else if (c === 'palette') palette?.show()
    else if (c === 'newProject') openNew()
    else if (c === 'sync') void connect()
    else if (c === 'intro') void window.api.setUp(false).then((s) => (settings = s))
    else if (!project) return
    else if (c === 'overview') go({ name: 'overview' })
    else if (c === 'points') go({ name: 'points' })
    else if (!first) return
    else if (c === 'agenda') go({ name: 'agenda', series: first })
    else if (c === 'record') record()
    else if (c === 'addRecording') void addRecording(first)
  }
  $effect(() => window.api.onCommand(command))

  // The palette lists what the window can do now, the project's meetings and open points, and the other projects.
  let palette = $state<{ show: () => void }>()
  const mac = window.api.platform === 'darwin'
  const k = (onMac: string, elsewhere: string): string => (mac ? onMac : elsewhere)
  const entries = $derived.by((): Entry[] => {
    const cmd = (label: string, c: Command, keys?: string): Entry => ({ group: 'Kommandon', label, keys, run: () => command(c) })
    const list: Entry[] = []
    if (project) {
      list.push(cmd('Översikt', 'overview', k('⌘1', 'Ctrl+1')), cmd('Öppna punkter', 'points', k('⌘2', 'Ctrl+2')))
      if (project.series.length) list.push(cmd('Dagordning', 'agenda', k('⌘3', 'Ctrl+3')), cmd(live ? 'Visa inspelningsfönstret' : 'Spela in möte…', 'record', k('⌘R', 'Ctrl+R')), cmd('Lägg till en inspelning…', 'addRecording', k('⌘O', 'Ctrl+O')))
    }
    if (view.name === 'protocol') {
      list.push(cmd('Sök i utskriften', 'find', k('⌘F', 'Ctrl+F')), cmd(doc.inspector ? 'Dölj utskriften' : 'Visa utskriften', 'inspector', k('⌥⌘I', 'Ctrl+I')))
      if (doc.protocol) list.push(cmd('Nästa att kontrollera', 'nextCheck', k('⌘J', 'Ctrl+J')), cmd('Spara som Word…', 'saveDocx', k('⇧⌘S', 'Ctrl+Skift+S')), cmd('Spara som PDF…', 'savePdf'), cmd('Spara som Markdown…', 'saveMd'),
        cmd('Kopiera texten', 'copyText', k('⇧⌘C', 'Ctrl+Skift+C')), cmd('Byt namn på mötet…', 'rename'))
      if (doc.free) list.push(cmd('Ny punkt', 'newPoint', k('⌘N', 'Ctrl+N')), cmd('Skriv om protokollet…', 'rewrite'))
      if (doc.sendable) list.push(cmd('Skicka till Stommen…', 'send', k('⌘⏎', 'Ctrl+Enter')))
    }
    list.push(cmd('Nytt projekt…', 'newProject', k('⇧⌘N', 'Ctrl+Skift+N')), cmd('Inställningar…', 'settings', k('⌘,', 'Ctrl+,')), cmd(sidebar ? 'Dölj sidopanelen' : 'Visa sidopanelen', 'sidebar', k('⌃⌘S', 'Ctrl+B')))
    if (stommen?.connected) list.push(cmd('Hämta från Stommen', 'sync', k('⇧⌘U', 'F5')))
    for (const r of rows) list.push({ group: 'Möten', label: r.title, detail: `${shortDate(r.recorded_at)} · ${standing(r).text}`, run: () => go({ name: 'protocol', dir: r.dir }) })
    for (const a of agendas ?? []) for (const h of a.headings) for (const pt of h.open) {
      const from = rows.find((r) => r.series === a.series && r.no === Number(pt.no.split('.')[0]))
      list.push({ group: 'Öppna punkter', label: `${pt.no} ${pt.text}`, detail: [pt.role, pt.due].filter(Boolean).join(' · '), run: () => go(from ? { name: 'protocol', dir: from.dir } : { name: 'points' }) })
    }
    for (const x of projects) if (x.id !== project?.id) list.push({ group: 'Projekt', label: x.name, run: () => choose(x.id) })
    return list
  })
  $effect(() => {
    void window.api.menuState({
      ready: loaded && Boolean(settings?.setUp), held: false, project: Boolean(project), series: Boolean(project?.series.length),
      connected: Boolean(stommen?.connected), sidebar, ...doc, meeting: view.name === 'protocol',
      ...(view.name === 'protocol' ? {} : { protocol: false, free: false, sendable: false })
    })
  })
</script>

{#if settings && !settings.setUp}
  <div class="strip drag"></div>
  <Onboarding {settings} {stommen} changed={(s) => (settings = s)} stommenChanged={(s) => (stommen = s)} refresh={load} done={() => (view = { name: 'overview' })} />
{:else}
<div class="shell">
  {#if sidebar}
  <aside>
    <!-- On the Mac the window's three buttons sit here, and the strip moves the window. -->
    <div class="side-top drag"></div>

    {#if projects.length}
      <label class="sr-only" for="project">Projekt</label>
      <select id="project" class="field" value={project?.id}
        onchange={(e) => {
          if (e.currentTarget.value === NEW) {
            e.currentTarget.value = project?.id ?? ''
            openNew()
          } else choose(e.currentTarget.value)
        }}>
        {#each projects as p (p.id)}
          <option value={p.id}>{p.name}</option>
        {/each}
        <option value={NEW}>Nytt projekt…</option>
      </select>
    {/if}

    <nav aria-label="Huvudmeny">
      {#if projects.length}
        <p class="side-head">Projektet</p>
        <button class="item" class:current={view.name === 'overview'} aria-current={view.name === 'overview' ? 'page' : undefined}
          onclick={() => go({ name: 'overview' })}>
          <Icon name="home" size={16} /> Översikt
        </button>
        <button class="item" class:current={view.name === 'points'} aria-current={view.name === 'points' ? 'page' : undefined}
          onclick={() => go({ name: 'points' })}>
          <Icon name="clock" size={16} /> Öppna punkter {#if open}<span class="n">{open}</span>{/if}
        </button>
        {#each project?.series ?? [] as s (s.id)}
          {@const here = view.name === 'agenda' && view.series.id === s.id}
          <button class="item" class:current={here} aria-current={here ? 'page' : undefined} onclick={() => go({ name: 'agenda', series: s })}>
            <Icon name="list" size={16} /> <span class="clip">Dagordning inför {s.name.toLowerCase()} {s.next}</span>
          </button>
        {/each}

        <div class="library">
          {#if live}
            <p class="side-head"><span>Spelas in</span></p>
            <button class="meeting" onclick={() => window.api.recordShow()}>
              <span class="l1"><span class="name">{live.title}</span><span class="when">{clock(live.seconds)}</span></span>
              <span class="l2">{live.phase === 'paused' ? 'Pausad' : live.phase === 'saving' ? 'Sparar inspelningen' : live.phase === 'idle' ? 'Inte igång' : 'Spelar in'}{live.heading ? ` · ${live.heading}` : ''}</span>
            </button>
          {/if}
          {#if runs.length}
            <p class="side-head"><span>Skrivs ut</span></p>
            {#each runs as r (r.id)}
              {@const here = view.name === 'working' && shown === r.id}
              <button class="meeting" class:current={here} aria-current={here ? 'page' : undefined}
                onclick={() => { shown = r.id; view = { name: 'working', job: r.job } }}>
                <span class="l1"><span class="name">{r.job.title}</span></span>
                <span class="l2">{r.problem ? 'Gick inte att skriva ut' : r === runs.find((x) => !x.problem) ? `${STEPS[r.at]} · steg ${r.at + 1} av ${STEPS.length}` : 'Väntar på sin tur'}</span>
                {#if !r.problem}<span class="bar"><span style="width: {((r.at + r.fraction) / STEPS.length) * 100}%"></span></span>{/if}
              </button>
            {/each}
          {/if}
          {#each groups as g (g.id)}
            <p class="side-head"><span>{g.name}</span><span class="count">{g.rows.length === 1 ? '1 möte' : `${g.rows.length} möten`}</span></p>
            {#each g.rows as r (r.dir)}
              {@const here = view.name === 'protocol' && view.dir === r.dir}
              <button class="meeting" class:current={here} aria-current={here ? 'page' : undefined}
                onclick={() => go({ name: 'protocol', dir: r.dir })}>
                <span class="l1"><span class="name">{r.title}</span><span class="when">{shortDate(r.recorded_at)}</span></span>
                <span class="l2">{standing(r).text} · {minutes(r.duration)}</span>
              </button>
            {/each}
          {/each}
        </div>
      {:else if loaded && !problem}
        <!-- Without a project the menu is otherwise empty, and this is the way back from Inställningar. -->
        <button class="item current" aria-current="page"
          onclick={() => go({ name: 'overview' })}>
          <Icon name="plus" size={16} /> Nytt projekt
        </button>
      {/if}
    </nav>

    <div class="foot">
      <p class="status">
        <span class="dot" class:on={stommen?.connected}></span>
        {#if stommen?.connected}
          Kopplad till Stommen som {stommen.user}.
        {:else}
          Stommen är inte kopplat än. Projekt och personer ligger på den här datorn.
        {/if}
      </p>
      <p class="status"><Icon name="lock" size={13} /> Ljud och utskrift stannar på den här datorn</p>
      <button class="item" onclick={() => window.api.settingsOpen()}>
        <Icon name="gear" size={16} /> Inställningar
      </button>
    </div>
  </aside>
  {/if}

  <div class="content">
    <header class="drag" class:alone={!sidebar}>
      <button class="tool" aria-label={sidebar ? 'Dölj sidopanelen' : 'Visa sidopanelen'} aria-pressed={sidebar} onclick={() => showSidebar(!sidebar)}>
        <Icon name="sidebar" size={17} />
      </button>
      <div class="titles">
        {#if view.name === 'protocol' && meeting.title}
          <p class="title">{meeting.title}</p>
          <p class="sub">{meeting.sub}</p>
        {:else}
          <p class="title">{TITLES[view.name]}</p>
          {#if project}<p class="sub">{project.name}</p>{/if}
        {/if}
      </div>
      <!-- A view with a title of its own puts it here, and the window's is put away. -->
      <div id="title"></div>
      <span class="grow"></span>
      <!-- A view puts what is done in it here (Protocol.svelte). -->
      <div id="tools"></div>
      {#if live}
        <button class="btn rec" onclick={() => window.api.recordShow()}>{live.phase === 'paused' ? 'Pausad' : 'Spelar in'} {clock(live.seconds)}</button>
      {:else if project?.series.length}
        <button class="btn rec" onclick={record}>Spela in</button>
      {/if}
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
      {:else if !project}
        <div class="page">
          <div class="page-head"><div><h1>Skapa ditt första projekt</h1></div></div>
          <section class="card narrow">
            <p class="muted" style="margin-bottom: 12px">Ett projekt samlar mötena för ett bygge. Du kan spela in det första mötet direkt efteråt.</p>
            <NewProject created={made} />
          </section>
          <p class="small muted" style="margin-top: 16px">Har du Stommen? <button class="link" onclick={() => window.api.settingsOpen('stommen')}>Koppla dit</button> så hämtas dina Projekt, Roller och Kontakter hit.</p>
        </div>
      {:else}
        {#key project.id}
          {#if view.name === 'overview'}
            <Overview {project} rows={read ? rows : null} {agendas} {go} refresh={load} gone={() => (view = { name: 'overview' })} {stommen} sync={connect}
              record={(s) => (live ? void window.api.recordShow() : recorder?.show(s))} />
          {:else if view.name === 'points'}
            <OpenPoints {project} {rows} {agendas} {go} />
          {:else if view.name === 'agenda'}
            <Agenda {project} series={view.series} />
          {:else if view.name === 'working'}
            {@const run = runs.find((r) => r.id === shown)}
            {#if run}<Working {run} {project} waiting={run !== runs.find((r) => !r.problem) && !run.problem} dismiss={() => dismiss(run.id)} />{/if}
          {:else if view.name === 'protocol'}
            {#key view.dir}
              <Protocol bind:this={protocol} {project} dir={view.dir} problem={view.problem ?? ''} connected={Boolean(stommen?.connected)} {go} refresh={load}
                about={(title, sub) => (meeting = { title, sub })} state={(s) => (doc = s)} />
            {/key}
          {/if}
        {/key}
      {/if}
    </main>
  </div>
</div>
{/if}

{#if project}<RecordDialog bind:this={recorder} {project} />{/if}
<Palette bind:this={palette} {entries} />

<dialog bind:this={dialog} aria-labelledby="new-title" onclose={() => (naming = false)}>
  <h2 id="new-title">Nytt projekt</h2>
  {#if naming}<NewProject created={made} cancel={closeNew} />{/if}
</dialog>

<style>
  dialog { width: min(440px, calc(100vw - 32px)); margin: auto; padding: 24px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); box-shadow: var(--shadow-sm); }
  dialog::backdrop { background: rgb(0 0 0 / 0.35); }
  dialog h2 { margin-bottom: 16px; }
  .narrow { max-width: 680px; }
  .shell { display: flex; height: 100%; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }

  /* The sidebar: the project's library on the pane colour, in the rows of a source list. */
  aside { flex: 0 0 264px; display: flex; flex-direction: column; min-height: 0; padding: 8px; background: var(--pane); border-right: 1px solid var(--line); }
  .side-top { flex: none; height: 0; }
  :global(:root[data-platform='mac']) .side-top { height: 40px; }
  select { width: 100%; font-weight: 600; margin-bottom: 4px; }
  nav { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; gap: 1px; }
  .side-head { display: flex; align-items: center; justify-content: space-between; height: 24px; margin-top: 8px; padding: 0 8px; font-size: var(--ui-small); font-weight: 600; color: var(--ink-500); }
  .side-head .count { font-weight: 400; }
  .item { display: flex; align-items: center; gap: 8px; flex: none; height: var(--row-h); padding: 0 8px; border: 0; border-radius: var(--ctl-r); background: transparent; text-align: left; white-space: nowrap; }
  .item :global(svg) { flex: none; color: var(--coral-700); }
  .item .n { margin-left: auto; font-size: var(--ui-small); color: var(--ink-500); }
  .item.current .n { color: inherit; }
  .item .clip { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  .item:hover:not(:disabled):not(.current) { background: rgb(0 0 0 / 0.045); }
  .library { flex: 1 1 auto; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; margin: 0 -8px; padding: 0 8px; }
  .meeting { display: flex; flex-direction: column; gap: 1px; flex: none; padding: 6px 8px; border: 0; border-radius: var(--ctl-r); background: transparent; text-align: left; }
  .meeting:hover:not(:disabled):not(.current) { background: rgb(0 0 0 / 0.045); }
  .meeting .l1 { display: flex; align-items: baseline; gap: 8px; font-weight: 600; white-space: nowrap; }
  .meeting .name { overflow: hidden; text-overflow: ellipsis; }
  .meeting .when { margin-left: auto; font-weight: 400; font-size: var(--ui-small); color: var(--ink-500); }
  .meeting .bar { display: block; height: 3px; margin-top: 4px; border-radius: 2px; background: rgb(0 0 0 / 0.12); overflow: hidden; }
  .meeting .bar span { display: block; height: 100%; background: var(--coral-700); transition: width 0.3s; }
  :global(:root[data-platform='mac']) .meeting.current .bar { background: rgb(255 255 255 / 0.35); }
  :global(:root[data-platform='mac']) .meeting.current .bar span { background: #fff; }
  .meeting .l2 { font-size: var(--ui-small); color: var(--ink-500); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  /* The chosen row: the Mac's solid accent, Windows' tint with the accent bar at its edge. */
  .item.current, .meeting.current { background: rgb(201 58 66 / 0.1); box-shadow: inset 3px 0 0 var(--coral-700); }
  :global(:root[data-platform='mac']) .item.current, :global(:root[data-platform='mac']) .meeting.current { background: var(--coral-700); box-shadow: none; color: #fff; }
  :global(:root[data-platform='mac']) .item.current :global(svg) { color: #fff; }
  :global(:root[data-platform='mac']) .meeting.current .when, :global(:root[data-platform='mac']) .meeting.current .l2 { color: rgb(255 255 255 / 0.85); }
  .foot { flex: none; display: flex; flex-direction: column; gap: 4px; margin: 0 -8px; padding: 8px 8px 0; border-top: 1px solid var(--line); }
  .status { display: flex; align-items: baseline; gap: 6px; padding: 0 8px; font-size: var(--ui-small); color: var(--ink-500); }
  .status :global(svg) { flex: none; align-self: center; }
  .dot { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--ink-300); }
  .dot.on { background: var(--ok); }

  /* The toolbar: what the window shows, and the one thing that is always at hand. */
  .content { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; background: var(--canvas); }
  header { flex: none; display: flex; align-items: center; gap: 8px; height: var(--bar-h); padding: 0 12px; background: var(--surface); border-bottom: 1px solid var(--line); }
  /* Without the sidebar, the Mac's three buttons are over the toolbar. */
  :global(:root[data-platform='mac']) header.alone { padding-left: 84px; }
  .tool { display: inline-grid; place-items: center; flex: none; width: 32px; height: 28px; border: 0; border-radius: var(--ctl-r); background: transparent; color: var(--ink-700); }
  .tool:hover { background: rgb(0 0 0 / 0.06); }
  .titles { min-width: 0; }
  .titles:has(+ #title:not(:empty)) { display: none; }
  #title { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .title { font-weight: 700; font-size: calc(var(--ui) + 1px); line-height: 1.2; white-space: nowrap; }
  .sub { font-size: var(--ui-small); color: var(--ink-500); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .rec::before { content: ''; width: 9px; height: 9px; border-radius: 50%; background: #fff; }
  .rec { background: var(--coral-700); border-color: var(--coral-800); color: #fff; font-weight: 600; }
  #tools { display: flex; align-items: center; min-width: 0; }
  main { flex: 1 1 auto; min-height: 0; overflow: auto; }

  .strip { position: fixed; inset: 0 0 auto 0; height: 0; z-index: 1; }
  :global(:root[data-platform='mac']) .strip { height: 40px; }
  /* The Mac's window has no title bar: these move it. A control inside one still takes its click. */
  :global(:root[data-platform='mac']) .drag { -webkit-app-region: drag; }
  :global(:root[data-platform='mac']) .drag :global(button) { -webkit-app-region: no-drag; }
</style>
