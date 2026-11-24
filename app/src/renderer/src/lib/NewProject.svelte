<script lang="ts">
  // Names a project and makes it. Used in the dialog the project select opens, and on its own before the first project.
  import Icon from './Icon.svelte'
  import { failure } from './format'

  let { created, cancel }: { created: (id: string) => Promise<void> | void; cancel?: () => void } = $props()

  let name = $state('')
  let problem = $state('')
  let busy = $state(false)

  async function add(e: SubmitEvent): Promise<void> {
    e.preventDefault()
    busy = true
    problem = ''
    try {
      const id = await window.api.projectAdd(name)
      name = ''
      await created(id)
    } catch (err) {
      problem = failure(err)
    } finally {
      busy = false
    }
  }
</script>

<form onsubmit={add}>
  {#if problem}
    <div class="note bad" role="alert" style="margin-bottom: 12px"><Icon name="alert" /><p>{problem}</p></div>
  {/if}
  <label class="label" for="project-name">Projektets namn</label>
  <!-- svelte-ignore a11y_autofocus -->
  <input id="project-name" class="field" type="text" required autofocus autocomplete="off" placeholder="Till exempel Kv. Eken" bind:value={name} />
  <div class="row buttons">
    {#if cancel}<button class="btn" type="button" onclick={cancel}>Avbryt</button>{/if}
    <button class="btn primary" type="submit" disabled={busy || !name.trim()}><Icon name="plus" /> Skapa projekt</button>
  </div>
</form>

<style>
  .field { width: 100%; }
  .buttons { margin-top: 20px; justify-content: flex-end; }
</style>
