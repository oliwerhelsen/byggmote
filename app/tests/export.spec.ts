// The Word and PDF files against protocol.md: the same headings and points, in the same order, and nothing added.
// No Electron and no Word: the .docx is read back as the zip it is, and the PDF's page as the HTML it is printed from.
import { expect, test } from '@playwright/test'
import { strFromU8, unzipSync } from 'fflate'
import { blocks, imageSize, toDocx, toHtml } from '../src/main/export'

const md = `# Protokoll, byggmöte 5

Kv. Björken. 2026-03-12, 48 minuter. Utkast, inte justerat.

## 1. Närvarande

- Anna Berg, Projektledare
- Olle Sand, Platschef

## 2. Ekonomi & ÄTA

- **ÄTA** Extra dränering mot grannen, 86 500 kr. Platschef, senast 2026-03-20.
  - 2.1 sagt 00:12:30
- Beslut: Bjälklaget gjuts v. 14 <klart>.

## 3. Övrigt

Inget noterat.
`

// One pixel, enough to be a PNG with a size.
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAfbLI3wAAAABJRU5ErkJggg==', 'base64')

const text = (xml: string): string[] =>
  [...xml.matchAll(/<w:p[ >][\s\S]*?<\/w:p>/g)].map((p) => [...p[0].matchAll(/<w:t[^>]*>([^<]*)<\/w:t>/g)].map((t) => t[1]).join('')).filter(Boolean)
const plain = (s: string): string => s.replace(/\*\*/g, '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

type Zip = Record<string, Uint8Array>
const part = (zip: Zip, name: string): string => strFromU8(zip[name])

async function document(sheet = {}): Promise<{ zip: Zip; body: string[] }> {
  const zip = unzipSync(new Uint8Array(await toDocx(md, sheet)))
  return { zip, body: text(part(zip, 'word/document.xml')) }
}

test('the Word file has the points of protocol.md, in order, and nothing else', async () => {
  const { body } = await document()
  expect(body).toEqual(blocks(md).map((b) => plain(b.text)))
  expect(body.filter((t) => t.includes('Extra dränering'))).toHaveLength(1)
})

test('the PDF page has the same points', () => {
  const html = toHtml(md, {})
  const shown = [...html.matchAll(/<(?:h1|h2|p)[^>]*>([\s\S]*?)<\/(?:h1|h2|p)>/g)].map((m) => m[1].replace(/<\/?strong>/g, ''))
  expect(shown).toEqual(blocks(md).map((b) => plain(b.text)))
})

test('without a template the file is plain: no header, no image', async () => {
  const { zip } = await document()
  expect(Object.keys(zip).some((f) => f.startsWith('word/header') || f.startsWith('word/media'))).toBe(false)
  expect(toHtml(md, {})).not.toContain('class="top"')
})

test('a Projekt template adds its logo and header text, and the points stay the same', async () => {
  const { zip, body } = await document({ header: 'Byggfirman AB, Storgatan 1', logo: { data: PNG, type: 'png' } })
  expect(body).toEqual(blocks(md).map((b) => plain(b.text)))
  expect(text(part(zip, 'word/header1.xml'))).toEqual(['Byggfirman AB, Storgatan 1'])
  expect(Object.keys(zip).some((f) => f.startsWith('word/media/'))).toBe(true)
  const html = toHtml(md, { header: 'Byggfirman AB, Storgatan 1', logo: { data: PNG, type: 'png' } })
  expect(html).toContain('Byggfirman AB, Storgatan 1')
  expect(html).toContain('data:image/png;base64,')
})

test('closing lines (consent, justering) come after the last point in both files', async () => {
  const closing = ['Mötet spelades in med deltagarnas samtycke.']
  const { body } = await document({ closing })
  expect(body.at(-1)).toBe(closing[0])
  expect(body.slice(0, -1)).toEqual(blocks(md).map((b) => plain(b.text)))
  expect(toHtml(md, { closing }).trimEnd().endsWith(`<p class="closing">${closing[0]}</p>`)).toBe(true)
})

test('a logo size is read from the file', () => {
  expect(imageSize(PNG, 'png')).toEqual({ width: 1, height: 1 })
  expect(imageSize(Buffer.from('nope'), 'png')).toBeNull()
  expect(imageSize(Buffer.from([0xff, 0xd8, 0xff, 0xc0, 0, 17, 8, 0, 20, 0, 30, 3, 0, 0, 0, 0, 0, 0]), 'jpg')).toEqual({ width: 30, height: 20 })
})
