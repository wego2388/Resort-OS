import defaultTheme from 'tailwindcss/defaultConfig.js'
import dsPreset from '../../packages/ui/tailwind-preset.js'

/** @type {import('tailwindcss').Config} */
export default {
  presets: [defaultTheme, dsPreset],
  content: [
    './index.html',
    './src/**/*.{vue,ts}',
    '../../packages/ui/src/**/*.{vue,ts}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Resolved from CSS custom properties (light values on :root, dark
        // overrides under .dark — see src/assets/main.css) so every existing
        // `owner-*` utility class across the app automatically repaints for
        // both themes with zero changes at the call site. The
        // `rgb(var(--x) / <alpha-value>)` shape also makes Tailwind's opacity
        // modifiers (e.g. `bg-owner-red/10`) work correctly in both themes —
        // same convention as `@resort-os/ui`'s tailwind-preset.js.
        'owner-bg':     'rgb(var(--owner-bg) / <alpha-value>)',
        'owner-card':   'rgb(var(--owner-card) / <alpha-value>)',
        'owner-border': 'rgb(var(--owner-border) / <alpha-value>)',
        'owner-text':   'rgb(var(--owner-text) / <alpha-value>)',
        'owner-muted':  'rgb(var(--owner-muted) / <alpha-value>)',
        'owner-green':  'rgb(var(--owner-green) / <alpha-value>)',
        'owner-red':    'rgb(var(--owner-red) / <alpha-value>)',
        'owner-amber':  'rgb(var(--owner-amber) / <alpha-value>)',
      },
    },
  },
}
