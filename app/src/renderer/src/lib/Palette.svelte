<script lang="ts" module>
  /** Something the palette can do or open. `group` is its heading; `keys` its shortcut, as the computer writes it. */
  export type Entry = { group: string; label: string; detail?: string; keys?: string; run: () => void }
</script>

<script lang="ts">
  // Type a few letters to run a command or open a meeting, a point or a project: everything the window can do, from
  // the keyboard. What it lists is the window's (App.svelte), so nothing here can do what a button could not.
  import Icon from './Icon.svelte'

  let { entries }: { entries: Entry[] } = $props()

  let dialog = $state<HTMLDialogElement>()
  let query = $state('')
  let at = $state(0)

  export function show(): void {
    query = ''
    at = 0
    dialog?.showModal()
  }

  const found = $derived.by(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean)
    return entries.filter((e) => words.every((w) => `${e.label} ${e.detail ?? ''} ${e.group}`.toLowerCase().includes(w))).slice(0, 14)
  })

  function choose(e: Entry | undefined): void {
    if (!e) return
    dialog?.close()
    e.run()
  }

  function keys(e: KeyboardEvent): void {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      at = (at + (e.key === 'ArrowDown' ? 1 : -1) + found.length) % Math.max(1, found.length)
      document.getElementById(`palette-${at}`)?.scrollIntoView({ block: 'nearest' })
    } else if (e.key === 'Enter') {
      e.preventDefault()
      choose(found[at])
    }
  }
</script>

<dialog bind:this={dialog} aria-label="Kommandopalett" onclick={(e) => e.target === dialog && dialog?.close()}>
  <label class="ask">
    <Icon name="search" size={16} />
    <input type="text" role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={found.length ? `palette-${at}` : undefined}
      aria-label="Sök kommando, möte eller punkt" placeholder="Sök kommando, möte eller punkt" autocomplete="off" spellcheck="false"
      bind:value={query} oninput={() => (at = 0)} onkeydown={keys} />
  </label>
  <ul id="palette-list" role="listbox" aria-label="Träffar">
    {#each found as e, i (e.group + e.label + (e.detail ?? ''))}
      {#if i === 0 || found[i - 1].group !== e.group}<li class="group" role="presentation">{e.group}</li>{/if}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <li id="palette-{i}" role="option" aria-selected={i === at} class:at={i === at} onclick={() => choose(e)} onmousemove={() => (at = i)}>
        <span class="label">{e.label}</span>
        {#if e.detail}<span class="detail">{e.detail}</span>{/if}
        {#if e.keys}<span class="keys">{e.keys}</span>{/if}
      </li>
    {:else}
      <li class="none">Inget stämmer med det du skrev.</li>
    {/each}
  </ul>
  <p class="hint"><kbd>↑</kbd><kbd>↓</kbd> välj <kbd>⏎</kbd> öppna <kbd>esc</kbd> stäng</p>
</dialog>

<style>
  dialog { width: min(620px, calc(100vw - 48px)); margin: 12vh auto auto; padding: 0; border: 1px solid rgb(0 0 0 / 0.18); border-radius: 12px; background: var(--surface); box-shadow: 0 24px 60px rgb(0 0 0 / 0.35); overflow: hidden; }
  dialog::backdrop { background: rgb(0 0 0 / 0.25); }
  .ask { display: flex; align-items: center; gap: 10px; height: 48px; padding: 0 16px; border-bottom: 1px solid var(--line); color: var(--ink-500); }
  .ask input { flex: 1; min-width: 0; height: 100%; border: 0; outline: none; box-shadow: none; background: transparent; font-size: calc(var(--ui) + 3px); color: var(--ink-900); }
  ul { max-height: 46vh; overflow-y: auto; margin: 0; padding: 6px; }
  li { display: flex; align-items: baseline; gap: 10px; min-height: 32px; padding: 6px 10px; border-radius: 6px; }
  li.group { min-height: 0; padding: 8px 10px 2px; font-size: var(--ui-small); font-weight: 600; color: var(--ink-500); }
  li.none { color: var(--ink-500); }
  li.at { background: var(--coral-700); color: #fff; }
  .label { flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .detail { flex: 1 1 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--ui-small); color: var(--ink-500); }
  .keys { margin-left: auto; flex: none; font-size: var(--ui-small); color: var(--ink-500); letter-spacing: 0.04em; }
  li.at .detail, li.at .keys { color: rgb(255 255 255 / 0.85); }
  .hint { display: flex; align-items: center; gap: 6px; height: 32px; padding: 0 14px; border-top: 1px solid var(--line); background: var(--canvas); font-size: var(--ui-small); color: var(--ink-500); }
  kbd { padding: 0 5px; border: 1px solid var(--edge); border-bottom-width: 2px; border-radius: 4px; background: var(--surface); font: 500 11px var(--font-mono); color: var(--ink-700); }
  kbd + kbd { margin-left: -2px; }
</style>
