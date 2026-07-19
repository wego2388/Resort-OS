export * from './api/client'
export * from './api/endpoints'
export * from './types'
export * from './stores/auth'
export * from './composables/useWebSocket'
export * from './composables/useTheme'
export * from './utils/dates'
// App-scoped i18n runtimes are deliberately NOT re-exported from this root
// barrel. Re-exporting an initialized staff/public singleton evaluates it in
// every app that imports any core utility, which can overwrite that app's
// <html lang/dir> and pull the other app's catalogs into its bundle. Import
// `@resort-os/core/i18n` (public) or `@resort-os/core/i18n/staff` explicitly.
// Only side-effect-free factories/formatters remain safe root exports.
export { createLocaleController } from './i18n/controller'
export type { LocaleController, LocaleControllerOptions } from './i18n/controller'
export {
  localeTag,
  formatNumber,
  formatMoney,
  formatDate,
  formatTime,
  formatDateTime,
  RESORT_TIME_ZONE,
} from './i18n/format'
