<script lang="ts">
  import { onMount } from 'svelte'
  // The small window a meeting is recorded in. It stays over other programs; the main window is free meanwhile.
  import type { Agenda, Kind, RecordCommand, RecordSpec } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { clock, failure, KINDS } from '../lib/format'

  let { spec }: { spec: RecordSpec } = $props()
  // svelte-ignore state_referenced_locally
  const { series, agenda: withAgenda } = spec
  // svelte-ignore state_referenced_locally
  const project = { id: spec.projectId, name: spec.projectName }

  const MARKS: Kind[] = ['decision', 'todo', 'changeOrder', 'question']

  let agenda = $state<Agenda | null>(null)
  let phase = $state<'idle' | 'recording' | 'paused' | 'saving'>('idle')
  let elapsed = $state(0) // seconds of recorded sound: a pause does not count
  let level = $state(0)
  let current = $state<number | null>(null)
  let pressed = $state<{ no: number; at: number }[]>([])
  let marks = $state<{ kind: Kind; at: number }[]>([])
  let problem = $state('')

  let stream: MediaStream | undefined
  let recorder: MediaRecorder | undefined
  let context: AudioContext | undefined
  let id = ''
  let saved = Promise.resolve()
  let before = 0
  let since = 0
  let ticking: ReturnType<typeof setInterval> | undefined

  // The agenda is read while the microphone opens, and the first heading is pressed once both are there.
  let loaded: Promise<unknown> = Promise.resolve()
  const load = (): Promise<unknown> =>
    withAgenda
    ? window.api
        .agenda(project.id, series.id)
        .then((a) => (agenda = a))
        .catch((e) => (problem = failure(e)))
    : Promise.resolve()

  const title = $derived(`${series.name} ${agenda?.no ?? series.next}`)
  // Without an agenda nothing is pressed: the protocol finds the headings itself, which the marks only help with.
  const next = $derived.by(() => {
    if (!agenda) return null
    const i = agenda.headings.findIndex((h) => h.no === current) // -1 before the first is pressed: the first is next
    return agenda.headings[i + 1] ?? null
  })
  const now = (): number => (phase === 'recording' ? before + (performance.now() - since) / 1000 : before)

  function meter(source: MediaStream): void {
    context = new AudioContext()
    void context.resume() // a context can start suspended, and then the meter would show silence
    const analyser = context.createAnalyser()
    analyser.fftSize = 1024
    context.createMediaStreamSource(source).connect(analyser)
    const buffer = new Float32Array(analyser.fftSize)
    const read = (): void => {
      if (!context) return
      analyser.getFloatTimeDomainData(buffer)
      level = Math.min(1, Math.sqrt(buffer.reduce((sum, v) => sum + v * v, 0) / buffer.length) * 6)
      requestAnimationFrame(read)
    }
    read()
  }

  async function begin(): Promise<void> {
    problem = ''
    try {
      const wanted = (await window.api.settings().catch(() => null))?.microphone
      const audio = { echoCancellation: false, noiseSuppression: false, autoGainControl: true, channelCount: 1 }
      // The microphone chosen in the settings; if it is gone (unplugged), the computer's own, not no recording.
      stream = await navigator.mediaDevices.getUserMedia({ audio: wanted ? { ...audio, deviceId: { exact: wanted } } : audio }).catch(() =>
        navigator.mediaDevices.getUserMedia({ audio })
      )
    } catch {
      problem = 'Byggmöte kommer inte åt mikrofonen. Tillåt mikrofonen för Byggmöte i datorns inställningar och försök igen.'
      return
    }
    try {
      id = await window.api.recordingStart()
      recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 64000 })
      // A second at a time to disk, in order: a crash loses a second, not the meeting.
      recorder.ondataavailable = (e) => {
        if (!e.data.size) return
        saved = saved.then(async () => window.api.recordingChunk(id, new Uint8Array(await e.data.arrayBuffer()))).catch((err) => {
          problem = `Inspelningen går inte att spara. ${failure(err)}`
        })
      }
      recorder.start(1000)
      meter(stream)
      since = performance.now()
      phase = 'recording'
      ticking = setInterval(() => (elapsed = now()), 250)
      await loaded
      if (withAgenda && agenda?.headings[0]) press(agenda.headings[0].no)
    } catch (e) {
      problem = failure(e)
      quiet()
    }
  }

  function pause(): void {
    if (phase === 'recording') {
      before = now()
      recorder?.pause()
      phase = 'paused'
    } else if (phase === 'paused') {
      recorder?.resume()
      since = performance.now()
      phase = 'recording'
    }
  }

  function quiet(): void {
    clearInterval(ticking)
    stream?.getTracks().forEach((t) => t.stop())
    void context?.close()
    context = undefined
    level = 0
  }

  function finish(): void {
    if (!recorder) return
    before = now()
    elapsed = before
    phase = 'saving'
    recorder.onstop = async () => {
      await saved
      quiet()
      if (problem) return // what could not be saved is said above; the file that was written stays
      try {
        const file = await window.api.recordingStop(id)
        await window.api.recordDone({ projectId: project.id, seriesId: series.id, file, title, marks: { headings: $state.snapshot(pressed), marks: $state.snapshot(marks) } })
      } catch (e) {
        problem = failure(e)
      }
    }
    recorder.stop()
  }

  async function leave(): Promise<void> {
    if (phase !== 'idle') {
      if (!confirm('Avbryta inspelningen? Det som är inspelat tas bort.')) return
      // The last second arrives before the recorder says it has stopped: only then is everything written, and can go.
      if (recorder && recorder.state !== 'inactive') await new Promise<void>((done) => ((recorder!.onstop = () => done()), recorder!.stop()))
      quiet()
      await saved
      await window.api.recordingDiscard(id)
    }
    await window.api.recordClose()
  }

  const press = (no: number): void => {
    if (phase === 'idle' || phase === 'saving' || no === current) return
    current = no
    pressed.push({ no, at: Math.round(now() * 10) / 10 })
  }
  const mark = (kind: Kind): void => {
    marks.push({ kind, at: Math.round(now() * 10) / 10 })
  }
  const at = (no: number): number | undefined => pressed.findLast((p) => p.no === no)?.at

  // Everyone has been told in the dialog before this view opens, so the recording starts at once.
  onMount(() => {
    loaded = load()
    void begin()
  })
  $effect(() => quiet)

  const label = (h: { no: number; name: string } | null | undefined): string | null => (h ? `${h.no}. ${h.name}` : null)
  const heading = $derived(agenda?.headings.find((h) => h.no === current) ?? null)

  // The menu, the icon beside the clock and the main window follow the recording.
  $effect(() => {
    document.title = title
    void window.api.recordStatus({ title, phase, seconds: Math.floor(elapsed), heading: label(heading), next: phase === 'idle' ? null : label(next) })
  })

  /** From the menu, the icon beside the clock, or a shortcut pressed in another program. */
  function command(c: RecordCommand): void {
    if (c === 'pause') pause()
    else if (c === 'next') next && press(next.no)
    else if (c === 'finish') phase === 'recording' || phase === 'paused' ? finish() : undefined
    else if (c === 'cancel') phase === 'saving' ? undefined : void leave()
    else if (phase === 'recording') mark(c)
  }
  $effect(() => window.api.onRecordCommand(command))

  // The shortcuts as the computer writes them (app/src/main/recording.ts registers them).
  const mac = window.api.platform === 'darwin'
  const keys = (k: string): string => (mac ? `⌃⌥${k}` : `Alt+Skift+${k}`)
  let all = $state(false) // the whole agenda, for a heading that is not the next one
</script>

<div class="rec">
  <header>
    <p class="timer" class:off={phase !== 'recording'} aria-live="off">{clock(elapsed)}</p>
    <div class="right">
      <p class="state">
        {#if phase === 'idle'}
          Inte igång
        {:else if phase === 'recording'}
          <span class="live" aria-hidden="true"></span> Spelar in
        {:else if phase === 'paused'}
          <span class="live paused" aria-hidden="true"></span> Pausad
        {:else}
          Sparar inspelningen
        {/if}
      </p>
      <div class="level" role="meter" aria-label="Ljudnivå i mikrofonen" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(level * 100)}>
        <div style="width: {level * 100}%"></div>
      </div>
    </div>
  </header>
  <h1 class="sr">{title}</h1>
  <p class="small muted where">{title} · {project.name}</p>

  {#if problem}
    <div class="note bad" role="alert"><Icon name="alert" size={16} /><p>{problem}</p></div>
  {/if}

    {#if withAgenda}
      <section class="now" aria-labelledby="agenda">
        <h2 id="agenda" class="sr">Dagordning</h2>
        {#if agenda}
          <p class="cur">{#if !heading}<span class="muted">Ingen rubrik än</span>{/if}{#if heading}<strong>{heading.no}. {heading.name}</strong>{#if at(heading.no) !== undefined}<span class="small muted">sedan {clock(at(heading.no)!)}</span>{/if}{/if}</p>
          {#if next}
            <button class="btn next" disabled={phase === 'saving' || phase === 'idle'} onclick={() => press(next.no)}>
              <span class="grow">Nästa rubrik: {next.no}. {next.name}</span><kbd>{keys('N')}</kbd>
            </button>
          {/if}
          <button class="link" aria-expanded={all} onclick={() => (all = !all)}>{all ? 'Dölj rubrikerna' : 'Alla rubriker'}</button>
          {#if all}
            <ol class="headings">
              {#each agenda.headings as h (h.no)}
                <li>
                  <button class="heading" class:current={h.no === current} aria-current={h.no === current ? 'step' : undefined}
                    disabled={phase === 'saving' || phase === 'idle'} onclick={() => press(h.no)}>
                    <span class="no mono">{h.no}</span>
                    <span class="grow">{h.name}{#if h.open.length}<span class="small muted"> · {h.open.length === 1 ? '1 öppen punkt' : `${h.open.length} öppna punkter`}</span>{/if}</span>
                    {#if at(h.no) !== undefined}<span class="mono small muted">{clock(at(h.no)!)}</span>{/if}
                  </button>
                </li>
              {/each}
            </ol>
          {/if}
        {:else if !problem}
          <p class="muted">Läser in dagordningen.</p>
        {/if}
      </section>
    {/if}

    <section aria-labelledby="marks">
      <h2 id="marks" class="head">Sätt ett märke</h2>
      <div class="marks">
        {#each MARKS as kind, i}
          <button class="btn" disabled={phase !== 'recording'} onclick={() => mark(kind)}><span class="grow">{KINDS[kind]}</span><kbd>{keys(String(i + 1))}</kbd></button>
        {/each}
      </div>
      {#if marks.length}
        <ul class="marked">
          {#each marks.slice(-3).reverse() as m (m.at + m.kind)}
            <li>
              <span class="mono">{clock(m.at)}</span>
              <span class="grow">{KINDS[m.kind]}</span>
              <button class="link" aria-label="Ta bort märket {KINDS[m.kind]} vid {clock(m.at)}" onclick={() => marks.splice(marks.indexOf(m), 1)}>Ta bort</button>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

  {#if phase === 'idle'}
    <div class="row foot">
      <button class="btn primary" onclick={begin}><Icon name="mic" size={16} /> {problem ? 'Försök igen' : 'Börja spela in'}</button>
      <button class="btn" onclick={leave}>Stäng</button>
    </div>
  {:else}
    <div class="row foot">
      <button class="btn" disabled={phase === 'saving'} onclick={pause}>
        {#if phase === 'paused'}<Icon name="mic" size={16} /> Fortsätt{:else}<Icon name="pause" size={16} /> Pausa{/if}
      </button>
      <button class="btn primary" disabled={phase === 'saving'} onclick={finish}><Icon name="stop" size={16} /> Avsluta mötet</button>
    </div>
    <button class="link cancel" disabled={phase === 'saving'} onclick={leave}>Avbryt inspelningen…</button>
  {/if}
</div>

<style>
  .rec { display: flex; flex-direction: column; gap: 10px; min-height: 100%; padding: 14px 16px 12px; background: var(--surface); }
  header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .timer { font: 600 52px/1 var(--font-ui); font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
  .timer.off { color: var(--ink-400); }
  .right { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
  .state { display: flex; align-items: center; gap: 6px; font-weight: 600; white-space: nowrap; }
  .live { width: 9px; height: 9px; border-radius: 50%; background: var(--coral-600); animation: pulse 1.6s ease-in-out infinite; }
  .live.paused { background: var(--warn); animation: none; }
  @keyframes pulse { 50% { opacity: 0.3; } }
  .level { width: 110px; height: 6px; border-radius: 3px; background: var(--sunken); overflow: hidden; }
  .level div { height: 100%; background: var(--coral-600); transition: width 0.08s linear; }
  .where { margin-top: -6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .now { display: flex; flex-direction: column; gap: 8px; padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--canvas); }
  .cur { display: flex; align-items: baseline; gap: 8px; min-height: 26px; white-space: nowrap; }
  .cur strong { font-size: 20px; line-height: 26px; overflow: hidden; text-overflow: ellipsis; }
  .next { justify-content: flex-start; min-height: 44px; font-size: calc(var(--ui) + 2px); font-weight: 600; text-align: left; }
  kbd { flex: none; padding: 1px 5px; border: 1px solid var(--edge); border-bottom-width: 2px; border-radius: 4px; background: var(--surface); font: 500 11px var(--font-mono); color: var(--ink-700); white-space: nowrap; }
  .head { font: 600 var(--ui-small) var(--font-ui); letter-spacing: 0; color: var(--ink-500); margin-bottom: 6px; }
  .marks { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
  .marks .btn { justify-content: flex-start; min-height: 34px; font-weight: 600; text-align: left; }
  .link { align-self: flex-start; padding: 0; border: 0; background: transparent; color: var(--ink-500); font-size: var(--ui-small); }
  .link:hover:not(:disabled) { color: var(--coral-800); text-decoration: underline; }
  .marked { margin-top: 6px; }
  .marked li { display: flex; align-items: center; gap: 12px; min-height: 24px; border-top: 1px solid var(--line); }
  .headings { display: flex; flex-direction: column; gap: 1px; max-height: 180px; overflow-y: auto; }
  .heading { display: flex; align-items: center; gap: 8px; width: 100%; min-height: var(--row-h); padding: 2px 8px; border: 0; border-radius: var(--ctl-r); background: transparent; text-align: left; }
  .heading:hover:not(:disabled) { background: var(--sunken); }
  .heading.current { background: var(--coral-100); font-weight: 600; }
  .no { flex: 0 0 18px; text-align: right; color: var(--ink-500); }
  .foot { margin-top: auto; flex-wrap: nowrap; gap: 8px; padding-top: 4px; }
  .foot .btn { flex: 1 1 0; min-height: 34px; }
  .cancel { align-self: flex-end; }
</style>
