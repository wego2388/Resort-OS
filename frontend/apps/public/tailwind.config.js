import dsPreset from '../../packages/ui/tailwind-preset.js'

/** @type {import('tailwindcss').Config} */
export default {
  // ⚠️ نفس باج el-kheima's tailwind.config.js — content مكنش شامل
  // '../../packages/ui/src'، يعني Tailwind classes مستخدمة بس جوه مكوّنات
  // @resort-os/ui المشتركة (ToastContainer مثلاً) كانت بتتشال بصمت من الـ CSS.
  content: ['./index.html', './src/**/*.{vue,ts}', '../../packages/ui/src/**/*.{vue,ts}'],
  // Shared Design System preset (packages/ui/tailwind-preset.js) — see
  // el-kheima's tailwind.config.js for the full rationale. `extend` below
  // still merges on top, so public's own primary/gold/resort/brand palette
  // and heading/body fonts are untouched.
  presets: [dsPreset],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#0B4F8A',
          50: '#EFF6FF', 100: '#DBEAFE', 200: '#BFDBFE',
          300: '#93C5FD', 400: '#60A5FA', 500: '#3B82F6',
          600: '#2563EB', 700: '#0B4F8A', 800: '#083C6A', 900: '#05294A',
        },
        gold: {
          DEFAULT: '#C9963C',
          light: '#F5D78E', dark: '#A07530',
        },
        resort: {
          bg: '#F9F7F4',
          surface: '#FFFFFF',
          border: '#E5E0D8',
        },
        // Official El Kheima Beach Resort palette — see
        // /home/wego/projects/elkheima-beach-resort-marketing/01_brand/VISUAL_IDENTITY_GUIDE.md
        brand: {
          ocean: '#0077BE',
          sandy: '#E8D5B7',
          sunset: '#FF6B35',
          teal: '#006B7D',
          warmwhite: '#FDFBF7',
          coral: '#FFB4A2',
          charcoal: '#2C3E50',
          lightgray: '#ECF0F1',
        },
      },
      fontFamily: {
        sans: ['Cairo', 'Tajawal', 'system-ui', 'sans-serif'],
        // Latin glyphs render in Montserrat/Open Sans, Arabic glyphs fall
        // back to Cairo/Tajawal automatically (per-character font fallback)
        // — see VISUAL_IDENTITY_GUIDE.md typography section.
        heading: ['Montserrat', 'Cairo', 'system-ui', 'sans-serif'],
        body: ['"Open Sans"', 'Tajawal', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
