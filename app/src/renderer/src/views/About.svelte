<script lang="ts">
  // Om Byggmöte on the Mac, from the app menu: what the app does and what it is made of. On Windows the same is a
  // page of Inställningar (views/Settings.svelte).
  import type { ModelRow } from '../../../shared/types'
  import Glyph from '../lib/Glyph.svelte'
  import '../settings.css'

  let { version }: { version: string } = $props()

  let models = $state<ModelRow[] | null>(null)
  void window.api.models().then((m) => (models = m)).catch(() => (models = []))
  document.title = 'Om Byggmöte'
</script>

<div class="prefs mac about">
  <span class="tile"><Glyph name="wave" size={38} width={1.6} /></span>
  <h1>Byggmöte</h1>
  {#if version}<p class="d">Version {version}</p>{/if}
  <p class="what">Spelar in byggmöten, skriver utskriften och protokollet på den här datorn, och skickar det du godkänner vidare till Stommen.</p>
  <h2>Modeller</h2>
  {#if models}
    <ul>
      {#each models as m (m.id)}
        <li><span>{m.name}</span><span class="d">{m.license}</span></li>
      {/each}
    </ul>
  {:else}
    <p class="d">Läser in.</p>
  {/if}
  <p class="d">Villkoren i sin helhet finns i NOTICE.md i appens mapp.</p>
</div>

<style>
  .about { min-height: 100%; align-items: center; gap: 6px; padding: 26px 28px 22px; text-align: center; }
  .tile { flex: none; width: 64px; height: 64px; border-radius: 15px; background: var(--coral-700); color: #fff; display: grid; place-items: center; margin-bottom: 6px; }
  h1 { font: 700 15px/1.3 var(--font-ui); letter-spacing: 0; }
  .what { max-width: 340px; margin: 8px 0 10px; }
  h2 { align-self: stretch; text-align: left; font-size: 11px; color: var(--ink-500); }
  ul { align-self: stretch; margin-bottom: 8px; border-top: 1px solid var(--line); }
  li { display: flex; justify-content: space-between; gap: 16px; padding: 5px 0; border-bottom: 1px solid var(--line); text-align: left; }
  li .d { text-align: right; }
</style>
