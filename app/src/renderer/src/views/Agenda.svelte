<script lang="ts">
  // The next meeting's agenda as an outline: the series' headings as rows, and under each the points earlier meetings
  // left open. Beside it, what follows along and how a point's number is read.
  import type { Agenda, Project, SeriesRef } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { failure, KINDS, overdue } from '../lib/format'
  import { title } from '../lib/tools'

  let { project, series }: { project: Project; series: SeriesRef } = $props()

  const mac = window.api.platform === 'darwin'
  let agenda = $state<Agenda | null>(null)
  let problem = $state('')
  let folded = $state<number[]>([]) // the headings whose points are put away

  $effect(() => {
    window.api
      .agenda(project.id, series.id)
      .then((a) => (agenda = a))
      .catch((e) => (problem = failure(e)))
  })

  const name = $derived(series.name.toLowerCase())
  const open = $derived(agenda ? agenda.headings.flatMap((h) => h.open) : [])
  const late = $derived(open.filter((p) => overdue(p.due)).length)
  // How many points each earlier meeting left: a point's number begins with its meeting's.
  const from = $derived.by(() => {
    const n = new Map<number, number>()
    for (const p of open) n.set(Number(p.no.split('.')[0]), (n.get(Number(p.no.split('.')[0])) ?? 0) + 1)
    return [...n].sort((a, b) => a[0] - b[0])
  })

  function fold(no: number): void {
    folded = folded.includes(no) ? folded.filter((x) => x !== no) : [...folded, no]
  }
</script>

<div class="view">
  <div class="bar-title" class:head={!mac} use:title={mac}>
    <h1>Dagordning, {name} {series.next}</h1>
    <p>Rubrikerna är seriens. Under dem står de punkter som tidigare möten lämnade öppna.</p>
  </div>

  {#if problem}
    <div class="pad"><div class="note bad" role="alert"><Icon name="alert" /><div><p><strong>Det gick inte att läsa dagordningen.</strong></p><p class="small mono">{problem}</p></div></div></div>
  {:else if !agenda}
    <p class="muted pad">Läser in dagordningen.</p>
  {:else}
    <div class="body">
      <section class="outline" aria-label="Rubriker och punkter">
        <div class="cols" aria-hidden="true"><span class="c1">Rubrik och punkt</span><span class="who">Ansvarig</span><span class="due">Senast</span></div>
        <ol class="headings">
          {#each agenda.headings as h (h.no)}
            {@const shut = folded.includes(h.no)}
            <li>
              <div class="heading">
                <span class="tw">
                  {#if h.open.length}
                    <button class="twist" class:shut aria-expanded={!shut} aria-label="{shut ? 'Visa' : 'Dölj'} punkterna under {h.name}" onclick={() => fold(h.no)}>
                      <svg width="8" height="6" viewBox="0 0 8 6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m1 1.5 3 3 3-3" /></svg>
                    </button>
                  {/if}
                </span>
                <span class="n">{h.no}</span>
                <h3>{h.name}</h3>
                <span class="hint">{h.hint ?? ''}</span>
                {#if h.open.length}<span class="cnt">{h.open.length === 1 ? '1 öppen punkt' : `${h.open.length} öppna punkter`}</span>{/if}
              </div>
              {#if h.open.length && !shut}
                <ul>
                  {#each h.open as p (p.no)}
                    <li class="point">
                      <span class="no">{p.no}</span>
                      <span class="ty">{KINDS[p.kind]}</span>
                      <span class="tx">{p.text}</span>
                      <span class="who">{p.role ?? ''}</span>
                      <span class="due" class:late={overdue(p.due)}>{p.due ? `${overdue(p.due) ? 'Förfallen' : 'Senast'} ${p.due}` : ''}</span>
                    </li>
                  {/each}
                </ul>
              {/if}
            </li>
          {/each}
        </ol>
      </section>

      <aside class="side" aria-label="Om dagordningen">
        <section>
          <h2>Följer med från tidigare möten</h2>
          {#if open.length}
            <p class="figure">{open.length === 1 ? '1 öppen punkt' : `${open.length} öppna punkter`}</p>
            {#if late}<p class="flag"><span class="dot"></span><span>{late === 1 ? 'En' : late} har passerat sitt datum.</span></p>{/if}
            <dl>
              {#each from as [no, n] (no)}
                <div><dt>Från {name} {no}</dt><dd>{n}</dd></div>
              {/each}
            </dl>
          {:else}
            <p class="muted">Inga öppna punkter.</p>
          {/if}
        </section>
        <section class="reading">
          <h2>Så läses ett punktnummer</h2>
          <div class="parts" aria-hidden="true">
            <div><b>3</b><span>{series.name} 3</span></div>
            <i>.</i>
            <div><b>4</b><span>Rubrik 4</span></div>
            <i>.</i>
            <div><b>2</b><span>Andra punkten</span></div>
          </div>
          <p class="muted small"><span class="mono">3.4.2</span> är den andra punkten under rubrik 4 från {name} 3.</p>
        </section>
      </aside>
    </div>
  {/if}
</div>

<style>
  /* The drawing's measures: a heading's row, the columns, the small text. The Mac's first, Windows' below. */
  .view { --h: 30px; --who: 124px; --due: 138px; --no: 46px; --ty: 58px; --tiny: 11px; --head: 28px;
    display: flex; flex-direction: column; height: 100%; background: var(--win-bg); }
  :global(:root[data-platform='win']) .view { --h: 32px; --who: 136px; --due: 150px; --no: 50px; --ty: 64px; --tiny: 12px; --head: 30px; }
  .pad { padding: 12px 16px; }
  .head { flex: none; justify-content: center; gap: 2px; height: 64px; padding: 0 16px; border-bottom: 1px solid var(--line); }
  .head h1 { font: 600 18px/1.25 var(--font-ui); }
  .head p { font-size: 12px; }
  .body { flex: 1 1 auto; min-height: 0; display: flex; }
  .outline { flex: 1 1 auto; min-width: 0; overflow-y: auto; }
  .cols { position: sticky; top: 0; display: flex; align-items: center; gap: 8px; height: var(--head); padding: 0 12px; border-bottom: 1px solid var(--line);
    font-size: var(--ui-small); font-weight: 600; color: var(--ink-500); background: var(--canvas); }
  .cols .c1 { flex: 1 1 auto; padding-left: 44px; }
  .who { flex: none; width: var(--who); }
  .due { flex: none; width: var(--due); }
  .heading { display: flex; align-items: center; gap: 8px; height: var(--h); padding: 0 12px; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }
  .tw { flex: none; width: 10px; display: grid; place-items: center; }
  .twist { display: grid; place-items: center; width: 18px; height: 18px; margin: 0 -4px; padding: 0; border: 0; border-radius: 4px; background: transparent; color: var(--ink-500); }
  .twist:hover { background: rgb(0 0 0 / 0.06); }
  .twist.shut svg { transform: rotate(-90deg); }
  .n { flex: none; width: 18px; text-align: right; color: var(--ink-500); font-variant-numeric: tabular-nums; }
  h3 { flex: none; font: 600 var(--ui) / 1.35 var(--font-ui); }
  .hint { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; color: var(--ink-500); font-size: var(--tiny); }
  .cnt { flex: none; margin-left: auto; color: var(--ink-500); font-size: var(--tiny); }
  .point { display: flex; align-items: flex-start; gap: 8px; padding: 6px 12px 6px 56px; border-bottom: 1px solid var(--line-soft); background: var(--canvas); line-height: 1.35; }
  .point .no { flex: none; width: var(--no); font: 500 calc(var(--ui) - 1px) / calc(var(--ui) * 1.35) var(--font-mono); color: var(--ink-700); }
  .ty { flex: none; width: var(--ty); color: var(--ink-500); }
  .tx { flex: 1 1 auto; min-width: 0; }
  .point .due { color: var(--ink-500); }
  .point .due.late { color: var(--bad); font-weight: 600; }

  .side { flex: none; width: 260px; overflow-y: auto; background: var(--canvas); border-left: 1px solid var(--line); }
  .side section { display: flex; flex-direction: column; gap: 6px; padding: 10px 14px; border-bottom: 1px solid var(--line-soft); }
  .side section.reading { gap: 10px; }
  .side h2 { font: 600 var(--ui-small) / 1.35 var(--font-ui); letter-spacing: 0; color: var(--ink-500); }
  .figure { font-size: calc(var(--ui) + 2px); font-weight: 600; }
  .flag { display: flex; align-items: center; gap: 6px; }
  .dot { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--bad); }
  dl { margin: 4px 0 0; display: flex; flex-direction: column; gap: 6px; }
  dl div { display: flex; justify-content: space-between; gap: 12px; }
  dt { color: var(--ink-500); }
  dd { margin: 0; }
  .parts { display: flex; align-items: flex-start; gap: 6px; }
  .parts div { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; }
  .parts b { width: 100%; height: calc(var(--h) + 2px); display: grid; place-items: center; border-radius: var(--ctl-r); border: 1px solid var(--line); background: var(--surface); font: 500 15px var(--font-mono); }
  .parts span { font-size: var(--tiny); color: var(--ink-500); white-space: nowrap; }
  .parts i { font: 500 12px/calc(var(--h) + 2px) var(--font-mono); color: var(--ink-500); }
  .small { font-size: var(--ui-small); }
</style>
