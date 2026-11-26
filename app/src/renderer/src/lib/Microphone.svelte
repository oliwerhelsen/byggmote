<script lang="ts">
  // Which microphone a meeting is recorded with. The computer asks for permission the first time one is listed, so the
  // person meets that question here and not in the middle of a meeting.
  import Icon from './Icon.svelte'

  // `bare`: in Inställningar, where the setting's name stands beside it and the level the microphone hears is shown.
  let { value, choose, bare = false }: { value: string; choose: (deviceId: string) => void; bare?: boolean } = $props()

  // The level as a row of bars, lit from the left as far as the sound reaches.
  const BARS = [6, 10, 14, 8, 16, 12, 18, 10, 14, 8, 12, 16, 6, 10, 8, 6, 8, 6, 10, 6, 8, 6, 6, 8]
  let level = $state(0)

  // Listened to only while this is shown, with the microphone that is chosen; nothing is recorded or kept.
  $effect(() => {
    if (!bare || access !== 'ready') return
    const wanted = value
    let stream: MediaStream | undefined
    let context: AudioContext | undefined
    let gone = false
    void navigator.mediaDevices
      .getUserMedia({ audio: wanted ? { deviceId: { exact: wanted } } : true })
      .catch(() => navigator.mediaDevices.getUserMedia({ audio: true })) // unplugged: the computer's own, as a recording does
      .then((s) => {
        if (gone) return s.getTracks().forEach((t) => t.stop())
        stream = s
        context = new AudioContext()
        void context.resume()
        const analyser = context.createAnalyser()
        analyser.fftSize = 1024
        context.createMediaStreamSource(s).connect(analyser)
        const buffer = new Float32Array(analyser.fftSize)
        const read = (): void => {
          if (gone) return
          analyser.getFloatTimeDomainData(buffer)
          level = Math.min(1, Math.sqrt(buffer.reduce((sum, v) => sum + v * v, 0) / buffer.length) * 6)
          requestAnimationFrame(read)
        }
        read()
      })
      .catch(() => {})
    return () => {
      gone = true
      stream?.getTracks().forEach((t) => t.stop())
      void context?.close()
      level = 0
    }
  })

  let devices = $state<MediaDeviceInfo[]>([])
  let access = $state<'unasked' | 'ready' | 'refused'>('unasked')

  async function list(): Promise<void> {
    devices = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'audioinput' && d.deviceId)
  }

  async function allow(): Promise<void> {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true })
      s.getTracks().forEach((t) => t.stop())
      access = 'ready'
      await list()
    } catch {
      access = 'refused'
    }
  }

  // Already allowed: the devices have names, and nothing is asked.
  $effect(() => {
    void navigator.permissions
      ?.query({ name: 'microphone' as PermissionName })
      .then(async (p) => {
        if (p.state === 'granted') {
          access = 'ready'
          await list()
        } else if (p.state === 'denied') access = 'refused'
      })
      .catch(() => {})
  })
</script>

{#if bare}
  <div class="mic">
    {#if access === 'ready'}
      <div class="mic-line">
        <select id="mic" class="field" aria-label="Mikrofon" title="Är den inte inkopplad används datorns egen. Datorns ljud spelas inte in." {value} onchange={(e) => choose(e.currentTarget.value)}>
          <option value="">Datorns val</option>
          {#each devices as d (d.deviceId)}
            <option value={d.deviceId}>{d.label || 'Mikrofon'}</option>
          {/each}
        </select>
        <span class="badge ok"><span class="dot ok"></span>Tillåten</span>
      </div>
      <div class="meter" role="meter" aria-label="Mikrofonens nivå" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(level * 100)}>
        {#each BARS as h, i (i)}<i class:on={i < Math.round(level * BARS.length)} style="height: {h}px"></i>{/each}
      </div>
    {:else if access === 'refused'}
      <div class="mic-line"><span class="badge bad"><span class="dot bad"></span>Inte tillåten</span></div>
      <p class="d" role="alert">Byggmöte får inte använda mikrofonen. Tillåt den för Byggmöte i datorns inställningar, under Integritet och säkerhet, och öppna sedan det här igen.</p>
    {:else}
      <div class="mic-line"><button class="btn" onclick={allow}>Tillåt mikrofonen</button></div>
      <p class="d">Datorn frågar en gång. Ljudet lämnar aldrig datorn.</p>
    {/if}
  </div>
{:else if access === 'ready'}
  <div class="row">
    <label class="label" for="mic" style="margin: 0">Mikrofon</label>
    <select id="mic" class="field" {value} onchange={(e) => choose(e.currentTarget.value)}>
      <option value="">Datorns val</option>
      {#each devices as d (d.deviceId)}
        <option value={d.deviceId}>{d.label || 'Mikrofon'}</option>
      {/each}
    </select>
    <span class="badge ok"><Icon name="check" size={14} /> Tillåten</span>
  </div>
{:else if access === 'refused'}
  <div class="note warn" role="alert">
    <Icon name="alert" />
    <p>Byggmöte får inte använda mikrofonen. Tillåt den för Byggmöte i datorns inställningar, under Integritet och säkerhet, och öppna sedan det här igen.</p>
  </div>
{:else}
  <div class="row">
    <button class="btn" onclick={allow}><Icon name="mic" /> Tillåt mikrofonen</button>
    <span class="small muted">Datorn frågar en gång. Ljudet lämnar aldrig datorn.</span>
  </div>
{/if}
