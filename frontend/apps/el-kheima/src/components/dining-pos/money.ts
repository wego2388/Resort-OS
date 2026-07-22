export const MONEY_SCALE = 100

/**
 * POS-only display/input helper. The backend Decimal fields remain the source
 * of truth; converting to integer minor units here avoids binary-float drift
 * while the cashier fills cash received or split tender amounts.
 */
export function moneyToMinor(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const normalized = String(value).trim().replace(',', '.')
  if (!/^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/.test(normalized)) return null
  const [whole = '0', fraction = ''] = normalized.split('.')
  const minor = Number(whole) * MONEY_SCALE + Number(fraction.padEnd(2, '0'))
  return Number.isSafeInteger(minor) ? minor : null
}

export function minorToMoney(minor: number): string {
  const sign = minor < 0 ? '-' : ''
  const absolute = Math.abs(minor)
  return `${sign}${Math.floor(absolute / MONEY_SCALE)}.${String(absolute % MONEY_SCALE).padStart(2, '0')}`
}

export function remainingMinor(total: number | string, amounts: Array<number | string>): number | null {
  const totalMinor = moneyToMinor(total)
  if (totalMinor === null) return null
  let allocated = 0
  for (const amount of amounts) {
    const minor = moneyToMinor(amount)
    if (minor === null) continue
    allocated += minor
  }
  return totalMinor - allocated
}

export function cashPresetMinorValues(total: number | string): number[] {
  const totalMinor = moneyToMinor(total)
  if (totalMinor === null) return []
  const steps = [5_000, 10_000, 20_000, 50_000]
  const values = [totalMinor]
  for (const step of steps) values.push(Math.ceil(totalMinor / step) * step)
  return [...new Set(values)].slice(0, 4)
}
