import { BorderStyle, Document, Header, HeadingLevel, ImageRun, Packer, Paragraph, TextRun } from 'docx'

// protocol.md is the one text the engine writes. Word and PDF are made from it here, so they cannot differ from
// what the window shows. It only has headings, a paragraph and bullets (one level of sub-bullets) with **bold**.
type Block = { kind: 'h1' | 'h2' | 'p' | 'li' | 'sub'; text: string }

export function blocks(md: string): Block[] {
  const out: Block[] = []
  for (const line of md.split('\n')) {
    if (!line.trim()) continue
    if (line.startsWith('## ')) out.push({ kind: 'h2', text: line.slice(3) })
    else if (line.startsWith('# ')) out.push({ kind: 'h1', text: line.slice(2) })
    else if (/^\s+- /.test(line)) out.push({ kind: 'sub', text: line.replace(/^\s+- /, '') })
    else if (line.startsWith('- ')) out.push({ kind: 'li', text: line.slice(2) })
    else out.push({ kind: 'p', text: line })
  }
  return out
}

/** Text with **bold** parts split out. */
const parts = (text: string): { text: string; bold: boolean }[] =>
  text.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((s) => (s.startsWith('**') ? { text: s.slice(2, -2), bold: true } : { text: s, bold: false }))

/** What a Projekt adds around the protocol. All of it is optional: with none the file is plain and still presentable.
 * `header`: a line of text (the contractor's name, an address) at the top of every page. `logo`: a PNG or JPEG.
 * `closing`: lines after the last heading, one paragraph each. That is where the consent line (stommen#268) and the
 * justering line (stommen#272) go once they exist: the caller passes them, this file does not know them. */
export type Sheet = { header?: string; logo?: { data: Buffer; type: 'png' | 'jpg' }; closing?: string[] }

/** A logo's width and height in pixels, read from the file's own header, so no image library is needed. */
export function imageSize(data: Buffer, type: 'png' | 'jpg'): { width: number; height: number } | null {
  if (type === 'png') return data.length > 24 && data.toString('latin1', 1, 4) === 'PNG' ? { width: data.readUInt32BE(16), height: data.readUInt32BE(20) } : null
  if (data[0] !== 0xff || data[1] !== 0xd8) return null
  for (let i = 2; i + 9 < data.length; ) {
    if (data[i] !== 0xff) return null
    const marker = data[i + 1]
    if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) return { height: data.readUInt16BE(i + 5), width: data.readUInt16BE(i + 7) }
    i += 2 + data.readUInt16BE(i + 2)
  }
  return null
}

/** The logo scaled to at most 48 px high (docx counts in pixels at 96 dpi). */
function logoSize(logo: NonNullable<Sheet['logo']>): { width: number; height: number } | null {
  const s = imageSize(logo.data, logo.type)
  if (!s || !s.width || !s.height) return null
  const k = Math.min(1, 48 / s.height, 240 / s.width)
  return { width: Math.round(s.width * k), height: Math.round(s.height * k) }
}

// Same look as the PDF below: sans-serif, a light title, bold headings with a thin rule, grey notes under a point.
const FONT = 'Arial'
const INK = '1A1A1A'
const GREY = '555555'
const RULE = 'DDDDDD'

export async function toDocx(md: string, sheet: Sheet = {}): Promise<Buffer> {
  // Font, colour and size go on every run: Word honours that where a document default is not always applied.
  const runs = (t: string, extra: { color?: string; size?: number; bold?: boolean } = {}): TextRun[] =>
    parts(t).map((p) => new TextRun({ text: p.text, font: FONT, color: INK, size: 22, ...extra, bold: extra.bold || p.bold }))
  const paragraphs = blocks(md).map((b) => {
    if (b.kind === 'h1') return new Paragraph({ heading: HeadingLevel.TITLE, children: runs(b.text, { size: 40 }) })
    if (b.kind === 'h2')
      return new Paragraph({
        heading: HeadingLevel.HEADING_1,
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, space: 3, color: RULE } },
        children: runs(b.text, { size: 26, bold: true })
      })
    if (b.kind === 'li') return new Paragraph({ bullet: { level: 0 }, spacing: { after: 80 }, children: runs(b.text) })
    // A note under a point: smaller, grey, indented, with no bullet of its own.
    if (b.kind === 'sub') return new Paragraph({ indent: { left: 720 }, spacing: { after: 80 }, children: runs(b.text, { color: GREY, size: 20 }) })
    return new Paragraph({ spacing: { after: 120 }, children: runs(b.text) })
  })
  for (const line of sheet.closing ?? []) paragraphs.push(new Paragraph({ spacing: { before: 120, after: 120 }, children: runs(line) }))
  const size = sheet.logo ? logoSize(sheet.logo) : null
  const top = [
    ...(sheet.logo && size ? [new ImageRun({ type: sheet.logo.type, data: sheet.logo.data, transformation: size, altText: { name: 'Logotyp', description: 'Logotyp', title: 'Logotyp' } })] : []),
    ...(sheet.header ? runs(sheet.header, { size: 18, color: GREY }) : [])
  ]
  const headers = top.length ? { default: new Header({ children: [new Paragraph({ children: top })] }) } : undefined
  const font = FONT
  return Packer.toBuffer(
    new Document({
      creator: 'Byggmöte',
      styles: {
        default: { document: { run: { font, size: 22, color: INK }, paragraph: { spacing: { line: 330 } } } },
        paragraphStyles: [
          { id: 'Title', name: 'Title', basedOn: 'Normal', run: { font, size: 40, bold: false, color: INK }, paragraph: { spacing: { after: 80 } } },
          { id: 'Heading1', name: 'heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font, size: 26, bold: true, color: INK }, paragraph: { spacing: { before: 360, after: 120 }, keepNext: true } }
        ]
      },
      sections: [{ properties: { page: { margin: { top: 1150, bottom: 1150, left: 1150, right: 1150 } } }, headers, children: paragraphs }]
    })
  )
}

const esc = (s: string): string => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

export function toHtml(md: string, sheet: Sheet): string {
  const inline = (t: string): string => parts(t).map((p) => (p.bold ? `<strong>${esc(p.text)}</strong>` : esc(p.text))).join('')
  const body = blocks(md)
    .map((b) => {
      const t = inline(b.text)
      if (b.kind === 'h1') return `<h1>${t}</h1>`
      if (b.kind === 'h2') return `<h2>${t}</h2>`
      if (b.kind === 'li') return `<p class="li">${t}</p>`
      if (b.kind === 'sub') return `<p class="sub">${t}</p>`
      return `<p>${t}</p>`
    })
    .join('\n')
  const closing = (sheet.closing ?? []).map((l) => `<p class="closing">${inline(l)}</p>`).join('\n')
  const top =
    sheet.logo || sheet.header
      ? `<div class="top">${sheet.logo ? `<img src="data:image/${sheet.logo.type === 'png' ? 'png' : 'jpeg'};base64,${sheet.logo.data.toString('base64')}">` : ''}${sheet.header ? `<span>${esc(sheet.header)}</span>` : ''}</div>`
      : ''
  return `<!doctype html><meta charset="utf-8"><style>
    body{font:11pt/1.5 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif;color:#1a1a1a;margin:0}
    h1{font-size:20pt;font-weight:400;margin:0 0 4pt} h2{font-size:13pt;margin:18pt 0 6pt;border-bottom:1px solid #ddd;padding-bottom:3pt}
    p{margin:0 0 6pt} .li{padding-left:14pt;text-indent:-10pt}.li:before{content:"• "} .sub{padding-left:30pt;color:#555;font-size:10pt} .closing{margin-top:10pt}
    .top{display:flex;align-items:center;gap:12pt;margin-bottom:14pt;color:#555;font-size:9pt} .top img{max-height:48px;max-width:240px}
  </style><body>${top}${body}${closing}`
}

/** The protocol on paper: a window nobody sees prints it, so no library or browser is needed. */
export async function toPdf(md: string, sheet: Sheet = {}): Promise<Buffer> {
  const { BrowserWindow } = await import('electron') // here and not at the top, so the Word part runs in a test with no Electron
  const win = new BrowserWindow({ show: false, webPreferences: { sandbox: true, javascript: false } })
  try {
    await win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(toHtml(md, sheet)))
    return await win.webContents.printToPDF({ pageSize: 'A4', margins: { top: 0.8, bottom: 0.8, left: 0.8, right: 0.8 } })
  } finally {
    win.destroy()
  }
}
