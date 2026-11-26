<script lang="ts">
  // What earlier meetings left open, across the project's mötesserier: a list to work through, with the chosen
  // point beside it. The points are the agendas': nothing is kept here.
  import type { Agenda, MeetingRow, OpenPoint } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { KINDS, overdue } from '../lib/format'
  import { tools } from '../lib/tools'
  import type { Go } from '../lib/view'

  let { rows, agendas, go }: { rows: MeetingRow[]; agendas: Agenda[] | null; go: Go } = $props()

  type Row = OpenPoint & { series: string; seriesName: string; under: string; from: number }

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
  // The meeting a point was raised at, when it is still among the project's meetings.
  const meeting = $derived(point ? (rows.find((r) => r.series === point.series && r.no === point.from) ?? null) : null)
</script>

<div class="view">
  <div class="tools" use:tools>
    <div class="seg" role="group" aria-label="Vilka punkter">
      <button aria-pressed={only === 'all'} onclick={() => (only = 'all')}>Alla</button>
      <button aria-pressed={only === 'late'} onclick={() => (only = 'late')}>Förfallna</button>
    </div>
    <label class="search">
      <span class="sr">Sök bland punkterna</span>
      <Icon name="search" size={15} />
      <input type="search" placeholder="Sök bland punkterna" bind:value={query} />
    </label>
  </div>

  <section class="list" aria-labelledby="points-title">
    <h1 id="points-title" class="sr">Öppna punkter</h1>
    {#if agendas === null}
      <p class="muted pad">Läser in punkterna.</p>
    {:else if !all.length}
      <p class="muted pad">Inga punkter väntar.</p>
    {:else}
      <table class="table">
        <thead>
          <tr><th>Nr</th><th>Typ</th><th>Punkt</th><th>Ansvarig</th><th>Senast</th><th>Från möte</th></tr>
        </thead>
        <tbody>
          {#each shown as p (key(p))}
            <tr class:chosen={point !== null && key(p) === key(point)} aria-selected={point !== null && key(p) === key(point)} onclick={() => (chosen = key(p))}>
              <td class="mono"><button class="pick" onclick={() => (chosen = key(p))}>{p.no}</button></td>
              <td>{KINDS[p.kind]}</td>
              <td class="wrap">{p.text}</td>
              <td>{p.role ?? ''}</td>
              <td class="mono">
                {#if !p.due}<span class="muted plain">Inget datum</span>
                {:else if overdue(p.due)}<span class="late"><span class="dot"></span>{p.due}</span>
                {:else}{p.due}{/if}
              </td>
              <td>{p.seriesName} {p.from}</td>
            </tr>
          {:else}
            <tr><td colspan="6" class="muted">Ingen punkt stämmer med urvalet.</td></tr>
          {/each}
        </tbody>
      </table>
      <p class="small muted pad">
        {all.length === 1 ? 'En öppen punkt' : `${all.length} öppna punkter`}{late ? `, ${late === 1 ? 'en har' : `${late} har`} passerat sitt datum` : ''}.
        Punkterna följer med till nästa mötes dagordning.
      </p>
    {/if}
  </section>

  {#if point}
    <aside class="inspector" aria-label="Vald punkt">
      <p class="small muted"><span class="mono">{point.no}</span> · {KINDS[point.kind]}</p>
      <p class="text">{point.text}</p>
      <dl>
        <div><dt>Ansvarig</dt><dd>{point.role ?? 'Ingen ansvarig'}</dd></div>
        <div><dt>Senast</dt><dd class:late={overdue(point.due)}>{point.due ? `${point.due}${overdue(point.due) ? ', förfallen' : ''}` : 'Inget datum'}</dd></div>
        <div><dt>Togs upp på</dt><dd>{point.seriesName} {point.from}</dd></div>
        <div><dt>Rubrik</dt><dd>{point.under}</dd></div>
      </dl>
      {#if meeting}
        <button class="btn" onclick={() => go({ name: 'protocol', dir: meeting.dir })}>Öppna i protokollet</button>
      {/if}
    </aside>
  {/if}
</div>

<style>
  .view { display: flex; height: 100%; background: var(--surface); }
  .list { flex: 1 1 auto; min-width: 0; overflow: auto; }
  .pad { padding: 12px 14px; }
  .tools { display: flex; align-items: center; gap: 8px; }
  .seg { display: inline-flex; padding: 2px; border-radius: calc(var(--ctl-r) + 1px); background: rgb(0 0 0 / 0.06); }
  .seg button { height: calc(var(--ctl-h) - 4px); padding: 0 12px; border: 0; border-radius: var(--ctl-r); background: transparent; }
  .seg button[aria-pressed='true'] { background: var(--surface); box-shadow: 0 1px 2px rgb(0 0 0 / 0.16); font-weight: 600; }
  .search { display: flex; align-items: center; gap: 6px; width: 220px; height: var(--ctl-h); padding: 0 8px; border: 1px solid var(--edge); border-radius: var(--ctl-r); background: var(--surface); color: var(--ink-500); }
  .search:focus-within { box-shadow: var(--focus); }
  .search input { flex: 1; min-width: 0; height: 100%; border: 0; background: transparent; color: var(--ink-900); outline: none; box-shadow: none; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  tbody tr { cursor: default; }
  tr.chosen td { background: rgb(201 58 66 / 0.1); }
  tr.chosen td:first-child { box-shadow: inset 3px 0 0 var(--coral-700); }
  .pick { padding: 0; border: 0; background: transparent; font: inherit; }
  .late { display: inline-flex; align-items: center; gap: 5px; color: var(--bad); }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--bad); }
  .plain { font-family: var(--font-ui); }
  .inspector { flex: none; width: 320px; display: flex; flex-direction: column; align-items: flex-start; gap: 8px; padding: 14px; overflow-y: auto; background: var(--canvas); border-left: 1px solid var(--line); }
  .text { font-weight: 600; font-size: calc(var(--ui) + 2px); line-height: 1.35; }
  dl { align-self: stretch; margin: 4px 0; padding: 8px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); display: flex; flex-direction: column; gap: 4px; }
  dl div { display: flex; justify-content: space-between; gap: 12px; }
  dt { color: var(--ink-500); }
  dd { margin: 0; text-align: right; }
  dd.late { color: var(--bad); }
</style>
