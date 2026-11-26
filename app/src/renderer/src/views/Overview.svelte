<script lang="ts">
  // One project at a glance: the next meeting, what is still open, the meetings, who is in it. A project made here is
  // this computer's own, renamed and removed here. One that came from Stommen is Stommen's.
  import type { Agenda, MeetingRow, Project, SeriesRef, StommenState } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { date, failure, KINDS, minutes, overdue, standing } from '../lib/format'
  import { title, tools } from '../lib/tools'
  import type { Go } from '../lib/view'

  let { project, rows, agendas, stommen, go, refresh, gone, record, sync }: {
    project: Project; rows: MeetingRow[] | null; agendas: Agenda[] | null; stommen: StommenState | null; go: Go; refresh: () => Promise<void>; gone: () => void
    record: (s: SeriesRef) => void; sync: () => Promise<void>
  } = $props()

  const mac = window.api.platform === 'darwin'
  const SHOWN = 5 // how many open points and meetings the overview lists; the rest are a click away
  let fetching = $state(false)

  let problem = $state('')
  let busy = $state(false)
  let renaming = $state(false)
  let renamed = $state('')
  let confirm = $state<HTMLDialogElement>()

  // `since`: the meeting a point is from, when a later one has been held and it is still open.
  const open = $derived(
    (agendas ?? [])
      .flatMap((a) => a.headings.flatMap((h) => h.open.map((p) => ({ ...p, key: `${a.series} ${p.no}`, since: Number(p.no.split('.')[0]) < a.no - 1 ? `${a.name.toLowerCase()} ${p.no.split('.')[0]}` : '' }))))
      .sort((a, b) => Number(overdue(b.due)) - Number(overdue(a.due)) || (a.due ?? '9').localeCompare(b.due ?? '9'))
  )
  const late = $derived(open.filter((p) => overdue(p.due)).length)
  const latest = $derived(rows?.[0])

  /** What the next meeting of a series starts with. */
  function carried(id: string): string {
    const a = agendas?.find((x) => x.series === id)
    if (!a) return ''
    const pts = a.headings.flatMap((h) => h.open)
    const n = pts.filter((p) => overdue(p.due)).length
    if (!pts.length) return 'Inga öppna punkter från tidigare möten.'
    const first = pts.length === 1 ? 'En öppen punkt följer med från tidigare möten.' : `${pts.length} öppna punkter följer med från tidigare möten.`
    return n ? `${first} ${n === 1 ? 'En' : n} har passerat sitt datum.` : first
  }

  async function act(fn: () => Promise<unknown>): Promise<boolean> {
    busy = true
    problem = ''
    try {
      await fn()
      await refresh()
      return true
    } catch (e) {
      problem = failure(e)
      return false
    } finally {
      busy = false
    }
  }

  async function fetchAgain(): Promise<void> {
    fetching = true
    await sync().finally(() => (fetching = false))
  }

  async function rename(e: SubmitEvent): Promise<void> {
    e.preventDefault()
    if (await act(() => window.api.projectRename(project.id, renamed))) renaming = false
  }

  async function remove(): Promise<void> {
    if (await act(() => window.api.projectDelete(project.id))) {
      confirm?.close()
      gone()
    } else confirm?.close()
  }

  /** `2026-11-26 13:58`, by the computer's clock. */
  function when(iso: string): string {
    const d = new Date(iso)
    const two = (n: number): string => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`
  }
</script>


<div class="view">
  {#if stommen?.connected}
    <div class="tools" use:tools>
      <button class="tool" aria-label={mac ? 'Hämta från Stommen' : undefined} title={mac ? 'Hämta från Stommen' : undefined} disabled={fetching} onclick={fetchAgain}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13.5 8a5.5 5.5 0 0 1-9.6 3.7M2.5 8a5.5 5.5 0 0 1 9.6-3.7M12.5 1.5v3h-3M3.5 14.5v-3h3" /></svg>
        {#if !mac}<span>Hämta från Stommen</span>{/if}
      </button>
      <span class="sep"></span>
    </div>
  {/if}

  <!-- The figures as one row, not as cards. On Windows the project's name leads it; on the Mac it is in the toolbar. -->
  <div class="strip">
    <div class="bar-title" class:name={!mac} use:title={mac}>
      <div class="named">
        <h1>{project.name}</h1>
        {#if !project.stommen && !renaming}
          <button class="pencil" aria-label="Byt namn" title="Byt namn" onclick={() => { renaming = true; renamed = project.name }}><Icon name="edit" size={14} /></button>
        {/if}
      </div>
      <p>{project.stommen ? 'Från Stommen' : 'Projektet ligger på den här datorn.'}</p>
    </div>
    <dl class="figures" aria-label="Läget">
      <div><dt>Möten</dt><dd>{rows === null ? '' : rows.length}</dd></div>
      <div><dt>Senaste mötet</dt><dd>{rows === null ? '' : latest ? date(latest.recorded_at) || latest.title : 'Inget än'}</dd></div>
      <div><dt>Öppna punkter</dt><dd>{agendas === null ? '' : open.length}{#if late}<span class="aside"><span class="dot bad"></span>{late === 1 ? 'en har' : `${late} har`} passerat sitt datum</span>{/if}</dd></div>
      {#if project.series.length}<div><dt>Nästa möte</dt><dd>{project.series[0].name} {project.series[0].next}</dd></div>{/if}
    </dl>
  </div>

  <div class="body">
    <div class="main">
      {#if renaming}
        <form class="row rename" onsubmit={rename}>
          <label class="sr" for="rename">Nytt namn</label>
          <input id="rename" class="field grow" type="text" required bind:value={renamed} />
          <button class="btn primary" type="submit" disabled={busy || !renamed.trim()}>Spara</button>
          <button class="btn" type="button" onclick={() => (renaming = false)}>Avbryt</button>
        </form>
      {/if}
      {#if problem}
        <div class="note bad" role="alert" style="margin-bottom: 12px"><Icon name="alert" /><p>{problem}</p></div>
      {/if}

      {#each project.series as s (s.id)}
        <section class="sec" aria-labelledby="next-{s.id}">
          <h2 id="next-{s.id}">Nästa möte</h2>
          <div class="next">
            <span class="which">{s.name} {s.next}</span>
            <span class="grow"></span>
            <button class="btn primary" onclick={() => record(s)}>Spela in möte…</button>
            <button class="btn" onclick={() => go({ name: 'agenda', series: s })}>Se dagordningen</button>
          </div>
          <p class="muted carried">{carried(s.id)}</p>
        </section>
      {:else}
        <section class="sec">
          <h2>Projektet har ingen mötesserie än</h2>
          <p class="muted">
            En mötesserie är en sorts möte som återkommer, som byggmötet. Den har sin egen dagordning, och punkterna numreras
            efter möte och rubrik så att de går att följa från möte till möte.
          </p>
          <button class="btn primary" style="margin-top: 10px" disabled={busy} onclick={() => act(() => window.api.startSeries(project.id, 'Byggmöte'))}>Starta serien Byggmöte</button>
        </section>
      {/each}

      <section class="sec" aria-labelledby="open">
        <div class="between">
          <h2 id="open">Öppna punkter</h2>
          {#if open.length}<button class="link" onclick={() => go({ name: 'points' })}>Visa alla</button>{/if}
        </div>
        {#if agendas === null}
          <p class="muted">Läser in punkterna.</p>
        {:else if !open.length}
          <p class="muted">Inga punkter väntar.</p>
        {:else}
          <table class="table top">
            <thead><tr><th class="c-no">Nr</th><th class="c-kind">Typ</th><th>Punkt</th><th class="c-who">Ansvarig</th><th class="c-due">Senast</th></tr></thead>
            <tbody>
              {#each open.slice(0, SHOWN) as p (p.key)}
                <tr>
                  <td class="mono">{p.no}</td>
                  <td>{KINDS[p.kind]}</td>
                  <td class="wrap">{p.text}{#if p.since}<br /><span class="muted tiny">Kvarstår, från {p.since}</span>{/if}</td>
                  <td>{p.role ?? ''}</td>
                  <td class="num">
                    {#if !p.due}<span class="muted">Inget datum</span>
                    {:else if overdue(p.due)}<span class="late"><span class="dot bad"></span><span class="sr">{'Förfallen '}</span>{p.due}</span>
                    {:else}{p.due}{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#if open.length > SHOWN}<p class="tiny muted" style="margin-top: 6px">Och {open.length - SHOWN} till.</p>{/if}
        {/if}
      </section>

      <section class="sec" aria-labelledby="meetings">
        <h2 id="meetings">Senaste möten</h2>
        {#if rows === null}
          <p class="muted">Läser in mötena.</p>
        {:else if rows.length === 0}
          <p class="muted">Inga möten än. Spela in det första, eller lägg till en inspelning du redan har.</p>
        {:else}
          <table class="table">
            <thead><tr><th>Möte</th><th class="c-date">Datum</th><th class="c-date">Längd</th><th class="c-state">Läge</th></tr></thead>
            <tbody>
              {#each rows.slice(0, SHOWN) as r (r.dir)}
                {@const st = standing(r)}
                <tr>
                  <td><button class="open" onclick={() => go({ name: 'protocol', dir: r.dir })}>{r.title}</button></td>
                  <td class="num">{date(r.recorded_at)}</td>
                  <td>{minutes(r.duration)}</td>
                  <td><span class="dot {st.tone}"></span>{st.text}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>
    </div>

    <!-- Who is in it, and where what is shown comes from. -->
    <aside class="side">
      <section class="sec" aria-labelledby="people">
        <h2 id="people">Personer och Roller</h2>
        {#if project.people.length}
          <ul class="people">
            {#each project.people as person (person.id)}
              <li><span>{person.name}</span><span class="muted">{person.role ?? ''}</span></li>
            {/each}
          </ul>
        {:else}
          <p class="muted">Ingen är tillagd än. Den som talar på ett möte får sitt namn i protokollet.</p>
        {/if}
        {#if project.stommen}
          <p class="tiny muted" style="margin-top: 8px; line-height: 16px">Personer och Roller kommer från Stommen. Ändra dem där, och hämta sedan projektet igen.</p>
        {/if}
      </section>

      {#if stommen?.connected}
        <section class="sec" aria-labelledby="stommen">
          <h2 id="stommen">Stommen</h2>
          <ul class="people">
            <li class="start"><span class="dot ok"></span><span>Inloggad som {stommen.user}</span></li>
            {#if stommen.organization}<li>{stommen.organization}</li>{/if}
            {#if stommen.syncedAt}<li class="muted num">Hämtat senast {when(stommen.syncedAt)}</li>{/if}
          </ul>
        </section>
      {/if}

      {#if !project.stommen}
        <section class="sec" aria-labelledby="danger">
          <h2 id="danger">Ta bort projektet</h2>
          <p class="muted">Det försvinner ur listan, mötena ligger kvar i sin mapp.</p>
          <div><button class="btn danger-btn" style="margin-top: 8px" onclick={() => confirm?.showModal()}><Icon name="trash" size={16} /> Ta bort projektet</button></div>
        </section>
      {/if}
    </aside>
  </div>
</div>

<dialog bind:this={confirm} aria-labelledby="confirm-title">
  <div class="note bad" role="alert">
    <Icon name="alert" />
    <div>
      <h2 id="confirm-title">Ta bort {project.name}?</h2>
      <p>Projektet försvinner ur listan och det går inte att ångra. Mötena ligger kvar i sin mapp på datorn.</p>
    </div>
  </div>
  <div class="row end">
    <button class="btn" onclick={() => confirm?.close()}>Avbryt</button>
    <button class="btn danger-btn solid" disabled={busy} onclick={remove}>Ta bort projektet</button>
  </div>
</dialog>

<style>
  /* The drawing's measures, Windows' first and the Mac's below. */
  .view { --tiny: 12px; --h: 13px; --fig: 16px; --fig-lh: 22px; --kv: 28px; --side: 296px;
    display: flex; flex-direction: column; min-height: 100%; background: var(--win-bg); }
  :global(:root[data-platform='mac']) .view { --tiny: 11px; --h: 12px; --fig: 15px; --fig-lh: 20px; --kv: 24px; --side: 280px; }
  .tiny { font-size: var(--tiny); }
  .num { font-variant-numeric: tabular-nums; }

  .tools { display: flex; align-items: center; gap: 8px; }
  .tool { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 36px; min-width: 32px; padding: 0 10px; border: 0; border-radius: var(--ctl-r); background: transparent; white-space: nowrap; }
  .tool svg { color: var(--coral-700); }
  .tool:hover:not(:disabled) { background: rgb(0 0 0 / 0.07); }
  :global(:root[data-platform='mac']) .tool { height: 28px; padding: 0 7px; color: var(--ink-700); }
  :global(:root[data-platform='mac']) .tool svg { color: inherit; }
  .sep { width: 1px; height: 20px; margin: 0 4px; background: var(--line); }
  :global(:root[data-platform='win']) .tools .sep { display: none; } /* Windows' command bar has nothing after it */

  .strip { flex: none; display: flex; align-items: center; margin: 0 24px; padding: 12px 0; border-bottom: 1px solid var(--line); }
  :global(:root[data-platform='mac']) .strip { padding: 16px 0; }
  .name { padding-right: 24px; gap: 0; }
  .name h1 { font: 600 16px/22px var(--font-ui); }
  .name p { font-size: var(--ui-small); line-height: 16px; }
  .named { display: flex; align-items: center; gap: 4px; min-width: 0; }
  .pencil { display: inline-grid; place-items: center; flex: none; width: 22px; height: 22px; padding: 0; border: 0; border-radius: var(--ctl-r); background: transparent; color: var(--ink-500); }
  .pencil:hover { background: rgb(0 0 0 / 0.07); color: var(--ink-900); }
  .figures { display: flex; margin: 0; }
  .figures div { padding: 0 24px; border-left: 1px solid var(--line); }
  :global(:root[data-platform='mac']) .figures div:first-child { padding-left: 0; border-left: 0; }
  .figures dt { font-size: var(--tiny); line-height: 16px; color: var(--ink-500); white-space: nowrap; }
  .figures dd { margin: 0; font-size: var(--fig); line-height: var(--fig-lh); font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .aside { margin-left: 6px; font-size: var(--ui); font-weight: 400; color: var(--ink-700); }
  .aside .dot { margin-right: 5px; }
  .dot { display: inline-block; flex: none; width: 7px; height: 7px; margin-right: 6px; border-radius: 50%; background: var(--ink-400); }
  .dot.ok { background: var(--ok); } .dot.warn { background: var(--warn); } .dot.bad { background: var(--bad); }

  .body { flex: 1 1 auto; display: flex; padding: 16px 24px 0; }
  .main { flex: 1 1 auto; min-width: 0; padding-bottom: 24px; }
  .side { flex: none; width: var(--side); margin-left: 24px; padding: 0 0 24px 24px; border-left: 1px solid var(--line); }
  .sec + .sec { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--line); }
  .sec h2 { margin-bottom: 8px; font: 600 var(--h) / 16px var(--font-ui); letter-spacing: 0; color: var(--ink-500); }
  .rename { margin-bottom: 16px; flex-wrap: nowrap; gap: 8px; }
  .next { display: flex; align-items: center; gap: 8px; }
  .which { font-size: var(--fig); font-weight: 600; }
  .carried { margin-top: 4px; }
  .between { display: flex; align-items: center; justify-content: space-between; height: 16px; margin-bottom: 8px; }
  .between h2 { margin: 0; }
  .link { padding: 0; border: 0; background: none; color: var(--coral-700); }
  .link:hover { color: var(--coral-800); text-decoration: underline; }
  .table td { padding: 0 10px; border-bottom-color: var(--line-soft); }
  .table.top td { vertical-align: top; padding-top: 8px; padding-bottom: 8px; }
  :global(:root[data-platform='mac']) .table.top td { padding-top: 5px; padding-bottom: 5px; }
  .c-no { width: 68px; } .c-kind { width: 84px; } .c-who { width: 156px; } .c-due { width: 120px; } .c-date { width: 120px; } .c-state { width: 232px; }
  :global(:root[data-platform='mac']) .c-no { width: 60px; }
  :global(:root[data-platform='mac']) .c-kind { width: 76px; }
  :global(:root[data-platform='mac']) .c-who { width: 144px; }
  :global(:root[data-platform='mac']) .c-due, :global(:root[data-platform='mac']) .c-date { width: 112px; }
  :global(:root[data-platform='mac']) .c-state { width: 220px; }
  .open { padding: 0; border: 0; background: transparent; font-weight: 600; text-align: left; }
  .open:hover { color: var(--coral-800); text-decoration: underline; }
  .late { color: var(--bad); }
  .people li { display: flex; align-items: center; justify-content: space-between; gap: 12px; height: var(--kv); white-space: nowrap; }
  .people li.start { justify-content: flex-start; gap: 0; }
  .end { justify-content: flex-end; margin-top: 20px; }
  .danger-btn { border-color: var(--bad); color: var(--bad); }
  .danger-btn:hover:not(:disabled) { border-color: var(--bad); background: var(--bad-bg); color: var(--bad); }
  .danger-btn.solid { background: var(--bad); color: #fff; }
  .danger-btn.solid:hover:not(:disabled) { background: var(--bad); color: #fff; filter: brightness(0.92); }
  dialog { width: min(480px, calc(100vw - 32px)); margin: auto; padding: 20px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); box-shadow: 0 20px 50px rgb(0 0 0 / 0.3); }
  dialog::backdrop { background: rgb(0 0 0 / 0.35); }
  dialog h2 { margin: 0 0 4px; }
</style>
