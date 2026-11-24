<script lang="ts">
  // Which microphone a meeting is recorded with. The computer asks for permission the first time one is listed, so the
  // person meets that question here and not in the middle of a meeting.
  import Icon from './Icon.svelte'

  let { value, choose }: { value: string; choose: (deviceId: string) => void } = $props()

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

{#if access === 'ready'}
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
