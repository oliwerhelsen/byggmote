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
  import { title } from '../lib/tools'

  let { run, project, waiting, dismiss }: { run: Run; project: { name: string }; waiting: boolean; dismiss: () => void } = $props()
  const mac = window.api.platform === 'darwin'
  const job = $derived(run.job)
  const at = $derived(run.at)
  const fraction = $derived(run.fraction)
  const problem = $derived(run.problem)
</script>

<div class="view">
  <div class="bar-title" class:sr={!mac} use:title={mac}>
    <h1>{job.title}</h1>
    <p>{project.name}</p>
  </div>
  {#if mac}<span class="badge" use:title>{problem ? 'Gick inte att skriva ut' : waiting ? 'Väntar på sin tur' : 'Skrivs ut'}</span>{/if}

  <div class="job">
    <h2>{job.title} {problem ? 'skrevs inte ut' : waiting ? 'väntar på sin tur' : 'skrivs ut'}</h2>
    <p class="muted">Inspelningen skrivs ut och blir ett protokoll. Allt görs på den här datorn.</p>

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
      <ol aria-live="polite">
        {#each STEPS as step, i}
          <li class:done={i < at} class:now={i === at}>
            <div class="step">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
                {#if i < at}
                  <circle cx="9" cy="9" r="8" fill="var(--ok-bg)" /><path d="m5.5 9.2 2.4 2.4 4.6-5" stroke="var(--ok)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
                {:else if i === at}
                  <circle cx="9" cy="9" r="7" stroke="var(--line)" stroke-width="2" /><path class="turn" d="M9 2a7 7 0 0 1 7 7" stroke="var(--coral-700)" stroke-width="2" stroke-linecap="round" />
                {:else}
                  <circle cx="9" cy="9" r="7.25" stroke="var(--line)" stroke-width="1.5" />
                {/if}
              </svg>
              <span>{step}{#if i < at}<span class="sr">, klart</span>{/if}</span>
            </div>
            {#if i === at}
              <div class="bar" role="progressbar" aria-label={step} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(fraction * 100)}>
                <div class:waiting={fraction === 0 || fraction === 1} style="width: {Math.max(4, fraction * 100)}%"></div>
              </div>
            {/if}
          </li>
        {/each}
      </ol>
      <p class="small muted foot">Ett möte på en timme tar några minuter. Du kan arbeta vidare i andra möten så länge.</p>
    {/if}
  </div>
</div>

<style>
  .view { display: flex; align-items: center; justify-content: center; min-height: 100%; padding: 24px; background: var(--win-bg); }
  .job { width: 460px; max-width: 100%; display: flex; flex-direction: column; }
  h2 { margin-bottom: 6px; font: 600 17px/1.3 var(--font-ui); letter-spacing: 0; }
  .small { font-size: var(--ui-small); }
  .note { margin-top: 20px; }
  ol { display: flex; flex-direction: column; gap: 12px; margin-top: 20px; }
  li { display: flex; flex-direction: column; gap: 12px; color: var(--ink-500); }
  li.done { color: var(--ink-900); }
  li.now { color: var(--ink-900); font-weight: 600; }
  .step { display: flex; align-items: center; gap: 12px; min-height: 22px; }
  .step svg { flex: none; }
  .turn { transform-origin: 9px 9px; animation: turn 1s linear infinite; }
  @keyframes turn { to { transform: rotate(360deg); } }
  .bar { height: 4px; margin-left: 30px; border-radius: 2px; background: var(--line); overflow: hidden; }
  .bar div { height: 100%; border-radius: 2px; background: var(--coral-700); transition: width 0.3s; }
  .bar div.waiting { width: 30% !important; animation: slide 1.4s ease-in-out infinite; }
  @keyframes slide { from { margin-left: -30%; } to { margin-left: 100%; } }
  .foot { margin-top: 24px; }
</style>
