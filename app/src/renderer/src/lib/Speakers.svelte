<script lang="ts">
  // The speakers the recording could not put a name to, in a sheet over the protocol: a line of each to listen to, and
  // the project's people to choose among. A project of this computer's own takes a new person on the spot.
  import type { Line, Project } from '../../../shared/types'
  import Icon from './Icon.svelte'
  import { clock, failure } from './format'

  type Props = {
    project: Project
    unnamed: { id: string; name: string }[]
    lines: Line[]
    listen: (at: number, line: number) => void
    name: (speaker: string, personId: string) => Promise<void>
    /** Adds the typed name to the Projekt and names the speaker with it. */
    add: (speaker: string, typed: string) => Promise<void>
  }
  let { project, unnamed, lines, listen, name, add }: Props = $props()

  let dialog = $state<HTMLDialogElement>()
  let naming = $state<Record<string, string>>({})
  let finding = $state<Record<string, string>>({}) // what is typed in a speaker's search
  let open = $state<string | null>(null) // the speaker whose list is showing
  let problem = $state('')

  export function show(): void {
    problem = ''
    dialog?.showModal()
  }
  // With the last name set there is nothing left to ask.
  $effect(() => {
    if (!unnamed.length) dialog?.close()
  })

  /** People in the Projekt that match what is typed, by name or Roll. */
  function matches(speaker: string): Project['people'] {
    const q = (finding[speaker] ?? '').trim().toLowerCase()
    return project.people.filter((x) => !q || `${x.name} ${x.role ?? ''}`.toLowerCase().includes(q))
  }

  /** Whether what is typed is a new person, which a Projekt of our own can add on the spot. */
  function addable(speaker: string): boolean {
    const q = (finding[speaker] ?? '').trim().toLowerCase()
    return Boolean(q) && !project.stommen && !project.people.some((x) => x.name.toLowerCase() === q)
  }

  function pick(speaker: string, id: string, label: string): void {
    naming[speaker] = id
    finding[speaker] = label
    open = null
  }

  async function run(what: Promise<void>): Promise<void> {
    problem = ''
    open = null
    try {
      await what
    } catch (e) {
      problem = failure(e)
    }
  }
</script>

<dialog bind:this={dialog} aria-labelledby="speakers-title">
  <h2 id="speakers-title">Sätt namn på talare</h2>
  <p class="muted lead">
    {unnamed.length === 1 ? 'En talare har inget namn.' : `${unnamed.length} talare har inget namn.`}
    Lyssna på en rad och välj vem det är. Namnen styr vilka som står som närvarande, och med vilken Roll.
  </p>
  {#if problem}<p class="bad" role="alert">{problem}</p>{/if}
  <ul>
    {#each unnamed as s (s.id)}
      {@const first = lines.find((l) => l.speaker === s.id)}
      <li>
        {#if first}
          <button class="play" aria-label="Lyssna på {s.name} från {clock(first.at)}" onclick={() => listen(first.at, first.id)}>
            <svg width="10" height="10" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true"><path d="M3 1.5v9l7.5-4.5z" /></svg>
          </button>
        {/if}
        <div class="who">
          <p><strong>{s.name}</strong>{#if first}<span class="chip">{clock(first.at)}</span>{/if}</p>
          {#if first}<p class="said">”{first.text}”</p>{/if}
        </div>
        <div class="combo">
          <input
            class="field"
            type="text"
            role="combobox"
            aria-label="Vem är {s.name}?"
            aria-expanded={open === s.id}
            aria-controls="who-{s.id}"
            autocomplete="off"
            placeholder="Sök eller skriv ett namn"
            value={finding[s.id] ?? ''}
            onfocus={() => (open = s.id)}
            onblur={() => setTimeout(() => open === s.id && (open = null), 150)}
            oninput={(e) => {
              finding[s.id] = e.currentTarget.value
              naming[s.id] = ''
              open = s.id
            }}
          />
          {#if open === s.id}
            <ul class="options" id="who-{s.id}" role="listbox">
              {#each matches(s.id) as person (person.id)}
                <li role="option" aria-selected={naming[s.id] === person.id}>
                  <button type="button" onmousedown={(e) => e.preventDefault()} onclick={() => pick(s.id, person.id, person.name)}>
                    {person.name}{person.role ? `, ${person.role}` : ''}
                  </button>
                </li>
              {/each}
              {#if addable(s.id)}
                <li role="option" aria-selected="false">
                  <button type="button" class="add" onmousedown={(e) => e.preventDefault()} onclick={() => run(add(s.id, (finding[s.id] ?? '').trim()))}>
                    <Icon name="plus" size={14} /> Lägg till ”{(finding[s.id] ?? '').trim()}”
                  </button>
                </li>
              {:else if !matches(s.id).length}
                <li class="none">{project.stommen ? 'Ingen med det namnet. Personer läggs till i Stommen.' : 'Skriv ett namn för att lägga till.'}</li>
              {/if}
            </ul>
          {/if}
        </div>
        <button class="btn" disabled={!naming[s.id]} onclick={() => run(name(s.id, naming[s.id]))}>Sätt namn</button>
      </li>
    {/each}
  </ul>
  <div class="foot"><button class="btn" onclick={() => dialog?.close()}>Klar</button></div>
</dialog>

<style>
  /* A sheet: on the Mac it hangs from the toolbar, on Windows it is a dialog in the middle of the window. */
  dialog { width: min(620px, calc(100vw - 32px)); max-height: calc(100vh - 96px); margin: auto; padding: 16px 18px 14px; border: 1px solid rgb(0 0 0 / 0.16); border-radius: 8px; background: var(--surface); box-shadow: 0 10px 30px rgb(0 0 0 / 0.22); overflow: visible; }
  :global(:root[data-platform='mac']) dialog { margin-top: var(--bar-h); border-top: 0; border-radius: 0 0 10px 10px; }
  dialog::backdrop { background: rgb(0 0 0 / 0.2); }
  h2 { font: 600 var(--ui)/1.4 var(--font-ui); letter-spacing: 0; }
  .lead { margin: 2px 0 10px; font-size: var(--ui-small); }
  .bad { margin-bottom: 8px; padding: 6px 10px; border-radius: var(--ctl-r); background: var(--bad-bg); font-size: var(--ui-small); }
  dialog > ul > li { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-top: 1px solid var(--line); }
  .play { flex: none; display: inline-grid; place-items: center; width: 28px; height: 28px; border: 0; border-radius: var(--ctl-r); background: rgb(0 0 0 / 0.06); color: var(--ink-900); }
  .play:hover { background: rgb(0 0 0 / 0.1); }
  .who { flex: 1 1 auto; min-width: 0; }
  .who p:first-child { display: flex; align-items: center; gap: 6px; }
  .chip { display: inline-flex; align-items: center; height: 18px; padding: 0 6px; border-radius: 9px; background: var(--sunken); font: 500 11px var(--font-mono); color: var(--ink-700); }
  :global(:root[data-platform='win']) .chip { border-radius: 4px; }
  .said { font-size: var(--ui-small); color: var(--ink-500); display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .combo { position: relative; flex: none; width: 260px; }
  .combo .field { width: 100%; }
  .options { position: absolute; z-index: 20; top: calc(100% + 4px); left: 0; right: 0; max-height: 220px; overflow: auto; padding: 5px; background: rgb(250 249 252 / 0.98); border: 1px solid rgb(0 0 0 / 0.16); border-radius: 8px; box-shadow: 0 10px 30px rgb(0 0 0 / 0.22); }
  .options button { display: flex; align-items: center; gap: 6px; width: 100%; min-height: var(--ctl-h); padding: 0 10px; border: 0; border-radius: var(--ctl-r); background: none; text-align: left; }
  .options button:hover, .options button:focus-visible { background: rgb(0 0 0 / 0.06); }
  .options .add { font-weight: 500; }
  .options .none { padding: 8px 10px; font-size: var(--ui-small); color: var(--ink-500); }
  .foot { display: flex; justify-content: flex-end; padding-top: 12px; border-top: 1px solid var(--line); }
</style>
