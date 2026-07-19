/**
 * Vitest global setup. Runs before each test file.
 *
 * Resets DOM direction/lang and localStorage between tests so locale
 * migration, direction, and storage-namespacing assertions never leak state
 * from one test to the next.
 */
import { afterEach, beforeEach } from 'vitest'

function reset() {
  localStorage.clear()
  document.documentElement.removeAttribute('dir')
  document.documentElement.removeAttribute('lang')
}

beforeEach(reset)
afterEach(reset)
