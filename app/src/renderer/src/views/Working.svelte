<script lang="ts">
  import type { Job, Progress } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { failure } from '../lib/format'
  import type { Go } from '../lib/view'

  let { job, go }: { job: Job; go: Go } = $props()

  // The engine's steps, as a person would name them. It loads a model before the second and the third.
  const STEPS = ['Ljudet läses in', 'Talet skrivs ut', 'Talarna skiljs åt', 'Utskriften sparas', 'Protokollet skrivs']
  const AT: Record<string, number> = { extract: 0, asr: 1, diarize: 2, merge: 3, write: 3, protocol: 4 }

  let at = $state(0)
  let fraction = $state(0)
  let problem = $state('')

  function heard(p: Progress): void {
    const i = AT[p.step.split(':')[0]]
    if (i === undefined) {
      if (p.step === 'load' && p.state === 'start' && at < 2) (at += 1), (fraction = 0)
      return
    }
    if (i > at) (at = i), (fraction = 0)
    if (i === at) fraction = p.state === 'done' ? 1 : p.state === 'progress' ? (p.fraction ?? 0) : fraction
  }

  $effect(() => {
    const off = window.api.onProgress(heard)
    window.api
      .process($state.snapshot(job))
      .then((done) => go({ name: 'protocol', dir: done.dir, problem: done.protocolError ?? undefined }))
      .catch((e) => (problem = failure(e)))
    return off
  })
</script>

<div class="page narrow">
  <div class="page-head">
    <div>
      <h1>{job.title}</h1>
      <p class="muted">Inspelningen skrivs ut och blir ett protokoll. Allt görs på den här datorn.</p>
    </div>
  </div>

  {#if problem}
    <div class="note bad" role="alert">
      <Icon name="alert" />
      <div>
        <p><strong>Det gick inte att skriva ut inspelningen.</strong> Den ligger kvar där den var, så inget är förlorat.</p>
        <p class="small mono">{problem}</p>
        <p class="small mono">{job.file}</p>
        <button class="btn" style="margin-top: 12px" onclick={() => go({ name: 'meetings' })}>Till möten</button>
      </div>
    </div>
  {:else}
    <section class="card" aria-live="polite">
      <ol>
        {#each STEPS as step, i}
          <li class:done={i < at} class:now={i === at}>
            <span class="mark">{#if i < at}<Icon name="check" size={16} />{:else}<span class="mono">{i + 1}</span>{/if}</span>
            <div class="grow">
              <p>{step}</p>
              {#if i === at}
                <div class="bar" role="progressbar" aria-label={step} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(fraction * 100)}>
                  <div class:waiting={fraction === 0 || fraction === 1} style="width: {Math.max(4, fraction * 100)}%"></div>
                </div>
              {/if}
            </div>
          </li>
        {/each}
      </ol>
      <p class="small muted" style="margin-top: 16px">
        Ett möte på en timme tar några minuter. Låt fönstret vara öppet så länge.
      </p>
    </section>
  {/if}
</div>

<style>
  .narrow { max-width: 720px; }
  ol { display: flex; flex-direction: column; gap: 4px; }
  li { display: flex; gap: 14px; align-items: flex-start; padding: 10px 0; color: var(--ink-500); }
  li.now, li.done { color: var(--ink-900); }
  .mark { flex: none; display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; background: var(--sunken); color: var(--ink-500); }
  li.done .mark { background: var(--ok-bg); color: var(--ok); }
  li.now .mark { background: var(--coral-100); color: var(--ink-900); }
  .bar { height: 6px; margin-top: 8px; border-radius: 3px; background: var(--sunken); overflow: hidden; }
  .bar div { height: 100%; border-radius: 3px; background: var(--coral-700); transition: width 0.3s; }
  .bar div.waiting { width: 30% !important; animation: slide 1.4s ease-in-out infinite; }
  @keyframes slide { from { margin-left: -30%; } to { margin-left: 100%; } }
</style>
