<script lang="ts">
  // Asks what is needed before a meeting is recorded: with or without the agenda, and that everyone knows. Used on
  // the meetings page and on the agenda page (which has chosen the agenda already).
  import type { SeriesRef } from '../../../shared/types'
  import Icon from './Icon.svelte'
  import type { Go } from './view'

  let { go }: { go: Go } = $props()

  let dialog = $state<HTMLDialogElement>()
  let series = $state<SeriesRef | null>(null)
  let fixed = $state(false) // the agenda is already chosen: no question about it
  let withAgenda = $state(true)
  let consent = $state(false)

  export function show(s: SeriesRef, agenda?: boolean): void {
    series = s
    fixed = agenda !== undefined
    withAgenda = agenda ?? true
    consent = false
    dialog?.showModal()
  }

  function begin(): void {
    const s = series
    dialog?.close()
    if (s) go({ name: 'recording', series: s, agenda: withAgenda })
  }
</script>

<dialog bind:this={dialog} aria-labelledby="record-title" onclose={() => (series = null)}>
  <h2 id="record-title">Nytt möte</h2>
  {#if series}
    <p class="muted">{series.name} {series.next}</p>
    {#if !fixed}
      <fieldset>
        <legend class="small muted">Dagordning</legend>
        <label class="choice">
          <input type="radio" name="agenda" value={true} bind:group={withAgenda} />
          <span><strong>Med dagordning</strong><span class="small muted block">Ni trycker när ni byter rubrik, och öppna punkter följer med.</span></span>
        </label>
        <label class="choice">
          <input type="radio" name="agenda" value={false} bind:group={withAgenda} />
          <span><strong>Utan dagordning</strong><span class="small muted block">Ett möte som inte följer rubrikerna. Protokollet sorterar punkterna själv.</span></span>
        </label>
      </fieldset>
    {/if}
    <label class="consent">
      <input type="checkbox" bind:checked={consent} />
      <span>Alla i rummet vet att mötet spelas in</span>
    </label>
    <div class="row actions">
      <button class="btn" onclick={() => dialog?.close()}>Avbryt</button>
      <button class="btn primary" disabled={!consent} onclick={begin}><Icon name="mic" /> Börja spela in</button>
    </div>
  {/if}
</dialog>

<style>
  dialog { width: min(440px, calc(100vw - 32px)); margin: auto; padding: 24px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); box-shadow: var(--shadow-sm); }
  dialog::backdrop { background: rgb(0 0 0 / 0.35); }
  dialog h2 { margin-bottom: 4px; }
  fieldset { border: 0; padding: 0; margin: 16px 0 0; display: flex; flex-direction: column; gap: 8px; }
  .choice { display: flex; align-items: flex-start; gap: 12px; min-height: 44px; padding: 10px 12px; border: 1px solid var(--line); border-radius: var(--radius-sm); cursor: pointer; }
  .choice:has(input:checked) { border-color: var(--coral-700); background: var(--coral-100); }
  .choice input { width: 20px; height: 20px; margin-top: 2px; accent-color: var(--coral-700); }
  .block { display: block; }
  .consent { display: flex; align-items: center; gap: 10px; min-height: 44px; margin-top: 16px; }
  .consent input { width: 20px; height: 20px; accent-color: var(--coral-700); }
  .actions { justify-content: flex-end; margin-top: 12px; }
</style>
