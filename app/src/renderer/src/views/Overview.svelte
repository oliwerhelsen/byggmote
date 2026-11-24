<script lang="ts">
  // One project at a glance: where its meetings stand, and the project's own settings (name, removal).
  // A project made here is this computer's own. One that came from Stommen is Stommen's, and is not renamed or removed here.
  import type { Agenda, MeetingRow, Project } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { date, failure, overdue } from '../lib/format'
  import type { Go } from '../lib/view'

  let { project, go, refresh, gone }: { project: Project; go: Go; refresh: () => Promise<void>; gone: () => void } = $props()

  let rows = $state<MeetingRow[] | null>(null)
  let agendas = $state<Agenda[]>([])
  let problem = $state('')
  let busy = $state(false)
  let renaming = $state(false)
  let renamed = $state('')
  let removing = $state(false)

  $effect(() => {
    const series = project.series.map((s) => s.id)
    void (async () => {
      try {
        const [r, a] = await Promise.all([window.api.meetings(project.id), Promise.all(series.map((id) => window.api.agenda(project.id, id)))])
        rows = r
        agendas = a
      } catch (e) {
        problem = failure(e)
        rows = rows ?? []
      }
    })()
  })

  const open = $derived(agendas.flatMap((a) => a.headings.flatMap((h) => h.open)))
  const late = $derived(open.filter((p) => overdue(p.due)).length)
  const latest = $derived(rows?.[0])

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
    if (await act(() => window.api.projectDelete(project.id))) gone()
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
        <h1>{project.name}</h1>
        <p class="muted">
          {#if project.stommen}<span class="badge"><Icon name="link" size={14} /> Från Stommen</span>{:else}Projektet ligger på den här datorn.{/if}
        </p>
      {/if}
    </div>
    {#if !project.stommen && !renaming}
      <div class="row">
        <button class="btn quiet icon" aria-label="Byt namn" title="Byt namn" onclick={() => { renaming = true; renamed = project.name }}><Icon name="edit" size={18} /></button>
        <button class="btn quiet icon" aria-label="Ta bort projektet" title="Ta bort projektet" onclick={() => (removing = true)}><Icon name="trash" size={18} /></button>
      </div>
    {/if}
  </div>

  <div class="stack narrow">
    {#if problem}
      <div class="note bad" role="alert"><Icon name="alert" /><p>{problem}</p></div>
    {/if}

    {#if removing}
      <div class="note warn" role="alert">
        <Icon name="alert" />
        <div class="grow">
          <p>Projektet försvinner ur listan. Mötena ligger kvar i sin mapp.</p>
          <div class="row" style="margin-top: 12px">
            <button class="btn primary" disabled={busy} onclick={remove}>Ta bort projektet</button>
            <button class="btn" onclick={() => (removing = false)}>Avbryt</button>
          </div>
        </div>
      </div>
    {/if}

    <section class="card" aria-labelledby="status">
      <h2 id="status">Läget</h2>
      {#if rows === null}
        <p class="muted">Läser in mötena.</p>
      {:else}
        <dl class="facts">
          <div><dt>Möten</dt><dd>{rows.length}</dd></div>
          <div><dt>Senaste mötet</dt><dd>{latest ? date(latest.recorded_at) || latest.title : 'Inget än'}</dd></div>
          <div><dt>Öppna punkter</dt><dd>{open.length}{late ? ` (${late === 1 ? 'en har' : late + ' har'} passerat sitt datum)` : ''}</dd></div>
        </dl>
      {/if}
      <div class="row" style="margin-top: 20px">
        <button class="btn primary" onclick={() => go({ name: 'meetings' })}>Gå till mötena</button>
      </div>
    </section>

    {#if project.stommen}
      <p class="small muted">Personer och Roller kommer från Stommen. Ändra dem där, och hämta sedan projektet igen.</p>
    {/if}
  </div>
</div>

<style>
  .narrow { max-width: 680px; }
  .facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin: 0; }
  dt { font-size: 13px; color: var(--ink-500); }
  dd { margin: 2px 0 0; font-size: 18px; font-weight: 500; }
  .btn.icon { padding: 0; width: 44px; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
