<script lang="ts">
  // The form a person corrects a point in, or writes a new one in. It sends the engine only what the person changed,
  // so a field left alone stays the model's, and a Roll the project lacks stays a question until the person answers it.
  import type { Heading, Kind, Line, NewPoint, Point, PointFields } from '../../../shared/types'
  import Icon from './Icon.svelte'
  import { clock, failure, KINDS } from './format'

  type Props = {
    /** The point to change. Without one, a new point under `heading`. */
    point?: Point
    heading?: number
    /** The headings a point can be under. */
    headings: Heading[]
    roles: string[]
    /** What the series calls a meeting, for an earlier meeting's point. */
    series: string
    /** The transcript line marked now, which a new point can point at. */
    pointer?: Line | null
    change?: (fields: PointFields) => Promise<void>
    add?: (fields: NewPoint) => Promise<void>
    remove?: () => Promise<void>
    cancel: () => void
  }
  let { point, heading, headings, roles, series, pointer = null, change, add, remove, cancel }: Props = $props()

  const uid = $props.id()
  const CLOSED: Kind[] = ['decision', 'note'] // said and done at the meeting: the engine never leaves one open
  // svelte-ignore state_referenced_locally
  const carried = point?.since !== undefined
  // svelte-ignore state_referenced_locally
  const asked = point?.checks.find((c) => c.code === 'role') // the model named a Roll the project lacks

  // The form starts from the point as it is and lives until it is saved or left, so the first values are the ones to keep.
  // svelte-ignore state_referenced_locally
  let text = $state(point?.text ?? '')
  // svelte-ignore state_referenced_locally
  let kind = $state<Kind>(point?.kind ?? 'todo')
  // svelte-ignore state_referenced_locally
  let head = $state(point?.heading ?? heading ?? headings[0]?.no ?? 0)
  // svelte-ignore state_referenced_locally
  let open = $state(point ? point.open : true)
  // svelte-ignore state_referenced_locally
  let role = $state(asked ? '?' : (point?.role ?? ''))
  // svelte-ignore state_referenced_locally
  let due = $state(point?.due ?? '')
  // svelte-ignore state_referenced_locally
  let follow = $state(point?.follow ?? '')
  let pointing = $state(true)
  let busy = $state(false)
  let problem = $state('')

  const stays = $derived(carried ? open : open && !CLOSED.includes(kind))
  const tidy = (t: string): string => t.trim().replace(/\s+/g, ' ')

  function kindChanged(was: Kind): void {
    if (CLOSED.includes(was) && !CLOSED.includes(kind)) open = true // a task or a question usually stays open
  }

  /** What the person changed, and nothing else. */
  function changed(x: Point): PointFields {
    const f: PointFields = {}
    if (carried) {
      if ((tidy(follow) || null) !== (x.follow ?? null)) f.follow = tidy(follow) || null
      if (open !== x.open) f.open = open
    } else {
      if (tidy(text) !== x.text) f.text = tidy(text)
      if (kind !== x.kind) f.kind = kind
      if (head !== x.heading) f.heading = head
      if (stays !== x.open) f.open = stays
    }
    if (stays) {
      if (role !== '?' && (asked || (role || null) !== x.role)) f.role = role || null
      if ((due || null) !== x.due) f.due = due || null
    }
    return f
  }

  async function submit(e: SubmitEvent): Promise<void> {
    e.preventDefault()
    busy = true
    problem = ''
    try {
      if (point) {
        const f = changed(point)
        if (Object.keys(f).length) await change?.(f)
        else cancel()
      } else {
        await add?.({ heading: head, kind, text: tidy(text), open: stays, role: stays && role ? role : null, due: stays && due ? due : null,
          line: pointing && pointer ? pointer.id : null })
      }
    } catch (x) {
      problem = failure(x)
      busy = false
    }
  }

  async function drop(): Promise<void> {
    busy = true
    problem = ''
    try {
      await remove?.()
    } catch (x) {
      problem = failure(x)
      busy = false
    }
  }

  const first = (el: HTMLTextAreaElement): void => {
    el.focus()
    el.setSelectionRange(el.value.length, el.value.length)
  }
</script>

<form class="form" onsubmit={submit} aria-label={point ? `Ändra punkt ${point.no}` : 'Ny punkt'}>
  {#if carried && point}
    <div>
      <label class="label" for="{uid}-follow">På mötet</label>
      <textarea id="{uid}-follow" class="field" rows="2" bind:value={follow} use:first></textarea>
      <p class="small muted help">
        Det som sades om punkten på det här mötet. Punktens egen text hör till {series} {point.since} och ändras inte här.
      </p>
    </div>
  {:else}
    <div>
      <label class="label" for="{uid}-text">Punkten</label>
      <textarea id="{uid}-text" class="field" rows="3" required bind:value={text} use:first></textarea>
      {#if point?.proposed?.text && point.proposed.text !== point.text}
        <p class="small muted help">Modellen skrev: ”{point.proposed.text}”</p>
      {/if}
    </div>
    <div class="pair">
      <div>
        <label class="label" for="{uid}-kind">Typ</label>
        <select id="{uid}-kind" class="field" bind:value={() => kind, (v) => { const was = kind; kind = v; kindChanged(was) }}>
          {#each Object.entries(KINDS) as [k, name] (k)}<option value={k}>{name}</option>{/each}
        </select>
      </div>
      <div>
        <label class="label" for="{uid}-heading">Rubrik</label>
        <select id="{uid}-heading" class="field" bind:value={head}>
          {#each headings as h (h.no)}<option value={h.no}>{h.no}. {h.name}</option>{/each}
        </select>
      </div>
    </div>
  {/if}

  {#if carried || !CLOSED.includes(kind)}
    <div>
      <label class="tick"><input type="checkbox" bind:checked={open} /><span>{carried ? 'Kvarstår efter mötet' : 'Återstår efter mötet'}</span></label>
      <p class="small muted help">En punkt som återstår följer med på dagordningen tills ett möte stänger den.</p>
    </div>
  {/if}

  {#if stays}
    <div class="pair">
      <div>
        <label class="label" for="{uid}-role">Ansvarig</label>
        <select id="{uid}-role" class="field" bind:value={role}>
          {#if asked}<option value="?">Välj Roll (modellen skrev ”{asked.said}”)</option>{/if}
          <option value="">Ingen ansvarig</option>
          {#each roles as r (r)}<option value={r}>{r}</option>{/each}
        </select>
      </div>
      <div>
        <label class="label" for="{uid}-due">Senast</label>
        <input id="{uid}-due" class="field" type="date" bind:value={due} />
      </div>
    </div>
  {/if}

  {#if !point}
    {#if pointer}
      <label class="tick">
        <input type="checkbox" bind:checked={pointing} />
        <span>Punkten pekar på {clock(pointer.at)} i utskriften, där {pointer.who} säger: <span class="muted">”{pointer.text}”</span></span>
      </label>
    {:else}
      <p class="small muted">Klicka på en tid i utskriften om punkten ska peka på stället där det sägs.</p>
    {/if}
  {/if}

  {#if problem}
    <div class="note bad" role="alert"><Icon name="alert" /><div><p><strong>Det gick inte att spara.</strong></p><p class="small mono">{problem}</p></div></div>
  {/if}

  <div class="row">
    <button class="btn primary" type="submit" disabled={busy || (!carried && !tidy(text))}>{point ? 'Spara' : 'Lägg till punkten'}</button>
    <button class="btn" type="button" disabled={busy} onclick={cancel}>Avbryt</button>
    <span class="grow"></span>
    {#if remove}
      <button class="btn quiet" type="button" disabled={busy} onclick={drop}><Icon name="trash" size={16} /> Ta bort punkten</button>
    {/if}
  </div>
</form>

<style>
  .form { display: flex; flex-direction: column; gap: 14px; padding: 16px; border: 1px solid var(--ink-300); border-radius: var(--radius-sm); background: var(--surface); }
  .pair { display: flex; gap: 12px; flex-wrap: wrap; }
  .pair > div { flex: 1 1 200px; min-width: 0; }
  .pair .field { width: 100%; }
  .help { margin-top: 4px; }
  .tick { align-items: flex-start; }
  .tick input { flex: none; margin-top: 13px; }
  .tick > span { padding: 10px 0; }
</style>
