<script lang="ts">
  // Asks what is needed before a meeting is recorded: with or without the agenda, and that everyone knows. It says
  // which microphone will be used and shows that it hears. Opened from the toolbar, the overview and the menu, and from
  // an agenda (which has chosen the agenda already). An alert on the Mac, a ContentDialog on Windows.
  import type { SeriesRef } from '../../../shared/types'

  let { project }: { project: { id: string; name: string } } = $props()

  const BARS = [6, 10, 14, 9, 16, 12, 7, 11, 15, 8] // the meter's bars when lit, in pixels

  let dialog = $state<HTMLDialogElement>()
  let series = $state<SeriesRef | null>(null)
  let fixed = $state(false) // the agenda is already chosen: no question about it
  let withAgenda = $state(true)
  let consent = $state(false)
  let microphone = $state('Datorns val')
  let level = $state(0)
  let hears = $state(false)
  let listening: { stream: MediaStream; context: AudioContext } | null = null
  let turn = 0 // a microphone that opens after the dialog has closed is let go at once

  export function show(s: SeriesRef, agenda?: boolean): void {
    series = s
    fixed = agenda !== undefined
    withAgenda = agenda ?? true
    consent = false
    dialog?.showModal()
    void listen()
  }

  /** The microphone the recording will use (RecordWindow.svelte asks the same way), heard only for its level. Only
   * when the computer has already allowed it: the question is asked in Inställningar and the first run, not here. */
  async function listen(): Promise<void> {
    const mine = ++turn
    microphone = 'Datorns val'
    try {
      const wanted = (await window.api.settings()).microphone
      const allowed = await navigator.permissions.query({ name: 'microphone' as PermissionName })
      if (allowed.state !== 'granted' || mine !== turn) return
      const stream = await navigator.mediaDevices.getUserMedia({ audio: wanted ? { deviceId: { exact: wanted } } : true }).catch(() => navigator.mediaDevices.getUserMedia({ audio: true }))
      if (mine !== turn) return stream.getTracks().forEach((t) => t.stop())
      const track = stream.getAudioTracks()[0]
      // The chosen one by its name. If it is gone the computer's own is used, and that is what this says.
      if (wanted && track?.getSettings().deviceId === wanted) microphone = track.label || 'Mikrofon'
      const context = new AudioContext()
      const analyser = context.createAnalyser()
      context.createMediaStreamSource(stream).connect(analyser)
      listening = { stream, context }
      hears = true
      const buffer = new Float32Array(analyser.fftSize)
      const read = (): void => {
        if (listening?.context !== context) return
        analyser.getFloatTimeDomainData(buffer)
        level = Math.min(1, Math.sqrt(buffer.reduce((sum, v) => sum + v * v, 0) / buffer.length) * 6)
        requestAnimationFrame(read)
      }
      read()
    } catch {
      // No microphone to hear: the line names the choice and the meter is still. The recording window says what is wrong.
    }
  }

  function quiet(): void {
    turn++
    listening?.stream.getTracks().forEach((t) => t.stop())
    void listening?.context.close()
    listening = null
    hears = false
    level = 0
  }

  function begin(e: SubmitEvent): void {
    e.preventDefault()
    const s = series
    if (!s || !consent) return
    dialog?.close()
    // The meeting is recorded in a small window of its own; this one stays free.
    void window.api.recordOpen({ projectId: project.id, projectName: project.name, series: $state.snapshot(s), agenda: withAgenda })
  }

  function closed(): void {
    quiet()
    series = null
  }
</script>

<dialog bind:this={dialog} aria-labelledby="record-title" onclose={closed}>
  {#if series}
    <form onsubmit={begin}>
      <div class="body">
        <h2 id="record-title">Nytt möte</h2>
        <p class="muted">{series.name} {series.next} · {project.name}</p>
        {#if !fixed}
          <fieldset>
            <legend class="sr">Dagordning</legend>
            <label class="choice">
              <input type="radio" name="agenda" value={true} bind:group={withAgenda} />
              <span><span class="name">Med dagordning</span><span class="hint">Ni trycker när ni byter rubrik, och öppna punkter följer med.</span></span>
            </label>
            <label class="choice">
              <input type="radio" name="agenda" value={false} bind:group={withAgenda} />
              <span><span class="name">Utan dagordning</span><span class="hint">Ett möte som inte följer rubrikerna. Protokollet sorterar punkterna själv.</span></span>
            </label>
          </fieldset>
        {/if}
        <div class="mic">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" aria-hidden="true"><rect x="6" y="1.5" width="4" height="8" rx="2" /><path d="M3.5 7.5a4.5 4.5 0 0 0 9 0M8 12v2.5" /></svg>
          <span class="which"><span class="muted">Mikrofon:</span> {microphone}</span>
          <div class="meter" role="img" aria-label={hears ? 'Mikrofonens nivå' : 'Mikrofonen hörs inte här'}>
            {#each BARS as h, i}
              {@const lit = level * BARS.length > i}
              <i class:lit style="height: {lit ? h : 4}px"></i>
            {/each}
          </div>
        </div>
        <label class="consent">
          <input type="checkbox" bind:checked={consent} />
          <span>Alla i rummet vet att mötet spelas in</span>
        </label>
      </div>
      <!-- The Mac's order has the default button last; Windows has it first, and both as wide. -->
      <div class="actions">
        <button class="btn cancel" type="button" onclick={() => dialog?.close()}>Avbryt</button>
        <button class="btn primary" type="submit" disabled={!consent}>Börja spela in</button>
      </div>
    </form>
  {/if}
</dialog>

<style>
  /* Windows' ContentDialog first, the Mac's alert below. */
  dialog { width: min(480px, calc(100vw - 32px)); margin: auto; padding: 0; overflow: hidden; border: 1px solid rgb(0 0 0 / 0.2); border-radius: 8px; background: #fff; color: inherit;
    box-shadow: 0 32px 64px rgb(0 0 0 / 0.3), 0 2px 21px rgb(0 0 0 / 0.16); }
  dialog::backdrop { background: rgb(0 0 0 / 0.3); }
  .body { display: flex; flex-direction: column; padding: 24px; }
  h2 { font: 600 20px/28px var(--font-ui); letter-spacing: 0; }
  fieldset { border: 0; padding: 0; margin: 16px 0 0; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
  .choice { display: flex; gap: 10px; }
  .name, .hint { display: block; }
  .hint { font-size: var(--ui-small); color: var(--ink-500); }
  input { appearance: none; flex: none; display: inline-grid; place-items: center; margin: 0; background: #fff; border: 1px solid var(--ink-500); }
  input[type='radio'] { width: 20px; height: 20px; border-radius: 50%; }
  input[type='radio']:checked { background: var(--coral-700); border-color: var(--coral-700); }
  input[type='radio']:checked::after { content: ''; width: 8px; height: 8px; border-radius: 50%; background: #fff; }
  input[type='checkbox'] { width: 18px; height: 18px; border-radius: 4px; }
  input[type='checkbox']:checked { background: var(--coral-700); border-color: var(--coral-800); }
  input[type='checkbox']:checked::after { content: ''; width: 9px; height: 5px; margin-top: -2px; border: solid #fff; border-width: 0 0 1.6px 1.6px; transform: rotate(-45deg); }
  .mic { display: flex; align-items: center; gap: 10px; height: 40px; margin-top: 16px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
  .mic svg { flex: none; color: var(--ink-500); }
  .which { flex: 1 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .meter { flex: none; display: flex; align-items: center; gap: 2px; height: 20px; }
  .meter i { width: 3px; border-radius: 2px; background: var(--ink-300); }
  .meter i.lit { background: var(--coral-600); }
  .consent { display: flex; align-items: center; gap: 10px; margin-top: 14px; }
  .actions { display: flex; flex-direction: row-reverse; gap: 8px; padding: 24px; background: #f3f3f3; border-top: 1px solid var(--line); }
  .actions .btn { flex: 1; }
  .btn:disabled { opacity: 0.45; }

  :global(:root[data-platform='mac']) dialog { width: min(420px, calc(100vw - 32px)); margin-top: 96px; border-radius: 12px; background: #f6f5f9;
    box-shadow: 0 22px 54px rgb(0 0 0 / 0.36), 0 2px 6px rgb(0 0 0 / 0.18); }
  :global(:root[data-platform='mac']) dialog::backdrop { background: rgb(0 0 0 / 0.14); }
  :global(:root[data-platform='mac']) .body { padding: 20px 20px 0; }
  :global(:root[data-platform='mac']) h2 { font: 700 15px/1.35 var(--font-ui); }
  :global(:root[data-platform='mac']) h2 + p { margin-top: 2px; }
  :global(:root[data-platform='mac']) fieldset { margin-top: 14px; gap: 10px; }
  :global(:root[data-platform='mac']) .choice { gap: 8px; }
  :global(:root[data-platform='mac']) .choice:has(input:checked) .name { font-weight: 600; }
  :global(:root[data-platform='mac']) input { border-color: #b9b8c2; }
  :global(:root[data-platform='mac']) input[type='radio'] { width: 14px; height: 14px; margin-top: 2px; }
  :global(:root[data-platform='mac']) input[type='radio']:checked { border-color: var(--coral-800); }
  :global(:root[data-platform='mac']) input[type='radio']:checked::after { width: 5px; height: 5px; }
  :global(:root[data-platform='mac']) input[type='checkbox'] { width: 14px; height: 14px; border-radius: 3.5px; }
  :global(:root[data-platform='mac']) input[type='checkbox']:checked::after { width: 7px; height: 4px; }
  :global(:root[data-platform='mac']) .mic { gap: 8px; height: 36px; margin-top: 14px; }
  :global(:root[data-platform='mac']) .consent { gap: 8px; margin-top: 12px; }
  :global(:root[data-platform='mac']) .actions { flex-direction: row; justify-content: flex-end; padding: 18px 20px 20px; background: transparent; border-top: 0; }
  :global(:root[data-platform='mac']) .actions .btn { flex: none; }
  :global(:root[data-platform='mac']) .actions .cancel { min-width: 76px; }
</style>
