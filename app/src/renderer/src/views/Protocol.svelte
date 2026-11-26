<script lang="ts">
  import { tick } from 'svelte'
  import type { Confirmation, Kind, MeetingDetail, NewPoint, Point, PointFields, Project } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import PointForm from '../lib/PointForm.svelte'
  import { clock, day, failure, KINDS, minutes, overdue } from '../lib/format'
  import type { Go } from '../lib/view'

  let { project, dir, problem: handed, connected, go, refresh }: { project: Project; dir: string; problem: string; connected: boolean; go: Go; refresh: () => Promise<void> } = $props()

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
  let typed = $state<Record<string, string>>({}) // the name written for a speaker
  let everyone = $state<Record<string, boolean>>({}) // a speaker whose list shows the whole project
  let busy = $state<string | null>(null) // the speaker being named
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

  type Speaker = MeetingDetail['speakers'][number]
  const SHOWN = 8 // names before "N till": a Projekt from Stommen can have many Kontakter

  /** Names a speaker, then the next one without a name gets the focus, so a meeting is named from the keyboard. */
  async function name(s: Speaker, who: { person: string } | { name: string }): Promise<void> {
    busy = s.id
    try {
      await window.api.nameSpeaker(dir, s.id, who)
      delete typed[s.id]
      stale = Boolean(p)
      if ('name' in who) await refresh() // a new person is in the project now
      await load()
      problem = ''
      await tick()
      document.querySelector<HTMLInputElement>('.speakers input')?.focus()
    } catch (e) {
      problem = failure(e)
    } finally {
      busy = null
    }
  }

  /** What is written for a speaker, its spaces tidied. */
  const written = (s: Speaker): string => (typed[s.id] ?? '').split(/\s+/).filter(Boolean).join(' ')
  const fits = (s: Speaker, x: { name: string; role?: string }): boolean => `${x.name} ${x.role ?? ''}`.toLowerCase().includes(written(s).toLowerCase())

  /** The person offered with just the written name: one of the project's, or who the voice sounds like. */
  function same(s: Speaker): string | null {
    const t = written(s).toLowerCase()
    if (!t) return null
    return project.people.find((x) => x.name.toLowerCase() === t)?.id ?? (s.voice?.name.toLowerCase() === t ? s.voice.person : null)
  }

  /** Enter: the person with the written name, else a new person with it. */
  function enter(s: Speaker): void {
    const text = written(s)
    if (!text || busy) return
    const hit = same(s)
    void name(s, hit ? { person: hit } : { name: text })
  }

  /** The project's people that fit what is written, those not yet heard in the meeting first. Not the voice's match: it is offered on its own. */
  function choices(s: Speaker) {
    const hit = project.people.filter((x) => x.id !== s.voice?.person && fits(s, x))
    const heard = new Set(m?.speakers.map((x) => x.person))
    return [...hit.filter((x) => !heard.has(x.id)), ...hit.filter((x) => heard.has(x.id))]
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

  const tone: Partial<Record<Kind, string>> = { decision: 'ok', risk: 'warn' }
  const icon = (k: Kind): 'check' | 'alert' | 'flag' => (k === 'decision' ? 'check' : k === 'risk' ? 'alert' : 'flag')
  const sentence = (t: string): string => (/[.!?]$/.test(t) ? t : `${t}.`)
  const under = (no: number): Point[] => (p ? p.points.filter((x) => x.heading === no) : [])
</script>

<div class="page">
  {#if problem && !m}
    <div class="note bad" role="alert">
      <Icon name="alert" />
      <div>
        <p><strong>Det gick inte att läsa mötet.</strong></p>
        <p class="small mono">{problem}</p>
        <button class="btn" style="margin-top: 12px" onclick={() => go({ name: 'meetings' })}>Till möten</button>
      </div>
    </div>
  {:else if !m}
    <p class="muted">Läser in mötet.</p>
  {:else}
    <div class="page-head">
      <div>
        <div class="row">
          {#if renaming !== null}
            <form class="row" onsubmit={(e) => { e.preventDefault(); void rename() }}>
              <input class="field" aria-label="Mötets namn" bind:value={renaming} onkeydown={(e) => e.key === 'Escape' && (renaming = null)} />
              <button class="btn" type="submit" disabled={!renaming.trim()}>Spara</button>
              <button class="btn" type="button" onclick={() => (renaming = null)}>Avbryt</button>
            </form>
          {:else}
            <h1>{p && !renamed ? `Protokoll, ${p.name.toLowerCase()} ${p.no}` : m.title}</h1>
          {/if}
          {#if renaming === null}<button class="btn" onclick={() => (renaming = m?.title ?? '')}><Icon name="edit" /> Byt namn</button>{/if}
          {#if confirmed}<span class="badge"><Icon name="lock" size={14} /> Justerat</span>
          {:else if p?.status === 'draft'}<span class="badge"><Icon name="file" size={14} /> Utkast</span>{/if}
        </div>
        <p class="muted">{day(m.recorded_at)}. {minutes(m.duration)}, {m.speakers.length === 1 ? 'en talare' : `${m.speakers.length} talare`}.</p>
      </div>
      <div class="row">
        <button class="btn" onclick={() => go({ name: 'meetings' })}><Icon name="back" /> Till möten</button>
        {#if p}
          <div class="menu" onfocusout={(e) => !e.currentTarget.contains(e.relatedTarget as Node | null) && (saving = false)}
            onkeydown={saveKeys} role="presentation">
            <button id="save-as" class="btn" aria-haspopup="menu" aria-expanded={saving} aria-controls="save-as-menu" onclick={() => (saving = !saving)}>
              <Icon name="file" /> Spara som <Icon name="down" size={16} />
            </button>
            {#if saving}
              <ul class="options" id="save-as-menu" role="menu" aria-labelledby="save-as">
                {#each SAVE as [how, label] (how)}
                  <li role="none"><button type="button" role="menuitem" onclick={() => { saving = false; void keep(how) }}>{label}</button></li>
                {/each}
              </ul>
            {/if}
          </div>
          <button class="btn" onclick={() => keep('copy')}>{copied ? 'Kopierat' : 'Kopiera texten'}</button>
        {/if}
        {#if p && series && free}
          <button class="btn" disabled={writing} onclick={() => write()}><Icon name="refresh" /> Skriv om protokollet</button>
        {/if}
      </div>
    </div>

    {#if problem}
      <div class="note bad" role="alert" style="margin-bottom: 16px"><Icon name="alert" /><p class="small mono">{problem}</p></div>
    {/if}

    <div class="columns">
      <div class="main stack">
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
            <p class="muted">Lyssna på en rad och skriv vem det är, eller välj ett namn. Namnen styr vilka som står som närvarande, och med vilken Roll.</p>
            <ul class="speakers">
              {#each unnamed as s (s.id)}
                {@const first = m.lines.find((l) => l.speaker === s.id)}
                {@const list = choices(s)}
                {@const few = everyone[s.id] || written(s) ? list : list.slice(0, SHOWN)}
                <li>
                  <div class="said">
                    <div class="grow">
                      <p><strong>{s.name}</strong></p>
                      {#if first}<p class="small muted clamp">”{first.text}”</p>{/if}
                    </div>
                    {#if first}
                      <button class="time" aria-label="Lyssna på {s.name} från {clock(first.at)}" onclick={() => listen(first.at, first.id)}>
                        <span><Icon name="play" size={12} /> {clock(first.at)}</span>
                      </button>
                    {/if}
                  </div>
                  <label class="name">
                    <input
                      class="field"
                      type="text"
                      aria-label="Vem är {s.name}?"
                      placeholder="Skriv ett namn"
                      autocomplete="off"
                      disabled={busy === s.id}
                      value={typed[s.id] ?? ''}
                      oninput={(e) => (typed[s.id] = e.currentTarget.value)}
                      onkeydown={(e) => {
                        if (e.isComposing) return
                        if (e.key === 'Enter') enter(s)
                        else if (e.key === 'Escape' && typed[s.id]) typed[s.id] = ''
                        else return
                        e.preventDefault()
                      }}
                    />
                    <kbd aria-hidden="true">↩</kbd>
                  </label>
                  {#if written(s) && !same(s)}
                    <p class="small muted">
                      Enter sparar ”{written(s)}” som en ny person {project.stommen ? 'här. I Stommen står namnet utan Kontakt.' : 'i projektet.'}
                    </p>
                  {/if}
                  {#if s.voice && fits(s, s.voice)}
                    {@const voice = s.voice}
                    <p class="small muted" id="heard-{s.id}">Rösten känns igen från ett tidigare möte</p>
                    <div class="chips" role="group" aria-labelledby="heard-{s.id}">
                      <button class="chip heard" disabled={busy === s.id} onclick={() => name(s, { person: voice.person })}>
                        <Icon name="wave" size={14} /> {voice.name}
                      </button>
                    </div>
                  {/if}
                  {#if list.length}
                    <p class="small muted" id="people-{s.id}">I projektet</p>
                    <div class="chips" role="group" aria-labelledby="people-{s.id}">
                      {#each few as x (x.id)}
                        <button class="chip" title={x.role} disabled={busy === s.id} onclick={() => name(s, { person: x.id })}>{x.name}</button>
                      {/each}
                      {#if few.length < list.length}
                        <button class="chip more" onclick={() => (everyone[s.id] = true)}>{list.length - few.length} till</button>
                      {/if}
                    </div>
                  {/if}
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
              <p class="small muted" style="margin-top: 12px">Projektet behöver en mötesserie först. Den startas från Möten.</p>
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

          {#if standing && standing.why !== 'local'}
            <section class="card" aria-labelledby="to-stommen">
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

          <article class="card document">
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

      <aside class="side transcript card" aria-labelledby="transcript">
        <h2 id="transcript">Utskrift</h2>
        {#if sound}
          <audio bind:this={player} src={sound} controls preload="metadata"></audio>
        {:else}
          <p class="small muted">{m.audio ? 'Ljudet läses in.' : 'Mötet har inget ljud sparat.'}</p>
        {/if}
        <label class="search">
          <span class="sr">Sök i utskriften</span>
          <Icon name="search" size={16} />
          <input type="search" placeholder="Sök i utskriften" bind:value={query} />
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
      </aside>
    </div>
  {/if}
</div>

<style>
  .document { display: flex; flex-direction: column; gap: 28px; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; min-height: 44px; margin-bottom: 8px;
    border-bottom: 1px solid var(--line); }
  .head h2 { display: flex; gap: 12px; align-items: baseline; }
  /* One under every heading and on every point: quiet until it is wanted, so the document is what is read. */
  .head .btn, .top .btn { color: var(--ink-500); font-weight: 400; }
  .head .btn:hover:not(:disabled), .top .btn:hover:not(:disabled) { color: var(--coral-800); }
  .attendees { display: flex; flex-direction: column; gap: 2px; }
  .attendees li { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; min-height: 28px; }
  .point { display: flex; flex-direction: column; gap: 4px; padding: 8px 12px 12px; margin: 0 -12px; border-radius: var(--radius-sm); }
  .point.selected { background: var(--coral-50); }
  .badge.plain { padding-left: 10px; }
  .top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; min-height: 44px; }
  .follow { padding-left: 12px; border-left: 2px solid var(--line); }
  .check { margin-top: 6px; padding: 10px 12px; }
  .answers { margin-top: 8px; gap: 8px; }
  .confirmed { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .confirmed :global(svg) { flex: none; color: var(--ok); }
  .point :global(.form) { margin: 4px 0 8px; }
  .speakers li { display: grid; gap: 8px; padding: 16px 0; border-bottom: 1px solid var(--line); }
  .said { display: flex; align-items: center; gap: 12px; }
  .name { position: relative; display: block; max-width: 360px; margin-top: 4px; }
  .name .field { width: 100%; padding-right: 40px; }
  .name kbd { position: absolute; top: 50%; right: 14px; transform: translateY(-50%); font-family: var(--font-mono); font-size: 16px; color: var(--ink-400); pointer-events: none; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; min-height: 40px; padding: 0 16px; border: 1px solid var(--ink-300); border-radius: var(--radius-pill); background: var(--surface); color: var(--ink-700); font: inherit; font-size: 14px; cursor: pointer; }
  .chip:hover:not(:disabled) { border-color: var(--ink-500); color: var(--ink-900); }
  .chip:disabled { opacity: 0.5; cursor: default; }
  .chip.heard { border-color: var(--coral-200); background: var(--coral-50); color: var(--ink-900); font-weight: 500; }
  .chip.heard :global(svg) { color: var(--coral-700); }
  .chip.more { border-style: dashed; color: var(--ink-500); }
  .menu { position: relative; }
  .menu .options { right: auto; min-width: 100%; }
  .options { position: absolute; z-index: 20; top: calc(100% + 4px); left: 0; right: 0; max-height: 240px; overflow: auto; margin: 0; padding: 4px; list-style: none; background: var(--surface); border: 1px solid var(--ink-300); border-radius: var(--radius-sm); box-shadow: 0 8px 24px rgb(0 0 0 / 0.12); }
  .options button { display: flex; align-items: center; gap: 6px; width: 100%; min-height: 40px; padding: 0 10px; border: 0; border-radius: 6px; background: none; text-align: left; font: inherit; cursor: pointer; }
  .options button:hover, .options button:focus-visible { background: var(--ink-100, #f3f3f3); }
  .speakers li:last-child { border-bottom: 0; padding-bottom: 0; }
  .clamp { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  details summary { cursor: pointer; font-weight: 500; min-height: 44px; display: flex; align-items: center; }
  .dropped { display: flex; flex-direction: column; gap: 12px; }
  .transcript { position: sticky; top: 24px; display: flex; flex-direction: column; gap: 12px; max-height: calc(100vh - 64px - 48px); padding-bottom: 12px; }
  audio { width: 100%; height: 44px; }
  .search { display: flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 12px; border: 1px solid var(--ink-300); border-radius: var(--radius-sm); color: var(--ink-500); }
  .search:focus-within { box-shadow: var(--focus); }
  .search input { flex: 1; min-width: 0; height: 42px; border: 0; background: transparent; color: var(--ink-900); outline: none; box-shadow: none; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .lines { overflow: auto; margin: 0 -12px; display: flex; flex-direction: column; }
  .lines li { display: flex; gap: 4px; align-items: flex-start; padding: 2px 12px 2px 4px; border-radius: var(--radius-sm); }
  .lines li.active { background: var(--coral-50); }
  .lines p { padding-top: 10px; padding-bottom: 6px; }
  @media (max-width: 1000px) { .transcript { position: static; max-height: 70vh; } }
</style>
