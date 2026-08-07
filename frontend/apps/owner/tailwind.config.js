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
        'owner-bg':     '#0A0908',
        'owner-card':   '#1C1B1A',
        'owner-border': '#2C2B2A',
        'owner-text':   '#F5F5F4',
        'owner-muted':  '#A8A29E',
        'owner-green':  '#22C55E',
        'owner-red':    '#EF4444',
        'owner-amber':  '#F59E0B',
      },
    },
  },
}
