<script lang="ts">
  import { onMount } from 'svelte'
  // The small window a meeting is recorded in. It stays over other programs; the main window is free meanwhile.
  import { accelerators, spell, type Global } from '../../../shared/keys'
  import type { Agenda, Kind, RecordCommand, RecordSpec, Shortcuts } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { clock, count, failure, KINDS } from '../lib/format'

  let { spec }: { spec: RecordSpec } = $props()
  // svelte-ignore state_referenced_locally
  const { series, agenda: withAgenda } = spec
  // svelte-ignore state_referenced_locally
  const project = { id: spec.projectId, name: spec.projectName }

  const MARKS = ['decision', 'todo', 'changeOrder', 'question'] as const satisfies Kind[]

  let agenda = $state<Agenda | null>(null)
  let phase = $state<'idle' | 'recording' | 'paused' | 'saving'>('idle')
  let elapsed = $state(0) // seconds of recorded sound: a pause does not count
  let level = $state(0)
  // The meter is the last couple of seconds as bars, the newest last: how loud the room was, not only is.
  const BARS = 22
  let heard = $state<number[]>(Array(BARS).fill(0))
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
      loudest = Math.max(loudest, level)
      requestAnimationFrame(read)
    }
    read()
    sampling = setInterval(() => {
      heard = [...heard.slice(1), phase === 'recording' ? loudest : 0]
      loudest = 0
    }, 90)
  }
  let loudest = 0
  let sampling: ReturnType<typeof setInterval> | undefined

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
      heard = Array(BARS).fill(0)
    } else if (phase === 'paused') {
      recorder?.resume()
      since = performance.now()
      phase = 'recording'
    }
  }

  function quiet(): void {
    clearInterval(ticking)
    clearInterval(sampling)
    heard = Array(BARS).fill(0)
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
    document.title = mac ? title : `${title} · ${project.name}` // Windows' title bar is the system's, and says both
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

  // The shortcuts as the computer writes them (app/src/main/recording.ts registers them): the standard keys or the
  // person's own, read again when they are changed in Inställningar while the meeting goes on.
  const mac = window.api.platform === 'darwin'
  let chosen = $state<Shortcuts>({})
  const read = (): Promise<unknown> => window.api.settings().then((s) => (chosen = s.shortcuts)).catch(() => {})
  void read()
  $effect(() => window.api.onChanged(() => void read()))
  const keys = (c: Global): string => spell(accelerators(chosen, mac)[c], mac)
  let all = $state(false) // the whole agenda, for a heading that is not the next one

  // The window is as tall as what it shows: small while paused, taller with the agenda open.
  let root = $state<HTMLElement>()
  $effect(() => {
    if (!root) return
    const seen = new ResizeObserver(() => void window.api.recordFit(Math.ceil(root!.getBoundingClientRect().height)))
    seen.observe(root)
    return () => seen.disconnect()
  })
</script>

<div class="rec" bind:this={root}>
  <!-- The Mac's title bar is the window's own: the meeting over its project. Windows' is the system's. -->
  {#if mac}
    <div class="bar"><h1>{title}</h1><p>{project.name}</p></div>
  {:else}
    <h1 class="sr">{title}</h1>
  {/if}
  <div class="body">
    <header>
      <p class="timer" class:off={phase !== 'recording'} aria-live="off">{clock(elapsed)}</p>
      <div>
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
          {#each heard as h, i (i)}<i class:on={h > 0.03} style="height: {h > 0.03 ? Math.round(5 + h * 15) : phase === 'recording' ? 6 : 4}px"></i>{/each}
        </div>
      </div>
    </header>

    {#if problem}
      <div class="note bad" role="alert"><Icon name="alert" size={16} /><p>{problem}</p></div>
    {/if}

    {#if phase === 'paused'}
      <!-- Paused: the clock stands still, and going on is the one clear thing to do. -->
      <p class="muted still">{heading ? `${heading.no}. ${heading.name}. ` : ''}Inget spelas in just nu.</p>
      <div class="foot">
        <button class="btn primary" onclick={pause}><span class="go"></span>Fortsätt<kbd>{keys('pause')}</kbd></button>
        <button class="btn" onclick={finish}>Avsluta mötet{#if mac}<kbd>⇧⌘R</kbd>{/if}</button>
      </div>
    {:else}
      {#if withAgenda}
        <section class="now" aria-labelledby="agenda">
          <h2 id="agenda" class="sr">Dagordning</h2>
          {#if agenda}
            <p class="lbl">
              <span>{heading ? `Rubrik ${agenda.headings.indexOf(heading) + 1} av ${agenda.headings.length}` : count(agenda.headings.length, 'rubrik', 'rubriker')}</span>
              <button class="quiet" aria-expanded={all} onclick={() => (all = !all)}>{all ? 'Dölj rubrikerna' : 'Alla rubriker'}</button>
            </p>
            <p class="cur">{#if !heading}<span class="muted">Ingen rubrik än</span>{/if}{#if heading}<strong>{heading.no}. {heading.name}</strong>{#if at(heading.no) !== undefined}<span class="muted">sedan {clock(at(heading.no)!)}</span>{/if}{/if}</p>
            {#if next}
              <button class="next" disabled={phase === 'saving' || phase === 'idle'} onclick={() => press(next.no)}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 2.5v8M4.5 7.5 8 11l3.5-3.5M3.5 13.5h9" /></svg>
                <span class="grow">Nästa rubrik: {next.no}. {next.name}</span><kbd>{keys('next')}</kbd>
              </button>
            {/if}
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
          {#each MARKS as kind (kind)}
            <button class="mark" disabled={phase !== 'recording'} onclick={() => mark(kind)}><span>{KINDS[kind]}</span><kbd>{keys(kind)}</kbd></button>
          {/each}
        </div>
        {#if marks.length}
          <ul class="marked">
            {#each marks.slice(-3).reverse() as m (m.at + m.kind)}
              <li>
                <span class="t">{clock(m.at)}</span>
                <span class="grow">{KINDS[m.kind]}</span>
                <button class="quiet" aria-label="Ta bort märket {KINDS[m.kind]} vid {clock(m.at)}" onclick={() => marks.splice(marks.indexOf(m), 1)}>Ta bort</button>
              </li>
            {/each}
          </ul>
        {/if}
      </section>

      {#if phase === 'idle'}
        <div class="foot">
          <button class="btn primary" onclick={begin}><Icon name="mic" size={16} /> {problem ? 'Försök igen' : 'Börja spela in'}</button>
          <button class="btn" onclick={leave}>Stäng</button>
        </div>
      {:else}
        <div class="foot">
          <button class="btn" disabled={phase === 'saving'} onclick={pause}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true"><rect x="2.5" y="1.5" width="2.5" height="9" rx="0.5" /><rect x="7" y="1.5" width="2.5" height="9" rx="0.5" /></svg>
            Pausa{#if mac}<kbd>{keys('pause')}</kbd>{/if}
          </button>
          <button class="btn primary" disabled={phase === 'saving'} onclick={finish}>Avsluta mötet{#if mac}<kbd>⇧⌘R</kbd>{/if}</button>
        </div>
        <p class="last"><button class="quiet" disabled={phase === 'saving'} onclick={leave}>Avbryt inspelningen…</button></p>
      {/if}
    {/if}
  </div>
</div>

<style>
  /* The measures are the drawing's, per computer. */
  .rec { --rule: #e4e3e9; --soft: #efeef3; display: flex; flex-direction: column; background: var(--win-bg); }
  .bar { flex: none; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 44px; padding: 0 76px; background: #ecebf0; border-bottom: 1px solid var(--rule); line-height: 1.2; white-space: nowrap; -webkit-app-region: drag; }
  .bar h1 { max-width: 100%; overflow: hidden; text-overflow: ellipsis; font: 600 var(--ui)/1.2 var(--font-ui); letter-spacing: 0; }
  .bar p { max-width: 100%; overflow: hidden; text-overflow: ellipsis; font-size: 11px; color: var(--ink-500); }
  .body { display: flex; flex-direction: column; padding: 14px 16px 12px; border-top: 1px solid var(--rule); }
  :global(:root[data-platform='mac']) .body { border-top: 0; }
  header { display: flex; align-items: center; justify-content: space-between; height: 56px; }
  .timer { font: 600 52px/56px var(--font-ui); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
  :global(:root[data-platform='mac']) header { height: 58px; }
  :global(:root[data-platform='mac']) .timer { font-size: 54px; line-height: 58px; letter-spacing: -0.02em; }
  .timer.off { color: var(--ink-400); }
  .state { display: flex; align-items: center; justify-content: flex-end; gap: 7px; height: 20px; font-weight: 600; white-space: nowrap; }
  :global(:root[data-platform='mac']) .state { gap: 6px; height: 18px; }
  .live { width: 9px; height: 9px; border-radius: 50%; background: var(--coral-600); animation: pulse 1.6s ease-in-out infinite; }
  .live.paused { background: var(--warn); animation: none; }
  @keyframes pulse { 50% { opacity: 0.3; } }
  .level { display: flex; align-items: center; justify-content: flex-end; gap: 2px; height: 20px; margin-top: 6px; }
  .level i { width: 3px; border-radius: 2px; background: var(--ink-300); }
  .level i.on { background: var(--coral-600); }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .note { margin-top: 10px; }
  .still { height: 18px; margin-top: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .now { margin-top: 12px; padding: 10px; border: 1px solid var(--rule); border-radius: 6px; background: #fff; }
  :global(:root[data-platform='mac']) .now { border-radius: 8px; background: var(--sunken); }
  .lbl { display: flex; justify-content: space-between; height: 16px; font-size: var(--ui-small); line-height: 16px; color: var(--ink-500); }
  .cur { display: flex; align-items: baseline; gap: 8px; height: 26px; margin-top: 2px; white-space: nowrap; }
  .cur strong { font-size: 20px; line-height: 26px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; }
  :global(:root[data-platform='mac']) .cur strong { font-weight: 700; }
  .next { display: flex; align-items: center; gap: 10px; width: 100%; height: 44px; margin-top: 8px; padding: 0 10px 0 12px; border: 1px solid #b9b8c2; border-bottom-color: #8e8d99; border-radius: 4px; background: #fff; font-size: 15px; font-weight: 600; text-align: left; white-space: nowrap; }
  :global(:root[data-platform='mac']) .next { gap: 8px; border-bottom-color: #a3a2ae; border-radius: 8px; box-shadow: 0 1px 1px rgb(0 0 0 / 0.06); }
  .next svg { flex: none; color: var(--coral-700); }
  .next .grow { overflow: hidden; text-overflow: ellipsis; }
  .next:hover:not(:disabled), .mark:hover:not(:disabled) { border-color: var(--ink-500); }
  kbd { display: inline-flex; align-items: center; justify-content: center; flex: none; min-width: 20px; height: 20px; padding: 0 5px; border: 1px solid #d5d4dc; border-bottom-width: 2px; border-radius: 4px; background: #fff; font: 500 11px/1 var(--font-mono); color: var(--ink-700); white-space: nowrap; }
  .head { height: 18px; margin-top: 12px; font: 600 var(--ui-small)/18px var(--font-ui); letter-spacing: 0; color: var(--ink-500); }
  :global(:root[data-platform='mac']) .head { height: 16px; margin-top: 14px; line-height: 16px; }
  .marks { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 6px; }
  .mark { display: flex; align-items: center; justify-content: space-between; gap: 2px; height: 36px; padding: 0 6px 0 10px; border: 1px solid #cfced6; border-bottom-color: #b9b8c2; border-radius: 4px; background: #fff; font-weight: 600; white-space: nowrap; }
  .mark kbd, .next kbd { padding: 0 3px; }
  :global(:root[data-platform='mac']) .mark { padding: 0 8px 0 12px; border-radius: 6px; }
  :global(:root[data-platform='mac']) :is(.mark, .next) kbd { padding: 0 5px; }
  .quiet { padding: 0; border: 0; background: transparent; color: var(--ink-500); font-size: var(--ui-small); white-space: nowrap; }
  .quiet:hover:not(:disabled) { color: var(--coral-800); text-decoration: underline; }
  .marked { margin-top: 10px; border-bottom: 1px solid var(--soft); }
  :global(:root[data-platform='mac']) .marked { margin-top: 12px; }
  .marked li { display: flex; align-items: center; gap: 10px; height: 28px; border-top: 1px solid var(--soft); white-space: nowrap; }
  :global(:root[data-platform='mac']) .marked li { height: 26px; }
  .t { width: 42px; font: 500 12px var(--font-mono); color: var(--ink-700); }
  .headings { display: flex; flex-direction: column; gap: 1px; max-height: 180px; margin-top: 8px; overflow-y: auto; }
  .heading { display: flex; align-items: center; gap: 8px; width: 100%; min-height: 28px; padding: 2px 8px; border: 0; border-radius: var(--ctl-r); background: transparent; text-align: left; }
  .heading:hover:not(:disabled) { background: rgb(0 0 0 / 0.05); }
  .heading.current { background: var(--coral-100); font-weight: 600; }
  .no { flex: 0 0 18px; text-align: right; color: var(--ink-500); }
  .foot { display: flex; gap: 8px; margin-top: 12px; }
  .foot .btn { flex: 1 1 0; min-height: 32px; height: 32px; padding: 0 8px; }
  .go { width: 9px; height: 9px; border-radius: 50%; background: #fff; }
  .last { display: flex; justify-content: flex-end; height: 18px; margin-top: 8px; }
  :global(:root[data-platform='mac']) .last { height: 16px; }
</style>
