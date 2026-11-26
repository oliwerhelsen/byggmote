<script lang="ts">
  // The recording's shortcuts, with their keys as the computer writes them. A click on one that works in any program
  // takes the next combination pressed as its keys; the main process says no to one that cannot be used.
  import { accelerators, caps, FIXED } from '../../../shared/keys'
  import type { Settings } from '../../../shared/types'
  import Glyph from './Glyph.svelte'
  import { failure } from './format'

  let { settings, changed }: { settings: Settings; changed: (s: Settings) => void } = $props()

  const mac = window.api.platform === 'darwin'
  type Own = 'pause' | 'next' | 'mark'

  const keys = $derived(accelerators(settings.shortcuts, mac))
  // In the order of a meeting. The two without `own` are the application menu's, and stay as they are.
  const rows = $derived<{ name: string; keys: string[]; own?: Own }[]>([
    { name: 'Spela in möte', keys: [FIXED.record] },
    { name: 'Pausa', keys: [keys.pause], own: 'pause' },
    { name: 'Avsluta mötet', keys: [FIXED.finish] },
    { name: 'Nästa rubrik', keys: [keys.next], own: 'next' },
    { name: 'Sätt märke', keys: [keys.decision, keys.question], own: 'mark' }
  ])
  const own = $derived(Object.keys(settings.shortcuts).length > 0)

  let open = $state(true)
  let listening = $state<Own | ''>('')
  let problem = $state('')

  async function keep(shortcuts: Settings['shortcuts']): Promise<void> {
    problem = ''
    try {
      changed(await window.api.settingsSet({ shortcuts }))
    } catch (e) {
      problem = failure(e)
    }
  }

  function listen(to: Own | ''): void {
    if (to) problem = ''
    listening = to
    void window.api.shortcutListen(Boolean(to))
  }

  // The key by where it sits, not by what it types: Alt with a letter types another character on a Mac.
  function pressed(e: KeyboardEvent): void {
    if (!listening || ['Control', 'Alt', 'Shift', 'Meta', 'AltGraph'].includes(e.key)) return
    const plain = !e.ctrlKey && !e.altKey && !e.metaKey
    if (e.key === 'Tab' && plain) return listen('') // on to the next control, as Tab does
    e.preventDefault()
    e.stopPropagation()
    if (e.key === 'Escape' && plain) return listen('')
    const key = /^Key[A-Z]$/.test(e.code) ? e.code.slice(3) : /^(Digit|Numpad)\d$/.test(e.code) ? e.code.slice(-1) : e.key.length === 1 ? e.key.toUpperCase() : e.key
    const to = listening
    listen('')
    void keep({ [to]: [e.ctrlKey && 'Control', e.altKey && 'Alt', e.shiftKey && 'Shift', e.metaKey && mac && 'Command', key].filter(Boolean).join('+') })
  }
  $effect(() => () => void window.api.shortcutListen(false))
</script>

<svelte:window onkeydowncapture={pressed} />

{#snippet drawn(r: (typeof rows)[number])}
  <span class="name">{r.name}</span>
  {#if listening && listening === r.own}
    <span class="d">Tryck nya tangenter</span>
  {:else if mac}
    <span class="keys">{#each r.keys as k, i (i)}{#if i}<span class="d">…</span>{/if}<span class="kbd">{caps(k, mac)[0]}</span>{/each}</span>
  {:else}
    {#each r.keys as k, i (i)}{#if i}<span class="plus">…</span>{/if}{#each caps(k, mac) as c, j (j)}{#if j}<span class="plus">+</span>{/if}<span class="kbd">{c}</span>{/each}{/each}
  {/if}
{/snippet}

{#snippet list()}
  {#each rows as r (r.name)}
    {#if r.own}
      <button class="sc-row" aria-label="{r.name}, byt tangenter" aria-pressed={listening === r.own} onclick={() => listen(listening === r.own ? '' : r.own!)} onblur={() => listening === r.own && listen('')}>{@render drawn(r)}</button>
    {:else}
      <div class="sc-row">{@render drawn(r)}</div>
    {/if}
  {/each}
  {#if problem}<p class="sc-row hint d bad-text" role="alert">{problem}</p>{/if}
  <div class="sc-row hint d">
    <span class="name">Fungerar även när ett annat program ligger överst. Klicka på ett kommando för att byta tangenter.</span>
    {#if own}<button class="back" onclick={() => keep({ pause: '', next: '', mark: '' })}>Återställ standard</button>{/if}
  </div>
{/snippet}

{#if mac}
  <span class="lbl">Kortkommandon:</span>
  <div class="val"><div class="sc">{@render list()}</div></div>
{:else}
  <div class="exp">
    <button class="srow" aria-expanded={open} onclick={() => (open = !open)}>
      <span class="ic"><Glyph name="keyboard" /></span>
      <span class="tx"><span class="t">Kortkommandon</span><span class="d">Under inspelning</span></span>
      <span class="ctl muted"><Glyph name={open ? 'up' : 'down'} size={12} /></span>
    </button>
    {#if open}{@render list()}{/if}
  </div>
{/if}

<style>
  /* The Mac's list: the names in one column, the keys in the next, a line each. */
  .sc { display: grid; grid-template-columns: 1fr auto; row-gap: 8px; align-items: center; width: 100%; max-width: 360px; padding: 4px 40px 0 0; }
  .sc .sc-row { grid-column: 1 / -1; display: grid; grid-template-columns: subgrid; align-items: center; padding: 0; border: 0; background: transparent; text-align: left; }
  .sc .sc-row.hint { display: block; padding-top: 2px; }
  .sc button.sc-row:hover :global(.kbd) { border-color: var(--ink-400); }
  .back { margin-left: 8px; padding: 0; border: 0; background: transparent; color: var(--coral-700); font: inherit; white-space: nowrap; }
  .back:hover { text-decoration: underline; }
  button.srow { font: inherit; color: inherit; }
</style>
