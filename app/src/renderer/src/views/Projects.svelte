<script lang="ts">
  // The projects of this computer, and who is at their meetings. Byggmöte needs no Stommen for this: a project made here
  // is this computer's own. One that came from Stommen is Stommen's, and its people and Roller are read here, not changed.
  import type { Project } from '../../../shared/types'
  import Icon from '../lib/Icon.svelte'
  import { failure } from '../lib/format'

  let { projects, chosen, refresh, choose, first }: {
    projects: Project[]
    chosen: string
    refresh: () => Promise<void>
    choose: (id: string) => void
    first: boolean
  } = $props()

  let name = $state('')
  let problem = $state('')
  let busy = $state(false)
  let renaming = $state<string | null>(null)
  let renamed = $state('')
  let removing = $state<string | null>(null)
  let who = $state<Record<string, { name: string; role: string }>>({})

  const draft = (id: string): { name: string; role: string } => who[id] ?? { name: '', role: '' }
  const typed = (id: string, field: 'name' | 'role', value: string): void => {
    who[id] = { ...draft(id), [field]: value }
  }

  async function act(fn: () => Promise<unknown>): Promise<boolean> {
    busy = true
    problem = ''
    try {
      await fn()
      await refresh()
      return true
    } catch (e) {
      problem = failure(e)
      return false
    } finally {
      busy = false
    }
  }

  async function add(e: SubmitEvent): Promise<void> {
    e.preventDefault()
    let id = ''
    if (await act(async () => (id = await window.api.projectAdd(name)))) {
      name = ''
      choose(id)
    }
  }

  async function rename(p: Project, e: SubmitEvent): Promise<void> {
    e.preventDefault()
    if (await act(() => window.api.projectRename(p.id, renamed))) renaming = null
  }

  async function remove(p: Project): Promise<void> {
    if (await act(() => window.api.projectDelete(p.id))) removing = null
  }

  async function addPerson(p: Project, e: SubmitEvent): Promise<void> {
    e.preventDefault()
    const d = draft(p.id)
    if (await act(() => window.api.personAdd(p.id, d.name, d.role))) who[p.id] = { name: '', role: '' }
  }
</script>

<div class="page">
  <div class="page-head">
    <div>
      <h1>Projekt</h1>
      <p class="muted">Projekten ligger på den här datorn. Varje projekt har sina möten och sina personer.</p>
    </div>
  </div>

  <div class="stack narrow">
    {#if problem}
      <div class="note bad" role="alert"><Icon name="alert" /><p>{problem}</p></div>
    {/if}

    <form class="card" onsubmit={add} aria-labelledby="new">
      <h2 id="new">{first ? 'Skapa ditt första projekt' : 'Nytt projekt'}</h2>
      {#if first}
        <p class="muted" style="margin-bottom: 12px">
          Ett projekt samlar mötena för ett bygge. Du kan spela in det första mötet direkt efteråt, och lägga till vilka som brukar vara med när du vill.
        </p>
      {/if}
      <label class="label" for="project-name">Projektets namn</label>
      <div class="row">
        <input id="project-name" class="field grow" type="text" required autocomplete="off" placeholder="Till exempel Kv. Eken" bind:value={name} />
        <button class="btn primary" type="submit" disabled={busy || !name.trim()}><Icon name="plus" /> Skapa projekt</button>
      </div>
    </form>

    {#each projects as p (p.id)}
      <section class="card" aria-labelledby="p-{p.id}">
        <div class="row head">
          {#if renaming === p.id}
            <form class="row grow" onsubmit={(e) => rename(p, e)}>
              <label class="label sr" for="rename-{p.id}">Nytt namn</label>
              <input id="rename-{p.id}" class="field grow" type="text" required bind:value={renamed} />
              <button class="btn primary" type="submit" disabled={busy || !renamed.trim()}>Spara</button>
              <button class="btn" type="button" onclick={() => (renaming = null)}>Avbryt</button>
            </form>
          {:else}
            <h2 id="p-{p.id}" class="grow">{p.name}</h2>
            {#if p.stommen}<span class="badge"><Icon name="link" size={14} /> Från Stommen</span>{/if}
            {#if p.id !== chosen}<button class="btn" onclick={() => choose(p.id)}>Öppna</button>{/if}
          {/if}
        </div>

        <h3 style="margin-top: 16px">Personer</h3>
        {#if p.people.length === 0}
          <p class="muted">Ingen är tillagd än. Det går bra att börja utan: namn sätts på de som talar efter mötet.</p>
        {:else}
          <ul class="people">
            {#each p.people as x (x.id)}
              <li class="row">
                <span class="grow">{x.name}{x.role ? `, ${x.role}` : ''}</span>
                {#if !p.stommen}
                  <button class="btn quiet" aria-label="Ta bort {x.name} från {p.name}" disabled={busy} onclick={() => act(() => window.api.personRemove(p.id, x.id))}>
                    <Icon name="trash" size={16} /> Ta bort
                  </button>
                {/if}
              </li>
            {/each}
          </ul>
        {/if}

        {#if p.stommen}
          <p class="small muted" style="margin-top: 12px">Personer och Roller kommer från Stommen. Ändra dem där, och hämta sedan projektet igen.</p>
        {:else}
          <form class="row add" onsubmit={(e) => addPerson(p, e)} aria-label="Lägg till person i {p.name}">
            <input class="field grow" type="text" required placeholder="Namn" aria-label="Namn" autocomplete="off" value={draft(p.id).name} oninput={(e) => typed(p.id, 'name', e.currentTarget.value)} />
            <input class="field grow" type="text" placeholder="Roll, till exempel Platschef" aria-label="Roll" autocomplete="off" list="roles-{p.id}" value={draft(p.id).role} oninput={(e) => typed(p.id, 'role', e.currentTarget.value)} />
            <datalist id="roles-{p.id}">{#each p.roles as r (r)}<option value={r}></option>{/each}</datalist>
            <button class="btn" type="submit" disabled={busy || !draft(p.id).name.trim()}><Icon name="plus" /> Lägg till</button>
          </form>

          <div class="row actions">
            {#if renaming !== p.id}
              <button class="btn quiet" onclick={() => { renaming = p.id; renamed = p.name }}><Icon name="edit" size={16} /> Byt namn</button>
            {/if}
            {#if removing === p.id}
              <span class="small">Projektet försvinner ur listan. Mötena ligger kvar i sin mapp.</span>
              <button class="btn primary" disabled={busy} onclick={() => remove(p)}>Ta bort projektet</button>
              <button class="btn" onclick={() => (removing = null)}>Avbryt</button>
            {:else}
              <button class="btn quiet" onclick={() => (removing = p.id)}><Icon name="trash" size={16} /> Ta bort projektet</button>
            {/if}
          </div>
        {/if}
      </section>
    {/each}
  </div>
</div>

<style>
  .narrow { max-width: 680px; }
  .head { margin-bottom: 4px; }
  .people li { min-height: 44px; border-bottom: 1px solid var(--line); }
  .people li:last-child { border-bottom: 0; }
  .add { margin-top: 12px; align-items: stretch; }
  .add .field { min-width: 140px; }
  .actions { margin-top: 16px; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
