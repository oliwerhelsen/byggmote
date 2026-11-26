<script lang="ts">
  import { onMount } from 'svelte'
  import type { Agenda, Kind, Project, SeriesRef } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { clock, failure, KINDS } from '../lib/format'
  import type { Go } from '../lib/view'

  let { project, series, agenda: withAgenda, go }: { project: Project; series: SeriesRef; agenda: boolean; go: Go } = $props()

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
    const i = agenda.headings.findIndex((h) => h.no === current)
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
        go({ name: 'working', job: { projectId: project.id, seriesId: series.id, file, title, marks: { headings: $state.snapshot(pressed), marks: $state.snapshot(marks) } } })
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
    go({ name: 'meetings' })
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
</script>

<div class="page">
  <div class="page-head">
    <div>
      <h1>{title}</h1>
      <p class="muted">{project.name}</p>
    </div>
    <button class="btn" disabled={phase === 'saving'} onclick={leave}>{phase === 'idle' ? 'Till möten' : 'Avbryt inspelningen'}</button>
  </div>

  {#if problem}
    <div class="note bad" role="alert" style="margin-bottom: 24px"><Icon name="alert" /><p>{problem}</p></div>
  {/if}

  <div class="columns">
    <div class="main stack">
      <section class="card recorder" aria-label="Inspelning">
        <p class="timer" aria-live="off">{clock(elapsed)}</p>
        <p class="state">
          {#if phase === 'idle'}
            Inte igång
          {:else if phase === 'recording'}
            <span class="live" aria-hidden="true"></span> Spelar in
          {:else if phase === 'paused'}
            Pausad
          {:else}
            Sparar inspelningen
          {/if}
        </p>
        <div class="level" role="meter" aria-label="Ljudnivå i mikrofonen" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(level * 100)}>
          <div style="width: {level * 100}%"></div>
        </div>

        {#if phase === 'idle'}
          <button class="btn primary" onclick={begin}><Icon name="mic" /> {problem ? 'Försök igen' : 'Börja spela in'}</button>
        {:else}
          <div class="row">
            <button class="btn" disabled={phase === 'saving'} onclick={pause}>
              {#if phase === 'paused'}<Icon name="mic" /> Fortsätt{:else}<Icon name="pause" /> Pausa{/if}
            </button>
            <button class="btn primary" disabled={phase === 'saving'} onclick={finish}><Icon name="stop" /> Avsluta mötet</button>
          </div>
        {/if}
      </section>

      <section class="card" aria-labelledby="marks">
        <h2 id="marks">Sätt ett märke</h2>
        <p class="muted">Tryck när något viktigt sägs. Märket hjälper protokollet att hitta stället, men inget går förlorat utan det.</p>
        <div class="row" style="margin-top: 12px">
          {#each MARKS as kind}
            <button class="btn" disabled={phase !== 'recording'} onclick={() => mark(kind)}><Icon name="flag" /> {KINDS[kind]}</button>
          {/each}
        </div>
        {#if marks.length}
          <ul class="marked">
            {#each marks as m, i}
              <li>
                <span class="mono">{clock(m.at)}</span>
                <span class="grow">{KINDS[m.kind]}</span>
                <button class="btn quiet" aria-label="Ta bort märket {KINDS[m.kind]} vid {clock(m.at)}" onclick={() => marks.splice(i, 1)}>Ta bort</button>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    </div>

    {#if withAgenda}
    <aside class="side card" aria-labelledby="agenda">
      <h2 id="agenda">Dagordning</h2>
      <p class="muted small">Tryck när ni byter rubrik, så hamnar det som sägs på rätt ställe i protokollet.</p>
      {#if agenda}
        <ol class="headings">
          {#each agenda.headings as h (h.no)}
            <li>
              <button class="heading" class:current={h.no === current} aria-current={h.no === current ? 'step' : undefined}
                disabled={phase === 'idle' || phase === 'saving'} onclick={() => press(h.no)}>
                <span class="no mono">{h.no}</span>
                <span class="grow">
                  {h.name}
                  {#if h.open.length}<span class="small muted block">{h.open.length === 1 ? '1 öppen punkt' : `${h.open.length} öppna punkter`}</span>{/if}
                </span>
                {#if at(h.no) !== undefined}<span class="mono small muted">{clock(at(h.no)!)}</span>{/if}
              </button>
            </li>
          {/each}
        </ol>
        {#if next && phase !== 'idle'}
          <button class="btn" style="width: 100%; margin-top: 12px" disabled={phase === 'saving'} onclick={() => press(next.no)}>
            Nästa rubrik: {next.no}. {next.name}
          </button>
        {/if}
      {:else if !problem}
        <p class="muted">Läser in dagordningen.</p>
      {/if}
    </aside>
    {/if}
  </div>
</div>

<style>
  .recorder { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 40px 24px; text-align: center; }
  .timer { font: 300 72px/1 var(--font-body); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
  .state { display: flex; align-items: center; gap: 8px; color: var(--ink-700); min-height: 24px; }
  .live { width: 10px; height: 10px; border-radius: 50%; background: var(--bad); animation: pulse 1.6s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.3; } }
  .level { width: min(360px, 100%); height: 8px; border-radius: 4px; background: var(--sunken); overflow: hidden; margin-bottom: 12px; }
  .level div { height: 100%; background: var(--ok); transition: width 0.08s linear; }
  .marked { margin-top: 16px; }
  .marked li { display: flex; align-items: center; gap: 16px; border-top: 1px solid var(--line); }
  .headings { margin-top: 12px; display: flex; flex-direction: column; gap: 2px; }
  .heading { display: flex; align-items: center; gap: 12px; width: 100%; min-height: var(--ctl-h); padding: 6px 12px; border: 0; border-radius: var(--radius-sm);
    background: transparent; text-align: left; }
  .heading:hover:not(:disabled) { background: var(--sunken); }
  .heading.current { background: var(--coral-100); font-weight: 600; }
  .heading:disabled { opacity: 1; color: var(--ink-700); }
  .no { flex: 0 0 20px; text-align: right; color: var(--ink-500); }
  .block { display: block; font-weight: 400; }
</style>
