<script lang="ts" module>
  import type { Job } from '../../../shared/types'

  // The engine's steps, as a person would name them.
  export const STEPS = ['Ljudet läses in', 'Talet skrivs ut', 'Talarna skiljs åt', 'Utskriften sparas', 'Protokollet skrivs']
  /** A recording on its way to a protocol: the step it is at and how far into it, or why it stopped. The window keeps
   * these (App.svelte), so the work goes on whatever the window shows. */
  export type Run = { id: number; job: Job; at: number; fraction: number; problem: string }
</script>

<script lang="ts">
  import Icon from '../lib/Icon.svelte'

  let { run, waiting, dismiss }: { run: Run; waiting: boolean; dismiss: () => void } = $props()
  const job = $derived(run.job)
  const at = $derived(run.at)
  const fraction = $derived(run.fraction)
  const problem = $derived(run.problem)
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
        <button class="btn" style="margin-top: 12px" onclick={dismiss}>Till översikten</button>
      </div>
    </div>
  {:else if waiting}
    <div class="note" role="status"><Icon name="clock" /><p><strong>Väntar på sin tur.</strong> Ett annat möte skrivs ut först. Inspelningen är sparad.</p></div>
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
        Ett möte på en timme tar några minuter. Du kan arbeta vidare i andra möten så länge, men låt Byggmöte vara igång.
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
