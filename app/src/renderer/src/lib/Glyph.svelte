<script lang="ts">
  import { GLYPHS, type Glyph } from './glyphs'

  let { name, size = 16, width = 1.4 }: { name: Glyph; size?: number; width?: number } = $props()
</script>

<!-- The icons are this app's own constants, never text from outside. -->
<svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width={width} stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{@html GLYPHS[name]}</svg>
