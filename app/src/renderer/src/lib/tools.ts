/** The toolbar's place for what is done in a view: the buttons are the view's, the bar is the window's (App.svelte). */
export function tools(node: HTMLElement): { destroy: () => void } {
  document.getElementById('tools')?.appendChild(node)
  return { destroy: () => node.remove() }
}

/** The toolbar's place for a view's own title, which then stands instead of the window's. On the Mac the drawings put
 * a view's title there; on Windows it stays in the view, so `on` is false and nothing moves. */
export function title(node: HTMLElement, on = true): { destroy: () => void } {
  if (on) document.getElementById('title')?.appendChild(node)
  return { destroy: () => node.remove() }
}

/** Windows' status bar, for a view that says more of itself there than the window knows (App.svelte). */
export function status(node: HTMLElement): { destroy: () => void } {
  document.getElementById('status')?.appendChild(node)
  return { destroy: () => node.remove() }
}
