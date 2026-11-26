/** The toolbar's place for what is done in a view: the buttons are the view's, the bar is the window's (App.svelte). */
export function tools(node: HTMLElement): { destroy: () => void } {
  document.getElementById('tools')?.appendChild(node)
  return { destroy: () => node.remove() }
}
