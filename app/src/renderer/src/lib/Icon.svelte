<script lang="ts">
  // Line icons drawn here, so the app carries no icon font and nothing is fetched.
  const PATHS = {
    wave: 'M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4',
    lock: 'M7 11V8a5 5 0 0 1 10 0v3M6 11h12v9H6z',
    mic: 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3',
    play: 'M7 5l12 7-12 7z',
    pause: 'M8 5v14M16 5v14',
    stop: 'M6 6h12v12H6z',
    check: 'M5 12l5 5 9-10',
    alert: 'M12 4l9 16H3zM12 10v4M12 17v.5',
    clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
    home: 'M4 11l8-7 8 7M6 10v10h12V10',
    list: 'M8 6h12M8 12h12M8 18h12M4 6h.5M4 12h.5M4 18h.5',
    plus: 'M12 5v14M5 12h14',
    back: 'M15 5l-7 7 7 7',
    down: 'M6 9l6 6 6-6',
    search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4',
    file: 'M7 3h7l5 5v13H7zM14 3v5h5',
    person: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0',
    flag: 'M5 21V4h11l-2 4 2 4H5',
    refresh: 'M20 12a8 8 0 1 1-2.4-5.7M20 4v5h-5',
    edit: 'M4 20h4L19 9l-4-4L4 16zM13 7l4 4',
    trash: 'M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13',
    undo: 'M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3',
    gear: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 0 0-2-1.2L14.2 3H9.8l-.4 2.6a7 7 0 0 0-2 1.2l-2.3-.9-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-.9a7 7 0 0 0 2 1.2l.4 2.6h4.4l.4-2.6a7 7 0 0 0 2-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z',
    sidebar: 'M4 5h16v14H4zM9 5v14',
    link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1'
  } as const

  let { name, size = 18 }: { name: keyof typeof PATHS; size?: number } = $props()
</script>

<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d={PATHS[name]} />
</svg>
