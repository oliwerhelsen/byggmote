<script lang="ts">
  import { tick } from 'svelte'
  import type { Command, Confirmation, Kind, MeetingDetail, NewPoint, Point, PointFields, Project } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import PointForm from '../lib/PointForm.svelte'
  import { clock, day, failure, KINDS, minutes, overdue } from '../lib/format'
  import { tools } from '../lib/tools'
  import type { Go } from '../lib/view'

  // `about`: what the window's toolbar says of the meeting. `state`: what the application menu can do with it now.
  let { project, dir, problem: handed, connected, go, refresh, about, state: tell }: {
    project: Project; dir: string; problem: string; connected: boolean; go: Go; refresh: () => Promise<void>
    about: (title: string, sub: string) => void
    state: (s: { protocol: boolean; free: boolean; sendable: boolean; inspector: boolean }) => void
  } = $props()

  let m = $state<MeetingDetail | null>(null)
  let problem = $state('')
  // svelte-ignore state_referenced_locally
  let wrote = $state(handed) // why the protocol was not written, when the transcript was: as handed over, then this view's own
  let sound = $state('')
  let player = $state<HTMLAudioElement>()
  let query = $state('')
  let active = $state<number | null>(null)
  let writing = $state(false)
  let stale = $state(false)
  let naming = $state<Record<string, string>>({})
  let finding = $state<Record<string, string>>({}) // what is typed in a speaker's search
  let open = $state<string | null>(null) // the speaker whose list is showing
  let editing = $state<string | null>(null) // the number of the point in its form
  let adding = $state<number | null>(null) // the heading a new point is written under
  let asking = $state(false) // whether to write over a person's corrections
  let present = $state('')
  let sending = $state<'' | 'ask' | 'busy'>('') // the protocol on its way to Stommen: asked about first, then sent
  let sendProblem = $state('')
  let asked = $state<'' | 'busy' | 'done'>('') // Stommen asked whether the sent protocol is justerat
  let copied = $state(false)
  let renaming = $state<string | null>(null) // the title while it is being written
  let saving = $state(false) // whether the Spara som menu is showing
  let inspector = $state(localStorage.getItem('inspector') !== 'hidden') // the transcript beside the protocol
  let at = $state<number | null>(null) // the heading chosen in the outline: a new point from the toolbar goes under it
  let seen = -1 // the check Nästa att kontrollera showed last

  const SAVE = [['docx', 'Word'], ['pdf', 'PDF'], ['md', 'Markdown']] as const

  /** The Spara som menu from the keyboard: arrows move between the formats, Escape closes it and gives the button the focus back. */
  function saveKeys(e: KeyboardEvent): void {
    const button = document.getElementById('save-as')
    if (e.key === 'Escape' && saving) {
      saving = false
      button?.focus()
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      saving = true
      void tick().then(() => {
        const items = [...document.querySelectorAll<HTMLElement>('#save-as-menu button')]
        const at = items.indexOf(document.activeElement as HTMLElement)
        items[(at + (e.key === 'ArrowDown' ? 1 : at < 0 ? 0 : -1) + items.length) % items.length]?.focus()
      })
    }
  }

  async function rename(): Promise<void> {
    const text = renaming?.trim()
    renaming = null
    if (!text || !m || text === m.title) return
    try {
      await window.api.setTitle(dir, text)
      await load()
    } catch (e) {
      problem = failure(e)
    }
  }

  /** The protocol as the Markdown file it also is: saved where the person says, or on the clipboard. */
  async function keep(how: 'docx' | 'pdf' | 'md' | 'copy'): Promise<void> {
    try {
      if (how !== 'copy') await window.api.protocolSave(dir, how)
      else {
        await window.api.protocolCopy(dir)
        copied = true
        setTimeout(() => (copied = false), 2000)
      }
    } catch (e) {
      problem = failure(e)
    }
  }

  async function load(): Promise<void> {
    try {
      m = await window.api.meeting(dir)
      problem = ''
      if (m.audio && !sound) {
        const bytes = await window.api.audio(dir)
        if (bytes) sound = URL.createObjectURL(new Blob([bytes as BlobPart], { type: 'audio/mp4' }))
      }
    } catch (e) {
      problem = failure(e)
    }
  }
  // A sent protocol's Justering is asked for when the meeting is opened, and again when the person asks. On opening
  // a failure is quiet and the last known state stays; only the person's own ask says what went wrong.
  void load().then(() => {
    if (connected && m?.stommen?.sent_at) void look(true)
  })

  async function look(quiet = false): Promise<void> {
    asked = 'busy'
    if (!quiet) sendProblem = ''
    try {
      await window.api.stommenConfirmation(dir)
      await load()
      asked = 'done'
    } catch (e) {
      if (!quiet) sendProblem = failure(e)
      asked = ''
    }
  }

  $effect(() => () => {
    if (sound) URL.revokeObjectURL(sound)
  })

  const p = $derived(m?.protocol ?? null)
  const series = $derived(project.series.find((s) => s.id === (m?.series ?? p?.series)) ?? project.series[0])
  // Until the person words a title of their own it is the one the series gave: its name and number.
  const renamed = $derived(Boolean(m && p && m.title.toLowerCase() !== `${p.name} ${p.no}`.toLowerCase()))
  const unnamed = $derived(m ? m.speakers.filter((s) => !s.person && /^Talare \d+$/.test(s.name)) : [])
  const shown = $derived.by(() => {
    const q = query.trim().toLowerCase()
    return m ? m.lines.filter((l) => !q || l.text.toLowerCase().includes(q) || l.who.toLowerCase().includes(q)) : []
  })
  const checks = $derived(p ? p.points.reduce((n, x) => n + x.checks.filter((c) => c.code === 'role' || !c.confirmed).length, 0) : 0)
  // A protocol is corrected while it is a draft and no later meeting builds on it: the engine refuses anything else.
  const draft = $derived(p?.status === 'draft')
  const confirmed = $derived(m?.stommen?.confirmed ?? null) // justerat in Stommen: final, a change is a new version there
  const free = $derived(draft && m?.later === null && !confirmed)
  const roles = $derived(project.roles)
  const pointable = $derived(p ? p.headings.filter((h) => !h.fill) : [])
  const pointer = $derived(m && active !== null ? (m.lines.find((l) => l.id === active) ?? null) : null)
  const silent = $derived(p ? project.people.filter((x) => !p.attendees.some((a) => a.name === x.name)) : [])

  /** Play from where a point is said, and show the line. */
  function listen(at: number, line: number | null): void {
    active = line
    if (line !== null) {
      query = ''
      requestAnimationFrame(() => document.getElementById(`line-${line}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }))
    }
    if (player && sound) {
      player.currentTime = at
      void player.play()
    }
  }

  async function write(discard = false): Promise<void> {
    if (!series) return
    if (m?.corrections && !discard) {
      asking = true // a model does not write over what a person has set right without a yes
      return
    }
    asking = false
    editing = adding = null
    writing = true
    wrote = ''
    try {
      await window.api.writeProtocol(dir, series.id, discard)
      stale = false
      await load()
    } catch (e) {
      wrote = failure(e)
    } finally {
      writing = false
    }
  }

  async function name(speaker: string): Promise<void> {
    if (!naming[speaker]) return
    try {
      await window.api.nameSpeaker(dir, speaker, naming[speaker])
      stale = Boolean(p)
      await load()
    } catch (e) {
      problem = failure(e)
    }
  }


  /** People in the Projekt that match what is typed, by name or Roll. */
  function matches(speaker: string) {
    const q = (finding[speaker] ?? '').trim().toLowerCase()
    return project.people.filter((x) => !q || `${x.name} ${x.role ?? ''}`.toLowerCase().includes(q))
  }

  /** Whether what is typed is a new person, which a Projekt of our own can add on the spot. */
  function addable(speaker: string): boolean {
    const q = (finding[speaker] ?? '').trim().toLowerCase()
    return Boolean(q) && !project.stommen && !project.people.some((x) => x.name.toLowerCase() === q)
  }

  function pick(speaker: string, id: string, label: string): void {
    naming[speaker] = id
    finding[speaker] = label
    open = null
  }

  /** Adds the typed name to the Projekt and names the speaker with it. */
  async function addAndName(speaker: string): Promise<void> {
    const typed = (finding[speaker] ?? '').trim()
    try {
      await window.api.personAdd(project.id, typed, '')
      const added = (await window.api.projects()).projects.find((x) => x.id === project.id)?.people.find((x) => x.name === typed)
      if (!added) throw new Error('Personen hittades inte efter att den lades till')
      await window.api.nameSpeaker(dir, speaker, added.id)
      stale = Boolean(p)
      open = null
      await refresh()
      await load()
    } catch (e) {
      problem = failure(e)
    }
  }

  /** A correction from a button: the engine makes it and the meeting is read again. */
  async function correct(run: Promise<void>): Promise<void> {
    try {
      await run
      problem = ''
      await load()
    } catch (e) {
      problem = failure(e)
    }
  }

  /** Leave a form, and put the focus back where the person was. */
  function close(id: string): void {
    editing = adding = null
    void tick().then(() => document.getElementById(id)?.focus())
  }

  // From a form: what goes wrong is thrown back to it, and shown there.
  async function change(no: string, fields: PointFields): Promise<void> {
    await window.api.changePoint(dir, no, fields)
    close(`edit-${no}`)
    await load()
  }

  async function add(fields: NewPoint): Promise<void> {
    await window.api.addPoint(dir, fields)
    close(`add-${fields.heading}`)
    await load()
  }

  async function remove(x: Point): Promise<void> {
    await window.api.removePoint(dir, x.no)
    close(`add-${x.heading}`)
    await load()
  }

  function attend(): void {
    if (!present) return
    void correct(window.api.attend(dir, present, false))
    present = ''
  }

  const WHEN = new Intl.DateTimeFormat('sv-SE', { dateStyle: 'long', timeStyle: 'short' })
  const ON = new Intl.DateTimeFormat('sv-SE', { dateStyle: 'long', timeZone: 'UTC' })
  // As Stommen words them.
  const HOW: Record<Confirmation['method'], string> = { next_meeting: 'på nästa byggmöte', email: 'per e-post', signed: 'signerat' }
  const standing = $derived(m?.stommen ?? null)

  async function send(): Promise<void> {
    sending = 'busy'
    sendProblem = ''
    try {
      await window.api.stommenSend(dir)
      await load()
    } catch (e) {
      sendProblem = failure(e)
      await load() // justerat meanwhile: the main process has asked Stommen by whom and when
    } finally {
      sending = ''
    }
  }

  function showInspector(on: boolean): void {
    inspector = on
    localStorage.setItem('inspector', on ? 'shown' : 'hidden')
  }

  /** The outline: a heading is brought to the top of the page. */
  function reach(no: number): void {
    at = no
    document.getElementById(`h-${no}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }

  /** A new point from the toolbar or the menu: under the heading chosen in the outline, else the first that takes points. */
  function newPoint(): void {
    const h = pointable.find((x) => x.no === at) ?? pointable[0]
    if (!free || !h) return
    editing = null
    adding = h.no
    void tick().then(() => document.getElementById(`h-${h.no}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' }))
  }

  /** The next thing to read against the recording, round and round. */
  function nextCheck(): void {
    const all = [...document.querySelectorAll<HTMLElement>('.document .check')]
    if (!all.length) return
    seen = (seen + 1) % all.length
    all[seen].scrollIntoView({ block: 'center', behavior: 'smooth' })
    all[seen].querySelector<HTMLElement>('button')?.focus({ preventScroll: true })
  }

  const sendable = $derived(Boolean(connected && p && standing && standing.why === null && !confirmed && (!standing.sent_at || standing.changed)))

  /** A choice in the application menu that is about the protocol. */
  export function command(c: Command): void {
    if (c === 'inspector') showInspector(!inspector)
    else if (c === 'find') {
      showInspector(true)
      void tick().then(() => document.getElementById('find')?.focus())
    } else if (!p) return
    else if (c === 'saveDocx') void keep('docx')
    else if (c === 'savePdf') void keep('pdf')
    else if (c === 'saveMd') void keep('md')
    else if (c === 'copyText') void keep('copy')
    else if (c === 'nextCheck') nextCheck()
    else if (c === 'rename') renaming = m?.title ?? ''
    else if (c === 'newPoint') newPoint()
    else if (c === 'rewrite' && series && free && !writing) void write()
    else if (c === 'send' && sendable && sending === '') {
      showInspector(true)
      sending = 'ask'
    }
  }

  $effect(() => {
    if (m) about(p && !renamed ? `${p.name} ${p.no}` : m.title, `${day(m.recorded_at)} · ${minutes(m.duration)} · ${m.speakers.length === 1 ? 'en talare' : `${m.speakers.length} talare`}`)
  })
  $effect(() => tell({ protocol: Boolean(p), free: Boolean(free), sendable, inspector }))
  $effect(() => () => tell({ protocol: false, free: false, sendable: false, inspector: true }))

  const count = (no: number): number => (p ? p.points.filter((x) => x.heading === no).length : 0)
  const unchecked = (no: number): boolean => Boolean(p?.points.some((x) => x.heading === no && x.checks.some((c) => c.code === 'role' || !c.confirmed)))

  const tone: Partial<Record<Kind, string>> = { decision: 'ok', risk: 'warn' }
  const icon = (k: Kind): 'check' | 'alert' | 'flag' => (k === 'decision' ? 'check' : k === 'risk' ? 'alert' : 'flag')
  const sentence = (t: string): string => (/[.!?]$/.test(t) ? t : `${t}.`)
  const under = (no: number): Point[] => (p ? p.points.filter((x) => x.heading === no) : [])
</script>

<div class="doc" class:bare={!m}>
  {#if problem && !m}
    <div class="page">
      <div class="note bad" role="alert">
        <Icon name="alert" />
        <div>
          <p><strong>Det gick inte att läsa mötet.</strong></p>
          <p class="small mono">{problem}</p>
          <button class="btn" style="margin-top: 12px" onclick={() => go({ name: 'overview' })}>Till översikten</button>
        </div>
      </div>
    </div>
  {:else if !m}
    <div class="page"><p class="muted">Läser in mötet.</p></div>
  {:else}
    <!-- What is done to the protocol, in the window's toolbar. -->
    <div class="tools" use:tools>
      {#if p && free && pointable.length}
        <button class="btn" disabled={adding !== null} onclick={newPoint}><Icon name="plus" size={16} /> Ny punkt</button>
      {/if}
      {#if p && checks}
        <button class="btn" onclick={nextCheck}><Icon name="alert" size={16} /> Nästa att kontrollera <span class="n">{checks}</span></button>
      {/if}
      {#if p}
        <div class="menu" onfocusout={(e) => !e.currentTarget.contains(e.relatedTarget as Node | null) && (saving = false)}
          onkeydown={saveKeys} role="presentation">
          <button id="save-as" class="btn" aria-haspopup="menu" aria-expanded={saving} aria-controls="save-as-menu" onclick={() => (saving = !saving)}>
            <Icon name="file" size={16} /> Spara som <Icon name="down" size={14} />
          </button>
          {#if saving}
            <ul class="options" id="save-as-menu" role="menu" aria-labelledby="save-as">
              {#each SAVE as [how, label] (how)}
                <li role="none"><button type="button" role="menuitem" onclick={() => { saving = false; void keep(how) }}>{label}</button></li>
              {/each}
              <li role="none" class="rule"><button type="button" role="menuitem" onclick={() => { saving = false; void keep('copy') }}>Kopiera texten</button></li>
            </ul>
          {/if}
        </div>
        {#if copied}<span class="small muted" role="status">Kopierat</span>{/if}
      {/if}
      <button class="btn only" aria-label={inspector ? 'Dölj utskriften' : 'Visa utskriften'} aria-pressed={inspector} onclick={() => showInspector(!inspector)}>
        <Icon name="inspector" size={17} />
      </button>
    </div>

    {#if p}
      <nav class="outline" aria-label="Rubriker">
        <p class="side-head"><span>Rubriker</span><span>{p.points.length === 1 ? '1 punkt' : `${p.points.length} punkter`}</span></p>
        {#each p.headings as h (h.no)}
          <button class:current={at === h.no} onclick={() => reach(h.no)}>
            <span class="no">{h.no}</span><span class="name">{h.name}</span>
            {#if unchecked(h.no)}<span class="mark" aria-label="Något att kontrollera"></span>{/if}
            {#if count(h.no)}<span class="count">{count(h.no)}</span>{/if}
          </button>
        {/each}
      </nav>
    {/if}

    <div class="middle">
      <div class="scroll">
      <div class="sheet stack">
        <div class="row title">
          {#if renaming !== null}
            <form class="row" onsubmit={(e) => { e.preventDefault(); void rename() }}>
              <input class="field" aria-label="Mötets namn" bind:value={renaming} onkeydown={(e) => e.key === 'Escape' && (renaming = null)} />
              <button class="btn" type="submit" disabled={!renaming.trim()}>Spara</button>
              <button class="btn" type="button" onclick={() => (renaming = null)}>Avbryt</button>
            </form>
          {:else}
            <h1>{p && !renamed ? `Protokoll, ${p.name.toLowerCase()} ${p.no}` : m.title}</h1>
            <button class="btn quiet" onclick={() => (renaming = m?.title ?? '')}><Icon name="edit" size={16} /> Byt namn</button>
          {/if}
          {#if p && series && free && renaming === null}
            <button class="btn quiet" disabled={writing} onclick={() => write()}><Icon name="refresh" size={16} /> Skriv om protokollet</button>
          {/if}
          {#if confirmed}<span class="badge"><Icon name="lock" size={14} /> Justerat</span>
          {:else if p?.status === 'draft'}<span class="badge"><Icon name="file" size={14} /> Utkast</span>{/if}
        </div>

        {#if problem}
          <div class="note bad" role="alert"><Icon name="alert" /><p class="small mono">{problem}</p></div>
        {/if}

        {#if writing}
          <div class="note" role="status"><Icon name="clock" /><p><strong>Protokollet skrivs.</strong> Det tar ungefär en minut för ett kort möte, längre för ett långt.</p></div>
        {:else if wrote}
          <div class="note bad" role="alert">
            <Icon name="alert" />
            <div><p><strong>Protokollet gick inte att skriva.</strong> Utskriften finns, så det går att försöka igen.</p><p class="small mono">{wrote}</p></div>
          </div>
        {:else if asking && m.corrections}
          <div class="note warn" role="alert">
            <Icon name="alert" />
            <div>
              <p>
                <strong>Protokollet har {m.corrections === 1 ? 'en rättning' : `${m.corrections} rättningar`}.</strong>
                {m.corrections === 1 ? 'Den' : 'De'} försvinner om modellen skriver om protokollet.
              </p>
              <div class="row" style="margin-top: 12px">
                <button class="btn" onclick={() => write(true)}>Skriv om ändå</button>
                <button class="btn primary" onclick={() => (asking = false)}>{m.corrections === 1 ? 'Behåll rättningen' : 'Behåll rättningarna'}</button>
              </div>
            </div>
          </div>
        {:else if stale && free && !m.corrections}
          <div class="note" role="status">
            <Icon name="person" />
            <p>
              <strong>Talarna har fått namn sedan protokollet skrevs.</strong> Närvarande är uppdaterade. Skriv om protokollet om modellen
              ska läsa utskriften med namnen.
            </p>
          </div>
        {/if}

        {#if unnamed.length}
          <section class="card" aria-labelledby="unnamed">
            <h2 id="unnamed">{unnamed.length === 1 ? 'En talare har inget namn' : `${unnamed.length} talare har inget namn`}</h2>
            <p class="muted">Lyssna på en rad och välj vem det är. Namnen styr vilka som står som närvarande, och med vilken Roll.</p>
            <ul class="speakers">
              {#each unnamed as s (s.id)}
                {@const first = m.lines.find((l) => l.speaker === s.id)}
                <li>
                  <div class="grow">
                    <p><strong>{s.name}</strong></p>
                    {#if first}<p class="small muted clamp">”{first.text}”</p>{/if}
                  </div>
                  {#if first}
                    <button class="time" aria-label="Lyssna på {s.name} från {clock(first.at)}" onclick={() => listen(first.at, first.id)}>
                      <span><Icon name="play" size={12} /> {clock(first.at)}</span>
                    </button>
                  {/if}
                  <div class="combo">
                    <input
                      class="field"
                      type="text"
                      role="combobox"
                      aria-label="Vem är {s.name}?"
                      aria-expanded={open === s.id}
                      aria-controls="who-{s.id}"
                      autocomplete="off"
                      placeholder="Sök eller skriv ett namn"
                      value={finding[s.id] ?? ''}
                      onfocus={() => (open = s.id)}
                      onblur={() => setTimeout(() => open === s.id && (open = null), 150)}
                      oninput={(e) => {
                        finding[s.id] = e.currentTarget.value
                        naming[s.id] = ''
                        open = s.id
                      }}
                    />
                    {#if open === s.id}
                      <ul class="options" id="who-{s.id}" role="listbox">
                        {#each matches(s.id) as person (person.id)}
                          <li role="option" aria-selected={naming[s.id] === person.id}>
                            <button type="button" onmousedown={(e) => e.preventDefault()} onclick={() => pick(s.id, person.id, person.name)}>
                              {person.name}{person.role ? `, ${person.role}` : ''}
                            </button>
                          </li>
                        {/each}
                        {#if addable(s.id)}
                          <li role="option" aria-selected="false">
                            <button type="button" class="add" onmousedown={(e) => e.preventDefault()} onclick={() => addAndName(s.id)}>
                              <Icon name="plus" size={14} /> Lägg till ”{(finding[s.id] ?? '').trim()}”
                            </button>
                          </li>
                        {:else if !matches(s.id).length}
                          <li class="small muted none">{project.stommen ? 'Ingen med det namnet. Personer läggs till i Stommen.' : 'Skriv ett namn för att lägga till.'}</li>
                        {/if}
                      </ul>
                    {/if}
                  </div>
                  <button class="btn" disabled={!naming[s.id]} onclick={() => name(s.id)}>Sätt namn</button>
                </li>
              {/each}
            </ul>
          </section>
        {/if}

        {#if !p}
          <section class="card">
            <h2>Mötet har inget protokoll än</h2>
            <p class="muted">Utskriften finns till höger. Protokollet skrivs från den, av en språkmodell på den här datorn.</p>
            {#if series}
              <button class="btn primary" style="margin-top: 16px" disabled={writing} onclick={() => write()}>Skriv protokollet</button>
            {:else}
              <p class="small muted" style="margin-top: 12px">Projektet behöver en mötesserie först. Den startas från Översikt.</p>
            {/if}
          </section>
        {:else}
          <div class="note">
            <Icon name="lock" />
            <p>
              Protokollet är skrivet från inspelningen av en språkmodell på den här datorn.
              {#if !standing?.sent_at}Inget har skickats ut.{/if}
              Varje punkt
              modellen har skrivit pekar på stället där det sades.
              {#if free}
                Läs igenom det mot inspelningen och rätta det som är fel innan det går vidare.
              {:else if confirmed}
                Det är justerat i Stommen, så punkterna går inte att ändra här längre.
              {:else if m.later !== null}
                {p.name} {m.later} bygger på det här protokollet, så punkterna går inte att ändra längre.
              {/if}
            </p>
          </div>
          {#if checks}
            <div class="note warn" role="status">
              <Icon name="alert" />
              <p>
                <strong>{checks === 1 ? 'En sak ska kontrolleras' : `${checks} saker ska kontrolleras`}</strong> mot inspelningen.
                {checks === 1 ? 'Den står under sin punkt.' : 'De står under sina punkter.'}
              </p>
            </div>
          {/if}

          <article class="document paper">
            {#each p.headings as h (h.no)}
              <section aria-labelledby="h-{h.no}">
                <div class="head">
                  <h2 id="h-{h.no}"><span class="mono muted">{h.no}</span> {h.name}</h2>
                  {#if free && !h.fill}
                    <button id="add-{h.no}" class="btn quiet" aria-label="Lägg till punkt under {h.name}" disabled={adding === h.no}
                      onclick={() => { editing = null; adding = h.no }}>
                      <Icon name="plus" size={16} /> Lägg till punkt
                    </button>
                  {/if}
                </div>
                {#if h.fill === 'attendees'}
                  {#if p.attendees.length}
                    <ul class="attendees">
                      {#each p.attendees as a}
                        <li>
                          <span>{a.name}{#if a.role}<span class="muted">, {a.role}</span>{/if}</span>
                          {#if a.added && a.person && draft}
                            <span class="small muted">Tillagd för hand</span>
                            <button class="btn quiet" aria-label="Ta bort {a.name} från närvarande" onclick={() => correct(window.api.attend(dir, a.person!, true))}>
                              Ta bort
                            </button>
                          {/if}
                        </li>
                      {/each}
                    </ul>
                  {:else}
                    <p class="muted">Ingen talare i inspelningen.</p>
                  {/if}
                  {#if draft && silent.length}
                    <div class="row" style="margin-top: 12px">
                      <select class="field" aria-label="Någon som var med utan att säga något" bind:value={present}>
                        <option value="">Var någon med utan att säga något?</option>
                        {#each silent as person (person.id)}
                          <option value={person.id}>{person.name}{person.role ? `, ${person.role}` : ''}</option>
                        {/each}
                      </select>
                      <button class="btn" disabled={!present} onclick={attend}>Lägg till som närvarande</button>
                    </div>
                  {/if}
                {:else}
                  {#each under(h.no) as x (x.no)}
                    <div class="point" class:selected={active !== null && active === x.line}>
                      <div class="top">
                        <span class="point-no">{x.no}</span>
                        <span class="badge {tone[x.kind] ?? ''}" class:plain={x.kind === 'note'}>
                          {#if x.kind !== 'note'}<Icon name={icon(x.kind)} size={14} />{/if}
                          {KINDS[x.kind]}
                        </span>
                        {#if x.since !== undefined}
                          <span class="small muted">{x.open ? 'Kvarstår' : 'Avslutad'}, från {p.name.toLowerCase()} {x.since}</span>
                        {/if}
                        {#if x.added}
                          <span class="small muted">Tillagd för hand</span>
                        {:else if x.edited}
                          <span class="small muted">Ändrad för hand</span>
                        {/if}
                        <span class="grow"></span>
                        {#if x.at !== null}
                          <button class="time" aria-label="Lyssna från {clock(x.at)}" onclick={() => listen(x.at!, x.line)}>
                            <span><Icon name="play" size={12} /> {clock(x.at)}</span>
                          </button>
                        {/if}
                        {#if free && editing !== x.no}
                          <button id="edit-{x.no}" class="btn quiet" aria-label="Ändra punkt {x.no}" onclick={() => { adding = null; editing = x.no }}>
                            <Icon name="edit" size={16} /> Ändra
                          </button>
                        {/if}
                      </div>
                      {#if editing === x.no && x.since === undefined}
                        <PointForm point={x} headings={pointable} {roles} series={p.name.toLowerCase()} change={(f) => change(x.no, f)}
                          remove={() => remove(x)} cancel={() => close(`edit-${x.no}`)} />
                      {:else}
                        <p>{sentence(x.text)}</p>
                        {#if editing === x.no}
                          <PointForm point={x} headings={pointable} {roles} series={p.name.toLowerCase()} change={(f) => change(x.no, f)}
                            cancel={() => close(`edit-${x.no}`)} />
                        {:else}
                          {#if x.since !== undefined}
                            {#if !x.raised}
                              <p class="follow muted">Togs inte upp på mötet.</p>
                            {:else if x.follow}
                              <p class="follow"><span class="muted">På mötet:</span> {sentence(x.follow)}</p>
                            {:else}
                              <p class="follow"><span class="muted">På mötet sägs:</span> ”{x.said}”</p>
                            {/if}
                          {/if}
                          {#if x.role || x.due}
                            <p class="small muted">
                              {#if x.role}Ansvarig: {x.role}.{/if}
                              {#if x.due}Senast {x.due}{#if x.open && overdue(x.due)}, förfallen{/if}.{/if}
                            </p>
                          {/if}
                        {/if}
                      {/if}
                      {#each x.checks as c, i}
                        {#if c.code === 'amount' && c.confirmed}
                          <div class="confirmed small muted">
                            <Icon name="check" size={14} />
                            <span>Beloppet {c.value} är kontrollerat mot inspelningen.</span>
                            {#if free}
                              <button class="btn quiet" aria-label="Ångra kontrollen av {c.value} i punkt {x.no}"
                                onclick={() => correct(window.api.confirmCheck(dir, x.no, i + 1, true))}>
                                Ångra
                              </button>
                            {/if}
                          </div>
                        {:else}
                          <div class="note warn check">
                            <Icon name="alert" size={16} />
                            <div class="grow">
                              {#if c.code === 'amount'}
                                <p><strong>Kontrollera beloppet {c.value}.</strong> I inspelningen sägs: ”{c.said}”</p>
                              {:else}
                                <p><strong>Rollen ”{c.said}” finns inte i projektet.</strong> Punkten har ingen ansvarig.</p>
                              {/if}
                              {#if free && editing !== x.no}
                                <div class="row answers">
                                  {#if c.code === 'amount'}
                                    <button class="btn" aria-label="Beloppet {c.value} i punkt {x.no} stämmer"
                                      onclick={() => correct(window.api.confirmCheck(dir, x.no, i + 1, false))}>
                                      <Icon name="check" size={16} /> Stämmer
                                    </button>
                                    <button class="btn" aria-label="Ändra beloppet i punkt {x.no}" onclick={() => { adding = null; editing = x.no }}>Ändra</button>
                                  {:else}
                                    <button class="btn" aria-label="Välj Roll för punkt {x.no}" onclick={() => { adding = null; editing = x.no }}>Välj Roll</button>
                                  {/if}
                                </div>
                              {/if}
                            </div>
                          </div>
                        {/if}
                      {/each}
                    </div>
                  {:else}
                    {#if adding !== h.no}<p class="muted">Inget noterat.</p>{/if}
                  {/each}
                  {#if adding === h.no}
                    <PointForm heading={h.no} headings={pointable} {roles} series={p.name.toLowerCase()} {pointer} {add} cancel={() => close(`add-${h.no}`)} />
                  {/if}
                {/if}
              </section>
            {/each}
          </article>

          {#if p.removed?.length}
            <details class="card" open>
              <summary>{p.removed.length === 1 ? 'En punkt är borttagen' : `${p.removed.length} punkter är borttagna`}</summary>
              <p class="muted small" style="margin: 8px 0 12px">
                En borttagen punkt står inte i protokollet och följer inte med till nästa möte. Den går att lägga tillbaka.
              </p>
              <ul class="dropped">
                {#each p.removed as x (x.no)}
                  <li class="row">
                    <p class="grow"><span class="point-no">{x.no}</span> {KINDS[x.kind]}. {sentence(x.text)}</p>
                    {#if free}
                      <button class="btn" aria-label="Lägg tillbaka punkt {x.no}" onclick={() => correct(window.api.restorePoint(dir, x.no))}>
                        <Icon name="undo" size={16} /> Lägg tillbaka
                      </button>
                    {/if}
                  </li>
                {/each}
              </ul>
            </details>
          {/if}

          {#if p.dropped.length}
            <details class="card">
              <summary>
                {p.dropped.length === 1 ? 'Ett förslag från modellen togs inte med' : `${p.dropped.length} förslag från modellen togs inte med`}
              </summary>
              <p class="muted small" style="margin: 8px 0 12px">Det som inte går att hitta i utskriften visas inte i protokollet. Här står vad modellen föreslog.</p>
              <ul class="dropped">
                {#each p.dropped as d}
                  <li>
                    <p>{d.text}</p>
                    <p class="small muted">
                      {d.reason === 'heading' ? 'Rubriken finns inte.' : d.reason === 'unknown-point' ? `Punkten ${d.no ?? ''} finns inte.` : 'Citatet finns inte i utskriften.'}
                      {#if d.quote}Modellens citat: ”{d.quote}”{/if}
                    </p>
                  </li>
                {/each}
              </ul>
            </details>
          {/if}
        {/if}
      </div>
      </div>
    </div>

    {#if inspector}
      <aside class="inspector">
        {#if p && standing && standing.why !== 'local'}
            <section class="to-stommen" aria-labelledby="to-stommen">
              <h2 id="to-stommen">Till Stommen</h2>
              {#if confirmed}
                <p>
                  <strong>Justerat {ON.format(new Date(`${confirmed.on}T00:00:00Z`))}</strong>, {HOW[confirmed.method] ?? confirmed.method}, av {confirmed.by}.
                </p>
              {/if}
              <p class="muted">
                {#if standing.sent_at}
                  Skickat {WHEN.format(new Date(standing.sent_at))}, version {standing.version}.
                  {#if standing.changed}Protokollet har ändrats sedan dess.{/if}
                {:else if !confirmed}
                  Protokollet är inte skickat.
                {/if}
              </p>
              {#if sendProblem}
                <div class="note bad" role="alert" style="margin-top: 12px"><Icon name="alert" /><p>{sendProblem}</p></div>
              {/if}
              {#if confirmed}
                <p style="margin-top: 12px">
                  Ett justerat protokoll rättas inte och skickas inte igen härifrån. Behöver det ändras, be om en ny version i Stommen.
                </p>
              {:else if standing.why === 'checks'}
                <p style="margin-top: 12px">
                  {standing.about === 1 ? 'En sak ska kontrolleras' : `${standing.about} saker ska kontrolleras`} innan protokollet kan skickas.
                </p>
              {:else if standing.why === 'role'}
                <p style="margin-top: 12px">
                  Rollen ”{standing.about}” finns inte längre i Stommen. Hämta projektet igen under Inställningar → Stommen, eller välj en annan Roll för punkten.
                </p>
              {:else if !connected}
                <p style="margin-top: 12px">Logga in i Stommen under Inställningar för att skicka protokollet.</p>
              {:else if sending === 'ask'}
                <div class="note" style="margin-top: 12px">
                  <Icon name="lock" />
                  <div>
                    <p>
                      Det här går till Stommen: protokollet med {p.points.length === 1 ? 'sin punkt' : `sina ${p.points.length} punkter`}, och för varje
                      punkt hur långt in i inspelningen det sades, raden som sades där och vem som sa den. Ljudet och resten av utskriften
                      stannar på den här datorn.
                    </p>
                    <div class="row" style="margin-top: 12px">
                      <button class="btn primary" onclick={send}>Skicka</button>
                      <button class="btn" onclick={() => (sending = '')}>Avbryt</button>
                    </div>
                  </div>
                </div>
              {:else if !standing.sent_at || standing.changed}
                <button class="btn primary" style="margin-top: 12px" disabled={sending === 'busy'} onclick={() => (sending = 'ask')}>
                  {sending === 'busy' ? 'Skickar' : standing.sent_at ? 'Skicka igen' : 'Skicka till Stommen'}
                </button>
              {/if}
              {#if connected && (standing.sent_at || confirmed) && sending !== 'ask'}
                <div class="row" style="margin-top: 12px">
                  <button class="btn" disabled={asked === 'busy'} onclick={() => look()}>
                    <Icon name="refresh" /> {asked === 'busy' ? 'Ser efter' : 'Se efter om det är justerat'}
                  </button>
                  {#if asked === 'done' && !confirmed}<span class="small muted" role="status">Inte justerat i Stommen än.</span>{/if}
                </div>
              {/if}
            </section>
          {/if}

        <section class="transcript" aria-labelledby="transcript">
          <h2 id="transcript">Utskrift</h2>
          <label class="search">
            <span class="sr">Sök i utskriften</span>
            <Icon name="search" size={15} />
            <input id="find" type="search" placeholder="Sök i utskriften" bind:value={query} />
          </label>
          <ol class="lines">
            {#each shown as l (l.id)}
              <li id="line-{l.id}" class:active={active === l.id}>
                <button class="time" aria-label="Lyssna från {clock(l.at)}" onclick={() => listen(l.at, l.id)}><span>{clock(l.at)}</span></button>
                <p><strong>{l.who}</strong> {l.text}</p>
              </li>
            {:else}
              <li><p class="muted">{m.lines.length ? 'Inget i utskriften stämmer med sökningen.' : 'Inspelningen har inget tal som gick att skriva ut.'}</p></li>
            {/each}
          </ol>
        </section>
      </aside>
    {/if}

    <!-- The recording, under the page and the transcript: a point or a line plays from where it is said. -->
    <footer class="transport">
      {#if sound}
        <audio bind:this={player} src={sound} controls preload="metadata"></audio>
      {:else}
        <p class="small muted">{m.audio ? 'Ljudet läses in.' : 'Mötet har inget ljud sparat.'}</p>
      {/if}
    </footer>
  {/if}
</div>

<style>
  /* A document window: the outline, the page on its grey desk, the transcript beside it, the recording under both. */
  .doc { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; grid-template-rows: minmax(0, 1fr) auto; height: 100%; }
  .doc.bare { display: block; }
  .tools { display: flex; align-items: center; gap: 6px; }
  .tools .n { display: inline-grid; place-items: center; min-width: 16px; height: 16px; padding: 0 4px; border-radius: 8px; background: var(--warn); color: #fff; font-size: 11px; font-weight: 600; }
  .tools .only { padding: 0; width: 32px; border-color: transparent; background: transparent; color: var(--ink-700); }
  .tools .only[aria-pressed='true'] { background: rgb(0 0 0 / 0.07); }

  .outline { grid-row: 1; width: 196px; display: flex; flex-direction: column; gap: 1px; padding: 8px; overflow-y: auto; background: var(--canvas); border-right: 1px solid var(--line); }
  .side-head { display: flex; justify-content: space-between; height: 24px; padding: 0 8px; font-size: var(--ui-small); font-weight: 600; color: var(--ink-500); }
  .side-head span:last-child { font-weight: 400; }
  .outline button { display: flex; align-items: center; gap: 8px; flex: none; height: var(--row-h); padding: 0 8px; border: 0; border-radius: var(--ctl-r); background: transparent; text-align: left; white-space: nowrap; }
  .outline button:hover:not(.current) { background: rgb(0 0 0 / 0.045); }
  .outline button.current { background: rgb(201 58 66 / 0.12); font-weight: 600; }
  .outline .no { flex: none; width: 16px; text-align: right; color: var(--ink-500); font-variant-numeric: tabular-nums; }
  .outline .name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  .outline .count { flex: none; font-size: var(--ui-small); color: var(--ink-500); font-weight: 400; }
  .outline .mark { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--warn); }

  .middle { grid-row: 1; min-width: 0; display: flex; flex-direction: column; background: #e9e8ee; }
  .scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: 20px 24px 28px; }
  .sheet { max-width: 800px; margin: 0 auto; }
  .title { gap: 8px; }
  .paper { background: var(--surface); box-shadow: 0 1px 4px rgb(0 0 0 / 0.18); padding: 36px 44px 44px; }
  .sheet :global(.note), .sheet :global(.card) { background-color: var(--surface); }
  .sheet :global(.note.warn) { background: var(--warn-bg); }
  .sheet :global(.note.bad) { background: var(--bad-bg); }

  .inspector { grid-row: 1; width: 320px; display: flex; flex-direction: column; min-height: 0; background: var(--canvas); border-left: 1px solid var(--line); }
  .to-stommen { flex: none; padding: 12px 14px; border-bottom: 1px solid var(--line); }
  .to-stommen h2, .transcript h2 { font: 600 var(--ui-small) var(--font-ui); letter-spacing: 0; color: var(--ink-500); margin-bottom: 6px; }
  .transcript { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; gap: 8px; padding: 12px 14px 0; }
  .transport { grid-column: 1 / -1; display: flex; align-items: center; min-height: 44px; padding: 4px 12px; background: var(--surface); border-top: 1px solid var(--line); }
  audio { width: 100%; height: 34px; }

  .document { display: flex; flex-direction: column; gap: 22px; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; min-height: var(--ctl-h); margin-bottom: 6px;
    border-bottom: 1px solid var(--line); scroll-margin-top: 12px; }
  section :global(h2[id^='h-']) { scroll-margin-top: 12px; }
  .head h2 { display: flex; gap: 10px; align-items: baseline; }
  /* One under every heading and on every point: quiet until it is wanted, so the document is what is read. */
  .head .btn, .top .btn { color: var(--ink-500); font-weight: 400; }
  .head .btn:hover:not(:disabled), .top .btn:hover:not(:disabled) { color: var(--coral-800); }
  .attendees { display: flex; flex-direction: column; gap: 2px; }
  .attendees li { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; min-height: 24px; }
  .point { display: flex; flex-direction: column; gap: 3px; padding: 4px 10px 8px; margin: 0 -10px; border-radius: var(--ctl-r); }
  .point.selected { background: var(--coral-50); box-shadow: inset 0 0 0 1px var(--coral-200); }
  .badge.plain { padding-left: 8px; }
  .top { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-height: var(--ctl-h); }
  .follow { padding-left: 10px; border-left: 2px solid var(--line); }
  .check { margin-top: 4px; padding: 6px 10px; align-items: center; }
  .check .grow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .check .grow p { flex: 1 1 240px; }
  .answers { gap: 6px; }
  .confirmed { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .confirmed :global(svg) { flex: none; color: var(--ok); }
  .point :global(.form) { margin: 4px 0 8px; }
  .speakers li { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 8px 0; border-bottom: 1px solid var(--line); }
  .combo { position: relative; min-width: 240px; }
  .menu { position: relative; }
  .menu .options { right: auto; min-width: 100%; }
  .combo .field { width: 100%; }
  .options { position: absolute; z-index: 20; top: calc(100% + 4px); left: 0; right: 0; max-height: 240px; overflow: auto; margin: 0; padding: 4px; list-style: none; background: var(--surface); border: 1px solid var(--edge); border-radius: 8px; box-shadow: 0 8px 24px rgb(0 0 0 / 0.16); }
  .options button { display: flex; align-items: center; gap: 6px; width: 100%; min-height: var(--ctl-h); padding: 0 10px; border: 0; border-radius: var(--ctl-r); background: none; text-align: left; font: inherit; }
  .options button:hover, .options button:focus-visible { background: rgb(0 0 0 / 0.06); }
  .options .add { font-weight: 500; }
  .options .rule { margin-top: 4px; padding-top: 4px; border-top: 1px solid var(--line); }
  .title .btn.quiet { color: var(--ink-500); }
  .options .none { padding: 10px; }
  .speakers li:last-child { border-bottom: 0; padding-bottom: 0; }
  .clamp { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  details summary { cursor: default; font-weight: 500; min-height: var(--ctl-h); display: flex; align-items: center; }
  .dropped { display: flex; flex-direction: column; gap: 12px; }
  .search { flex: none; display: flex; align-items: center; gap: 6px; height: var(--ctl-h); padding: 0 8px; border: 1px solid var(--edge); border-radius: var(--ctl-r); background: var(--surface); color: var(--ink-500); }
  .search:focus-within { box-shadow: var(--focus); }
  .search input { flex: 1; min-width: 0; height: 100%; border: 0; background: transparent; color: var(--ink-900); outline: none; box-shadow: none; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .lines { flex: 1 1 auto; min-height: 0; overflow-y: auto; margin: 0 -14px; padding: 0 6px 8px; display: flex; flex-direction: column; }
  .lines li { display: flex; gap: 4px; align-items: flex-start; padding: 2px 8px 2px 2px; border-radius: var(--ctl-r); }
  .lines li.active { background: var(--coral-50); box-shadow: inset 0 0 0 1px var(--coral-200); }
  .lines p { padding-top: 5px; padding-bottom: 4px; }
</style>
