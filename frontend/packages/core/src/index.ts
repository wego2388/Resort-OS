export * from './api/client'
export * from './api/endpoints'
export * from './types'
export * from './stores/auth'
export * from './composables/useWebSocket'
export * from './utils/dates'
// i18n — exported so any app can app.use(i18n) and use switchLocale/getSavedLocale
export { default as i18n, switchLocale, getSavedLocale, SUPPORTED_LOCALES } from './i18n/index'
export type { SupportedLocale } from './i18n/index'
