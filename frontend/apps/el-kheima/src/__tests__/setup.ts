/**
 * Vitest global setup. Runs before each test file.
 *
 * Resets DOM direction/lang and localStorage between tests so locale
 * migration, direction, and storage-namespacing assertions never leak state
 * from one test to the next.
 */
import { afterEach, beforeEach } from 'vitest'

// Vue Router restores scroll positions after navigation. jsdom deliberately
// leaves this browser API unimplemented, so provide the inert browser contract
// once instead of emitting misleading errors from every router test.
window.scrollTo = () => undefined

function reset() {
  localStorage.clear()
  document.documentElement.removeAttribute('dir')
  document.documentElement.removeAttribute('lang')
}

beforeEach(reset)
afterEach(reset)
