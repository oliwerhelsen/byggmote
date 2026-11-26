<script lang="ts">
  // One setting, as each computer draws one. On the Mac a line of a form: its label to the right in the left column,
  // the control in the right one, what it means in small text under it. On Windows a row: an icon, a title and a
  // line about it to the left, the control to the right. A choice between on and off is a tick box on the Mac and a
  // switch saying På or Av on Windows; to a screen reader both are a checkbox with the setting's name.
  import type { Snippet } from 'svelte'
  import Glyph from './Glyph.svelte'
  import type { Glyph as Name } from './glyphs'

  let { label, title = label, desc = '', macDesc = desc, icon, top = false, heading = false, toggle, children, ...rest }: {
    /** The Mac's label, without its colon. Empty: the line continues the one above. */
    label: string
    /** Windows' title, and the text beside the Mac's tick box. */
    title?: string
    desc?: string
    macDesc?: string
    icon: Name
    /** The control is taller than a line: the icon and the text stay at its top. */
    top?: boolean
    /** The title is a heading of the pane. */
    heading?: boolean
    toggle?: { checked: boolean; set: (on: boolean) => void }
    children?: Snippet
    /** The id of the control the label is for. */
    for?: string
  } = $props()

  const mac = window.api.platform === 'darwin'
  const of = $derived(rest.for)
</script>

{#snippet name(text: string, cls: string)}
  {#if heading}<h2 class={cls}>{text}</h2>{:else if of}<label class={cls} for={of}>{text}</label>{:else}<span class={cls}>{text}</span>{/if}
{/snippet}

{#if mac}
  {#if heading || toggle || !of}<span class="lbl">{label ? `${label}:` : ''}</span>{:else}<label class="lbl" for={of}>{label}:</label>{/if}
  <div class="val">
    {#if toggle}
      <label class="check"><input type="checkbox" checked={toggle.checked} onchange={(e) => toggle.set(e.currentTarget.checked)} /><span>{title}</span></label>
    {:else if heading}
      <h2 class="t">{title}</h2>
    {/if}
    {@render children?.()}
    {#if macDesc}<p class="d" class:in={toggle}>{macDesc}</p>{/if}
  </div>
{:else}
  <div class="srow" class:top>
    <span class="ic"><Glyph name={icon} /></span>
    <div class="tx">{@render name(title, 't')}{#if desc}<span class="d">{desc}</span>{/if}</div>
    {#if toggle}
      <label class="ctl"><span>{toggle.checked ? 'På' : 'Av'}</span><input class="switch" type="checkbox" aria-label={title} checked={toggle.checked} onchange={(e) => toggle.set(e.currentTarget.checked)} /></label>
    {:else if children}
      <div class="ctl">{@render children()}</div>
    {/if}
  </div>
{/if}
