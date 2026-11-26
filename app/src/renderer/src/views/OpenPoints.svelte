<script lang="ts">
  // What earlier meetings left open, across the project's mötesserier: a list to work through, with the chosen
  // point beside it. The points are the agendas': nothing is kept here. What the latest meeting said of a point and
  // where it was first said are read from those meetings' protocols when the point is chosen.
  import type { Agenda, MeetingDetail, MeetingRow, OpenPoint, Project } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { clock, KINDS, overdue } from '../lib/format'
  import { title, tools } from '../lib/tools'
  import type { Go } from '../lib/view'

  let { project, rows, agendas, go }: { project: Project; rows: MeetingRow[]; agendas: Agenda[] | null; go: Go } = $props()

  type Row = OpenPoint & { series: string; seriesName: string; under: string; from: number }

  const mac = window.api.platform === 'darwin'
  let only = $state<'all' | 'late'>('all')
  let query = $state('')
  let chosen = $state<string | null>(null) // series and number of the point beside the list

  const key = (p: Row): string => `${p.series} ${p.no}`
  const all = $derived(
    (agendas ?? [])
      .flatMap((a) => a.headings.flatMap((h) => h.open.map((p): Row => ({ ...p, series: a.series, seriesName: a.name, under: `${h.no} ${h.name}`, from: Number(p.no.split('.')[0]) }))))
      .sort((a, b) => Number(overdue(b.due)) - Number(overdue(a.due)) || (a.due ?? '9').localeCompare(b.due ?? '9'))
  )
  const late = $derived(all.filter((p) => overdue(p.due)).length)
  const shown = $derived.by(() => {
    const q = query.trim().toLowerCase()
    return all.filter((p) => (only === 'all' || overdue(p.due)) && (!q || `${p.no} ${p.text} ${p.role ?? ''} ${KINDS[p.kind]}`.toLowerCase().includes(q)))
  })
  const point = $derived(shown.find((p) => key(p) === chosen) ?? shown[0] ?? null)
  // The meeting a point was raised at, when it is still among the project's meetings, and the latest one after it.
  const meeting = $derived(point ? (rows.find((r) => r.series === point.series && r.no === point.from) ?? null) : null)
  const latest = $derived.by(() => {
    if (!point) return null
    const after = rows.filter((r) => r.series === point.series && r.no !== null && r.no > point.from && r.protocol).sort((a, b) => (b.no ?? 0) - (a.no ?? 0))
    return after[0] ?? null
  })

  const read = new Map<string, Promise<MeetingDetail | null>>()
  const detail = (dir: string): Promise<MeetingDetail | null> => {
    if (!read.has(dir)) read.set(dir, window.api.meeting(dir).catch(() => null))
    return read.get(dir)!
  }
  // Where the point is said in the recording of its own meeting, and what the latest meeting's protocol says of it.
  let said = $state<{ for: string; at: number; who: string; text: string } | null>(null)
  let then = $state<{ for: string; no: number; name: string; text: string; quoted: boolean } | null>(null)
  $effect(() => {
    const p = point
    if (!p) return
    const k = key(p)
    if (meeting) void detail(meeting.dir).then((m) => {
      const x = m?.protocol?.points.find((y) => y.no === p.no && y.since === undefined)
      const line = x ? m?.lines.find((l) => l.id === x.line) : undefined
      if (x && x.at !== null && (line || x.quote)) said = { for: k, at: x.at, who: line?.who ?? '', text: line?.text ?? x.quote ?? '' }
    })
    const l = latest
    if (l) void detail(l.dir).then((m) => {
      const x = m?.protocol?.points.find((y) => y.no === p.no && y.since !== undefined)
      if (!x || !m?.protocol) return
      const text = !x.raised ? 'Togs inte upp på mötet.' : x.follow ? (/[.!?]$/.test(x.follow) ? x.follow : `${x.follow}.`) : `”${x.said ?? ''}”`
      then = { for: k, no: m.protocol.no, name: m.protocol.name, text, quoted: Boolean(x.raised) }
    })
  })
  const here = $derived(point ? key(point) : '')

  const summary = $derived(agendas === null ? '' : `${all.length === 1 ? '1 punkt' : `${all.length} punkter`}${late ? `, ${late === 1 ? 'en har' : `${late} har`} passerat sitt datum` : ''}`)
  // Where the points go next: said by name when the project has one mötesserie.
  const next = $derived(agendas?.length === 1 ? `dagordningen för ${agendas[0].name.toLowerCase()} ${agendas[0].no}` : 'nästa mötes dagordning')
</script>

<div class="view">
  <div class="bar-title" class:sr={!mac} use:title={mac}>
    <h1 id="points-title">Öppna punkter</h1>
    <p>{project.name}{summary ? ` · ${summary}` : ''}</p>
  </div>
  <div class="tools" use:tools>
    <div class="seg" role="group" aria-label="Vilka punkter">
      <button aria-pressed={only === 'all'} onclick={() => (only = 'all')}>Alla</button>
      <button aria-pressed={only === 'late'} onclick={() => (only = 'late')}>Förfallna</button>
    </div>
    <span class="sep"></span>
    <label class="search">
      <span class="sr">Sök bland punkterna</span>
      <Icon name="search" size={14} />
      <input type="search" placeholder="Sök bland punkterna" bind:value={query} />
    </label>
  </div>

  <section class="list" aria-labelledby="points-title">
    {#if agendas === null}
      <p class="muted pad">Läser in punkterna.</p>
    {:else if !all.length}
      <p class="muted pad">Inga punkter väntar.</p>
    {:else}
      <table class="table">
        <colgroup><col class="c-no" /><col class="c-kind" /><col /><col class="c-who" /><col class="c-due" /><col class="c-from" /></colgroup>
        <thead>
          <tr>
            <th>Nr</th><th>Typ</th><th>Punkt</th><th>Ansvarig</th>
            <!-- The list is in the order of this column: what is past its date first, then the nearest date. -->
            <th class="sorted" aria-sort="ascending">Senast<svg width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 8.5v-7M2 4.5l3-3 3 3" /></svg></th>
            <th>Från möte</th>
          </tr>
        </thead>
        <tbody>
          {#each shown as p (key(p))}
            <tr class:chosen={key(p) === here} aria-selected={key(p) === here} onclick={() => (chosen = key(p))}>
              <td class="mono"><button class="pick" onclick={() => (chosen = key(p))}>{p.no}</button></td>
              <td>{KINDS[p.kind]}</td>
              <td class="wrap">{p.text}</td>
              <td class="wrap">{p.role ?? ''}</td>
              <td>
                {#if !p.due}<span class="muted">Inget datum</span>
                {:else if overdue(p.due)}<span class="late"><span class="dot"></span><span class="mono">{p.due}</span></span>
                {:else}<span class="mono">{p.due}</span>{/if}
              </td>
              <td>{p.seriesName} {p.from}</td>
            </tr>
          {:else}
            <tr><td colspan="6" class="muted">Ingen punkt stämmer med urvalet.</td></tr>
          {/each}
        </tbody>
      </table>
      <p class="small muted pad">Punkterna följer med till {next}.</p>
    {/if}
  </section>

  {#if point}
    <aside class="inspector" aria-label="Vald punkt">
      <section class="first">
        <h2><span class="mono">{point.no}</span> · {KINDS[point.kind]}</h2>
        <p class="text">{point.text}</p>
      </section>
      <section>
        <dl>
          <div><dt>Ansvarig</dt><dd>{point.role ?? 'Ingen ansvarig'}</dd></div>
          <div><dt>Senast</dt><dd class:late={overdue(point.due)}>{point.due ? `${point.due}${overdue(point.due) ? ', förfallen' : ''}` : 'Inget datum'}</dd></div>
          <div><dt>Togs upp på</dt><dd>{point.seriesName} {point.from}</dd></div>
          <div><dt>Rubrik</dt><dd>{point.under}</dd></div>
        </dl>
      </section>
      {#if then?.for === here}
        <section>
          <h2>På {then.name.toLowerCase()} {then.no}</h2>
          <p class:muted={!then.quoted}>{then.text}</p>
        </section>
      {/if}
      {#if said?.for === here}
        <section>
          <h2>I inspelningen</h2>
          <div class="said"><span class="at">{clock(said.at)}</span><span>{#if said.who}<b>{said.who}</b><br />{/if}{said.text}</span></div>
        </section>
      {/if}
      {#if meeting}
        <section class="last"><div><button class="btn" onclick={() => go({ name: 'protocol', dir: meeting.dir })}>Öppna i protokollet</button></div></section>
      {/if}
    </aside>
  {/if}
</div>

<style>
  .view { display: flex; height: 100%; background: var(--win-bg); }
  .list { flex: 1 1 auto; min-width: 0; overflow: auto; }
  .pad { padding: 12px; }
  .small { font-size: var(--ui-small); }
  .tools { display: flex; align-items: center; gap: 8px; }
  .seg { display: inline-flex; padding: 2px; border-radius: calc(var(--ctl-r) + 1px); background: rgb(0 0 0 / 0.06); }
  .seg button { height: calc(var(--ctl-h) - 4px); padding: 0 12px; border: 0; border-radius: var(--ctl-r); background: transparent; white-space: nowrap; }
  .seg button[aria-pressed='true'] { background: #fff; box-shadow: 0 1px 2px rgb(0 0 0 / 0.16); font-weight: 600; }
  .sep { width: 1px; height: 20px; margin: 0 4px; background: var(--line); }
  /* Windows' command bar: the choice at its start, the search at its end. */
  :global(:root[data-platform='win']) .tools { flex: 1 1 auto; }
  :global(:root[data-platform='win']) .sep { flex: 1 1 auto; height: 0; }
  /* The search field: white with an edge on Windows, a grey well on the Mac. */
  .search { display: flex; align-items: center; gap: 6px; width: 260px; height: var(--ctl-h); padding: 0 9px; border: 1px solid #dcdbe2; border-bottom-color: #8e8d99; border-radius: var(--ctl-r); background: #fff; color: var(--ink-500); }
  :global(:root[data-platform='mac']) .search { width: 180px; border-color: transparent; background: rgb(0 0 0 / 0.055); }
  :global(:root[data-platform='mac']) .sep ~ .search { margin-right: 4px; }
  .search:focus-within { box-shadow: var(--focus); }
  .search input { flex: 1; min-width: 0; height: 100%; padding: 0; border: 0; background: transparent; color: var(--ink-900); outline: none; box-shadow: none; }

  .table { table-layout: fixed; }
  .c-no { width: 66px; } .c-kind { width: 80px; } .c-who { width: 130px; } .c-due { width: 104px; } .c-from { width: 104px; }
  :global(:root[data-platform='mac']) .c-no { width: 60px; }
  :global(:root[data-platform='mac']) .c-kind { width: 72px; }
  :global(:root[data-platform='mac']) .c-who { width: 120px; }
  :global(:root[data-platform='mac']) .c-due { width: 108px; }
  :global(:root[data-platform='mac']) .c-from { width: 92px; }
  th.sorted { color: var(--ink-900); }
  th.sorted svg { margin-left: 4px; vertical-align: -1px; }
  .table td { padding: 0 10px; border-bottom-color: var(--line-soft); }
  .table td.wrap { min-width: 0; line-height: 1.35; padding-top: 7px; padding-bottom: 7px; }
  tbody tr { cursor: default; }
  .pick { padding: 0; border: 0; background: transparent; font: inherit; color: inherit; }
  .late { display: inline-flex; align-items: center; gap: 6px; color: var(--bad); }
  .dot { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--bad); }
  /* The chosen row: Windows' tint with the accent bar at its edge, the Mac's solid accent. */
  tr.chosen td { background: rgb(201 58 66 / 0.12); }
  tr.chosen td:first-child { box-shadow: inset 3px 0 0 var(--coral-700); }
  :global(:root[data-platform='mac']) tbody tr.chosen td { background: var(--coral-700); box-shadow: none; color: #fff; }
  :global(:root[data-platform='mac']) tr.chosen .late, :global(:root[data-platform='mac']) tr.chosen .muted { color: inherit; }
  :global(:root[data-platform='mac']) tr.chosen .dot { background: #fff; }

  .inspector { flex: none; width: 312px; display: flex; flex-direction: column; overflow-y: auto; background: var(--canvas); border-left: 1px solid var(--line); }
  .inspector section { display: flex; flex-direction: column; gap: 6px; padding: 10px 14px; border-bottom: 1px solid var(--line-soft); }
  .inspector section.first { gap: 8px; padding-top: 14px; }
  .inspector section.last { border-bottom: 0; }
  .inspector h2 { font: 600 var(--ui-small) / 1.35 var(--font-ui); letter-spacing: 0; color: var(--ink-500); }
  .inspector h2 .mono { font-size: 0.92em; }
  .text { font-weight: 600; font-size: 15px; line-height: 1.35; }
  dl { margin: 0; display: flex; flex-direction: column; gap: 6px; }
  dl div { display: flex; justify-content: space-between; gap: 12px; }
  dt { color: var(--ink-500); }
  dd { margin: 0; text-align: right; }
  dd.late { color: var(--bad); }
  .said { display: flex; align-items: flex-start; gap: 8px; }
  .said b { font-weight: 600; }
  .at { flex: none; display: inline-flex; align-items: center; height: 18px; padding: 0 6px; border-radius: 9px; background: var(--sunken); font: 500 11px var(--font-mono); color: var(--ink-700); }
</style>
