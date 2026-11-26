// The settings window's line icons, on the drawings' 16 pixel grid (lib/Icon.svelte's are on 24, for the main window).
export const GLYPHS = {
  general: '<circle cx="8" cy="8" r="2.2"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4"/>',
  recording: '<rect x="6" y="1.5" width="4" height="8" rx="2"/><path d="M3.5 7.5a4.5 4.5 0 0 0 9 0M8 12v2.5"/>',
  models: '<rect x="3.5" y="3.5" width="9" height="9" rx="1.5"/><path d="M6 1.5v2M10 1.5v2M6 12.5v2M10 12.5v2M1.5 6h2M1.5 10h2M12.5 6h2M12.5 10h2"/>',
  stommen: '<path d="M3 5.5h9.5M10 3l2.5 2.5L10 8M13 10.5H3.5M6 8l-2.5 2.5L6 13"/>',
  about: '<circle cx="8" cy="8" r="6"/><path d="M8 7.2v4M8 4.8h.01"/>',
  person: '<circle cx="8" cy="5.5" r="2.5"/><path d="M3 13.5c.5-2.6 2.5-4 5-4s4.5 1.4 5 4"/>',
  screen: '<rect x="2" y="3" width="12" height="9" rx="1.5"/><path d="M5.5 14.5h5M8 12v2.5"/>',
  keyboard: '<rect x="1.5" y="4" width="13" height="8" rx="1.5"/><path d="M4 7h.01M6.5 7h.01M9 7h.01M11.5 7h.01M5 9.5h6"/>',
  folder: '<path d="M1.5 4v8.5h13V5.5H8L6.5 4z"/>',
  intro: '<circle cx="8" cy="8" r="6"/><path d="M6.8 5.6v4.8l3.8-2.4z"/>',
  lock: '<rect x="3" y="7" width="10" height="6.5" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>',
  mail: '<rect x="1.5" y="3.5" width="13" height="9" rx="1.5"/><path d="m2 4.5 6 4.5 6-4.5"/>',
  refresh: '<path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9M13.5 2.5V5H11"/>',
  wave: '<path d="M2 6.5v3M5 4v8M8 2v12M11 4.5v7M14 6.5v3"/>',
  up: '<path d="m3 10 5-5 5 5"/>',
  down: '<path d="m3 6 5 5 5-5"/>'
} as const
export type Glyph = keyof typeof GLYPHS
