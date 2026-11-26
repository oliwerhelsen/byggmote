<script lang="ts">
  import { tick } from 'svelte'
  import type { Command, Confirmation, DocState, MeetingDetail, Point, PointFields, Project } from '../../../shared/types'
  import { NO_DOC } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import PointInspector, { type Fresh } from '../lib/PointInspector.svelte'
  import Speakers from '../lib/Speakers.svelte'
  import { clock, day, failure, KINDS, minutes, overdue } from '../lib/format'
  import { tools } from '../lib/tools'
  import type { About, Go } from '../lib/view'

  // `about`: what the window's toolbar says of the meeting. `state`: what the application menu can do with it now.
  let { project, dir, problem: handed, connected, go, refresh, about, state: tell }: {
    project: Project; dir: string; problem: string; connected: boolean; go: Go; refresh: () => Promise<void>
    about: (a: About) => void
    state: (s: DocState) => void
  } = $props()

  const mac = window.api.platform === 'darwin'
  const NEW = 'new' // what is chosen while a new point is written

  let m = $state<MeetingDetail | null>(null)
  let problem = $state('')
  // svelte-ignore state_referenced_locally
  let wrote = $state(handed) // why the protocol was not written, when the transcript was: as handed over, then this view's own
  let sound = $state('')
  let player = $state<HTMLAudioElement>()
  let query = $state('')
  let active = $state<number | null>(null) // the transcript line marked
  let writing = $state(false)
  let stale = $state(false)
  let asking = $state(false) // whether to write over a person's corrections
  let present = $state('')
  let attending = $state(false) // the question about someone who was there and said nothing is showing
  let sending = $state<'' | 'ask' | 'busy'>('') // the protocol on its way to Stommen: asked about first, then sent
  let sendProblem = $state('')
  let asked = $state<'' | 'busy' | 'done'>('') // Stommen asked whether the sent protocol is justerat
  let copied = $state(false)
  let renaming = $state<string | null>(null) // the title while it is being written
  let saving = $state(false) // whether the Spara som menu is showing
  let inspector = $state(localStorage.getItem('inspector') !== 'hidden')
  let tab = $state<'point' | 'transcript' | 'stommen'>('point')
  let at = $state<number | null>(null) // the heading chosen in the outline: a new point from the toolbar goes under it
  let selected = $state<string | null>(null) // the chosen point's number, or NEW
  let editing = $state(false) // the chosen point's text is a field on the page
  let text = $state('') // what that field holds
  let fresh = $state<Fresh | null>(null) // the point being written
  let speakers = $state<{ show: () => void }>()
  let now = $state(0) // where the recording is, in seconds
  let playing = $state(false)
  let heard = $state(0) // the sound's own length, once it is known
  let rate = $state(1)
  let seen = -1 // the check Nästa att kontrollera showed last

  const SAVE = [['docx', 'Word'], ['pdf', 'PDF'], ['md', 'Markdown']] as const
  const RATES = [0.75, 1, 1.25, 1.5, 2]

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
    const title = renaming?.trim()
    renaming = null
    if (!title || !m || title === m.title) return
    await correct(window.api.setTitle(dir, title))
  }

  /** The protocol as the Markdown file it also is: saved where the person says, or on the clipboard. */
  async function keep(how: 'docx' | 'pdf' | 'md' | 'copy'): Promise<void> {
    saving = false
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
    if (!m?.protocol) tab = 'transcript'
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
  const title = $derived(!m ? '' : p && !renamed ? `Protokoll, ${p.name.toLowerCase()} ${p.no}` : m.title)
  const unnamed = $derived(m ? m.speakers.filter((s) => !s.person && /^Talare \d+$/.test(s.name)) : [])
  const shown = $derived.by(() => {
    const q = query.trim().toLowerCase()
    return m ? m.lines.filter((l) => !q || l.text.toLowerCase().includes(q) || l.who.toLowerCase().includes(q)) : []
  })
  const open = (x: Point): boolean => x.checks.some((c) => c.code === 'role' || !c.confirmed)
  const checks = $derived(p ? p.points.reduce((n, x) => n + x.checks.filter((c) => c.code === 'role' || !c.confirmed).length, 0) : 0)
  // A protocol is corrected while it is a draft and no later meeting builds on it: the engine refuses anything else.
  const draft = $derived(p?.status === 'draft')
  const confirmed = $derived(m?.stommen?.confirmed ?? null) // justerat in Stommen: final, a change is a new version there
  const free = $derived(Boolean(draft && m?.later === null && !confirmed))
  const pointable = $derived(p ? p.headings.filter((h) => !h.fill) : [])
  const pointer = $derived(m && active !== null ? (m.lines.find((l) => l.id === active) ?? null) : null)
  const silent = $derived(p ? project.people.filter((x) => !p.attendees.some((a) => a.name === x.name)) : [])
  const point = $derived(p?.points.find((x) => x.no === selected) ?? null)
  const length = $derived(heard || m?.duration || 0)
  const tidy = (t: string): string => t.trim().replace(/\s+/g, ' ')

  /** A correction: the engine makes it and the meeting is read again. */
  async function correct(run: Promise<unknown>): Promise<void> {
    try {
      await run
      problem = ''
      await load()
    } catch (e) {
      problem = failure(e)
    }
  }

  // The recording: a hidden player, driven by the strip under the page.
  function seek(to: number): void {
    now = Math.min(Math.max(0, to), length)
    if (player && sound) player.currentTime = now
  }
  function toggle(): void {
    if (!player || !sound) return
    if (playing) player.pause()
    else void player.play()
  }
  /** Play from where a point or a line is said, and mark the line. */
  function listen(from: number, line: number | null): void {
    active = line
    seek(from)
    if (player && sound) void player.play()
  }
  $effect(() => {
    if (player) player.playbackRate = rate
  })
  function drag(e: PointerEvent): void {
    if (!sound) return
    const bar = e.currentTarget as HTMLElement
    const to = (x: number): void => { const r = bar.getBoundingClientRect(); seek(((x - r.left) / r.width) * length) }
    bar.setPointerCapture(e.pointerId)
    to(e.clientX)
    const move = (v: PointerEvent): void => to(v.clientX)
    bar.addEventListener('pointermove', move)
    bar.addEventListener('pointerup', () => bar.removeEventListener('pointermove', move), { once: true })
  }

  // Choosing and correcting on the page.
  const row = (no: string): HTMLElement | null => document.getElementById(`p-${no}`)
  const field = (): void => void tick().then(() => {
    const el = document.getElementById('point-text') as HTMLTextAreaElement | null
    el?.focus()
    el?.setSelectionRange(el.value.length, el.value.length)
  })

  /** Choose a point: its row is marked, its properties are in the inspector, and the recording stands where it is said. */
  function select(no: string | null, edit = false): void {
    if (fresh && no !== NEW) void commit(false)
    const x = p?.points.find((y) => y.no === no)
    selected = x ? x.no : no === NEW ? NEW : null
    editing = false
    if (!x) return
    tab = 'point'
    at = x.heading
    active = x.line
    if (x.at !== null && !playing) seek(x.at)
    if (edit && free && x.since === undefined) {
      text = x.text
      editing = true
      field()
    }
  }

  function pick(x: Point, e: MouseEvent): void {
    if ((e.target as HTMLElement).closest('button, textarea, input, select')) return
    select(x.no, true)
  }

  /** The text field on the page is left: what it holds is the point's text now. */
  async function saveText(): Promise<void> {
    const x = point
    if (!x || !editing) return
    editing = false
    const t = tidy(text)
    if (!t || t === x.text) return
    await correct(window.api.changePoint(dir, x.no, { text: t }))
    if (editing && selected === x.no) text = point?.text ?? text // chosen again while it was saved
  }

  function textKeys(e: KeyboardEvent): void {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      const no = selected
      if (no === NEW) void commit()
      else void saveText().then(() => no && row(no)?.focus())
    } else if (e.key === 'Escape') {
      e.preventDefault()
      const no = selected
      if (no === NEW) leave()
      else {
        editing = false
        if (no) row(no)?.focus()
      }
    }
  }

  /** From the inspector: what goes wrong is thrown back to it, and shown there. A point moved to another heading has a new number. */
  async function change(fields: PointFields): Promise<void> {
    if (fresh && !point) return void Object.assign(fresh, fields)
    const x = point
    if (!x || !p) return
    const before = new Set(p.points.map((y) => y.no))
    await window.api.changePoint(dir, x.no, fields)
    await load()
    const after = m?.protocol?.points ?? []
    if (selected === x.no && !after.some((y) => y.no === x.no)) selected = after.find((y) => !before.has(y.no))?.no ?? null
  }

  /** A new point: a row under its heading, chosen, with its text to write. From the toolbar or the menu it goes under
   * the heading chosen in the outline, else the first that takes points. */
  function newPoint(under?: number): void {
    const h = pointable.find((x) => x.no === (under ?? at)) ?? pointable[0]
    if (!free || !h) return
    if (!fresh) {
      editing = false
      fresh = { heading: h.no, kind: 'todo', open: true, role: null, due: null, pointing: true }
      text = ''
    } else fresh.heading = under ?? fresh.heading
    selected = NEW
    tab = 'point'
    editing = true
    void tick().then(() => document.getElementById(`h-${fresh?.heading}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
    field()
  }

  function leave(): void {
    fresh = null
    editing = false
    if (selected === NEW) selected = null
  }

  /** The new point is added when it has a text, and left when it has none. `stay`: it is the chosen point afterwards. */
  async function commit(stay = true): Promise<void> {
    const f = fresh
    const t = tidy(text)
    const line = f?.pointing && pointer ? pointer.id : null
    if (!f || !p) return
    const before = new Set(p.points.map((x) => x.no))
    leave()
    if (!t) return
    const stays = f.open && f.kind !== 'decision' && f.kind !== 'note'
    try {
      await window.api.addPoint(dir, { heading: f.heading, kind: f.kind, text: t, open: stays, role: stays ? f.role : null, due: stays ? f.due : null, line })
      problem = ''
      await load()
      const made = m?.protocol?.points.find((x) => !before.has(x.no))
      if (made && stay && selected === null) {
        select(made.no)
        void tick().then(() => row(made.no)?.focus())
      }
    } catch (e) {
      problem = failure(e)
      if (selected === null && !fresh) { // nothing is lost: the point is back to be written again
        fresh = f
        text = t
        selected = NEW
        editing = true
      }
    }
  }

  async function remove(): Promise<void> {
    const x = point
    if (!x || !free || x.since !== undefined) return
    selected = null
    editing = false
    await correct(window.api.removePoint(dir, x.no))
  }

  function attend(): void {
    if (!present) return
    void correct(window.api.attend(dir, present, false))
    present = ''
    attending = false
  }

  async function write(discard = false): Promise<void> {
    if (!series) return
    if (m?.corrections && !discard) {
      asking = true // a model does not write over what a person has set right without a yes
      return
    }
    asking = false
    leave()
    selected = null
    writing = true
    wrote = ''
    try {
      await window.api.writeProtocol(dir, series.id, discard)
      stale = false
      await load()
      if (m?.protocol) tab = 'point'
    } catch (e) {
      wrote = failure(e)
    } finally {
      writing = false
    }
  }

  /** Names a speaker with a person of the project, or a written name the engine makes a person of. */
  async function name(speaker: string, who: { person: string } | { name: string }): Promise<void> {
    await window.api.nameSpeaker(dir, speaker, who)
    stale = Boolean(p)
    if ('name' in who) await refresh() // a new person is in the project now
    await load()
  }

  const WHEN = new Intl.DateTimeFormat('sv-SE', { dateStyle: 'long', timeStyle: 'short' })
  const ON = new Intl.DateTimeFormat('sv-SE', { dateStyle: 'long', timeZone: 'UTC' })
  // As Stommen words them.
  const HOW: Record<Confirmation['method'], string> = { next_meeting: 'på nästa byggmöte', email: 'per e-post', signed: 'signerat' }
  const standing = $derived(m?.stommen ?? null)
  const sendable = $derived(Boolean(connected && p && standing && standing.why === null && !confirmed && (!standing.sent_at || standing.changed)))

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
  function show(which: typeof tab): void {
    tab = which
    showInspector(true)
  }

  /** The outline: a heading is brought to the top of the page. */
  function reach(no: number): void {
    at = no
    document.getElementById(`h-${no}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }

  /** The next point with something to read against the recording, round and round. */
  function nextCheck(): void {
    const all = p ? p.headings.flatMap((h) => p.points.filter((x) => x.heading === h.no && open(x))) : []
    if (!all.length) return
    seen = (seen + 1) % all.length
    const no = all[seen].no
    select(no)
    showInspector(true)
    void tick().then(() => {
      row(no)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
      row(no)?.focus({ preventScroll: true })
    })
  }

  function act(c: Command): void {
    if (c === 'inspector') showInspector(!inspector)
    else if (c === 'find') {
      show('transcript')
      void tick().then(() => document.getElementById('find')?.focus())
    } else if (c === 'nameSpeakers') unnamed.length && speakers?.show()
    else if (c === 'play') toggle()
    else if (c === 'back') seek(now - 10)
    else if (c === 'forward') seek(now + 10)
    else if (c === 'rename') renaming = m?.title ?? ''
    else if (!p) return
    else if (c === 'saveDocx') void keep('docx')
    else if (c === 'savePdf') void keep('pdf')
    else if (c === 'saveMd') void keep('md')
    else if (c === 'copyText') void keep('copy')
    else if (c === 'nextCheck') nextCheck()
    else if (c === 'newPoint') newPoint()
    else if (c === 'rewrite' && series && free && !writing) void write()
    else if (c === 'send' && sendable && sending === '') {
      show('stommen')
      sending = 'ask'
    } else if (c === 'confirmation' && connected && (standing?.sent_at || confirmed)) {
      show('stommen')
      void look()
    } else if (c === 'attend' && draft && silent.length) {
      attending = true
      void tick().then(() => document.getElementById('present')?.focus())
    } else if (c === 'listen' && point && point.at !== null) listen(point.at, point.line)
    else if (c === 'removePoint') void remove()
    else if (c === 'editPoint' && point && free) {
      if (point.since === undefined) select(point.no, true)
      else {
        show('point')
        void tick().then(() => document.getElementById('point-follow')?.focus())
      }
    }
  }

  // A key the page takes itself may also be the menu's (the Mac's menu takes what it shows): it is done once.
  let last = { c: '', from: '', at: 0 }
  function run(c: Command, from: 'key' | 'menu'): void {
    const t = performance.now()
    if (last.c === c && last.from !== from && t - last.at < 250) return
    last = { c, from, at: t }
    act(c)
  }
  /** A choice in the application menu that is about the protocol. */
  export function command(c: Command): void {
    run(c, 'menu')
  }

  /** The keys a text field needs for itself are taken here, where it is known that none has the focus. */
  function keys(e: KeyboardEvent): void {
    const el = e.target as HTMLElement
    if (e.defaultPrevented || document.querySelector('dialog[open]') || el.closest?.('input, textarea, select, [role="slider"]')) return
    const button = Boolean(el.closest?.('button, a, summary'))
    const mods = Number(e.metaKey) + Number(e.ctrlKey) + Number(e.altKey) + Number(e.shiftKey)
    const only = (k: boolean): boolean => k && mods === 1
    let c: Command | null = null
    if (e.code === 'Space' && !mods) c = button ? null : 'play'
    else if (mac) {
      if (e.key === 'Enter' && !mods) c = button ? null : 'editPoint'
      else if (e.code === 'Space' && only(e.altKey)) c = 'listen'
      else if (e.key === 'Backspace' && only(e.metaKey)) c = 'removePoint'
      else if (e.key === 'ArrowLeft' && only(e.altKey)) c = 'back'
      else if (e.key === 'ArrowRight' && only(e.altKey)) c = 'forward'
    } else if (e.key === 'F2' && !mods) c = 'editPoint'
    else if (e.key === 'Delete' && !mods) c = 'removePoint'
    else if (e.key.toLowerCase() === 'l' && only(e.ctrlKey)) c = 'listen'
    else if (e.key === 'ArrowLeft' && only(e.ctrlKey)) c = 'back'
    else if (e.key === 'ArrowRight' && only(e.ctrlKey)) c = 'forward'
    if (!c) return
    e.preventDefault()
    run(c, 'key')
  }

  $effect(() => {
    if (!m) return
    about({ title, edited: Boolean(p && m.corrections), standing: confirmed ? 'done' : p ? (draft ? 'draft' : 'done') : '' })
    // Windows has the title in the window's own bar.
    document.title = `${title}${p ? ` (${confirmed || !draft ? 'Justerat' : 'Utkast'})` : ''} - ${project.name} - Byggmöte`
  })
  $effect(() => tell({
    protocol: Boolean(p), free, sendable, inspector, point: Boolean(point && free), own: Boolean(point && free && point.since === undefined),
    said: Boolean(point && point.at !== null && sound), sound: Boolean(sound), unnamed: unnamed.length > 0, absent: Boolean(draft && silent.length),
    sent: Boolean(connected && (standing?.sent_at || confirmed))
  }))
  $effect(() => () => {
    tell({ ...NO_DOC, inspector })
    document.title = 'Byggmöte'
  })

  const count = (no: number): number => (p ? p.points.filter((x) => x.heading === no).length : 0)
  const unchecked = (no: number): boolean => Boolean(p?.points.some((x) => x.heading === no && open(x)))
  const sentence = (t: string): string => (/[.!?]$/.test(t) ? t : `${t}.`)
  const under = (no: number): Point[] => (p ? p.points.filter((x) => x.heading === no) : [])
  const some = (n: number, one: string, many: string): string => (n === 1 ? one : `${n} ${many}`)
  // Where the protocol stands with Stommen, in a few words for the status line.
  const where = $derived(!p ? 'Inget protokoll än' : !standing || standing.why === 'local' ? 'Projektet finns bara på den här datorn'
    : confirmed ? 'Justerat i Stommen' : !standing.sent_at ? 'Inte skickat till Stommen'
    : standing.changed ? `Ändrat sedan version ${standing.version} skickades till Stommen` : `Skickat till Stommen, version ${standing.version}`)
</script>

<svelte:window onkeydown={keys} />

{#snippet check(x: Point, c: Point['checks'][number], i: number)}
  <div class="strip">
    {#if mac}<span class="dot"></span>{:else}<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" aria-hidden="true"><circle cx="7" cy="7" r="5.5" /><path d="M7 4v3.5M7 9.8v.1" /></svg>{/if}
    {#if c.code === 'amount'}
      <span class="grow">Kontrollera beloppet {c.value}. I inspelningen sägs: ”{c.said}”</span>
      {#if free}
        <button class="btn small" aria-label="Beloppet {c.value} i punkt {x.no} stämmer" onclick={() => correct(window.api.confirmCheck(dir, x.no, i + 1, false))}>Stämmer</button>
        <button class="btn small" aria-label="Ändra beloppet i punkt {x.no}" onclick={() => select(x.no, true)}>Ändra</button>
      {/if}
    {:else}
      <span class="grow">Rollen ”{c.said}” finns inte i projektet. Punkten har ingen ansvarig.</span>
      {#if free}
        <button class="btn small" aria-label="Välj Roll för punkt {x.no}"
          onclick={() => { select(x.no); showInspector(true); void tick().then(() => document.getElementById('point-role')?.focus()) }}>Välj Roll</button>
      {/if}
    {/if}
  </div>
{/snippet}

{#snippet line(x: Point)}
  {@const sel = selected === x.no}
  {@const late = x.open && overdue(x.due)}
  <!-- The row is chosen with a click or by moving to it; Enter (Ändra punkt) then puts its text in a field. -->
  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
  <div class="prow point" class:sel id="p-{x.no}" role="group" tabindex="0" aria-label="Punkt {x.no}" aria-current={sel ? 'true' : undefined}
    onclick={(e) => pick(x, e)} onfocus={(e) => e.target === e.currentTarget && !sel && select(x.no)}>
    <span class="no">{x.no}</span>
    <span class="kind">{KINDS[x.kind]}</span>
    <div class="txt">
      {#if sel && editing}
        <textarea id="point-text" class="edit" rows="1" aria-label="Punkt {x.no}" bind:value={text} onkeydown={textKeys} onblur={saveText}></textarea>
      {:else}
        <p>{sentence(x.text)}</p>
      {/if}
      {#if x.since !== undefined && p}
        <p class="meta">{x.open ? 'Kvarstår' : 'Avslutad'}, från {p.name.toLowerCase()} {x.since}</p>
        <p class="meta">
          {#if !x.raised}Togs inte upp på mötet.{:else if x.follow}På mötet: {sentence(x.follow)}{:else if x.said}På mötet sägs: ”{x.said}”{/if}
        </p>
      {/if}
    </div>
    {#if x.at !== null}
      <button class="chip" aria-label="Lyssna från {clock(x.at)}" onclick={() => { select(x.no); listen(x.at!, x.line) }}>{clock(x.at)}</button>
    {:else}<span></span>{/if}
    <span class="who" class:muted={!x.role}>{x.role ?? (x.open || sel ? 'Ingen ansvarig' : '')}</span>
    <span class="due" class:late>{x.due ?? ''}{#if late}<br /><small>förfallen</small>{/if}</span>
    {#each x.checks as c, i}
      {#if c.code === 'role' || !c.confirmed}{@render check(x, c, i)}{/if}
    {/each}
  </div>
{/snippet}

<div class="doc">
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
    <!-- What is done to the protocol, in the window's toolbar: the Mac's icons, Windows' command bar with labels. -->
    <div class="tools" use:tools>
      <button class="tb" aria-label="Ny punkt" title="Ny punkt" disabled={!free || !pointable.length} onclick={() => newPoint()}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M8 3v10M3 8h10" /></svg>
        <span class="lbl">Ny punkt</span>
      </button>
      <span class="sep"></span>
      <div class="group">
        <button class="tb" aria-label={checks ? `Nästa att kontrollera, ${checks} kvar` : 'Nästa att kontrollera'} title="Nästa att kontrollera" disabled={!checks} onclick={nextCheck}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="5.5" /><path d="m5.5 8.2 1.8 1.8 3.2-3.6" /></svg>
          <span class="lbl">Nästa att kontrollera</span>
          {#if checks}<span class="n">{checks}</span>{/if}
        </button>
        <button class="tb" aria-label="Sätt namn på talare" title="Sätt namn på talare" disabled={!unnamed.length} onclick={() => speakers?.show()}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="5.5" r="2.5" /><path d="M1.5 13.5c.4-2.6 2.2-4 4.5-4 1 0 1.9.3 2.6.8M10.5 12h4M12.5 10v4" /></svg>
          <span class="lbl">Sätt namn på talare</span>
        </button>
      </div>
      <span class="sep mac"></span>
      <span class="fill"></span>
      <div class="pop" onfocusout={(e) => !e.currentTarget.contains(e.relatedTarget as Node | null) && (saving = false)} onkeydown={saveKeys} role="presentation">
        <button id="save-as" class="tb" class:on={saving} aria-label="Spara som" title="Spara som" aria-haspopup="menu" aria-expanded={saving} aria-controls="save-as-menu" disabled={!p}
          onclick={() => (saving = !saving)}>
          {#if mac}
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 10V2M5 4.5 8 1.5l3 3M3.5 8v5.5h9V8" /></svg>
          {:else}
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 2.5h8.5l2.5 2.5v8.5h-11zM5 2.5v3.5h5V2.5M5 13.5V9.5h6v4" /></svg>
          {/if}
          <span class="lbl">Spara som</span>
          <svg class="down" width="8" height="6" viewBox="0 0 8 6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m1 1.5 3 3 3-3" /></svg>
        </button>
        {#if saving}
          <ul class="menu" id="save-as-menu" role="menu" aria-labelledby="save-as">
            <li class="mhead" role="none">Spara som</li>
            {#each SAVE as [how, label] (how)}
              <li role="none"><button type="button" role="menuitem" onclick={() => keep(how)}>{label}</button></li>
            {/each}
            <li class="msep" role="none"></li>
            <li role="none"><button type="button" role="menuitem" onclick={() => keep('copy')}>Kopiera texten <span class="sc">{mac ? '⇧⌘C' : 'Ctrl+Skift+C'}</span></button></li>
          </ul>
        {/if}
      </div>
      <button class="btn primary send" disabled={!sendable || sending !== ''} onclick={() => act('send')}>
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2 7 9M14 2l-4.5 12L7 9 2 6.5z" /></svg>
        <span>Skicka till Stommen</span>
      </button>
      <span class="sep mac"></span>
      <label class="search">
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><circle cx="5.5" cy="5.5" r="4" /><path d="m8.5 8.5 3 3" /></svg>
        <input id="find" type="search" placeholder="Sök i utskriften" aria-label="Sök i utskriften" bind:value={query} oninput={() => show('transcript')} />
        {#if !query}<span class="hint">{mac ? '⌘F' : 'Ctrl+F'}</span>{/if}
      </label>
      <button class="tb insp" class:on={inspector} aria-label="Visa eller dölj inspektören" title="Visa eller dölj inspektören" aria-pressed={inspector} onclick={() => showInspector(!inspector)}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><rect x="1.5" y="2.5" width="13" height="11" rx={mac ? 2.5 : 1.5} /><path d="M10 2.5v11" /></svg>
      </button>
    </div>

    <!-- What the person needs to know or answer before reading on, in a bar under the toolbar. -->
    {#if problem}
      <div class="bar bad" role="alert"><Icon name="alert" size={15} /><p class="mono">{problem}</p></div>
    {/if}
    {#if writing}
      <div class="bar" role="status"><Icon name="clock" size={15} /><p><strong>Protokollet skrivs.</strong> Det tar ungefär en minut för ett kort möte, längre för ett långt.</p></div>
    {:else if wrote}
      <div class="bar bad" role="alert">
        <Icon name="alert" size={15} />
        <p><strong>Protokollet gick inte att skriva.</strong> Utskriften finns, så det går att försöka igen. <span class="mono">{wrote}</span></p>
      </div>
    {:else if asking && m.corrections}
      <div class="bar warn" role="alert">
        <Icon name="alert" size={15} />
        <p>
          <strong>Protokollet har {m.corrections === 1 ? 'en rättning' : `${m.corrections} rättningar`}.</strong>
          {m.corrections === 1 ? 'Den' : 'De'} försvinner om modellen skriver om protokollet.
        </p>
        <button class="btn small" onclick={() => write(true)}>Skriv om ändå</button>
        <button class="btn small primary" onclick={() => (asking = false)}>{m.corrections === 1 ? 'Behåll rättningen' : 'Behåll rättningarna'}</button>
      </div>
    {:else if stale && free && !m.corrections}
      <div class="bar" role="status">
        <Icon name="person" size={15} />
        <p><strong>Talarna har fått namn sedan protokollet skrevs.</strong> Närvarande är uppdaterade. Skriv om protokollet om modellen ska läsa utskriften med namnen.</p>
        <button class="btn small" disabled={writing} onclick={() => write()}>Skriv om protokollet</button>
      </div>
    {/if}
    {#if p && !free}
      <div class="bar">
        <Icon name="lock" size={15} />
        <p>
          {#if confirmed}Protokollet är justerat i Stommen, så punkterna går inte att ändra här längre.
          {:else if m.later !== null}{p.name} {m.later} bygger på det här protokollet, så punkterna går inte att ändra längre.
          {:else}Protokollet är justerat, så punkterna går inte att ändra längre.{/if}
        </p>
      </div>
    {/if}

    <div class="body">
      {#if p}
        <nav class="outline" aria-label="Rubriker">
          <p class="side-head"><span>Rubriker</span><span>{some(p.points.length, '1 punkt', 'punkter')}</span></p>
          {#each p.headings as h (h.no)}
            <button class:current={at === h.no} onclick={() => reach(h.no)}>
              <span class="no">{h.no}</span><span class="name">{h.name}</span>
              {#if unchecked(h.no)}<span class="mark" role="img" aria-label="Har något att kontrollera"></span>{/if}
              {#if count(h.no)}<span class="count">{count(h.no)}</span>{/if}
            </button>
          {/each}
        </nav>
      {/if}

      <div class="work">
        <div class="panes">
          <div class="desk">
            {#if p}
              <div class="colstrip"><div class="prow"><span>Nr</span><span>Typ</span><span>Punkt</span><span>Tid</span><span>Ansvarig</span><span>Senast</span></div></div>
            {/if}
            <article class="paper">
              {#if renaming !== null}
                <form class="rename" onsubmit={(e) => { e.preventDefault(); void rename() }}>
                  <!-- svelte-ignore a11y_autofocus -->
                  <input class="field" aria-label="Mötets namn" autofocus bind:value={renaming} onkeydown={(e) => e.key === 'Escape' && (renaming = null)} />
                  <button class="btn" type="submit" disabled={!renaming.trim()}>Spara</button>
                  <button class="btn" type="button" onclick={() => (renaming = null)}>Avbryt</button>
                </form>
              {:else}
                <h1>{title}</h1>
              {/if}
              <p class="meta">{project.name} · {day(m.recorded_at)} · {minutes(m.duration)}, {m.speakers.length === 1 ? 'en talare' : `${m.speakers.length} talare`}</p>

              {#if !p}
                <section class="empty">
                  <h2>Mötet har inget protokoll än</h2>
                  <p class="meta">Utskriften finns till höger. Protokollet skrivs från den, av en språkmodell på den här datorn.</p>
                  {#if series}
                    <button class="btn primary" disabled={writing} onclick={() => write()}>Skriv protokollet</button>
                  {:else}
                    <p class="meta">Projektet behöver en mötesserie först. Den startas från Översikt.</p>
                  {/if}
                </section>
              {:else}
                {#each p.headings as h (h.no)}
                  {@const points = under(h.no)}
                  {@const here = fresh?.heading === h.no}
                  <section aria-labelledby="h-{h.no}">
                    <div class="head">
                      <h2 id="h-{h.no}">{h.no} {h.name}</h2>
                      {#if !h.fill && !points.length && !here}<small>Inget noterat</small>{/if}
                      {#if free && !h.fill}
                        <button class="add" aria-label="Ny punkt under {h.name}" title="Ny punkt under {h.name}" onclick={() => newPoint(h.no)}>
                          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M8 3v10M3 8h10" /></svg>
                        </button>
                      {:else if h.fill === 'attendees' && draft && silent.length}
                        <button class="add" aria-label="Lägg till någon som var med" title="Lägg till någon som var med" onclick={() => act('attend')}>
                          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M8 3v10M3 8h10" /></svg>
                        </button>
                      {/if}
                    </div>
                    {#if h.fill === 'attendees'}
                      {#if p.attendees.length}
                        <ul class="attendees">
                          {#each p.attendees as a}
                            <li>
                              <span>{a.name}{#if a.role}, {a.role}{/if}</span>
                              {#if a.added}<span class="meta">(tillagd för hand)</span>{/if}
                              {#if a.added && a.person && draft}
                                <button class="quiet" aria-label="Ta bort {a.name} från närvarande" onclick={() => correct(window.api.attend(dir, a.person!, true))}>Ta bort</button>
                              {/if}
                            </li>
                          {/each}
                        </ul>
                      {:else}
                        <p class="meta pad">Ingen talare i inspelningen.</p>
                      {/if}
                      {#if attending && draft && silent.length}
                        <div class="present">
                          <select id="present" class="popup" aria-label="Någon som var med utan att säga något" bind:value={present}>
                            <option value="">Var någon med utan att säga något?</option>
                            {#each silent as person (person.id)}
                              <option value={person.id}>{person.name}{person.role ? `, ${person.role}` : ''}</option>
                            {/each}
                          </select>
                          <button class="btn" disabled={!present} onclick={attend}>Lägg till som närvarande</button>
                          <button class="btn" onclick={() => (attending = false)}>Avbryt</button>
                        </div>
                      {/if}
                    {:else}
                      {#each points as x (x.no)}{@render line(x)}{/each}
                      {#if here && fresh}
                        <div class="prow point sel" role="group" aria-label="Ny punkt">
                          <span class="no"></span>
                          <span class="kind">{KINDS[fresh.kind]}</span>
                          <div class="txt">
                            <textarea id="point-text" class="edit" rows="1" aria-label="Ny punkt" placeholder="Skriv punkten" bind:value={text} onkeydown={textKeys}
                              onblur={(e) => !(e.relatedTarget as HTMLElement | null)?.closest('.inspector') && commit()}></textarea>
                          </div>
                          {#if fresh.pointing && pointer}<span class="chip">{clock(pointer.at)}</span>{:else}<span></span>{/if}
                          <span class="who" class:muted={!fresh.role}>{fresh.role ?? 'Ingen ansvarig'}</span>
                          <span class="due">{fresh.due ?? ''}</span>
                        </div>
                      {/if}
                    {/if}
                  </section>
                {/each}

                <!-- What is not in the protocol, and how it was written: quiet, after the last heading. -->
                {#if p.removed?.length}
                  <section class="after">
                    <h3>{p.removed.length === 1 ? 'En punkt är borttagen' : `${p.removed.length} punkter är borttagna`}</h3>
                    <p class="meta">En borttagen punkt står inte i protokollet och följer inte med till nästa möte. Den går att lägga tillbaka.</p>
                    {#each p.removed as x (x.no)}
                      <div class="gone">
                        <span class="no">{x.no}</span><span class="kind">{KINDS[x.kind]}</span><span class="grow">{sentence(x.text)}</span>
                        {#if free}<button class="btn small" aria-label="Lägg tillbaka punkt {x.no}" onclick={() => correct(window.api.restorePoint(dir, x.no))}>Lägg tillbaka</button>{/if}
                      </div>
                    {/each}
                  </section>
                {/if}
                {#if p.dropped.length}
                  <details class="after">
                    <summary>{p.dropped.length === 1 ? 'Ett förslag från modellen togs inte med' : `${p.dropped.length} förslag från modellen togs inte med`}</summary>
                    <p class="meta">Det som inte går att hitta i utskriften visas inte i protokollet. Här står vad modellen föreslog.</p>
                    {#each p.dropped as d}
                      <p>{d.text}</p>
                      <p class="meta">
                        {d.reason === 'heading' ? 'Rubriken finns inte.' : d.reason === 'unknown-point' ? `Punkten ${d.no ?? ''} finns inte.` : 'Citatet finns inte i utskriften.'}
                        {#if d.quote}Modellens citat: ”{d.quote}”{/if}
                      </p>
                    {/each}
                  </details>
                {/if}
                <p class="after meta about">
                  Protokollet är skrivet från inspelningen av en språkmodell på den här datorn.
                  {#if !standing?.sent_at}Inget har skickats ut.{/if}
                  Varje punkt modellen har skrivit pekar på stället där det sades.
                  {#if free}Läs igenom det mot inspelningen och rätta det som är fel innan det går vidare.{/if}
                </p>
              {/if}
            </article>
          </div>

          {#if inspector}
            <aside class="inspector">
              <div class="tabs" role="tablist" aria-label="Inspektör">
                <div class="seg">
                  {#each [['point', 'Punkt'], ['transcript', 'Utskrift'], ['stommen', 'Stommen']] as const as [id, label] (id)}
                    <button role="tab" id="tab-{id}" aria-selected={tab === id} aria-controls="panel-{id}" class:on={tab === id} onclick={() => (tab = id)}>{label}</button>
                  {/each}
                </div>
                {#if point}<span class="chosen">{point.no}</span>{/if}
              </div>

              {#if tab === 'point'}
                <div class="panel" id="panel-point" role="tabpanel" aria-labelledby="tab-point">
                  <PointInspector {point} {fresh} ready={Boolean(tidy(text))} {free} headings={pointable} roles={project.roles} series={p?.name.toLowerCase() ?? ''}
                    written={p?.written_at ?? ''} lines={m.lines} {pointer} sound={Boolean(sound)} set={change} listen={() => act('listen')} remove={() => void remove()}
                    add={() => void commit()} {leave} aim={(on) => fresh && (fresh.pointing = on)}
                    unconfirm={(n) => point && correct(window.api.confirmCheck(dir, point.no, n, true))} />
                </div>
              {:else if tab === 'transcript'}
                <div class="panel" id="panel-transcript" role="tabpanel" aria-labelledby="tab-transcript">
                  {#if query.trim()}
                    <p class="found">
                      <span>{some(shown.length, 'En rad', 'rader')} med ”{query.trim()}”</span>
                      <button class="quiet" onclick={() => (query = '')}>Visa alla</button>
                    </p>
                  {/if}
                  <ol class="lines">
                    {#each shown as l (l.id)}
                      <li id="line-{l.id}" class:active={active === l.id}>
                        <button class="chip" aria-label="Lyssna från {clock(l.at)}" onclick={() => listen(l.at, l.id)}>{clock(l.at)}</button>
                        <p><strong>{l.who}</strong> {l.text}</p>
                      </li>
                    {:else}
                      <li><p class="quiet-text">{m.lines.length ? 'Inget i utskriften stämmer med sökningen.' : 'Inspelningen har inget tal som gick att skriva ut.'}</p></li>
                    {/each}
                  </ol>
                </div>
              {:else}
                <div class="panel stommen" id="panel-stommen" role="tabpanel" aria-labelledby="tab-stommen">
                  {#if !p || !standing}
                    <p class="quiet-text">Mötet har inget protokoll att skicka än.</p>
                  {:else if standing.why === 'local'}
                    <p class="quiet-text">Projektet finns bara på den här datorn, så protokollet skickas inte till Stommen.</p>
                  {:else}
                    {#if confirmed}
                      <p><strong>Justerat {ON.format(new Date(`${confirmed.on}T00:00:00Z`))}</strong>, {HOW[confirmed.method] ?? confirmed.method}, av {confirmed.by}.</p>
                    {/if}
                    <p class="quiet-text">
                      {#if standing.sent_at}
                        Skickat {WHEN.format(new Date(standing.sent_at))}, version {standing.version}.
                        {#if standing.changed}Protokollet har ändrats sedan dess.{/if}
                      {:else if !confirmed}
                        Protokollet är inte skickat.
                      {/if}
                    </p>
                    {#if sendProblem}<p class="bad" role="alert">{sendProblem}</p>{/if}
                    {#if confirmed}
                      <p>Ett justerat protokoll rättas inte och skickas inte igen härifrån. Behöver det ändras, be om en ny version i Stommen.</p>
                    {:else if standing.why === 'checks'}
                      <p>{standing.about === 1 ? 'En sak ska kontrolleras' : `${standing.about} saker ska kontrolleras`} innan protokollet kan skickas.</p>
                    {:else if standing.why === 'role'}
                      <p>Rollen ”{standing.about}” finns inte längre i Stommen. Hämta projektet igen under Inställningar → Stommen, eller välj en annan Roll för punkten.</p>
                    {:else if !connected}
                      <p>Logga in i Stommen under Inställningar för att skicka protokollet.</p>
                    {:else if sending === 'ask'}
                      <div class="ask">
                        <p>
                          Det här går till Stommen: protokollet med {p.points.length === 1 ? 'sin punkt' : `sina ${p.points.length} punkter`}, och för varje
                          punkt hur långt in i inspelningen det sades, raden som sades där och vem som sa den. Ljudet och resten av utskriften
                          stannar på den här datorn.
                        </p>
                        <div class="act">
                          <button class="btn primary" onclick={send}>Skicka</button>
                          <button class="btn" onclick={() => (sending = '')}>Avbryt</button>
                        </div>
                      </div>
                    {:else if !standing.sent_at || standing.changed}
                      <div class="act">
                        <button class="btn primary" disabled={sending === 'busy'} onclick={() => (sending = 'ask')}>
                          {sending === 'busy' ? 'Skickar' : standing.sent_at ? 'Skicka igen' : 'Skicka till Stommen'}
                        </button>
                      </div>
                    {/if}
                    {#if connected && (standing.sent_at || confirmed) && sending !== 'ask'}
                      <div class="act">
                        <button class="btn" disabled={asked === 'busy'} onclick={() => look()}>{asked === 'busy' ? 'Ser efter' : 'Se efter om det är justerat'}</button>
                      </div>
                      {#if asked === 'done' && !confirmed}<p class="quiet-text" role="status">Inte justerat i Stommen än.</p>{/if}
                    {/if}
                  {/if}
                </div>
              {/if}
            </aside>
          {/if}
        </div>

        <!-- The recording, under the page and the inspector: a point or a line plays from where it is said. -->
        <footer class="transport">
          {#if sound}
            <audio bind:this={player} src={sound} preload="metadata" ontimeupdate={() => (now = player?.currentTime ?? now)} onplay={() => (playing = true)}
              onpause={() => (playing = false)} ondurationchange={() => (heard = player && Number.isFinite(player.duration) ? player.duration : 0)}></audio>
          {/if}
          <button class="tb" aria-label="Hoppa 10 s bakåt" title="Hoppa 10 s bakåt" disabled={!sound} onclick={() => seek(now - 10)}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8a5 5 0 1 0 1.6-3.7M3 2.5v2.4h2.4" /></svg>
          </button>
          <button class="tb on" aria-label={playing ? 'Pausa' : 'Spela upp'} title={playing ? 'Pausa' : 'Spela upp'} disabled={!sound} onclick={toggle}>
            {#if playing}
              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true"><path d="M2.5 1.5h2.5v9H2.5zM7 1.5h2.5v9H7z" /></svg>
            {:else}
              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true"><path d="M3 1.5v9l7.5-4.5z" /></svg>
            {/if}
          </button>
          <button class="tb" aria-label="Hoppa 10 s framåt" title="Hoppa 10 s framåt" disabled={!sound} onclick={() => seek(now + 10)}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13 8a5 5 0 1 1-1.6-3.7M13 2.5v2.4h-2.4" /></svg>
          </button>
          <span class="at">{clock(now)}</span>
          <span class="of">av</span>
          <span class="at all">{clock(length)}</span>
          <div class="scrub" role="slider" tabindex={sound ? 0 : -1} aria-label="Plats i inspelningen" aria-valuemin="0" aria-valuemax={Math.round(length)} aria-valuenow={Math.round(now)}
            aria-valuetext="{clock(now)} av {clock(length)}" aria-disabled={!sound} onpointerdown={drag}
            onkeydown={(e) => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); seek(now + (e.key === 'ArrowLeft' ? -5 : 5)) } }}>
            <span class="track"></span>
            <span class="played" style="width: {length ? (now / length) * 100 : 0}%"></span>
            {#each p?.points ?? [] as x (x.no)}
              {#if x.at !== null && length}<span class="mark-at" class:on={x.no === selected} style="left: {Math.min(100, (x.at / length) * 100)}%"></span>{/if}
            {/each}
            <span class="knob" style="left: {length ? (now / length) * 100 : 0}%"></span>
          </div>
          {#if !sound}<span class="of">{m.audio ? 'Ljudet läses in.' : 'Mötet har inget ljud sparat.'}</span>{/if}
          <select class="popup rate" aria-label="Hastighet" disabled={!sound} bind:value={rate}>
            {#each RATES as r (r)}<option value={r}>{String(r).replace('.', ',')}×</option>{/each}
          </select>
        </footer>
      </div>
    </div>

    <!-- The document's status line. -->
    <footer class="status">
      {#if p && !mac}<span>{confirmed || !draft ? 'Justerat' : 'Utkast'}{m.corrections ? ', redigerat' : ''}</span>{/if}
      {#if p}
        <span>{some(p.points.length, '1 punkt', 'punkter')}</span>
        {#if checks}<span class="sepd"><span class="dot"></span>{checks} att kontrollera</span>{/if}
      {/if}
      <span class="sepd">{where}</span>
      {#if copied}<span class="sepd" role="status">Kopierat</span>{/if}
      <span class="fill"></span>
      <span class="promise">
        <svg width="12" height="13" viewBox="0 0 12 13" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><rect x="2" y="5.5" width="8" height="6" rx="1.5" /><path d="M4 5.5V4a2 2 0 0 1 4 0v1.5" /></svg>
        Ljud och utskrift stannar på den här datorn
      </span>
    </footer>

    <Speakers bind:this={speakers} {project} {unnamed} lines={m.lines} speakers={m.speakers} {listen} {name} />
  {/if}
</div>

<style>
  /* A document window: bars with what needs saying, then the outline, the page on its desk with the inspector beside
     it and the recording under both, and the status line at the foot. The measures are the drawing's, per computer. */
  .doc { --rule: #e4e3e9; --soft: #efeef3; --desk: #ebebef; --quiet: #fbfbfc; display: flex; flex-direction: column; height: 100%; min-width: 0; }
  :global(:root[data-platform='mac']) .doc { --desk: #e9e8ee; --quiet: #fbfafc; }
  .body { flex: 1 1 auto; min-height: 0; display: flex; }
  .work { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
  .panes { flex: 1 1 auto; min-height: 0; display: flex; }
  .fill, .grow { flex: 1 1 auto; min-width: 0; }

  /* The toolbar. */
  .tools { display: flex; align-items: center; gap: 4px; flex: 1 1 auto; min-width: 0; }
  .tb { display: inline-flex; align-items: center; justify-content: center; gap: 8px; flex: none; height: 36px; padding: 0 10px; border: 0; border-radius: 4px; background: transparent; color: var(--ink-900); white-space: nowrap; }
  .tb:hover:not(:disabled), .tb.on { background: rgb(0 0 0 / 0.06); }
  .tb svg { color: var(--coral-700); }
  .tb.insp svg, .tb .down { color: var(--ink-700); }
  .n { display: inline-grid; place-items: center; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; background: var(--coral-700); color: #fff; font-size: 11px; font-weight: 600; }
  .group { display: inline-flex; gap: 4px; }
  .sep { flex: none; width: 1px; height: 24px; margin: 0 4px; background: #e4e3e9; }
  .sep.mac { display: none; }
  .send { margin: 0 6px 0 4px; }
  .pop { position: relative; display: inline-flex; }
  .search { display: inline-flex; align-items: center; gap: 6px; flex: 0 1 200px; width: 200px; min-width: 120px; height: var(--ctl-h); padding: 0 9px; border: 1px solid #dcdbe2; border-bottom-color: #8e8d99; border-radius: var(--ctl-r); background: #fff; color: var(--ink-500); -webkit-app-region: no-drag; }
  .search svg { flex: none; order: 3; }
  .search:focus-within { box-shadow: var(--focus); }
  .search input { flex: 1 1 auto; min-width: 0; width: 0; height: 100%; padding: 0; border: 0; background: transparent; color: var(--ink-900); outline: none; box-shadow: none; }
  .search input::-webkit-search-cancel-button { display: none; }
  .hint { flex: none; font-size: var(--ui-small); color: var(--ink-400); }
  :global(:root[data-platform='mac']) .tools { gap: 8px; flex: none; }
  :global(:root[data-platform='mac']) .tools .fill { display: none; }
  :global(:root[data-platform='mac']) .tb { height: 28px; min-width: 32px; padding: 0 7px; gap: 6px; border-radius: 6px; color: var(--ink-700); }
  :global(:root[data-platform='mac']) .tb:hover:not(:disabled), :global(:root[data-platform='mac']) .tb.on { background: rgb(0 0 0 / 0.07); }
  :global(:root[data-platform='mac']) .tb svg { color: inherit; }
  :global(:root[data-platform='mac']) .tb .lbl { display: none; }
  :global(:root[data-platform='mac']) .n { min-width: 15px; height: 15px; padding: 0 4px; border-radius: 8px; font-size: 10px; font-weight: 700; }
  :global(:root[data-platform='mac']) .group { gap: 0; border-radius: 6px; background: rgb(0 0 0 / 0.05); }
  :global(:root[data-platform='mac']) .sep { height: 20px; margin: 0 4px; }
  :global(:root[data-platform='mac']) .sep.mac { display: block; }
  :global(:root[data-platform='mac']) .send { margin: 0 0 0 4px; }
  :global(:root[data-platform='mac']) .search { border: 0; background: rgb(0 0 0 / 0.055); }
  :global(:root[data-platform='mac']) .search svg { order: 0; }

  /* A menu that drops from a button. */
  .menu { position: absolute; z-index: 30; top: 40px; left: 0; width: 240px; padding: 5px; border: 1px solid rgb(0 0 0 / 0.16); border-radius: 8px; background: rgb(250 249 252 / 0.98); box-shadow: 0 10px 30px rgb(0 0 0 / 0.22); -webkit-app-region: no-drag; }
  .menu button { display: flex; align-items: center; width: 100%; height: 32px; padding: 0 10px; border: 0; border-radius: 4px; background: none; text-align: left; white-space: nowrap; }
  .menu button:hover, .menu button:focus-visible { background: rgb(0 0 0 / 0.06); box-shadow: none; }
  .sc { margin-left: auto; padding-left: 28px; font-size: 12px; color: var(--ink-500); }
  .msep { height: 1px; margin: 5px 10px; background: #e4e3e9; }
  .mhead { display: none; padding: 4px 10px 2px; font-size: var(--ui-small); font-weight: 600; color: var(--ink-500); }
  :global(:root[data-platform='mac']) .menu { top: 33px; width: 220px; }
  :global(:root[data-platform='mac']) .mhead { display: block; }
  :global(:root[data-platform='mac']) .menu button { height: 24px; border-radius: 5px; }
  :global(:root[data-platform='mac']) .menu button:hover, :global(:root[data-platform='mac']) .menu button:focus-visible { background: var(--coral-700); color: #fff; }
  :global(:root[data-platform='mac']) .sc { font-size: var(--ui); letter-spacing: 0.04em; }
  :global(:root[data-platform='mac']) .menu button:is(:hover, :focus-visible) .sc { color: rgb(255 255 255 / 0.85); }

  /* A bar under the toolbar. */
  .bar { flex: none; display: flex; align-items: center; gap: 8px; min-height: 32px; padding: 5px 14px; border-bottom: 1px solid var(--rule); background: var(--sunken); font-size: var(--ui-small); color: var(--ink-700); }
  .bar p { flex: 1 1 auto; min-width: 0; }
  .bar :global(svg) { flex: none; color: var(--ink-500); }
  .bar.warn { background: var(--warn-bg); }
  .bar.warn :global(svg) { color: var(--warn); }
  .bar.bad { background: var(--bad-bg); }
  .bar.bad :global(svg) { color: var(--bad); }
  .btn.small { flex: none; min-height: 22px; padding: 0 8px; font-size: var(--ui-small); }
  .mono { font-family: var(--font-mono); font-size: 0.92em; }

  /* The outline: the headings as a source list. */
  .outline { flex: none; width: 210px; display: flex; flex-direction: column; padding: 4px; overflow-y: auto; background: var(--pane); }
  .side-head { flex: none; display: flex; align-items: center; justify-content: space-between; height: 30px; margin-top: 6px; padding: 0 12px; font-size: var(--ui-small); font-weight: 600; color: var(--ink-500); }
  .side-head span:last-child { font-weight: 400; }
  .outline button { position: relative; display: flex; align-items: center; gap: 8px; flex: none; height: var(--row-h); padding: 0 10px; border: 0; border-radius: var(--ctl-r); background: transparent; text-align: left; white-space: nowrap; }
  .outline button:hover:not(.current) { background: rgb(0 0 0 / 0.04); }
  .outline button.current { background: rgb(0 0 0 / 0.055); }
  .outline button.current::before { content: ''; position: absolute; left: 0; top: 10px; bottom: 10px; width: 3px; border-radius: 2px; background: var(--coral-700); }
  .outline .no { flex: none; width: 18px; color: var(--ink-500); }
  .outline .name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  .outline .count { flex: none; font-size: var(--ui-small); color: var(--ink-500); font-weight: 400; }
  .outline .mark { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--warn); }
  :global(:root[data-platform='mac']) .outline { width: 196px; padding: 2px 8px 8px; border-right: 1px solid var(--rule); }
  :global(:root[data-platform='mac']) .side-head { height: 24px; margin-top: 10px; padding: 0 8px; }
  :global(:root[data-platform='mac']) .outline button { gap: 7px; padding: 0 8px; }
  :global(:root[data-platform='mac']) .outline button.current { background: rgb(201 58 66 / 0.14); font-weight: 600; }
  :global(:root[data-platform='mac']) .outline button.current::before { content: none; }
  :global(:root[data-platform='mac']) .outline .no { width: 16px; }
  :global(:root[data-platform='mac']) .outline .mark + .count { margin-left: -3px; }
  :global(:root[data-platform='win']) .work { border: 1px solid var(--rule); border-right: 0; border-bottom: 0; border-top-left-radius: 8px; overflow: hidden; background: var(--quiet); }

  /* The page on its desk, with the columns' names over it. */
  .desk { flex: 1 1 auto; min-width: 0; overflow-y: auto; background: var(--desk); padding: 0 0 28px; container-type: inline-size; }
  .colstrip { position: sticky; top: 0; z-index: 2; display: flex; justify-content: center; height: 26px; padding: 0 20px; background: var(--quiet); border-bottom: 1px solid var(--rule); font-size: 12px; color: var(--ink-500); }
  .colstrip .prow { width: 760px; max-width: 100%; padding: 0 42px; align-items: center; }
  :global(:root[data-platform='mac']) .colstrip { height: 24px; background: #f6f5f9; font-size: 11px; font-weight: 600; }
  .paper { width: 760px; max-width: calc(100% - 40px); min-height: calc(100% - 18px); margin: 18px auto 0; padding: 24px 36px 36px; background: #fff; box-shadow: 0 1px 4px rgb(0 0 0 / 0.18); font: 12.5px/1.55 var(--font-body); color: var(--ink-900); }
  .paper h1 { font: 300 24px/1.2 var(--font-display); letter-spacing: 0.01em; margin-bottom: 4px; }
  .rename { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font: var(--ui)/1.45 var(--font-ui); }
  .rename .field { flex: 1 1 auto; min-width: 0; }
  .meta { color: var(--ink-500); font-size: 12px; }
  .head { display: flex; align-items: baseline; gap: 8px; margin: 14px 0 4px; padding-bottom: 4px; border-bottom: 1px solid var(--rule); scroll-margin-top: 36px; }
  .head h2 { flex: 1 1 auto; font: 600 14px/1.3 var(--font-display); letter-spacing: 0.03em; scroll-margin-top: 40px; }
  .head small { font-size: 11.5px; color: var(--ink-400); }
  /* One under every heading: quiet until the pointer or the keyboard is there, so the document is what is read. */
  .add { align-self: center; display: inline-grid; place-items: center; width: 20px; height: 20px; margin: -2px 0; border: 0; border-radius: 4px; background: transparent; color: var(--ink-500); opacity: 0; }
  section:hover .add, .add:focus-visible { opacity: 1; }
  .add:hover { background: rgb(0 0 0 / 0.07); color: var(--ink-900); }
  .attendees { display: grid; grid-template-columns: 1fr 1fr; column-gap: 8px; padding: 0 6px; }
  .attendees li { display: flex; align-items: baseline; gap: 4px; min-width: 0; }
  .pad { padding: 0 6px; }
  .quiet { padding: 0 4px; border: 0; border-radius: 4px; background: transparent; color: var(--coral-700); font-size: var(--ui-small); }
  .quiet:hover { background: var(--coral-50); }
  .attendees .quiet { opacity: 0; }
  .attendees li:hover .quiet, .attendees .quiet:focus-visible { opacity: 1; }
  .present { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 8px 6px 0; font: var(--ui)/1.45 var(--font-ui); }
  .empty { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; margin-top: 20px; padding-top: 14px; border-top: 1px solid var(--rule); }
  .empty h2 { font: 600 14px/1.3 var(--font-display); letter-spacing: 0.03em; }
  .empty .btn { font: 600 var(--ui)/1.45 var(--font-ui); }

  /* A point: one row of the document's table. */
  .prow { display: grid; grid-template-columns: 42px 58px minmax(0, 1fr) 46px 112px 78px; column-gap: 8px; align-items: start; padding: 5px 6px; border-radius: 4px; }
  .point { scroll-margin: 40px 0; }
  .point:focus-visible { box-shadow: inset 0 0 0 1px var(--coral-200); }
  .prow .no, .gone .no { font: 500 12px/20px var(--font-mono); color: var(--ink-700); }
  .prow .kind, .gone .kind { font-size: 11px; line-height: 20px; color: var(--ink-500); }
  .txt { min-width: 0; }
  .txt p { overflow-wrap: anywhere; }
  .who, .due { font-size: 12px; line-height: 20px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .who.muted { color: var(--ink-500); }
  .due { font-variant-numeric: tabular-nums; }
  .due.late { color: var(--bad); }
  .due small { display: block; font-size: 11px; font-weight: 600; line-height: 1.4; }
  .chip { display: inline-flex; align-items: center; justify-self: start; height: 18px; margin-top: 1px; padding: 0 6px; border: 0; border-radius: 4px; background: var(--sunken); font: 500 11px var(--font-mono); color: var(--ink-700); }
  button.chip:hover { background: var(--coral-100); color: var(--ink-900); }
  .point.sel { background: rgb(0 0 0 / 0.045); box-shadow: inset 3px 0 0 var(--coral-700); }
  .edit { display: block; width: calc(100% + 12px); margin: -3px -6px; padding: 3px 6px; border: 0; border-radius: 4px; background: #fff; box-shadow: inset 0 0 0 1px #cfced6, inset 0 -2px 0 var(--coral-700); font: inherit; color: inherit; resize: none; outline: none; field-sizing: content; }
  .strip { grid-column: 2 / -1; display: flex; align-items: center; gap: 8px; margin-top: 8px; padding: 4px 6px 4px 8px; border-radius: 4px; background: var(--warn-bg); box-shadow: inset 0 0 0 1px rgb(183 121 31 / 0.25); font-size: 11.5px; }
  .strip svg { flex: none; color: var(--warn); }
  .strip .btn, .gone .btn, .after .btn { font-family: var(--font-ui); }
  .dot { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--warn); }
  :global(:root[data-platform='mac']) .chip { border-radius: 9px; }
  :global(:root[data-platform='mac']) .point.sel { background: var(--coral-50); box-shadow: inset 0 0 0 1px var(--coral-200); }
  :global(:root[data-platform='mac']) .edit { box-shadow: 0 0 0 1px var(--coral-700), 0 0 0 4px rgb(201 58 66 / 0.25); }
  :global(:root[data-platform='mac']) .strip { border-radius: 5px; box-shadow: none; }
  /* A narrow window: the page keeps its text column and gives up margin and some of the two last columns. */
  @container (max-width: 700px) {
    .paper { max-width: calc(100% - 20px); padding: 20px 16px 28px; }
    .colstrip { padding: 0 10px; }
    .colstrip .prow { padding: 0 22px; }
    .prow { grid-template-columns: 42px 52px minmax(0, 1fr) 46px 76px 80px; column-gap: 6px; }
  }
  .after { margin-top: 22px; padding-top: 10px; border-top: 1px solid var(--rule); }
  .after h3, .after summary { font: 600 12px/1.4 var(--font-body); color: var(--ink-700); cursor: default; }
  .after > p { margin-top: 4px; }
  .gone { display: flex; align-items: baseline; gap: 8px; padding: 4px 6px; color: var(--ink-500); }
  .gone .no { flex: none; width: 42px; }
  .gone .kind { flex: none; width: 58px; }
  .gone .btn { align-self: center; }
  .about { max-width: 560px; }

  /* The inspector. */
  .inspector { flex: none; width: 300px; display: flex; flex-direction: column; min-height: 0; background: var(--quiet); border-left: 1px solid var(--rule); }
  .tabs { flex: none; display: flex; align-items: stretch; height: 40px; padding: 0 14px; border-bottom: 1px solid var(--rule); }
  .seg { display: flex; gap: 20px; flex: 1 1 auto; }
  .seg button { padding: 0; border: 0; border-radius: 0; background: transparent; color: var(--ink-500); }
  .seg button.on { color: var(--ink-900); font-weight: 600; box-shadow: inset 0 -3px 0 var(--coral-700); }
  .chosen { display: inline-flex; align-items: center; font: 0.92em var(--font-mono); color: var(--ink-500); }
  :global(:root[data-platform='mac']) .inspector { background: var(--canvas); }
  :global(:root[data-platform='mac']) .tabs { height: auto; justify-content: center; padding: 8px; }
  :global(:root[data-platform='mac']) .chosen { display: none; }
  :global(:root[data-platform='mac']) .seg { flex: none; gap: 0; padding: 2px; border-radius: 7px; background: rgb(0 0 0 / 0.06); }
  :global(:root[data-platform='mac']) .seg button { height: 24px; padding: 0 12px; border-radius: 6px; color: var(--ink-900); }
  :global(:root[data-platform='mac']) .seg button.on { background: #fff; box-shadow: 0 1px 2px rgb(0 0 0 / 0.16); }
  .panel { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; overflow-y: auto; }
  .stommen { gap: 8px; padding: 12px 14px; }
  .quiet-text { color: var(--ink-500); }
  .bad { padding: 6px 10px; border-radius: var(--ctl-r); background: var(--bad-bg); }
  .ask { display: flex; flex-direction: column; gap: 10px; padding: 8px 10px; border-radius: var(--ctl-r); background: #fff; box-shadow: inset 0 0 0 1px var(--rule); }
  .act { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .found { flex: none; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 14px; border-bottom: 1px solid var(--soft); font-size: var(--ui-small); color: var(--ink-500); }
  .lines { display: flex; flex-direction: column; gap: 2px; padding: 8px; }
  .lines li { display: flex; gap: 8px; align-items: flex-start; padding: 4px 6px; border-radius: var(--ctl-r); }
  .lines li.active { background: var(--coral-50); box-shadow: inset 0 0 0 1px var(--coral-200); }
  .lines .chip { flex: none; margin-top: 1px; }
  .lines p { min-width: 0; overflow-wrap: anywhere; }
  .lines strong { font-weight: 600; }

  /* The recording. */
  .transport { flex: none; display: flex; align-items: center; gap: 6px; height: 40px; padding: 0 12px; border-top: 1px solid var(--rule); background: var(--quiet); }
  .transport .tb { height: 30px; padding: 0 8px; }
  .transport .tb svg { color: var(--ink-700); }
  .at { margin-left: 6px; font: 0.92em var(--font-mono); }
  .at.all { margin-left: 0; color: var(--ink-500); }
  .of { font-size: var(--ui-small); color: var(--ink-500); white-space: nowrap; }
  .scrub { position: relative; flex: 1 1 auto; min-width: 60px; height: 16px; margin: 0 10px; touch-action: none; }
  .scrub[aria-disabled='true'] .knob { display: none; }
  .track, .played { position: absolute; left: 0; top: 6px; height: 4px; border-radius: 2px; }
  .track { right: 0; background: #8e8d99; }
  .played { background: var(--coral-700); }
  .mark-at { position: absolute; top: 3px; width: 2px; height: 10px; margin-left: -1px; border-radius: 1px; background: var(--ink-700); }
  .mark-at.on { background: var(--coral-800); }
  .knob { position: absolute; top: -1px; width: 18px; height: 18px; margin-left: -9px; border-radius: 50%; background: #fff; border: 1px solid #c4c3cc; }
  .knob::after { content: ''; position: absolute; inset: 3px; border-radius: 50%; background: var(--coral-700); }
  .rate { flex: none; height: 26px; font-size: 12px; }
  :global(:root[data-platform='mac']) .transport { gap: 8px; padding: 0 14px; }
  :global(:root[data-platform='mac']) .transport .tb { height: 28px; padding: 0 7px; }
  :global(:root[data-platform='mac']) .at { margin-left: 4px; }
  :global(:root[data-platform='mac']) .at.all { margin-left: 0; }
  :global(:root[data-platform='mac']) .scrub { margin: 0 8px; }
  :global(:root[data-platform='mac']) .track { background: var(--rule); }
  :global(:root[data-platform='mac']) .mark-at { background: var(--ink-400); }
  :global(:root[data-platform='mac']) .mark-at.on { background: var(--coral-800); }
  :global(:root[data-platform='mac']) .knob { top: 1px; width: 14px; height: 14px; margin-left: -7px; border-color: #b9b8c2; box-shadow: 0 1px 2px rgb(0 0 0 / 0.2); }
  :global(:root[data-platform='mac']) .knob::after { content: none; }
  :global(:root[data-platform='mac']) .rate { height: 22px; padding: 0 22px 0 8px; font-size: 11px; background-position: right 6px center; background-size: 8px 10px; }

  /* The status line. */
  .status { flex: none; display: flex; align-items: center; gap: 16px; height: 26px; padding: 0 12px; border-top: 1px solid var(--rule); background: var(--pane); font-size: 12px; color: var(--ink-500); white-space: nowrap; overflow: hidden; }
  .status .sepd, .promise { display: inline-flex; align-items: center; gap: 6px; }
  :global(:root[data-platform='mac']) .status { gap: 6px; height: 24px; padding: 0 14px; background: #f6f5f9; font-size: 11px; }
  :global(:root[data-platform='mac']) .status > span + .sepd::before { content: '·'; }
  :global(:root[data-platform='mac']) .status .sepd { gap: 5px; }
</style>
