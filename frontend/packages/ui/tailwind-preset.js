/**
 * @resort-os/ui — shared Tailwind preset (the single Design System source of
 * truth for both `el-kheima` and `public`). Extend this from each app's own
 * tailwind.config.js via `presets: [preset]` — never fork/copy it.
 *
 * Everything here is purely *additive* to each app's existing config: no
 * default Tailwind key (colors, screens, fontSize, ...) is removed or
 * repointed, so every already-shipped screen keeps rendering exactly as
 * before. New Design System components (packages/ui/src/components/**)
 * should be built using ONLY the tokens below — no ad-hoc hex colors, no
 * arbitrary spacing/shadow/radius values.
 *
 * Colors are exposed as CSS custom properties (`rgb(var(--color-x) / <alpha-value>)`)
 * so Tailwind's opacity modifiers (`bg-primary/50`) keep working AND the
 * actual value can flip instantly for dark mode by re-declaring the same
 * variable under `.dark` — see src/styles/tokens.css for both value sets.
 *
 * @type {import('tailwindcss').Config}
 */
export default {
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Design System semantic tokens. Deliberately flat (not nested
        // shade scales like the pre-existing `primary`/`gold`/`resort`/
        // `brand` objects in each app's own config) — one canonical value
        // per role, dark-mode aware via CSS var swap. `primary` itself is
        // intentionally NOT redefined here: both apps already ship a full
        // 50-900 `primary` shade scale used across dozens of screens: this
        // preset adds a `secondary` alias pointing at the same brand gold
        // instead of colliding with it.
        secondary: withOpacity('--color-secondary'),
        success:   withOpacity('--color-success'),
        warning:   withOpacity('--color-warning'),
        danger:    withOpacity('--color-danger'),
        info:      withOpacity('--color-info'),
        surface:   withOpacity('--color-surface'),
        border:    withOpacity('--color-border'),
        muted:     withOpacity('--color-muted'),
        background: withOpacity('--color-background'),
        // Fixed (non-theme-switching) neutral extremes — for chrome that
        // must stay one specific value regardless of light/dark mode (e.g.
        // an overlay scrim, or a permanently-dark POS kiosk header).
        dark:  withOpacity('--color-dark'),
        light: withOpacity('--color-light'),
      },

      // Typography — same font-size/line-height pairs Tailwind ships by
      // default (so no existing screen's layout shifts), with letter-spacing
      // added explicitly per size so it's a real documented token instead of
      // an unspecified browser default. This *is* the canonical type scale;
      // new components must only use these names (text-xs … text-4xl).
      fontSize: {
        xs:   ['0.75rem',  { lineHeight: '1rem',    letterSpacing: '0.01em' }],
        sm:   ['0.875rem', { lineHeight: '1.25rem', letterSpacing: '0' }],
        base: ['1rem',     { lineHeight: '1.5rem',  letterSpacing: '0' }],
        lg:   ['1.125rem', { lineHeight: '1.75rem', letterSpacing: '0' }],
        xl:   ['1.25rem',  { lineHeight: '1.75rem', letterSpacing: '-0.01em' }],
        '2xl': ['1.5rem',  { lineHeight: '2rem',    letterSpacing: '-0.01em' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem', letterSpacing: '-0.015em' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem',  letterSpacing: '-0.02em' }],
      },

      // Elevation — a distinct additive scale (elevation-0..5) layered on
      // top of Tailwind's own shadow-sm/md/lg/xl (which stay untouched and
      // keep working in every existing screen). New components pick a level
      // by intent ("this floats above a card" = elevation-2) rather than a
      // shadow size.
      boxShadow: {
        'elevation-0': 'none',
        'elevation-1': '0 1px 2px 0 rgb(0 0 0 / 0.06)',
        'elevation-2': '0 2px 8px -2px rgb(0 0 0 / 0.10), 0 1px 2px -1px rgb(0 0 0 / 0.06)',
        'elevation-3': '0 8px 16px -4px rgb(0 0 0 / 0.12), 0 2px 6px -2px rgb(0 0 0 / 0.08)',
        'elevation-4': '0 16px 32px -8px rgb(0 0 0 / 0.16), 0 4px 12px -4px rgb(0 0 0 / 0.10)',
        'elevation-5': '0 24px 48px -12px rgb(0 0 0 / 0.22), 0 8px 20px -6px rgb(0 0 0 / 0.12)',
        // Focus ring rendered as a shadow so it composes with an element's
        // own box-shadow (elevation) instead of replacing it.
        'focus-ring': '0 0 0 2px rgb(var(--color-surface)), 0 0 0 4px rgb(var(--color-primary-ring, 11 79 138))',
      },

      // Motion system — semantic duration/easing names on top of Tailwind's
      // numeric durations (which stay available/untouched). `motion-safe:`/
      // `motion-reduce:` variants are Tailwind built-ins already; base.css
      // additionally hard-disables these via prefers-reduced-motion.
      transitionDuration: {
        fast: '120ms',
        base: '200ms',
        slow: '320ms',
      },
      transitionTimingFunction: {
        'ds-standard': 'cubic-bezier(0.4, 0, 0.2, 1)',
        'ds-decelerate': 'cubic-bezier(0, 0, 0.2, 1)',
        'ds-accelerate': 'cubic-bezier(0.4, 0, 1, 1)',
      },
      keyframes: {
        'ds-fade-in':   { from: { opacity: 0 },  to: { opacity: 1 } },
        'ds-fade-out':  { from: { opacity: 1 },  to: { opacity: 0 } },
        'ds-scale-in':  { from: { opacity: 0, transform: 'scale(0.96)' }, to: { opacity: 1, transform: 'scale(1)' } },
        'ds-slide-up':  { from: { opacity: 0, transform: 'translateY(8px)' },  to: { opacity: 1, transform: 'translateY(0)' } },
        'ds-slide-down': { from: { opacity: 0, transform: 'translateY(-8px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
        // Uses --color-primary-ring (defined in tokens.css, dark-mode aware)
        // rather than --color-primary, which this preset deliberately never
        // redeclares as a CSS var (see the `colors` block above).
        'ds-pulse-ring': { '0%': { boxShadow: '0 0 0 0 rgb(var(--color-primary-ring) / 0.35)' }, '100%': { boxShadow: '0 0 0 8px rgb(var(--color-primary-ring) / 0)' } },
        // Sweeping bar for Progress.vue's `indeterminate` state.
        'ds-indeterminate': { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'translateX(400%)' } },
      },
      animation: {
        'ds-fade-in':   'ds-fade-in 200ms cubic-bezier(0.4,0,0.2,1) both',
        'ds-fade-out':  'ds-fade-out 150ms cubic-bezier(0.4,0,1,1) both',
        'ds-scale-in':  'ds-scale-in 180ms cubic-bezier(0,0,0.2,1) both',
        'ds-slide-up':  'ds-slide-up 200ms cubic-bezier(0,0,0.2,1) both',
        'ds-slide-down': 'ds-slide-down 200ms cubic-bezier(0,0,0.2,1) both',
        'ds-pulse-ring': 'ds-pulse-ring 1.2s cubic-bezier(0.4,0,0.2,1) infinite',
        'ds-indeterminate': 'ds-indeterminate 1.2s ease-in-out infinite',
      },

      // Responsive tokens — additive named breakpoints for the 4 device
      // classes staff actually use this system on, layered next to
      // Tailwind's default sm/md/lg/xl/2xl (still fully intact/used across
      // every existing screen). `pos` targets the fixed-kiosk landscape
      // terminals at the till; `tablet` covers waiter/housekeeping handhelds.
      screens: {
        mobile: '375px',
        tablet: '768px',
        pos: '1024px',
        desktop: '1280px',
      },
    },
  },
  plugins: [],
}

/** `colorName: withOpacity('--color-x')` → Tailwind opacity modifiers (bg-x/50) keep working. */
function withOpacity(cssVar) {
  return ({ opacityValue }) =>
    opacityValue === undefined ? `rgb(var(${cssVar}))` : `rgb(var(${cssVar}) / ${opacityValue})`
}
