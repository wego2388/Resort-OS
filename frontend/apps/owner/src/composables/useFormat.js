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
});
const _fmtFull = new Intl.NumberFormat('ar-EG', {
    style: 'decimal',
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
});
export function formatMoney(value) {
    if (value === null || value === undefined || value === '')
        return '—';
    const n = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(n))
        return '—';
    return `${_fmt.format(n)} ج.م`;
}
export function formatMoneyFull(value) {
    if (value === null || value === undefined || value === '')
        return '—';
    const n = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(n))
        return '—';
    return `${_fmtFull.format(n)} ج.م`;
}
export function formatPct(value) {
    if (value === null || value === undefined || value === '')
        return '—';
    const n = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(n))
        return '—';
    const sign = n > 0 ? '+' : '';
    return `${sign}${n.toFixed(1)}%`;
}
export function formatOccupancyPct(value) {
    const n = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(n))
        return '—';
    return `${n.toFixed(0)}%`;
}
/** سهم الاتجاه + لون */
export function deltaClass(value) {
    if (value === null || value === undefined || value === '')
        return 'delta-flat';
    const n = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(n) || n === 0)
        return 'delta-flat';
    return n > 0 ? 'delta-up' : 'delta-down';
}
export function deltaArrow(value) {
    if (value === null || value === undefined || value === '')
        return '';
    const n = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(n) || n === 0)
        return '━';
    return n > 0 ? '↑' : '↓';
}
