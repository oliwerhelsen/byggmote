<script lang="ts">
  // One project at a glance: the next meeting, what is still open, the meetings, who is in it. A project made here is
  // this computer's own, renamed and removed here. One that came from Stommen is Stommen's.
  import type { Agenda, MeetingRow, Project, SeriesRef } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { date, failure, KINDS, minutes, overdue, standing } from '../lib/format'
  import type { Go } from '../lib/view'

  let { project, rows, agendas, go, refresh, gone, record, add }: {
    project: Project; rows: MeetingRow[] | null; agendas: Agenda[] | null; go: Go; refresh: () => Promise<void>; gone: () => void
    record: (s: SeriesRef) => void; add: (s: SeriesRef) => void
  } = $props()

  let problem = $state('')
  let busy = $state(false)
  let renaming = $state(false)
  let renamed = $state('')
  let confirm = $state<HTMLDialogElement>()

  const open = $derived(
    (agendas ?? [])
      .flatMap((a) => a.headings.flatMap((h) => h.open))
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
</script>

<div class="page">
  <div class="page-head">
    <div class="grow">
      {#if renaming}
        <form class="row" onsubmit={rename}>
          <label class="label sr" for="rename">Nytt namn</label>
          <input id="rename" class="field grow" type="text" required bind:value={renamed} />
          <button class="btn primary" type="submit" disabled={busy || !renamed.trim()}>Spara</button>
          <button class="btn" type="button" onclick={() => (renaming = false)}>Avbryt</button>
        </form>
      {:else}
        <div class="row name">
          <h1>{project.name}</h1>
          {#if !project.stommen}
            <button class="btn quiet icon" aria-label="Byt namn" title="Byt namn" onclick={() => { renaming = true; renamed = project.name }}><Icon name="edit" size={16} /></button>
          {/if}
          {#if project.stommen}<span class="badge"><Icon name="link" size={13} /> Från Stommen</span>{/if}
        </div>
        {#if !project.stommen}<p class="muted">Projektet ligger på den här datorn.</p>{/if}
      {/if}
    </div>
  </div>

  {#if problem}
    <div class="note bad" role="alert" style="margin-bottom: 12px"><Icon name="alert" /><p>{problem}</p></div>
  {/if}

  <dl class="facts" aria-label="Läget">
    <div><dt>Möten</dt><dd>{rows === null ? '' : rows.length}</dd></div>
    <div><dt>Senaste mötet</dt><dd>{rows === null ? '' : latest ? date(latest.recorded_at) || latest.title : 'Inget än'}</dd></div>
    <div><dt>Öppna punkter</dt><dd>{agendas === null ? '' : open.length}{#if late}<span class="aside"><span class="dot"></span>{late === 1 ? 'en har' : `${late} har`} passerat sitt datum</span>{/if}</dd></div>
  </dl>

  <div class="columns">
    <div class="main">
      {#each project.series as s (s.id)}
        <section class="block" aria-labelledby="next-{s.id}">
          <h2 id="next-{s.id}">Nästa möte</h2>
          <div class="row next">
            <p class="grow"><strong>{s.name} {s.next}</strong><br /><span class="muted">{carried(s.id)}</span></p>
            <button class="btn primary" onclick={() => record(s)}>Spela in möte</button>
            <button class="btn" onclick={() => go({ name: 'agenda', series: s })}>Se dagordningen</button>
            <button class="btn" onclick={() => add(s)}>Lägg till en inspelning</button>
          </div>
        </section>
      {:else}
        <section class="block">
          <h2>Projektet har ingen mötesserie än</h2>
          <p class="muted">
            En mötesserie är en sorts möte som återkommer, som byggmötet. Den har sin egen dagordning, och punkterna numreras
            efter möte och rubrik så att de går att följa från möte till möte.
          </p>
          <button class="btn primary" style="margin-top: 10px" disabled={busy} onclick={() => act(() => window.api.startSeries(project.id, 'Byggmöte'))}>Starta serien Byggmöte</button>
        </section>
      {/each}

      <section class="block" aria-labelledby="open">
        <div class="row between">
          <h2 id="open">Öppna punkter</h2>
          {#if open.length}<button class="btn quiet" onclick={() => go({ name: 'points' })}>Visa alla</button>{/if}
        </div>
        {#if agendas === null}
          <p class="muted">Läser in punkterna.</p>
        {:else if !open.length}
          <p class="muted">Inga punkter väntar.</p>
        {:else}
          <table class="table">
            <thead><tr><th>Nr</th><th>Typ</th><th>Punkt</th><th>Ansvarig</th><th>Senast</th></tr></thead>
            <tbody>
              {#each open.slice(0, 5) as p (p.no)}
                <tr>
                  <td class="mono">{p.no}</td>
                  <td>{KINDS[p.kind]}</td>
                  <td class="wrap">{p.text}</td>
                  <td>{p.role ?? ''}</td>
                  <td>
                    {#if !p.due}<span class="muted">Inget datum</span>
                    {:else if overdue(p.due)}<span class="late"><span class="dot"></span>Förfallen {p.due}</span>
                    {:else}<span class="mono">{p.due}</span>{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#if open.length > 5}<p class="small muted" style="margin-top: 6px">Och {open.length - 5} till.</p>{/if}
        {/if}
      </section>

      <section class="block" aria-labelledby="meetings">
        <h2 id="meetings">Möten</h2>
        {#if rows === null}
          <p class="muted">Läser in mötena.</p>
        {:else if rows.length === 0}
          <p class="muted">Inga möten än. Spela in det första, eller lägg till en inspelning du redan har.</p>
        {:else}
          <table class="table">
            <thead><tr><th>Möte</th><th>Datum</th><th>Längd</th><th>Läge</th></tr></thead>
            <tbody>
              {#each rows as r (r.dir)}
                {@const st = standing(r)}
                <tr>
                  <td><button class="open" onclick={() => go({ name: 'protocol', dir: r.dir })}>{r.title}</button></td>
                  <td class="mono">{date(r.recorded_at)}</td>
                  <td>{minutes(r.duration)}</td>
                  <td><span class="state"><span class="dot {st.tone}"></span>{st.text}</span></td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>
    </div>

    <aside class="side">
      <section class="block" aria-labelledby="people">
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
          <p class="small muted" style="margin-top: 8px">Personer och Roller kommer från Stommen. Ändra dem där, och hämta sedan projektet igen.</p>
        {/if}
      </section>

      {#if !project.stommen}
        <section class="block danger" aria-labelledby="danger">
          <h2 id="danger">Ta bort projektet</h2>
          <p class="muted">Det försvinner ur listan, mötena ligger kvar i sin mapp.</p>
          <button class="btn danger-btn" style="margin-top: 8px" onclick={() => confirm?.showModal()}><Icon name="trash" size={16} /> Ta bort projektet</button>
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
  .facts { display: flex; gap: 0; margin: 0 0 16px; padding: 10px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
  .facts div { padding: 0 24px; border-right: 1px solid var(--line); }
  .facts div:first-child { padding-left: 0; }
  .facts div:last-child { border-right: 0; }
  dt { font-size: var(--ui-small); color: var(--ink-500); }
  dd { display: flex; align-items: baseline; gap: 10px; margin: 1px 0 0; min-height: 22px; font-size: calc(var(--ui) + 3px); font-weight: 600; font-variant-numeric: tabular-nums; }
  .aside { display: inline-flex; align-items: center; gap: 5px; font-size: var(--ui); font-weight: 400; color: var(--ink-700); }
  .columns > .side { flex: 0 1 300px; }
  .block { padding-bottom: 16px; margin-bottom: 14px; border-bottom: 1px solid var(--line); }
  .block:last-child { border-bottom: 0; }
  .block h2 { font: 600 var(--ui) var(--font-ui); letter-spacing: 0; color: var(--ink-500); margin-bottom: 8px; }
  .between h2 { margin-bottom: 0; }
  .next { gap: 8px; align-items: center; }
  .open { padding: 0; border: 0; background: transparent; font-weight: 600; text-align: left; }
  .open:hover { color: var(--coral-800); text-decoration: underline; }
  .state, .late { display: inline-flex; align-items: center; gap: 6px; }
  .late { color: var(--bad); }
  .dot { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--ink-400); }
  .dot.ok { background: var(--ok); } .dot.warn { background: var(--warn); } .dot.bad, .late .dot, .aside .dot { background: var(--bad); }
  .people { display: flex; flex-direction: column; gap: 4px; }
  .people li { display: flex; justify-content: space-between; gap: 12px; }
  .btn.icon { padding: 0; width: var(--ctl-h); }
  .name { gap: 6px; }
  .danger h2 { color: var(--bad); }
  .between { justify-content: space-between; gap: 16px; margin-bottom: 6px; }
  .end { justify-content: flex-end; margin-top: 20px; }
  .danger-btn { border-color: var(--bad); color: var(--bad); }
  .danger-btn:hover:not(:disabled) { border-color: var(--bad); background: var(--bad-bg); color: var(--bad); }
  .danger-btn.solid { background: var(--bad); color: #fff; }
  .danger-btn.solid:hover:not(:disabled) { background: var(--bad); color: #fff; filter: brightness(0.92); }
  dialog { width: min(480px, calc(100vw - 32px)); margin: auto; padding: 20px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); box-shadow: 0 20px 50px rgb(0 0 0 / 0.3); }
  dialog::backdrop { background: rgb(0 0 0 / 0.35); }
  dialog h2 { margin: 0 0 4px; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
