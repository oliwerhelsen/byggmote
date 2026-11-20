<script lang="ts">
  import type { Agenda, MeetingRow, OpenPoint, Project, SeriesRef } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { date, failure, KINDS, minutes, overdue } from '../lib/format'
  import type { Go } from '../lib/view'

  let { project, go, refresh }: { project: Project; go: Go; refresh: () => Promise<void> } = $props()

  let rows = $state<MeetingRow[] | null>(null)
  let agendas = $state<Record<string, Agenda>>({})
  let problem = $state('')
  let starting = $state(false)

  $effect(() => {
    const series = project.series.map((s) => s.id) // read here, so a new series loads its agenda
    void (async () => {
      try {
        const [r, a] = await Promise.all([window.api.meetings(project.id), Promise.all(series.map((id) => window.api.agenda(project.id, id)))])
        rows = r
        agendas = Object.fromEntries(a.map((x) => [x.series, x]))
        problem = ''
      } catch (e) {
        problem = failure(e)
        rows = rows ?? []
      }
    })()
  })

  const open = $derived(
    Object.values(agendas)
      .flatMap((a) => a.headings.flatMap((h) => h.open))
      .sort((a, b) => Number(overdue(b.due)) - Number(overdue(a.due)) || (a.due ?? '9').localeCompare(b.due ?? '9'))
  )

  function carried(a: Agenda | undefined): string {
    if (!a) return ''
    const pts = a.headings.flatMap((h) => h.open)
    const late = pts.filter((p) => overdue(p.due)).length
    if (!pts.length) return 'Inga öppna punkter från tidigare möten.'
    const first = pts.length === 1 ? 'En öppen punkt följer med från tidigare möten.' : `${pts.length} öppna punkter följer med från tidigare möten.`
    return late ? `${first} ${late === 1 ? 'En' : late} har passerat sitt datum.` : first
  }

  type Tone = '' | 'ok' | 'warn' | 'bad'
  function standing(r: MeetingRow): { tone: Tone; icon: 'clock' | 'alert' | 'file' | 'check'; text: string } {
    if (r.status === 'processing') return { tone: '', icon: 'clock', text: 'Skrivs ut' }
    if (r.status === 'failed') return { tone: 'bad', icon: 'alert', text: 'Gick inte att skriva ut' }
    if (!r.protocol) return { tone: '', icon: 'file', text: 'Utskrift utan protokoll' }
    if (r.protocol.status === 'unreadable') return { tone: 'bad', icon: 'alert', text: 'Protokollet går inte att läsa' }
    if (r.protocol.status !== 'draft') return { tone: 'ok', icon: 'check', text: 'Justerat' }
    return r.protocol.checks ? { tone: 'warn', icon: 'alert', text: `Utkast, ${r.protocol.checks} att kontrollera` } : { tone: '', icon: 'file', text: 'Utkast' }
  }

  async function add(s: SeriesRef): Promise<void> {
    const file = await window.api.pickRecording()
    if (file) go({ name: 'working', job: { projectId: project.id, seriesId: s.id, file, title: `${s.name} ${s.next}` } })
  }

  async function start(): Promise<void> {
    starting = true
    try {
      await window.api.startSeries(project.id, 'Byggmöte')
      await refresh()
    } catch (e) {
      problem = failure(e)
    } finally {
      starting = false
    }
  }

  const who = (p: OpenPoint): string => [KINDS[p.kind], p.role].filter(Boolean).join(', ')
</script>

<div class="page">
  <div class="page-head">
    <div>
      <h1>Möten</h1>
      <p class="muted">{project.name}</p>
    </div>
  </div>

  {#if problem}
    <div class="note bad" role="alert" style="margin-bottom: 24px">
      <Icon name="alert" />
      <div><p><strong>Det gick inte att läsa mötena.</strong></p><p class="small mono">{problem}</p></div>
    </div>
  {/if}

  <div class="columns">
    <div class="main stack">
      {#each project.series as s (s.id)}
        <section class="card next" aria-labelledby="next-{s.id}">
          <p class="small muted">Nästa möte</p>
          <h2 id="next-{s.id}">{s.name} {s.next}</h2>
          <p class="muted">{carried(agendas[s.id])}</p>
          <div class="row" style="margin-top: 20px">
            <button class="btn primary" onclick={() => go({ name: 'recording', series: s })}><Icon name="mic" /> Spela in mötet</button>
            <button class="btn" onclick={() => go({ name: 'agenda', series: s })}>Se dagordningen</button>
            <button class="btn quiet" onclick={() => add(s)}><Icon name="plus" /> Lägg till en inspelning</button>
          </div>
        </section>
      {:else}
        <section class="card">
          <h2>Projektet har ingen mötesserie än</h2>
          <p class="muted">
            En mötesserie är en sorts möte som återkommer, som byggmötet. Den har sin egen dagordning, och punkterna numreras
            efter möte och rubrik så att de går att följa från möte till möte.
          </p>
          <button class="btn primary" style="margin-top: 16px" disabled={starting} onclick={start}>Starta serien Byggmöte</button>
        </section>
      {/each}

      <section class="card" aria-labelledby="earlier">
        <h2 id="earlier">Tidigare möten</h2>
        {#if rows === null}
          <p class="muted">Läser in mötena.</p>
        {:else if rows.length === 0}
          <p class="muted">Inga möten än. Spela in det första, eller lägg till en inspelning du redan har.</p>
        {:else}
          <table>
            <thead>
              <tr><th>Möte</th><th>Datum</th><th>Längd</th><th>Läge</th></tr>
            </thead>
            <tbody>
              {#each rows as r (r.dir)}
                {@const s = standing(r)}
                <tr>
                  <td><button class="open" onclick={() => go({ name: 'protocol', dir: r.dir })}>{r.title}</button></td>
                  <td class="mono">{date(r.recorded_at)}</td>
                  <td>{minutes(r.duration)}</td>
                  <td><span class="badge {s.tone}"><Icon name={s.icon} size={14} /> {s.text}</span></td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>
    </div>

    <aside class="side stack">
      <section class="card" aria-labelledby="open">
        <h2 id="open">Öppna punkter</h2>
        {#if open.length === 0}
          <p class="muted">Inga punkter väntar.</p>
        {:else}
          <ul class="points">
            {#each open.slice(0, 8) as p (p.no)}
              <li>
                <p><span class="point-no">{p.no}</span> <span class="small muted">{who(p)}</span></p>
                <p>{p.text}</p>
                {#if p.due}
                  {#if overdue(p.due)}
                    <p><span class="badge bad"><Icon name="alert" size={14} /> Förfallen {p.due}</span></p>
                  {:else}
                    <p class="small muted">Senast {p.due}</p>
                  {/if}
                {/if}
              </li>
            {/each}
          </ul>
          {#if open.length > 8}<p class="small muted" style="margin-top: 12px">Och {open.length - 8} till, i dagordningen.</p>{/if}
        {/if}
      </section>
    </aside>
  </div>
</div>

<style>
  .next h2 { font: 300 28px/1.2 var(--font-display); margin: 2px 0 6px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 13px; font-weight: 500; color: var(--ink-500); padding: 0 12px 8px 0; border-bottom: 1px solid var(--line); }
  td { padding: 6px 12px 6px 0; border-bottom: 1px solid var(--line); vertical-align: middle; }
  tr:last-child td { border-bottom: 0; }
  .open { min-height: 44px; padding: 0; border: 0; background: transparent; color: var(--coral-700); font-weight: 500; text-align: left; }
  .open:hover { color: var(--coral-800); text-decoration: underline; }
  .points li { padding: 12px 0; border-bottom: 1px solid var(--line); display: flex; flex-direction: column; gap: 4px; }
  .points li:first-child { padding-top: 0; }
  .points li:last-child { border-bottom: 0; padding-bottom: 0; }
  @media (max-width: 560px) {
    thead { display: none; }
    tr { display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--line); }
    td { border: 0; padding: 0; }
    td:first-child { flex: 1 1 100%; }
  }
</style>
