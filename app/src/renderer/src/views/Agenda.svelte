<script lang="ts">
  import type { Agenda, Project, SeriesRef } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import RecordDialog from '../lib/RecordDialog.svelte'
  import { failure, KINDS, overdue } from '../lib/format'
  import type { Go } from '../lib/view'

  let { project, series, go }: { project: Project; series: SeriesRef; go: Go } = $props()

  let agenda = $state<Agenda | null>(null)
  let problem = $state('')
  let recorder = $state<{ show: (s: SeriesRef, agenda?: boolean) => void }>()

  $effect(() => {
    window.api
      .agenda(project.id, series.id)
      .then((a) => (agenda = a))
      .catch((e) => (problem = failure(e)))
  })

  const open = $derived(agenda ? agenda.headings.flatMap((h) => h.open) : [])
</script>

<div class="page">
  <div class="page-head">
    <div>
      <h1>Dagordning, {series.name.toLowerCase()} {series.next}</h1>
      <p class="muted">Rubrikerna är seriens. Under dem står de punkter som tidigare möten lämnade öppna.</p>
    </div>
    <div class="row">
      <button class="btn primary" onclick={() => recorder?.show(series, true)}><Icon name="mic" /> Spela in mötet</button>
    </div>
  </div>

  {#if problem}
    <div class="note bad" role="alert"><Icon name="alert" /><div><p><strong>Det gick inte att läsa dagordningen.</strong></p><p class="small mono">{problem}</p></div></div>
  {:else if !agenda}
    <p class="muted">Läser in dagordningen.</p>
  {:else}
    <div class="columns">
      <section class="main card" aria-labelledby="headings">
        <h2 id="headings">Rubriker och punkter</h2>
        <ol class="headings">
          {#each agenda.headings as h (h.no)}
            <li>
              <div class="heading">
                <span class="no mono">{h.no}</span>
                <div>
                  <h3>{h.name}</h3>
                  {#if h.hint}<p class="small muted">{h.hint}</p>{/if}
                </div>
              </div>
              {#if h.open.length}
                <ul class="points">
                  {#each h.open as p (p.no)}
                    <li>
                      <p><span class="point-no">{p.no}</span> <span class="small muted">{[KINDS[p.kind], p.role].filter(Boolean).join(', ')}</span></p>
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
              {/if}
            </li>
          {/each}
        </ol>
      </section>

      <aside class="side stack">
        <section class="card">
          <h2>Följer med från tidigare möten</h2>
          {#if open.length}
            <p>{open.length === 1 ? 'En öppen punkt.' : `${open.length} öppna punkter.`} {open.filter((p) => overdue(p.due)).length || 'Ingen'} har passerat sitt datum.</p>
            <p class="small muted" style="margin-top: 8px">En punkt ligger kvar under sitt nummer tills ett möte avslutar den.</p>
          {:else}
            <p class="muted">Inga öppna punkter.</p>
          {/if}
        </section>
        <section class="card">
          <h2>Så läses ett punktnummer</h2>
          <p><span class="point-no">3.4.2</span> är byggmöte 3, rubrik 4, andra punkten under rubriken på det mötet.</p>
          <p class="small muted" style="margin-top: 8px">Därför ligger rubrikernas nummer fast. En rubrik kan byta namn och nya läggs sist.</p>
        </section>
      </aside>
    </div>
  {/if}
</div>

<RecordDialog bind:this={recorder} {project} />

<style>
  .headings > li { padding: 14px 0; border-bottom: 1px solid var(--line); }
  .headings > li:first-child { padding-top: 0; }
  .headings > li:last-child { border-bottom: 0; padding-bottom: 0; }
  .heading { display: flex; gap: 16px; align-items: baseline; }
  .no { flex: 0 0 24px; text-align: right; color: var(--ink-500); }
  .points { margin: 10px 0 0 40px; display: flex; flex-direction: column; gap: 8px; }
  .points li { padding: 10px 14px; border-radius: var(--radius-sm); background: var(--sunken); display: flex; flex-direction: column; gap: 2px; }
</style>
