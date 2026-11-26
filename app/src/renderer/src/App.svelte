<script lang="ts">
  import { NO_DOC, type Agenda as Headings, type Command, type DocState, type Job, type MeetingRow, type Progress, type Project, type RecordCommand, type RecordStatus, type SeriesRef, type Settings as Kept, type StommenState } from '../../shared/types'
  import Icon from './lib/Icon.svelte'
  import { accelerators, spell } from '../../shared/keys'
  import { brief, clock, count, failure, KINDS, overdue, shortDate, standing } from './lib/format'
  import type { About, View } from './lib/view'
  import Agenda from './views/Agenda.svelte'
  import OpenPoints from './views/OpenPoints.svelte'
  import NewProject from './lib/NewProject.svelte'
  import RecordDialog from './lib/RecordDialog.svelte'
  import Overview from './views/Overview.svelte'
  import Protocol from './views/Protocol.svelte'
  import Onboarding from './views/Onboarding.svelte'
  import Palette, { type Entry } from './lib/Palette.svelte'
  import Working, { STEPS, type Run } from './views/Working.svelte'

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
  let meeting = $state<About>({ title: '', edited: false, standing: '' })
  let doc = $state<DocState>({ ...NO_DOC, inspector: localStorage.getItem('inspector') !== 'hidden' })
  // Where the keys go: the menu leaves a field its own (Enter, the space bar), and another window's keys alone.
  let typing = $state(true)
  $effect(() => {
    // After the event: a field taken off the page loses the focus while the page is being drawn.
    const see = (): void => queueMicrotask(() => { typing = !document.hasFocus() || Boolean(document.activeElement?.closest('input, textarea, select, button, a, summary, dialog')) })
    const on = ['focusin', 'focusout', 'focus', 'blur'] as const
    for (const e of on) window.addEventListener(e, see)
    see()
    return () => { for (const e of on) window.removeEventListener(e, see) }
  })
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
    if (to.name === 'protocol') meeting = { title: '', edited: false, standing: '' }
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

  // What Windows' status bar says of the view (a protocol says its own, Protocol.svelte), and the window's title:
  // on Windows that is where the view is named, on the Mac it is what the Fönster menu and Mission Control call it.
  const said = $derived.by((): string[] => {
    const only = view.name === 'agenda' ? view.series.id : null // an agenda is one mötesserie's
    const points = (agendas ?? []).flatMap((a) => (only && a.series !== only ? [] : a.headings.flatMap((h) => h.open)))
    const late = points.filter((x) => overdue(x.due)).length
    const left = [count(points.length, 'öppen punkt', 'öppna punkter'), ...(late ? [late === 1 ? '1 förfallen' : `${late} förfallna`] : [])]
    if (!project || view.name === 'protocol') return []
    if (view.name === 'overview') return [count(rows.length, 'möte', 'möten'), left[0]]
    if (view.name === 'points') return left
    if (view.name === 'agenda') {
      const a = agendas?.find((x) => x.series === only)
      return a ? [count(a.headings.length, 'rubrik', 'rubriker'), ...left] : []
    }
    const run = runs.find((r) => r.id === shown)
    if (!run) return []
    return [run.problem ? `${run.job.title} gick inte att skriva ut` : run === runs.find((r) => !r.problem) ? `${run.job.title} skrivs ut · steg ${run.at + 1} av ${STEPS.length}` : `${run.job.title} väntar på sin tur`]
  })
  $effect(() => {
    const dir = view.name === 'protocol' ? view.dir : ''
    const what = view.name === 'overview' ? 'Översikt' : view.name === 'points' ? 'Öppna punkter' : view.name === 'agenda' ? `Dagordning inför ${view.series.name.toLowerCase()} ${view.series.next}`
      : view.name === 'working' ? view.job.title : (rows.find((r) => r.dir === dir)?.title ?? (meeting.title || 'Protokoll'))
    document.title = settings?.setUp && project ? `${what} – ${project.name} – Byggmöte` : 'Byggmöte'
  })

  const PROTOCOL: Command[] = ['saveDocx', 'savePdf', 'saveMd', 'copyText', 'find', 'inspector', 'newPoint', 'nextCheck', 'rename', 'rewrite', 'send',
    'editPoint', 'removePoint', 'nameSpeakers', 'attend', 'play', 'listen', 'back', 'forward', 'confirmation']

  /** A choice in the application menu, or its shortcut. The menu greys out what cannot run; this refuses it too. */
  function command(c: Command): void {
    if (c === 'sidebar') return showSidebar(!sidebar)
    if (!settings?.setUp) return
    // The open points have a search of their own, which is theirs (OpenPoints.svelte): the key finds it there.
    if (c === 'find' && view.name === 'points') return document.querySelector<HTMLInputElement>('#tools input[type=search]')?.focus()
    if (c === 'reveal') return view.name === 'protocol' ? void window.api.meetingShow(view.dir) : undefined
    if (PROTOCOL.includes(c)) return view.name === 'protocol' ? protocol?.command(c) : undefined
    const first = project?.series[0]
    if (c === 'settings') void window.api.settingsOpen()
    else if (c === 'palette') palette?.show()
    else if (c === 'shortcuts') palette?.show('Kommandon')
    else if (c === 'switchProject') palette?.show('Projekt')
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

  // The palette lists what the app can do, greyed with the reason when it cannot now, then the project's open
  // points and meetings, the views and the other projects.
  let palette = $state<{ show: (only?: string) => void }>()
  const mac = window.api.platform === 'darwin'
  const k = (onMac: string, elsewhere: string): string => (mac ? onMac : elsewhere)
  const entries = $derived.by((): Entry[] => {
    const inDoc = view.name === 'protocol'
    const cmd = (label: string, c: Command, keys?: string, off?: string | false): Entry => ({ group: 'Kommandon', label, keys, off: off || undefined, run: () => command(c) })
    // What is done to a protocol: only with one in the window, and then only when it can be (`can`, with why not).
    const about = (label: string, c: Command, keys: string | undefined, can: boolean, why: string): Entry => cmd(label, c, keys, !inDoc ? 'Bara i ett protokoll' : !can && why)
    const taped = live?.phase === 'recording' || live?.phase === 'paused'
    const recKeys = accelerators(settings?.shortcuts ?? {}, mac)
    const rec = (label: string, c: RecordCommand, keys: string | undefined, off?: string | false): Entry =>
      ({ group: 'Kommandon', label, keys, off: !taped ? 'Bara under inspelning' : off || undefined, run: () => void window.api.recordCommand(c) })
    const marked = (c: 'decision' | 'todo' | 'changeOrder' | 'question'): Entry => rec(`Sätt märke: ${KINDS[c]}`, c, spell(recKeys[c], mac), live?.phase === 'paused' && 'Inspelningen är pausad')
    const noSeries = !project?.series.length && 'Projektet har ingen mötesserie'
    const fixed = 'Protokollet går inte att ändra'
    const list: Entry[] = [
      cmd(live ? 'Visa inspelningsfönstret' : 'Spela in möte…', 'record', k('⌘R', 'Ctrl+R'), !project ? 'Inget projekt' : noSeries),
      rec(live?.phase === 'paused' ? 'Fortsätt' : 'Pausa', 'pause', spell(recKeys.pause, mac)),
      rec(live?.next ? `Nästa rubrik: ${live.next}` : 'Nästa rubrik', 'next', spell(recKeys.next, mac), !live?.next && 'Mötet har ingen rubrik kvar'),
      marked('decision'), marked('todo'), marked('changeOrder'), marked('question'),
      rec('Avsluta mötet', 'finish', k('⇧⌘R', 'Ctrl+Skift+R')),
      rec('Avbryt inspelningen…', 'cancel', undefined),
      cmd('Lägg till en inspelning…', 'addRecording', k('⌘O', 'Ctrl+O'), !project ? 'Inget projekt' : noSeries),
      about('Ny punkt', 'newPoint', k('⌘N', 'Ctrl+N'), doc.free, fixed),
      about('Nästa att kontrollera', 'nextCheck', k('⌘J', 'Ctrl+J'), doc.protocol, 'Mötet har inget protokoll'),
      about('Sätt namn på talare…', 'nameSpeakers', undefined, doc.unnamed, 'Alla talare har namn'),
      about('Lägg till som närvarande…', 'attend', undefined, doc.absent, 'Ingen att lägga till'),
      about('Sök i utskriften', 'find', k('⌘F', 'Ctrl+F'), true, ''),
      about(doc.inspector ? 'Dölj utskriften' : 'Visa utskriften', 'inspector', k('⌥⌘I', 'Ctrl+I'), true, ''),
      about('Spara som Word…', 'saveDocx', k('⇧⌘S', 'Ctrl+Skift+S'), doc.protocol, 'Mötet har inget protokoll'),
      about('Spara som PDF…', 'savePdf', undefined, doc.protocol, 'Mötet har inget protokoll'),
      about('Spara som Markdown…', 'saveMd', undefined, doc.protocol, 'Mötet har inget protokoll'),
      about('Kopiera texten', 'copyText', k('⇧⌘C', 'Ctrl+Skift+C'), doc.protocol, 'Mötet har inget protokoll'),
      about(k('Visa i Finder', window.api.platform === 'win32' ? 'Visa i Utforskaren' : 'Visa i mappen'), 'reveal', undefined, true, ''),
      about('Byt namn på mötet…', 'rename', undefined, doc.protocol, 'Mötet har inget protokoll'),
      about('Skriv om protokollet…', 'rewrite', undefined, doc.free, fixed),
      about('Skicka till Stommen…', 'send', k('⌘⏎', 'Ctrl+Enter'), doc.sendable, 'Går inte att skicka nu'),
      about('Se efter om det är justerat', 'confirmation', undefined, doc.sent, 'Inte skickat till Stommen'),
      cmd('Hämta från Stommen', 'sync', k('⇧⌘U', 'F5'), !stommen?.connected && 'Stommen är inte kopplat'),
      cmd('Nytt projekt…', 'newProject', k('⇧⌘N', 'Ctrl+Skift+N')),
      cmd(sidebar ? 'Dölj sidopanelen' : 'Visa sidopanelen', 'sidebar', k('⌃⌘S', 'Ctrl+B')),
      cmd('Inställningar…', 'settings', k('⌘,', 'Ctrl+,')),
      cmd('Visa introduktionen', 'intro')
    ]
    list.sort((a, b) => Number(Boolean(a.off)) - Number(Boolean(b.off))) // what can run now comes first
    const points = `Öppna punkter i ${project?.name ?? ''}`
    for (const a of agendas ?? []) for (const h of a.headings) for (const pt of h.open) {
      const from = rows.find((r) => r.series === a.series && r.no === Number(pt.no.split('.')[0]))
      list.push({ group: points, label: `${pt.no} ${pt.text}`, detail: [from?.title, KINDS[pt.kind]].filter(Boolean).join(' · '), run: () => go(from ? { name: 'protocol', dir: from.dir } : { name: 'points' }) })
    }
    for (const r of rows) list.push({ group: 'Möten', label: r.title, detail: `${shortDate(r.recorded_at)} · ${standing(r).text}`, run: () => go({ name: 'protocol', dir: r.dir }) })
    const to = (label: string, c: Command, n: number, off?: string | false): Entry => ({ group: 'Gå till', label, keys: k(`⌘${n}`, `Ctrl+${n}`), off: off || undefined, run: () => command(c) })
    if (project) list.push(to('Översikt', 'overview', 1), to('Öppna punkter', 'points', 2), to('Dagordning', 'agenda', 3, noSeries))
    for (const x of projects) if (x.id !== project?.id) list.push({ group: 'Projekt', label: x.name, detail: x.stommen ? 'Från Stommen' : undefined, run: () => choose(x.id) })
    return list
  })
  $effect(() => {
    void window.api.menuState({
      ready: loaded && Boolean(settings?.setUp), held: false, project: Boolean(project), series: Boolean(project?.series.length),
      connected: Boolean(stommen?.connected), sidebar, meeting: view.name === 'protocol', typing,
      view: view.name === 'overview' || view.name === 'points' || view.name === 'agenda' ? view.name : '',
      ...(view.name === 'protocol' ? doc : { ...NO_DOC, inspector: doc.inspector })
    })
  })
</script>

{#if settings && !settings.setUp}
  <div class="strip drag"></div>
  <Onboarding {settings} {stommen} changed={(s) => (settings = s)} stommenChanged={(s) => (stommen = s)} refresh={load} done={() => (view = { name: 'overview' })} />
{:else}
{#snippet rec()}
  {#if live}
    <button class="btn rec" onclick={() => window.api.recordShow()}>{live.phase === 'paused' ? 'Pausad' : 'Spelar in'} {clock(live.seconds)}</button>
  {:else if project?.series.length}
    <button class="btn rec" onclick={record}>Spela in</button>
  {/if}
{/snippet}
{#snippet toggle()}
  <button class="tool" aria-label={sidebar ? 'Dölj sidopanelen' : 'Visa sidopanelen'} title={sidebar ? 'Dölj sidopanelen' : 'Visa sidopanelen'} aria-pressed={sidebar} onclick={() => showSidebar(!sidebar)}>
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><rect x="1.5" y="2.5" width="13" height="11" rx={mac ? 2.5 : 1.5} /><path d="M6 2.5v11" /></svg>
  </button>
{/snippet}
<!-- Where the app stands with Stommen, the way to Inställningar, and the promise: the Mac's sidebar foot, Windows' status bar. -->
{#snippet standingWith()}
  <span class="with"><span class="dot" class:on={stommen?.connected}></span>{stommen?.connected ? `Stommen: ${stommen.user}` : 'Stommen är inte kopplat'}</span>
{/snippet}
{#snippet gear()}
  <button class="quiet" aria-label="Inställningar" title="Inställningar" onclick={() => window.api.settingsOpen()}>
    <Icon name="gear" size={13} />
  </button>
{/snippet}
{#snippet lock()}
  <svg width="12" height="13" viewBox="0 0 12 13" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><rect x="2" y="5.5" width="8" height="6" rx="1.5" /><path d="M4 5.5V4a2 2 0 0 1 4 0v1.5" /></svg>
{/snippet}

<div class="shell">
  {#if sidebar}
  <aside>
    <!-- On the Mac the window's three buttons sit here, and the strip moves the window. -->
    {#if mac}<div class="side-top drag"><span class="grow"></span>{@render toggle()}</div>{/if}

    {#if projects.length}
      <div class="pick">
        <label class="sr-only" for="project">Projekt</label>
        <select id="project" class="popup" value={project?.id}
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
      </div>
    {/if}

    <nav aria-label="Huvudmeny">
      {#if projects.length}
        <p class="side-head">Projektet</p>
        <button class="item" class:current={view.name === 'overview'} aria-current={view.name === 'overview' ? 'page' : undefined}
          onclick={() => go({ name: 'overview' })}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 7.5 8 2.5l5.5 5v6h-11z" /></svg> Översikt
        </button>
        <button class="item" class:current={view.name === 'points'} aria-current={view.name === 'points' ? 'page' : undefined}
          onclick={() => go({ name: 'points' })}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="5.5" /><path d="M8 5v3l2 1.5" /></svg> Öppna punkter {#if open}<span class="n">{open}</span>{/if}
        </button>
        {#each project?.series ?? [] as s (s.id)}
          {@const here = view.name === 'agenda' && view.series.id === s.id}
          <button class="item" class:current={here} aria-current={here ? 'page' : undefined} onclick={() => go({ name: 'agenda', series: s })}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" aria-hidden="true"><path d="M5.5 4h8M5.5 8h8M5.5 12h8M2.5 4h.5M2.5 8h.5M2.5 12h.5" /></svg> <span class="clip">Dagordning inför {s.name.toLowerCase()} {s.next}</span>
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
                <span class="l2">{standing(r).text} · {brief(r.duration)}</span>
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

    {#if mac}
      <div class="foot">
        {@render standingWith()}
        <span class="grow"></span>
        {@render gear()}
        <span class="promise" role="img" aria-label="Ljud och utskrift stannar på den här datorn" title="Ljud och utskrift stannar på den här datorn">{@render lock()}</span>
      </div>
    {/if}
  </aside>
  {/if}

  <!-- The Mac's toolbar: what the window shows, what is done in the view, and Spela in last. Windows' command bar,
       under its title and menu bars: Spela in first, then the view's commands; the window's title names the view. -->
  <header class="drag" class:alone={!sidebar}>
    {#if !sidebar}{@render toggle()}{/if}
    {#if !mac}{@render rec()}<span class="sep"></span>{/if}
    {#if mac && view.name === 'protocol' && project}
      <div class="titles">
        <p class="title">{meeting.title || 'Protokoll'}{#if meeting.edited}<span class="edited">Redigerat</span>{/if}</p>
        <p class="sub">{project.name}</p>
      </div>
    {/if}
    <!-- A view with a title of its own puts it here. -->
    <div id="title"></div>
    {#if mac && view.name === 'protocol' && meeting.standing}
      <span class="standing" class:done={meeting.standing === 'done'}><span></span>{meeting.standing === 'done' ? 'Justerat' : 'Utkast'}</span>
    {/if}
    {#if mac}<span class="grow"></span>{/if}
    <!-- A view puts what is done in it here (lib/tools.ts). -->
    <div id="tools"></div>
    {#if mac}{@render rec()}{/if}
  </header>

  {#if !mac}
    <footer class="statusbar">
      <!-- A view that says more of itself than the shell knows puts it here (lib/tools.ts). -->
      <div id="status">{#each said as x (x)}<span>{x}</span>{/each}</div>
      {@render standingWith()}
      <span class="grow"></span>
      {@render gear()}
      <span class="promise">{@render lock()} Ljud och utskrift stannar på den här datorn</span>
    </footer>
  {/if}

  <div class="content">
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
                about={(a) => (meeting = a)} state={(s) => (doc = s)} />
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
  /* The Mac: the sidebar from top to foot, the toolbar over the view. Windows: the command bar from edge to edge
     under the title and menu bars, the pane and the view as a lighter layer on it, the status bar at the foot. */
  .shell { --rule: #e4e3e9; --soft: #efeef3; display: grid; height: 100%; grid-template: 'bar bar' 48px 'side main' minmax(0, 1fr) 'status status' 26px / auto minmax(0, 1fr); background: var(--pane); }
  :global(:root[data-platform='mac']) .shell { grid-template: 'side bar' 52px 'side main' minmax(0, 1fr) / auto minmax(0, 1fr); }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  .grow { flex: 1 1 auto; }

  /* The sidebar: the project's library on the pane colour. Windows draws it as a navigation pane, the Mac as a source list. */
  aside { grid-area: side; width: 270px; display: flex; flex-direction: column; min-height: 0; padding: 4px; background: var(--pane); }
  :global(:root[data-platform='mac']) aside { width: 264px; padding: 0; border-right: 1px solid var(--rule); }
  .side-top { flex: none; display: flex; align-items: center; height: 52px; padding: 0 14px; }
  .pick { flex: none; padding: 4px 4px 6px; }
  :global(:root[data-platform='mac']) .pick { padding: 0 12px 4px; }
  .pick select { width: 100%; font-weight: 600; }
  /* The project's pop-up has the two arrows on Windows too, as it is drawn there. */
  .pick select { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='12' viewBox='0 0 10 12' fill='none' stroke='%236b6a77' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M2 4.5 5 1.5l3 3M2 7.5l3 3 3-3'/%3E%3C/svg%3E"); }
  nav { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
  :global(:root[data-platform='mac']) nav { padding: 0 8px; }
  .side-head { display: flex; align-items: center; justify-content: space-between; flex: none; height: 24px; margin-top: 10px; padding: 0 12px; font-size: var(--ui-small); font-weight: 600; color: var(--ink-500); }
  :global(:root[data-platform='mac']) .side-head { padding: 0 8px; }
  .pick + nav > .side-head:first-child { margin-top: 4px; }
  .side-head .count { font-weight: 400; }
  .item { position: relative; display: flex; align-items: center; gap: 12px; flex: none; height: var(--row-h); padding: 0 12px; border: 0; border-radius: var(--ctl-r); background: transparent; text-align: left; white-space: nowrap; }
  :global(:root[data-platform='mac']) .item { gap: 7px; padding: 0 8px; }
  .item :global(svg) { flex: none; color: var(--coral-700); }
  .item .n { margin-left: auto; font-size: var(--ui-small); color: var(--ink-500); }
  .item .clip { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  .item:hover:not(:disabled):not(.current), .meeting:hover:not(:disabled):not(.current) { background: rgb(0 0 0 / 0.04); }
  .library { flex: 1 1 auto; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; }
  :global(:root[data-platform='mac']) .library { margin: 0 -8px; padding: 0 8px 8px; }
  .meeting { display: flex; flex-direction: column; gap: 2px; flex: none; padding: 8px 12px; border: 0; border-bottom: 1px solid var(--soft); border-radius: 0; background: transparent; text-align: left; }
  .meeting .l1 { display: flex; align-items: baseline; gap: 8px; font-weight: 600; white-space: nowrap; }
  .meeting .name { overflow: hidden; text-overflow: ellipsis; }
  .meeting .when { margin-left: auto; font-weight: 400; font-size: var(--ui-small); color: var(--ink-500); }
  .meeting .bar { display: block; height: 3px; margin-top: 4px; border-radius: 2px; background: rgb(0 0 0 / 0.12); overflow: hidden; }
  .meeting .bar span { display: block; height: 100%; background: var(--coral-700); transition: width 0.3s; }
  :global(:root[data-platform='mac']) .meeting.current .bar { background: rgb(255 255 255 / 0.35); }
  :global(:root[data-platform='mac']) .meeting.current .bar span { background: #fff; }
  .meeting .l2 { font-size: var(--ui-small); color: var(--ink-500); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  /* The chosen row. Windows: a grey row with the accent pill at its edge, a meeting tinted with the accent bar. The Mac: solid accent. */
  .item.current { background: rgb(0 0 0 / 0.055); }
  .item.current::before { content: ''; position: absolute; left: 0; top: 10px; bottom: 10px; width: 3px; border-radius: 2px; background: var(--coral-700); }
  .meeting.current { background: rgb(201 58 66 / 0.12); box-shadow: inset 3px 0 0 var(--coral-700); border-radius: 4px; }
  :global(:root[data-platform='mac']) .item.current, :global(:root[data-platform='mac']) .meeting.current { background: var(--coral-700); box-shadow: none; color: #fff; }
  :global(:root[data-platform='mac']) .item.current { font-weight: 600; }
  :global(:root[data-platform='mac']) .item.current::before { content: none; }
  :global(:root[data-platform='mac']) .meeting.current { border-radius: var(--ctl-r); border-bottom-color: transparent; }
  :global(:root[data-platform='mac']) .item.current :global(svg), :global(:root[data-platform='mac']) .item.current .n { color: #fff; }
  :global(:root[data-platform='mac']) .meeting.current .when, :global(:root[data-platform='mac']) .meeting.current .l2 { color: rgb(255 255 255 / 0.85); }
  .foot { flex: none; display: flex; align-items: center; gap: 6px; padding: 8px 14px 10px; border-top: 1px solid var(--rule); font-size: var(--ui-small); color: var(--ink-500); white-space: nowrap; }
  .with { display: inline-flex; align-items: center; gap: 6px; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  .promise { display: inline-flex; align-items: center; gap: 6px; flex: none; }
  .dot { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--ink-400); }
  .dot.on { background: var(--ok); }
  .quiet { display: inline-grid; place-items: center; flex: none; width: 20px; height: 20px; padding: 0; border: 0; border-radius: 4px; background: transparent; color: inherit; -webkit-app-region: no-drag; }
  .quiet:hover { background: rgb(0 0 0 / 0.07); color: var(--ink-900); }

  /* The bar over the view. */
  header { grid-area: bar; display: flex; align-items: center; gap: 4px; min-width: 0; padding: 0 10px; background: var(--win-bg); border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }
  :global(:root[data-platform='mac']) header { gap: 8px; padding: 0 14px; background: #fbfafc; border-top: 0; }
  /* Without the sidebar, the Mac's three buttons are over the toolbar. */
  :global(:root[data-platform='mac']) header.alone { padding-left: 84px; }
  .tool { display: inline-grid; place-items: center; flex: none; width: 36px; height: 36px; border: 0; border-radius: var(--ctl-r); background: transparent; color: var(--ink-700); }
  :global(:root[data-platform='mac']) .tool { width: 32px; height: 28px; }
  .tool:hover { background: rgb(0 0 0 / 0.07); }
  .sep { flex: none; width: 1px; height: 24px; margin: 0 4px; background: var(--rule); }
  .sep:has(+ #title + #tools:empty), .sep:first-child { display: none; }
  .titles { min-width: 0; }
  .titles:has(+ #title:not(:empty)) { display: none; }
  #title { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .title { font-weight: 700; font-size: 15px; line-height: 1.2; white-space: nowrap; }
  .sub { font-size: var(--ui-small); color: var(--ink-500); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .rec { flex: none; background: var(--coral-700); border-color: var(--coral-800); color: #fff; font-weight: 600; }
  .rec::before { content: ''; width: 9px; height: 9px; border-radius: 50%; background: #fff; }
  .rec:hover:not(:disabled) { background: var(--coral-800); border-color: var(--coral-800); color: #fff; }
  :global(:root[data-platform='mac']) .rec { margin-left: 4px; }
  #tools { display: flex; align-items: center; flex: 1 1 auto; min-width: 0; }
  :global(:root[data-platform='mac']) #tools { flex: none; }
  .edited { margin-left: 7px; font-size: 12px; font-weight: 400; color: var(--ink-500); }
  .standing { display: inline-flex; align-items: center; gap: 5px; flex: none; height: 18px; margin-left: 6px; padding: 0 7px; border-radius: 9px; background: var(--warn-bg); font-size: var(--ui-small); font-weight: 500; white-space: nowrap; }
  .standing span { width: 7px; height: 7px; border-radius: 50%; background: var(--warn); }
  .standing.done { background: var(--ok-bg); }
  .standing.done span { background: var(--ok); }

  /* The view: on Windows a lighter layer on the pane, rounded where it meets the bar and the sidebar. */
  .content { grid-area: main; min-width: 0; min-height: 0; display: flex; flex-direction: column; background: var(--win-bg); border: 1px solid var(--rule); border-right: 0; border-bottom: 0; border-top-left-radius: 8px; overflow: hidden; }
  :global(:root[data-platform='mac']) .content { border: 0; border-radius: 0; background: var(--canvas); }
  main { flex: 1 1 auto; min-height: 0; overflow: auto; }

  .statusbar { grid-area: status; display: flex; align-items: center; gap: 16px; min-width: 0; padding: 0 12px; border-top: 1px solid var(--rule); background: var(--pane); font-size: 12px; color: var(--ink-500); white-space: nowrap; overflow: hidden; }
  #status { display: flex; align-items: center; gap: 16px; min-width: 0; }
  #status:empty { display: none; }

  .strip { position: fixed; inset: 0 0 auto 0; height: 0; z-index: 1; }
  :global(:root[data-platform='mac']) .strip { height: 40px; }
  /* The Mac's window has no title bar: these move it. A control inside one still takes its click. */
  :global(:root[data-platform='mac']) .drag { -webkit-app-region: drag; }
  :global(:root[data-platform='mac']) .drag :global(button) { -webkit-app-region: no-drag; }
</style>
