<script lang="ts">
  // The speakers the recording could not put a name to, in a sheet over the protocol: a line of each to listen to, a
  // voice that sounds like someone from an earlier meeting as a name to click, the project's people as names to click,
  // and a name written with Enter to save. The engine makes a person of a name nobody in the project has.
  import { tick } from 'svelte'
  import type { Line, MeetingDetail, Project } from '../../../shared/types'
  import Icon from './Icon.svelte'
  import { clock, failure } from './format'

  type Speaker = MeetingDetail['speakers'][number]
  type Props = {
    project: Project
    unnamed: Speaker[]
    lines: Line[]
    /** The speakers of the meeting, to tell the ones already heard from the rest of the project. */
    speakers: Speaker[]
    listen: (at: number, line: number) => void
    name: (speaker: string, who: { person: string } | { name: string }) => Promise<void>
  }
  let { project, unnamed, lines, speakers, listen, name }: Props = $props()

  const SHOWN = 8 // names before "N till": a Projekt from Stommen can have many Kontakter

  let dialog = $state<HTMLDialogElement>()
  let typed = $state<Record<string, string>>({}) // the name written for a speaker
  let everyone = $state<Record<string, boolean>>({}) // a speaker whose list shows the whole project
  let busy = $state<string | null>(null) // the speaker being named
  let problem = $state('')

  export function show(): void {
    problem = ''
    dialog?.showModal()
  }
  // With the last name set there is nothing left to ask.
  $effect(() => {
    if (!unnamed.length) dialog?.close()
  })

  /** What is written for a speaker, its spaces tidied. */
  const written = (s: Speaker): string => (typed[s.id] ?? '').split(/\s+/).filter(Boolean).join(' ')
  const fits = (s: Speaker, x: { name: string; role?: string }): boolean => `${x.name} ${x.role ?? ''}`.toLowerCase().includes(written(s).toLowerCase())

  /** The person offered with just the written name: one of the project's, or who the voice sounds like. */
  function same(s: Speaker): string | null {
    const t = written(s).toLowerCase()
    if (!t) return null
    return project.people.find((x) => x.name.toLowerCase() === t)?.id ?? (s.voice?.name.toLowerCase() === t ? s.voice.person : null)
  }

  /** The project's people that fit what is written, those not yet heard in the meeting first. Not the voice's match: it is offered on its own. */
  function choices(s: Speaker): Project['people'] {
    const hit = project.people.filter((x) => x.id !== s.voice?.person && fits(s, x))
    const heard = new Set(speakers.map((x) => x.person))
    return [...hit.filter((x) => !heard.has(x.id)), ...hit.filter((x) => heard.has(x.id))]
  }

  /** Names a speaker, then the next one without a name gets the focus, so a meeting is named from the keyboard. */
  async function set(s: Speaker, who: { person: string } | { name: string }): Promise<void> {
    busy = s.id
    problem = ''
    try {
      await name(s.id, who)
      delete typed[s.id]
      await tick()
      dialog?.querySelector<HTMLInputElement>('input')?.focus()
    } catch (e) {
      problem = failure(e)
    } finally {
      busy = null
    }
  }

  /** Enter: the person with the written name, else a new person with it. */
  function enter(s: Speaker): void {
    const text = written(s)
    if (!text || busy) return
    const hit = same(s)
    void set(s, hit ? { person: hit } : { name: text })
  }
</script>

<dialog bind:this={dialog} aria-labelledby="speakers-title">
  <h2 id="speakers-title">Sätt namn på talare</h2>
  <p class="muted lead">
    {unnamed.length === 1 ? 'En talare har inget namn.' : `${unnamed.length} talare har inget namn.`}
    Lyssna på en rad och skriv vem det är, eller välj ett namn. Namnen styr vilka som står som närvarande, och med vilken Roll.
  </p>
  {#if problem}<p class="bad" role="alert">{problem}</p>{/if}
  <ul>
    {#each unnamed as s (s.id)}
      {@const first = lines.find((l) => l.speaker === s.id)}
      {@const list = choices(s)}
      {@const few = everyone[s.id] || written(s) ? list : list.slice(0, SHOWN)}
      <li>
        <div class="said">
          {#if first}
            <button class="play" aria-label="Lyssna på {s.name} från {clock(first.at)}" onclick={() => listen(first.at, first.id)}>
              <svg width="10" height="10" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true"><path d="M3 1.5v9l7.5-4.5z" /></svg>
            </button>
          {/if}
          <div class="who">
            <p><strong>{s.name}</strong>{#if first}<span class="chip">{clock(first.at)}</span>{/if}</p>
            {#if first}<p class="quote">”{first.text}”</p>{/if}
          </div>
        </div>
        <label class="name">
          <input
            class="field"
            type="text"
            aria-label="Vem är {s.name}?"
            placeholder="Skriv ett namn"
            autocomplete="off"
            disabled={busy === s.id}
            value={typed[s.id] ?? ''}
            oninput={(e) => (typed[s.id] = e.currentTarget.value)}
            onkeydown={(e) => {
              if (e.isComposing) return
              if (e.key === 'Enter') enter(s)
              else if (e.key === 'Escape' && typed[s.id]) typed[s.id] = ''
              else return
              e.preventDefault()
              e.stopPropagation()
            }}
          />
          <kbd aria-hidden="true">↩</kbd>
        </label>
        {#if written(s) && !same(s)}
          <p class="hint">Enter sparar ”{written(s)}” som en ny person {project.stommen ? 'här. I Stommen står namnet utan Kontakt.' : 'i projektet.'}</p>
        {/if}
        {#if s.voice && fits(s, s.voice)}
          {@const voice = s.voice}
          <p class="hint" id="heard-{s.id}">Rösten känns igen från ett tidigare möte</p>
          <div class="chips" role="group" aria-labelledby="heard-{s.id}">
            <button class="pick heard" disabled={busy === s.id} onclick={() => set(s, { person: voice.person })}>
              <Icon name="wave" size={14} /> {voice.name}
            </button>
          </div>
        {/if}
        {#if list.length}
          <p class="hint" id="people-{s.id}">I projektet</p>
          <div class="chips" role="group" aria-labelledby="people-{s.id}">
            {#each few as x (x.id)}
              <button class="pick" title={x.role} disabled={busy === s.id} onclick={() => set(s, { person: x.id })}>{x.name}</button>
            {/each}
            {#if few.length < list.length}
              <button class="pick more" onclick={() => (everyone[s.id] = true)}>{list.length - few.length} till</button>
            {/if}
          </div>
        {/if}
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
  dialog > ul > li { display: grid; gap: 6px; padding: 10px 0; border-top: 1px solid var(--line); }
  .play { flex: none; display: inline-grid; place-items: center; width: 28px; height: 28px; border: 0; border-radius: var(--ctl-r); background: rgb(0 0 0 / 0.06); color: var(--ink-900); }
  .play:hover { background: rgb(0 0 0 / 0.1); }
  .who { flex: 1 1 auto; min-width: 0; }
  .who p:first-child { display: flex; align-items: center; gap: 6px; }
  .chip { display: inline-flex; align-items: center; height: 18px; padding: 0 6px; border-radius: 9px; background: var(--sunken); font: 500 11px var(--font-mono); color: var(--ink-700); }
  :global(:root[data-platform='win']) .chip { border-radius: 4px; }
  .quote { font-size: var(--ui-small); color: var(--ink-500); display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .foot { display: flex; justify-content: flex-end; padding-top: 12px; border-top: 1px solid var(--line); }
  .said { display: flex; align-items: center; gap: 10px; }
  .name { position: relative; display: block; max-width: 360px; }
  .name .field { width: 100%; padding-right: 36px; }
  .name kbd { position: absolute; top: 50%; right: 12px; transform: translateY(-50%); font-family: var(--font-mono); color: var(--ink-400); pointer-events: none; }
  .hint { font-size: var(--ui-small); color: var(--ink-500); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .pick { display: inline-flex; align-items: center; gap: 6px; min-height: var(--ctl-h); padding: 0 12px; border: 1px solid var(--ink-300); border-radius: 999px; background: var(--surface); color: var(--ink-700); }
  .pick:hover:not(:disabled) { border-color: var(--ink-500); color: var(--ink-900); }
  .pick:disabled { opacity: 0.5; }
  .pick.heard { border-color: var(--coral-200); background: var(--coral-50); color: var(--ink-900); font-weight: 500; }
  .pick.more { border-style: dashed; color: var(--ink-500); }
</style>
