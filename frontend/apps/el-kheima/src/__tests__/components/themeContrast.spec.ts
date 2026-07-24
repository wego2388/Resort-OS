import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { extname, join, resolve } from 'node:path'

const appRoot = process.cwd()
const appSourceRoot = resolve(appRoot, 'src')
const sharedUiRoot = resolve(appRoot, '../../packages/ui/src')
const mainCssPath = resolve(appRoot, 'src/assets/main.css')

function vueFiles(root: string): string[] {
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const path = join(root, entry.name)
    if (entry.isDirectory()) return vueFiles(path)
    return extname(entry.name) === '.vue' ? [path] : []
  })
}

function channelToLinear(channel: number): number {
  const normalized = channel / 255
  return normalized <= 0.04045
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4
}

function luminance(rgb: number[]): number {
  const [red, green, blue] = rgb.map(channelToLinear)
  return (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
}

function contrast(first: number[], second: number[]): number {
  const lighter = Math.max(luminance(first), luminance(second))
  const darker = Math.min(luminance(first), luminance(second))
  return (lighter + 0.05) / (darker + 0.05)
}

function darkToken(css: string, name: string): number[] {
  const darkBlock = css.match(/\.dark\s*\{([\s\S]*?)\}/)?.[1] ?? ''
  const rawValue = darkBlock.match(new RegExp(`--color-${name}:\\s*(\\d+)\\s+(\\d+)\\s+(\\d+)`))
  if (!rawValue) throw new Error(`Missing dark theme token: ${name}`)
  return rawValue.slice(1).map(Number)
}

describe('staff theme contrast guardrails', () => {
  it('keeps primary and muted text readable on the dark surface', () => {
    const css = readFileSync(mainCssPath, 'utf8')
    const surface = darkToken(css, 'surface')

    expect(contrast(darkToken(css, 'dark'), surface)).toBeGreaterThanOrEqual(7)
    expect(contrast(darkToken(css, 'muted'), surface)).toBeGreaterThanOrEqual(4.5)
  })

  it('does not reintroduce gray-500 text in dark mode', () => {
    const violations = [...vueFiles(appSourceRoot), ...vueFiles(sharedUiRoot)]
      .flatMap((path) => {
        const source = readFileSync(path, 'utf8')
        return source.includes('dark:text-gray-500') || source.includes('dark:text-stone-500')
          ? [path]
          : []
      })

    expect(violations, `Low-contrast dark text found in:\n${violations.join('\n')}`).toEqual([])
  })

  it('pairs pale semantic surfaces with a dark-mode surface', () => {
    const semanticColors = 'red|blue|green|amber|yellow|purple|pink|cyan|sky|emerald|orange|rose|violet'
    const paleSurface = new RegExp(`(?:^|\\s)bg-(${semanticColors})-(?:50|100|200)(?:\\s|$)`, 'g')
    const quotedClass = /(['"])([\s\S]*?)\1/g

    const violations = [...vueFiles(appSourceRoot), ...vueFiles(sharedUiRoot)]
      .flatMap((path) => {
        const source = readFileSync(path, 'utf8')
        return [...source.matchAll(quotedClass)].flatMap((quoted) => {
          const classes = quoted[2]
          const missingDarkColors = [...classes.matchAll(paleSurface)]
            .map((match) => match[1])
            .filter((color) => !classes.includes(`dark:bg-${color}-`))

          return missingDarkColors.length
            ? [`${path}: ${[...new Set(missingDarkColors)].join(', ')}`]
            : []
        })
      })

    expect(violations, `Pale surfaces without dark variants found in:\n${violations.join('\n')}`).toEqual([])
  })
})
