<script lang="ts" module>
  import type { Kind } from '../../../shared/types'
  /** A point being written: what it will be, until it has a text and is added. */
  export type Fresh = { heading: number; kind: Kind; open: boolean; role: string | null; due: string | null; pointing: boolean }
</script>

<script lang="ts">
  // The inspector's Punkt tab: the chosen point's properties as a form where each field is saved as it is changed,
  // the line it was said in, and what the engine knows of how it came to read as it does. The engine is sent only
  // what the person changed, so a field left alone stays the model's.
  import type { Heading, Line, Point, PointFields } from '../../../shared/types'
  import { clock, failure, KINDS } from './format'

  type Props = {
    point: Point | null
    /** A new point, shown when no point is chosen. `ready`: it has a text. */
    fresh: Fresh | null
    ready: boolean
    /** Whether the protocol can be corrected. */
    free: boolean
    headings: Heading[]
    roles: string[]
    /** What the series calls a meeting, for an earlier meeting's point. */
    series: string
    /** When the model wrote the protocol. */
    written: string
    lines: Line[]
    /** The transcript line marked now, which a new point can point at. */
    pointer: Line | null
    sound: boolean
    set: (fields: PointFields) => Promise<void>
    listen: () => void
    remove: () => void
    add: () => void
    leave: () => void
    /** Whether the new point points at the marked line. */
    aim: (on: boolean) => void
    /** Take back that check `n` (from 1) was right. */
    unconfirm: (n: number) => void
  }
  let { point, fresh, ready, free, headings, roles, series, written, lines, pointer, sound, set, listen, remove, add, leave, aim, unconfirm }: Props = $props()

  const mac = window.api.platform === 'darwin'
  const CLOSED: Kind[] = ['decision', 'note'] // said and done at the meeting: the engine never leaves one open
  const x = $derived(point ?? fresh)
  const carried = $derived(point?.since !== undefined)
  const can = $derived(fresh && !point ? true : free)
  const closed = $derived(Boolean(x && !carried && CLOSED.includes(x.kind)))
  const stays = $derived(Boolean(x && x.open && !closed))
  const asked = $derived(point?.checks.find((c) => c.code === 'role')) // the model named a Roll the project lacks
  const unchecked = $derived(Boolean(point?.checks.some((c) => c.code === 'role' || !c.confirmed)))
  const line = $derived(point && point.line !== null ? (lines.find((l) => l.id === point.line) ?? null) : null)
  const doubt = $derived(point?.checks.find((c) => c.code === 'amount' && !c.confirmed)?.said ?? '')

  let problem = $state('')
  let again = $state(0) // a save that failed draws the form again, from the point as it still is
  let follow = $state('')
  $effect(() => {
    follow = point?.follow ?? ''
  })

  async function save(fields: PointFields): Promise<void> {
    problem = ''
    try {
      await set(fields)
    } catch (e) {
      problem = failure(e)
      again++
    }
  }

  function kind(to: Kind): void {
    if (!x) return
    // a task or a question usually stays open
    void save(CLOSED.includes(x.kind) && !CLOSED.includes(to) ? { kind: to, open: true } : { kind: to })
  }

  function said(): void {
    const text = follow.trim().replace(/\s+/g, ' ') || null
    if (point && text !== (point.follow ?? null)) void save({ follow: text })
  }

  const WHEN = new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  const when = (iso: string | undefined): string => (iso && !Number.isNaN(Date.parse(iso)) ? WHEN.format(new Date(iso)) : '')
  /** The line with the words a check doubts marked. */
  const parts = $derived.by((): [string, string, string] => {
    const at = line && doubt ? line.text.indexOf(doubt) : -1
    return !line ? ['', '', ''] : at < 0 ? [line.text, '', ''] : [line.text.slice(0, at), doubt, line.text.slice(at + doubt.length)]
  })
</script>

{#if !x}
  <p class="none">Ingen punkt är vald. Klicka på en punkt i protokollet för att se och ändra den.</p>
{:else}
  <div class="sec top">
    <span class="name">{#if point}Punkt <span class="mono">{point.no}</span>{:else}Ny punkt{/if}</span>
    {#if unchecked}<span class="state"><span></span>Att kontrollera</span>{/if}
  </div>

  {#key again}
    <div class="sec form">
      {#if carried && point}
        <label class="over">
          <span class="lbl">På mötet</span>
          <textarea id="point-follow" class="field" rows="2" disabled={!can} bind:value={follow} onblur={said}
            onkeydown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); said() } }}></textarea>
        </label>
        <p class="help">Det som sades om punkten på det här mötet. Punktens egen text hör till {series} {point.since} och ändras inte här.</p>
      {/if}
      <div class="pair">
        <label class="f">
          <span class="lbl">Typ</span>
          <select class="popup" disabled={!can || carried} value={x.kind} onchange={(e) => kind(e.currentTarget.value as Kind)}>
            {#each Object.entries(KINDS) as [k, label] (k)}<option value={k}>{label}</option>{/each}
          </select>
        </label>
        <label class="f">
          <span class="lbl">Rubrik</span>
          <select class="popup" disabled={!can || carried} value={x.heading} onchange={(e) => save({ heading: Number(e.currentTarget.value) })}>
            {#each headings as h (h.no)}<option value={h.no}>{h.no} {h.name}</option>{/each}
          </select>
        </label>
      </div>
      <label class="f">
        <span class="lbl">Ansvarig</span>
        <select id="point-role" class="popup" disabled={!can || !stays} value={asked ? '?' : (x.role ?? '')}
          onchange={(e) => e.currentTarget.value !== '?' && save({ role: e.currentTarget.value || null })}>
          {#if asked}<option value="?">Välj Roll (modellen skrev ”{asked.said}”)</option>{/if}
          <option value="">Ingen ansvarig</option>
          {#each roles as r (r)}<option value={r}>{r}</option>{/each}
        </select>
      </label>
      <label class="f">
        <span class="lbl">Senast</span>
        <input class="field" type="date" disabled={!can || !stays} value={x.due ?? ''} onchange={(e) => save({ due: e.currentTarget.value || null })} />
      </label>
      <label class="tick" class:off={!can || closed}>
        <input type="checkbox" disabled={!can || closed} checked={carried ? x.open : stays} onchange={(e) => save({ open: e.currentTarget.checked })} />
        <span>{carried ? 'Kvarstår efter mötet' : 'Återstår efter mötet'}</span>
      </label>
      {#if closed}
        <p class="help in">{x.kind === 'decision' ? 'Ett Beslut är alltid avslutat.' : 'En Notering är alltid avslutad.'}</p>
      {/if}
      {#if problem}<p class="bad" role="alert"><strong>Det gick inte att spara.</strong> {problem}</p>{/if}
    </div>
  {/key}

  <div class="sec">
    <h3>I inspelningen</h3>
    {#if point}
      {#if point.at === null}
        <p class="help">Punkten pekar inte på något ställe i inspelningen.</p>
      {:else}
        <div class="said">
          <p class="head"><span class="chip">{clock(point.at)}</span>{#if line}<b>{line.who}</b>{/if}</p>
          {#if line}<p>{parts[0]}{#if parts[1]}<mark>{parts[1]}</mark>{/if}{parts[2]}</p>{/if}
        </div>
        <div class="act">
          <button class="btn" disabled={!sound} onclick={listen}>
            <svg width="10" height="10" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true"><path d="M3 1.5v9l7.5-4.5z" /></svg>
            <span>Lyssna från punkten</span>
          </button>
          <span class="keys">{mac ? '⌥Mellanslag' : 'Ctrl+L'}</span>
        </div>
      {/if}
    {:else if fresh && pointer}
      <label class="tick wrap">
        <input type="checkbox" checked={fresh.pointing} onchange={(e) => aim(e.currentTarget.checked)} />
        <span>Punkten pekar på {clock(pointer.at)} i utskriften, där {pointer.who} säger: <span class="quiet">”{pointer.text}”</span></span>
      </label>
    {:else}
      <p class="help">Klicka på en tid i utskriften om punkten ska peka på stället där det sägs.</p>
    {/if}
  </div>

  {#if point}
    <div class="sec last">
      <h3>Historik</h3>
      {#if point.added}
        <p class="kv"><span>Tillagd för hand</span><span>{when(point.added)}</span></p>
      {:else if point.since === undefined}
        <p class="kv"><span>Modellen skrev punkten</span><span>{when(written)}</span></p>
      {:else}
        <p class="kv"><span>Från {series} {point.since}</span><span></span></p>
      {/if}
      {#if point.edited}
        <p class="kv"><span>Ändrad för hand</span><span>{when(point.edited)}</span></p>
        {#if point.proposed?.text && point.proposed.text !== point.text}<p class="help">Modellen skrev: ”{point.proposed.text}”</p>{/if}
      {/if}
      {#each point.checks as c, i}
        {#if c.code === 'amount' && c.confirmed}
          <p class="kv"><span>Beloppet {c.value} är kontrollerat mot inspelningen.</span><span>{when(c.confirmed)}</span></p>
          {#if free}
            <button class="btn small" aria-label="Ångra kontrollen av {c.value} i punkt {point.no}" onclick={() => unconfirm(i + 1)}>Ångra kontrollen</button>
          {/if}
        {/if}
      {/each}
    </div>
  {/if}

  <span class="fill"></span>
  {#if !point}
    <div class="foot">
      <button class="btn primary" disabled={!ready} onclick={add}>Lägg till punkten</button>
      <button class="btn" onclick={leave}>Avbryt</button>
    </div>
  {:else if free && !carried}
    <div class="foot">
      <button class="btn remove" onclick={remove}>Ta bort punkten</button>
      <span class="keys">{mac ? '⌘⌫' : 'Delete'}</span>
    </div>
  {/if}
{/if}

<style>
  .none { padding: 14px; color: var(--ink-500); }
  .sec { display: flex; flex-direction: column; gap: 6px; padding: 10px 14px; border-bottom: 1px solid var(--line-soft, #efeef3); }
  .sec.last { border-bottom: 0; }
  .top { flex-direction: row; align-items: center; justify-content: space-between; gap: 8px; }
  .name { font-weight: 600; }
  .mono { font-family: var(--font-mono); font-size: 0.92em; }
  .state { display: inline-flex; align-items: center; gap: 5px; height: 18px; padding: 0 7px; border-radius: 9px; background: var(--warn-bg); font-size: var(--ui-small); font-weight: 500; white-space: nowrap; }
  .state span { width: 7px; height: 7px; border-radius: 50%; background: var(--warn); }
  h3 { font: 600 var(--ui-small)/1.4 var(--font-ui); color: var(--ink-500); }

  /* The Mac's form has its labels to the left of the fields; Windows' has them over, and Typ beside Rubrik. */
  .form { gap: 8px; }
  .pair { display: contents; }
  .f { display: flex; align-items: center; gap: 8px; }
  .f .lbl { flex: none; width: 64px; text-align: right; color: var(--ink-500); }
  .f :is(select, input) { flex: 1 1 0; min-width: 0; width: 100%; }
  .over { display: flex; flex-direction: column; gap: 4px; }
  .over .lbl { font-size: var(--ui-small); color: var(--ink-500); }
  .tick { min-height: 0; padding-left: 72px; }
  .tick.off { opacity: 0.5; }
  .tick.wrap { padding-left: 0; align-items: flex-start; }
  .tick.wrap input { flex: none; margin-top: 2px; }
  .help { font-size: var(--ui-small); color: var(--ink-500); }
  .help.in { padding-left: 72px; }
  .quiet { color: var(--ink-500); }
  .bad { padding: 6px 10px; border-radius: var(--ctl-r); background: var(--bad-bg); font-size: var(--ui-small); }
  :global(:root[data-platform='win']) .sec { padding: 12px 14px; }
  :global(:root[data-platform='win']) .top { display: none; }
  :global(:root[data-platform='win']) .form { gap: 10px; }
  :global(:root[data-platform='win']) .pair { display: flex; gap: 10px; }
  :global(:root[data-platform='win']) .f { flex: 1 1 0; min-width: 0; flex-direction: column; align-items: stretch; gap: 4px; }
  :global(:root[data-platform='win']) .f .lbl { width: auto; text-align: left; font-size: var(--ui-small); color: var(--ink-900); }
  :global(:root[data-platform='win']) .f :is(select, input) { flex: none; }
  :global(:root[data-platform='win']) :is(.tick, .help.in) { padding-left: 0; }
  :global(:root[data-platform='win']) .help.in { margin-top: -6px; }
  :global(:root[data-platform='win']) .tick input { width: 18px; height: 18px; }

  .said { padding: 6px 8px; border-radius: var(--ctl-r); background: #fff; box-shadow: inset 0 0 0 1px var(--line); }
  .said .head { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
  .said b { font-weight: 600; }
  mark { padding: 0 2px; border-radius: 2px; background: var(--warn-bg); color: inherit; }
  .chip { display: inline-flex; align-items: center; height: 18px; padding: 0 6px; border-radius: 9px; background: var(--sunken); font: 500 11px var(--font-mono); color: var(--ink-700); }
  :global(:root[data-platform='win']) .chip { border-radius: 4px; }
  .act { display: flex; align-items: center; gap: 8px; }
  .keys { font-size: var(--ui-small); color: var(--ink-500); }
  .kv { display: flex; justify-content: space-between; gap: 12px; }
  .kv span:last-child { flex: none; font-size: var(--ui-small); color: var(--ink-500); }
  .btn.small { align-self: flex-start; min-height: 22px; padding: 0 8px; font-size: var(--ui-small); }
  .fill { flex: 1 1 auto; }
  .foot { flex: none; display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-top: 1px solid var(--line-soft, #efeef3); }
  .remove { color: var(--bad); }
</style>
