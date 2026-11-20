<script lang="ts">
  import type { Kind, MeetingDetail, Point, Project } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { clock, day, failure, KINDS, minutes, overdue } from '../lib/format'
  import type { Go } from '../lib/view'

  let { project, dir, problem: handed, go }: { project: Project; dir: string; problem: string; go: Go } = $props()

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
  void load()
  $effect(() => () => {
    if (sound) URL.revokeObjectURL(sound)
  })

  const p = $derived(m?.protocol ?? null)
  const series = $derived(project.series.find((s) => s.id === (m?.series ?? p?.series)) ?? project.series[0])
  const unnamed = $derived(m ? m.speakers.filter((s) => !s.person && /^Talare \d+$/.test(s.name)) : [])
  const shown = $derived.by(() => {
    const q = query.trim().toLowerCase()
    return m ? m.lines.filter((l) => !q || l.text.toLowerCase().includes(q) || l.who.toLowerCase().includes(q)) : []
  })
  const checks = $derived(p ? p.points.reduce((n, x) => n + x.checks.length, 0) : 0)

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

  async function write(): Promise<void> {
    if (!series) return
    writing = true
    wrote = ''
    try {
      await window.api.writeProtocol(dir, series.id)
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
          <h1>{p ? `Protokoll, ${p.name.toLowerCase()} ${p.no}` : m.title}</h1>
          {#if p?.status === 'draft'}<span class="badge"><Icon name="file" size={14} /> Utkast</span>{/if}
        </div>
        <p class="muted">{day(m.recorded_at)}. {minutes(m.duration)}, {m.speakers.length === 1 ? 'en talare' : `${m.speakers.length} talare`}.</p>
      </div>
      <div class="row">
        <button class="btn" onclick={() => go({ name: 'meetings' })}><Icon name="back" /> Till möten</button>
        {#if p && series}
          <button class="btn" disabled={writing} onclick={write}><Icon name="refresh" /> Skriv om protokollet</button>
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
        {:else if stale}
          <div class="note warn" role="status">
            <Icon name="alert" />
            <p><strong>Talarna har fått namn sedan protokollet skrevs.</strong> Skriv om det, så står rätt personer och Roller som närvarande.</p>
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
                  <select class="field" aria-label="Vem är {s.name}?" bind:value={naming[s.id]}>
                    <option value="">Välj person</option>
                    {#each project.people as person (person.id)}
                      <option value={person.id}>{person.name}{person.role ? `, ${person.role}` : ''}</option>
                    {/each}
                  </select>
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
              <button class="btn primary" style="margin-top: 16px" disabled={writing} onclick={write}>Skriv protokollet</button>
            {:else}
              <p class="small muted" style="margin-top: 12px">Projektet behöver en mötesserie först. Den startas från Möten.</p>
            {/if}
          </section>
        {:else}
          <div class="note">
            <Icon name="lock" />
            <p>
              Protokollet är skrivet från inspelningen av en språkmodell på den här datorn. Inget har skickats ut. Varje punkt
              pekar på stället där det sades. Läs igenom det mot inspelningen innan det går vidare.
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

          <article class="card document">
            {#each p.headings as h (h.no)}
              <section aria-labelledby="h-{h.no}">
                <h2 id="h-{h.no}"><span class="mono muted">{h.no}</span> {h.name}</h2>
                {#if h.fill === 'attendees'}
                  {#if p.attendees.length}
                    <ul class="attendees">
                      {#each p.attendees as a}<li>{a.name}{#if a.role}<span class="muted">, {a.role}</span>{/if}</li>{/each}
                    </ul>
                  {:else}
                    <p class="muted">Ingen talare i inspelningen.</p>
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
                        <span class="grow"></span>
                        {#if x.at !== null}
                          <button class="time" aria-label="Lyssna från {clock(x.at)}" onclick={() => listen(x.at!, x.line)}>
                            <span><Icon name="play" size={12} /> {clock(x.at)}</span>
                          </button>
                        {/if}
                      </div>
                      <p>{sentence(x.text)}</p>
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
                      {#each x.checks as c}
                        <div class="note warn check">
                          <Icon name="alert" size={16} />
                          {#if c.code === 'amount'}
                            <p><strong>Kontrollera beloppet {c.value}.</strong> I inspelningen sägs: ”{c.said}”</p>
                          {:else}
                            <p><strong>Rollen ”{c.said}” finns inte i projektet.</strong> Punkten har ingen ansvarig.</p>
                          {/if}
                        </div>
                      {/each}
                    </div>
                  {:else}
                    <p class="muted">Inget noterat.</p>
                  {/each}
                {/if}
              </section>
            {/each}
          </article>

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
  .document h2 { display: flex; gap: 12px; align-items: baseline; padding-bottom: 8px; margin-bottom: 8px; border-bottom: 1px solid var(--line); }
  .attendees { display: flex; flex-direction: column; gap: 2px; }
  .point { display: flex; flex-direction: column; gap: 4px; padding: 8px 12px 12px; margin: 0 -12px; border-radius: var(--radius-sm); }
  .point.selected { background: var(--coral-50); }
  .badge.plain { padding-left: 10px; }
  .top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; min-height: 44px; }
  .follow { padding-left: 12px; border-left: 2px solid var(--line); }
  .check { margin-top: 6px; padding: 10px 12px; }
  .speakers li { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 0; border-bottom: 1px solid var(--line); }
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
