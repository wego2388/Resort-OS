#!/usr/bin/env node
/**
 * validate-i18n.mjs — dependency-free localization gate (Gate 3C).
 *
 * Runs with only Node built-ins (no test framework, no browser). It enforces
 * the Decision 0002 / Gate 3 invariants that must never silently regress:
 *
 *   1. Staff ar/en catalog parity — identical key sets, no missing keys.
 *   2. No empty / placeholder-like catalog values (TODO/TBD/FIXME/…).
 *   3. Public locale policy intact — ru/it catalogs present and the shared
 *      singleton still advertises all four public locales.
 *   4. Every t()/$t() key used by the migrated reference screens exists in
 *      both catalogs (no missing runtime keys where we claim full coverage).
 *   5. No forced `dir="rtl"` and no hard-coded ar-EG/en-US/en-GB locale tags
 *      inside the migrated scope (direction/format is central now).
 *   6. The retired legacy localStorage locale keys and the old shared-singleton
 *      switchLocale/getSavedLocale imports never come back into the staff app.
 *
 * Exit code 0 = clean, 1 = at least one violation (prints every offender).
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, relative } from 'node:path'

const APP_DIR = join(dirname(fileURLToPath(import.meta.url)), '..')
const SRC = join(APP_DIR, 'src')
const LOCALES = join(APP_DIR, '..', '..', 'packages', 'core', 'src', 'i18n', 'locales')
const CORE_I18N_INDEX = join(APP_DIR, '..', '..', 'packages', 'core', 'src', 'i18n', 'index.ts')
const CORE_BARREL = join(APP_DIR, '..', '..', 'packages', 'core', 'src', 'index.ts')

const errors = []
const fail = (msg) => errors.push(msg)

// ── helpers ────────────────────────────────────────────────────────────────
const loadJson = (p) => JSON.parse(readFileSync(p, 'utf8'))

function leafKeys(obj, prefix = '', acc = {}) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) leafKeys(v, key, acc)
    else acc[key] = v
  }
  return acc
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === 'dist') continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else out.push(full)
  }
  return out
}

const rel = (p) => relative(APP_DIR, p)

// ── 1 + 2. catalog parity + placeholder scan ────────────────────────────────
const ar = leafKeys(loadJson(join(LOCALES, 'ar.json')))
const en = leafKeys(loadJson(join(LOCALES, 'en.json')))
const arKeys = new Set(Object.keys(ar))
const enKeys = new Set(Object.keys(en))

for (const k of arKeys) if (!enKeys.has(k)) fail(`[parity] key present in ar but missing in en: ${k}`)
for (const k of enKeys) if (!arKeys.has(k)) fail(`[parity] key present in en but missing in ar: ${k}`)

const PLACEHOLDER = /^(TODO|TBD|FIXME|XXX|PLACEHOLDER|WIP|\?\?\?)$/i
for (const [catalog, map] of [['ar', ar], ['en', en]]) {
  for (const [k, v] of Object.entries(map)) {
    if (typeof v !== 'string') continue
    if (v.trim() === '') fail(`[empty] ${catalog}: "${k}" has an empty value`)
    else if (PLACEHOLDER.test(v.trim())) fail(`[placeholder] ${catalog}: "${k}" = "${v}"`)
  }
}

// ── 3. public locale policy intact ──────────────────────────────────────────
for (const loc of ['ru', 'it']) {
  try {
    loadJson(join(LOCALES, `${loc}.json`))
  } catch {
    fail(`[public-policy] public locale catalog ${loc}.json is missing or invalid`)
  }
}
const coreIndex = readFileSync(CORE_I18N_INDEX, 'utf8')
const supported = coreIndex.match(/SUPPORTED_LOCALES\s*=\s*\[([^\]]*)\]/)
if (!supported || !['ar', 'en', 'ru', 'it'].every((l) => supported[1].includes(`'${l}'`))) {
  fail('[public-policy] shared SUPPORTED_LOCALES must still advertise ar/en/ru/it')
}
if (!/PUBLIC_LOCALE_STORAGE_KEY\s*=\s*['"]resort-os:public:locale['"]/.test(coreIndex)) {
  fail('[public-policy] public locale must use its own namespaced storage key')
}
if (/localStorage\.setItem\(\s*['"](?:locale|kheima_lang|app_language)['"]/.test(coreIndex)) {
  fail('[public-policy] public runtime must not keep writing legacy locale keys')
}

// Importing any ordinary API/store utility from the root core barrel must not
// evaluate either app's initialized i18n singleton. That regression made the
// public bundle execute staffLocale and overwrite a Russian/Italian page's
// document direction with the staff fallback.
const coreBarrel = readFileSync(CORE_BARREL, 'utf8')
if (/from\s+['"]\.\/i18n\/(?:index|staff)['"]/.test(coreBarrel)) {
  fail('[runtime-isolation] root @resort-os/core barrel must not re-export an app-scoped i18n singleton')
}

// ── file inventories ─────────────────────────────────────────────────────────
// Fully migrated screens: reviewed ar/en copy, no forced dir, central format.
// Missing-key + direction + hard-coded-locale checks all apply here.
const STRICT_FILES = [
  'src/layouts/BackOfficeLayout.vue',
  'src/layouts/FieldLayout.vue',
  'src/layouts/KioskLayout.vue',
  'src/components/LanguageSwitcher.vue',
  'src/views/portal/ProfileView.vue',
  'src/views/account/SessionsView.vue',
  'src/views/admin/SettingsView.vue',
  'src/views/admin/CRMView.vue',
].map((p) => join(APP_DIR, p))

// Direction-normalized reference screens: forced dir + hard-coded locale tags
// removed and formatting centralized, but full copy migration is deliberately
// deferred (they still hold hard-coded Arabic strings — tracked, not claimed
// as bilingual). Only the direction/locale-tag checks apply here.
const DIRECTION_CLEAN_FILES = [
  'src/views/kds/DiningKDSView.vue',
  'src/views/pos/UnifiedPOSView.vue',
].map((p) => join(APP_DIR, p))

// ── 4. missing runtime keys in strict reference screens ─────────────────────
const T_CALL = /(?:\$t|(?<![A-Za-z0-9_])t)\(\s*['"`]([^'"`]+)['"`]/g
for (const file of STRICT_FILES) {
  const src = readFileSync(file, 'utf8')
  for (const m of src.matchAll(T_CALL)) {
    const key = m[1]
    // Skip dynamic keys (interpolated) — only static string keys are checkable.
    if (key.includes('${') || key.includes('{')) continue
    if (!arKeys.has(key)) fail(`[missing-key] ${rel(file)} uses t('${key}') absent from ar.json`)
    else if (!enKeys.has(key)) fail(`[missing-key] ${rel(file)} uses t('${key}') absent from en.json`)
  }
}

// ── 5. forced direction / hard-coded locale tags in migrated scope ──────────
const FORCED_RTL = /\bdir\s*=\s*["']rtl["']/
const HARDCODED_LOCALE = /['"`](ar-EG|en-US|en-GB)['"`]/
const PHYSICAL_DIRECTION_CLASS = /(?:^|[\s"'`])(?:text-(?:left|right)|[mp][lr]-\S+|(?:left|right)-\S+)(?=\s|["'`])/m
for (const file of [...STRICT_FILES, ...DIRECTION_CLEAN_FILES]) {
  const src = readFileSync(file, 'utf8')
  if (FORCED_RTL.test(src)) fail(`[forced-dir] ${rel(file)} contains a hard-coded dir="rtl" (direction is central)`)
  if (HARDCODED_LOCALE.test(src)) fail(`[hardcoded-locale] ${rel(file)} contains a hard-coded ar-EG/en-US/en-GB tag`)
  if (PHYSICAL_DIRECTION_CLASS.test(src)) {
    fail(`[physical-direction] ${rel(file)} contains left/right CSS utilities; use logical start/end/ms/me`)
  }
}

// ── 6. retired legacy locale storage keys / old singleton in staff app ──────
const FORBIDDEN_TOKENS = [
  { token: 'kheima_lang', why: 'retired legacy locale key' },
  { token: 'app_language', why: 'retired legacy locale key' },
  { token: 'switchLocale', why: 'retired shared-singleton API (use staffLocale)' },
  { token: 'getSavedLocale', why: 'retired shared-singleton API (use staffLocale)' },
]
const SELF = fileURLToPath(import.meta.url)
for (const file of walk(SRC)) {
  if (!/\.(ts|vue)$/.test(file) || file === SELF) continue
  // The migration tests legitimately reference the legacy keys to prove the
  // one-time migration works; the ban is on production staff code only.
  if (file.includes(`${'/'}__tests__${'/'}`)) continue
  const src = readFileSync(file, 'utf8')
  for (const { token, why } of FORBIDDEN_TOKENS) {
    if (src.includes(token)) fail(`[legacy] ${rel(file)} references "${token}" (${why})`)
  }
}

// ── report ───────────────────────────────────────────────────────────────────
if (errors.length) {
  console.error(`\n✖ i18n validation failed with ${errors.length} issue(s):\n`)
  for (const e of errors) console.error('  ' + e)
  console.error('')
  process.exit(1)
}
console.log('✓ i18n validation passed:')
console.log(`  • ar/en parity: ${arKeys.size} keys each, 0 missing`)
console.log('  • 0 empty/placeholder values')
console.log('  • public ar/en/ru/it policy intact')
console.log(`  • ${STRICT_FILES.length} strict + ${DIRECTION_CLEAN_FILES.length} direction-clean reference files verified`)
console.log('  • no legacy locale keys / retired singleton APIs in staff src')
