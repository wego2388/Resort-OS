/**
 * formatOwnerMoney — يحوّل string/number Decimal من الـ API
 * لرقم مُنسَّق بالجنيه المصري بدون كسور للأرقام الكبيرة.
 *
 * مثال: "12450.00" → "١٢,٤٥٠ ج.م"
 *
 * يستخدم Intl.NumberFormat — بدون مكتبة إضافية.
 */
const _fmt = new Intl.NumberFormat('ar-EG', {
  style: 'decimal',
  maximumFractionDigits: 0,
  minimumFractionDigits: 0,
})

const _fmtFull = new Intl.NumberFormat('ar-EG', {
  style: 'decimal',
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
})

const _fmtPct = new Intl.NumberFormat('ar-EG', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: 'exceptZero',
})

/**
 * Backend timestamps are UTC. Older endpoints serialize a naive ISO value
 * without the trailing `Z`; browsers otherwise read that value as Cairo time
 * and show it three hours early/late. Date-only values are intentionally left
 * unchanged because they represent a business day, not an instant.
 */
export function parseApiDateTime(value: string): Date {
  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value)
  const hasTimeZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)
  return new Date(!isDateOnly && !hasTimeZone ? `${value}Z` : value)
}

export function formatApiTime(value: string): string {
  const date = parseApiDateTime(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' })
}

export function formatApiDateTime(value: string): string {
  const date = parseApiDateTime(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('ar-EG', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(n)) return '—'
  return `${_fmt.format(n)} ج.م`
}

export function formatMoneyFull(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(n)) return '—'
  return `${_fmtFull.format(n)} ج.م`
}

export function formatPct(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(n)) return '—'
  return `${_fmtPct.format(n)}٪`
}

export function formatOccupancyPct(value: string | number): string {
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(n)) return '—'
  return `${n.toFixed(0)}%`
}

/** سهم الاتجاه + لون */
export function deltaClass(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return 'delta-flat'
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(n) || n === 0) return 'delta-flat'
  return n > 0 ? 'delta-up' : 'delta-down'
}

export function deltaArrow(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return ''
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(n) || n === 0) return '━'
  return n > 0 ? '↑' : '↓'
}
