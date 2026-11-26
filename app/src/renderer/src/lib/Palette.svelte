<script lang="ts" module>
  /** Something the palette can do or open. `group` is its heading; `keys` its shortcut, as the computer writes it;
   * `off` why it cannot run now: it is then shown greyed with that, and not chosen. */
  export type Entry = { group: string; label: string; detail?: string; keys?: string; off?: string; run: () => void }
</script>

<script lang="ts">
  // Type a few letters to run a command or open a meeting, a point or a project: everything the window can do, from
  // the keyboard. What it lists is the window's (App.svelte), so nothing here can do what a button could not.
  let { entries }: { entries: Entry[] } = $props()

  let dialog = $state<HTMLDialogElement>()
  let query = $state('')
  let open = $state(false) // its rows are in the page only while it is
  let only = $state('') // one group alone: the commands with their keys (Kortkommandon), the projects (Byt projekt)
  let moved = $state<number | null>(null) // the row the arrows or the pointer chose; before that, the best one

  export function show(group = ''): void {
    query = ''
    only = group
    moved = null
    open = true
    dialog?.showModal()
  }

  // The rows that are not commands are as many as the project is big: a few of each, the rest by typing more.
  const FEW = 6
  const words = $derived(query.toLowerCase().split(/\s+/).filter(Boolean))
  const has = (text: string): boolean => words.every((w) => text.toLowerCase().includes(w))
  const found = $derived.by(() => {
    const seen = new Map<string, number>()
    return entries.filter((e) => {
      // Kortkommandon: everything that has keys, whichever heading it is under.
      if (only === 'Kommandon' ? !e.keys : only ? e.group !== only : false) return false
      if (!has(only ? e.label : `${e.label} ${e.detail ?? ''}`)) return false
      const n = (seen.get(e.group) ?? 0) + 1
      seen.set(e.group, n)
      return only || e.group === 'Kommandon' || n <= FEW
    })
  })
  // The row Enter takes: one whose own words are what was typed, before one that only says so beside them.
  const best = $derived.by(() => {
    const named = found.findIndex((e) => !e.off && words.length > 0 && has(e.label))
    return named >= 0 ? named : found.findIndex((e) => !e.off)
  })
  const at = $derived(moved !== null && found[moved] && !found[moved].off ? moved : best)

  function choose(e: Entry | undefined): void {
    if (!e || e.off) return
    dialog?.close()
    e.run()
  }

  function keys(e: KeyboardEvent): void {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const step = e.key === 'ArrowDown' ? 1 : -1
      let i = at
      for (let n = 0; n < found.length; n++) {
        i = (i + step + found.length) % found.length
        if (!found[i].off) break
      }
      if (found[i] && !found[i].off) moved = i
      document.getElementById(`palette-${i}`)?.scrollIntoView({ block: 'nearest' })
    } else if (e.key === 'Enter') {
      e.preventDefault()
      choose(found[at])
    }
  }
</script>

<dialog bind:this={dialog} aria-label="Kommandopalett" onclick={(e) => e.target === dialog && dialog?.close()} onclose={() => (open = false)}>
  <label class="ask">
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></svg>
    <input type="text" role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={at >= 0 ? `palette-${at}` : undefined}
      aria-label="Sök kommando, möte eller punkt" placeholder={only === 'Projekt' ? 'Byt projekt' : only ? 'Sök kommando' : 'Sök kommando, möte eller punkt'} autocomplete="off" spellcheck="false"
      bind:value={query} oninput={() => (moved = null)} onkeydown={keys} />
  </label>
  <ul id="palette-list" role="listbox" aria-label="Träffar">
    {#each open ? found : [] as e, i (e.group + e.label + (e.detail ?? ''))}
      {#if i === 0 || found[i - 1].group !== e.group}<li class="group" role="presentation">{e.group}</li>{/if}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <li id="palette-{i}" role="option" aria-selected={i === at} aria-disabled={e.off ? 'true' : undefined} class:at={i === at} class:off={e.off} onclick={() => choose(e)} onmousemove={() => !e.off && (moved = i)}>
        <span class="label">{e.label}</span>
        {#if e.off}<span class="why">{e.off}</span>{/if}
        <span class="sc" class:words={!e.keys}>{e.keys ?? e.detail ?? ''}</span>
      </li>
    {:else}
      {#if open}<li class="none">{only === 'Projekt' && !query ? 'Det finns inget annat projekt.' : 'Inget stämmer med det du skrev.'}</li>{/if}
    {/each}
  </ul>
  <p class="hint"><span><kbd>↑</kbd><kbd>↓</kbd>välj</span><span><kbd>⏎</kbd>{only === 'Kommandon' ? 'kör' : 'öppna'}</span><span><kbd>esc</kbd>stäng</span></p>
</dialog>

<style>
  dialog { --r: 4px; --at: rgb(0 0 0 / 0.06); width: min(620px, calc(100vw - 48px)); margin: 110px auto auto; padding: 0; border: 1px solid rgb(0 0 0 / 0.16); border-radius: 12px; background: #fbfafc; box-shadow: 0 20px 50px rgb(0 0 0 / 0.35); overflow: hidden; }
  :global(:root[data-platform='mac']) dialog { --r: 5px; --at: var(--coral-700); }
  dialog::backdrop { background: rgb(0 0 0 / 0.25); }
  .ask { display: flex; align-items: center; gap: 10px; height: 48px; padding: 0 16px; border-bottom: 1px solid #e4e3e9; color: var(--ink-500); }
  .ask input { flex: 1; min-width: 0; height: 100%; border: 0; outline: none; box-shadow: none; background: transparent; font-size: 15px; color: var(--ink-900); caret-color: var(--coral-700); }
  ul { max-height: min(430px, calc(100vh - 260px)); overflow-y: auto; margin: 0; padding: 5px; }
  li { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border-radius: var(--r); white-space: nowrap; }
  li.group { height: auto; padding: 8px 10px 2px; font-size: var(--ui-small); font-weight: 600; color: var(--ink-500); }
  li.group:first-child { padding-top: 4px; }
  li.none { color: var(--ink-500); }
  .label { flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  .why { flex: none; margin-left: 2px; font-size: var(--ui-small); color: var(--ink-400); }
  .sc { flex: none; max-width: 50%; margin-left: auto; padding-left: 16px; overflow: hidden; text-overflow: ellipsis; color: var(--ink-500); font-size: 12px; }
  :global(:root[data-platform='mac']) .sc { font-size: var(--ui); letter-spacing: 0.04em; }
  :global(:root[data-platform='mac']) .sc.words { letter-spacing: 0; }
  li.off .label, li.off .sc { color: var(--ink-300); }
  li.at { background: var(--at); }
  :global(:root[data-platform='mac']) li.at { color: #fff; }
  :global(:root[data-platform='mac']) li.at .sc { color: rgb(255 255 255 / 0.85); }
  .hint { display: flex; align-items: center; gap: 14px; height: 36px; padding: 0 14px; border-top: 1px solid #e4e3e9; background: var(--canvas); font-size: 12px; color: var(--ink-500); }
  .hint span { display: inline-flex; align-items: center; gap: 6px; }
  kbd { display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 20px; padding: 0 5px; border: 1px solid #d5d4dc; border-bottom-width: 2px; border-radius: 4px; background: #fff; font: 500 11px/1 var(--font-mono); color: var(--ink-700); }
</style>
