<script setup lang="ts">
// كالندر أسابيع الملكية الجزئية (52 أسبوع/سنة) + طباعة PDF — استُخرج من
// TimeshareView.vue (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppIcon, EmptyState, LoadingState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

interface CalendarContract { id: number; customer_name: string; rci_included: boolean; status: string; contract_number?: string; room_type: string }
interface CalendarWeek { week: number; start_date: string; end_date: string; is_current: boolean; is_past: boolean; contracts: CalendarContract[] }
interface CalendarMonth { month: number; month_name: string; weeks: CalendarWeek[] }

const toast = useToast()
const { t, locale } = useI18n()
const { formatDate } = useStaffFormat()
const auth = useAuthStore()
const branchId = computed(() => props.branchId)

const calYear = ref(new Date().getFullYear())
const calLoading = ref(false)
const calendar = ref<{ calendar: CalendarMonth[]; total_booked_weeks: number }>({ calendar: [], total_booked_weeks: 0 })

async function loadCalendar() {
  calLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/calendar', { params: { branch_id: branchId.value, year: calYear.value } })
    calendar.value = r.data
  } catch (e) { toast.error(t('backoffice.timeshare.msg.loadCalendarError')) } finally { calLoading.value = false }
}

function calContractClass(c: CalendarContract) {
  if (c.rci_included) return 'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-800'
  const m: Record<string, string> = {
    'Studio': 'bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-800',
    'Chalet': 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800',
  }
  return m[c.room_type] || 'bg-stone-100 dark:bg-gray-700 text-stone-600 dark:text-stone-300 border-stone-200 dark:border-border'
}

// ── Print calendar (لعرض تقديمي في اجتماعات المبيعات) ──────────────────────
// طباعة/تصدير PDF من المتصفح مباشرة — نفس نمط QRGeneratorView.printSelected،
// لأن كالندر 52 أسبوع أصلاً layout مرئي (شبكة)، مش بيانات صفوف تصلح لملف Excel.
function escapeHtml(s: string): string {
  const map: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
  return s.replace(/[&<>"']/g, (ch) => map[ch])
}

function calContractPrintClass(c: CalendarContract): string {
  if (c.rci_included) return 'rci'
  const m: Record<string, string> = { 'Studio': 'studio', 'Chalet': 'chalet' }
  return m[c.room_type] || 'other'
}

function printCalendarView() {
  if (!calendar.value.calendar.length) { toast.error(t('backoffice.timeshare.msg.noCalendarData')); return }

  const dir = locale.value === 'ar' ? 'rtl' : 'ltr'
  const exportedAt = formatDate(new Date(), { dateStyle: 'medium', timeStyle: 'short' } as Intl.DateTimeFormatOptions)
  const exportedBy = auth.user?.full_name || auth.user?.username || '—'

  const monthsHtml = calendar.value.calendar.map(month => `
    <div class="month-card">
      <div class="month-header">${escapeHtml(month.month_name)} ${calYear.value}</div>
      <div class="weeks">
        ${month.weeks.map(week => `
          <div class="week-row ${week.is_current ? 'current' : ''} ${week.is_past && !week.is_current ? 'past' : ''}">
            <span class="week-no">${week.week}</span>
            <span class="week-date">${escapeHtml(week.start_date?.slice(5) ?? '')}</span>
            <span class="week-contracts">
              ${week.contracts.length
                ? week.contracts.map((c: CalendarContract) => `<span class="tag ${calContractPrintClass(c)}">${escapeHtml((c.customer_name ?? '').split(' ').slice(0, 2).join(' '))}${c.rci_included ? ' ✦' : ''}</span>`).join('')
                : '<span class="empty">—</span>'}
            </span>
          </div>
        `).join('')}
      </div>
    </div>
  `).join('')

  const html = `<!DOCTYPE html>
<html dir="${dir}" lang="${locale.value}">
<head>
<meta charset="UTF-8">
<title>${escapeHtml(t('backoffice.timeshare.calendarPrintTitle', { year: calYear.value }))}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Cairo', 'Segoe UI', sans-serif; margin: 0; padding: 24px; color: #1a1a1a; }
  .header { text-align: center; margin-bottom: 20px; }
  .header h1 { font-size: 20px; margin: 0 0 4px; }
  .header .meta { font-size: 11px; color: #666; }
  .legend { display: flex; gap: 14px; justify-content: center; margin-bottom: 18px; font-size: 11px; flex-wrap: wrap; }
  .legend span { display: inline-flex; align-items: center; gap: 4px; }
  .swatch { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
  .month-card { border: 1px solid #ddd; border-radius: 10px; overflow: hidden; page-break-inside: avoid; }
  .month-header { background: #f5f5f4; padding: 6px 10px; font-weight: 700; font-size: 12px; border-bottom: 1px solid #eee; }
  .week-row { display: flex; align-items: center; gap: 6px; padding: 3px 8px; border-bottom: 1px solid #f3f3f3; font-size: 9px; }
  .week-row.current { background: #fffbeb; }
  .week-row.past { opacity: 0.45; }
  .week-no { width: 16px; text-align: center; color: #999; font-weight: 700; }
  .week-date { width: 40px; color: #aaa; }
  .week-contracts { flex: 1; display: flex; flex-wrap: wrap; gap: 3px; }
  .tag { padding: 1px 5px; border-radius: 6px; font-weight: 700; border: 1px solid; }
  .tag.rci { background: #f3e8ff; color: #7e22ce; border-color: #e9d5ff; }
  .tag.studio { background: #e0f2fe; color: #0369a1; border-color: #bae6fd; }
  .tag.chalet { background: #fef3c7; color: #b45309; border-color: #fde68a; }
  .tag.other { background: #f5f5f4; color: #78716c; border-color: #e7e5e4; }
  .empty { color: #d6d3d1; }
  @media print {
    @page { size: A4 landscape; margin: 12mm; }
    .no-print { display: none; }
  }
</style>
</head>
<body>
  <div class="header">
    <h1>📅 ${escapeHtml(t('backoffice.timeshare.calendarPrintTitle', { year: calYear.value }))}</h1>
    <div class="meta">
      ${escapeHtml(t('backoffice.timeshare.bookedWeeksPrint', { count: calendar.value.total_booked_weeks || 0 }))} ·
      ${escapeHtml(t('backoffice.timeshare.exportedByPrint', { name: exportedBy }))} · ${escapeHtml(t('backoffice.timeshare.exportedAtPrint', { date: exportedAt }))}
    </div>
  </div>
  <div class="legend">
    <span><span class="swatch" style="background:#bae6fd"></span> ${escapeHtml(t('backoffice.timeshare.unitTypes.Studio'))}</span>
    <span><span class="swatch" style="background:#fde68a"></span> ${escapeHtml(t('backoffice.timeshare.unitTypes.Chalet'))}</span>
    <span><span class="swatch" style="background:#e9d5ff"></span> RCI ✦</span>
  </div>
  <div class="grid">
    ${monthsHtml}
  </div>
  <div class="no-print" style="text-align:center;margin-top:20px;color:#999;font-size:12px;">${escapeHtml(t('backoffice.timeshare.printHint'))}</div>
</body>
</html>`

  const win = window.open('', '_blank')
  if (!win) { toast.error(t('backoffice.timeshare.msg.popupBlocked')); return }
  win.document.write(html)
  win.document.close()
  win.focus()
  setTimeout(() => win.print(), 500)
}

onMounted(loadCalendar)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div class="flex items-center gap-3">
        <button type="button" :aria-label="t('backoffice.timeshare.previousYear')" @click="calYear--; loadCalendar()" class="w-11 h-11 rounded-xl bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 hover:bg-stone-50 dark:hover:bg-gray-800 text-lg font-bold">−</button>
        <h3 class="text-lg font-black text-gray-900 dark:text-gray-100">{{ calYear }}</h3>
        <button type="button" :aria-label="t('backoffice.timeshare.nextYear')" @click="calYear++; loadCalendar()" class="w-11 h-11 rounded-xl bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 hover:bg-stone-50 dark:hover:bg-gray-800 text-lg font-bold">＋</button>
      </div>
      <div class="flex items-center gap-3 flex-wrap">
        <span class="text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.bookedWeeks') }}: <span class="text-amber-600 dark:text-amber-300 font-bold">{{ calendar.total_booked_weeks || 0 }}</span></span>
        <AppButton variant="outline" @click="printCalendarView" :title="t('backoffice.timeshare.printCalendarHint')">
          <AppIcon name="print" size="sm" /> {{ t('backoffice.timeshare.printPdf') }}
        </AppButton>
      </div>
    </div>

    <LoadingState v-if="calLoading" :label="t('backoffice.timeshare.loadingCalendar')" />
    <EmptyState v-else-if="!calendar.calendar.length" icon="📅" :title="t('backoffice.timeshare.noCalendarData')" />
    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <div v-for="month in calendar.calendar" :key="month.month" class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border overflow-hidden shadow-sm">
        <div class="px-4 py-2.5 border-b border-stone-100 dark:border-border/50 bg-stone-50 dark:bg-gray-800/60">
          <p class="font-bold text-xs text-gray-700 dark:text-gray-300">{{ month.month_name }} {{ calYear }}</p>
        </div>
        <div class="divide-y divide-stone-100 dark:divide-border">
          <div v-for="week in month.weeks" :key="week.week"
            :class="['flex items-center gap-2 px-3 py-2.5', week.is_current ? 'bg-amber-50 dark:bg-amber-950/30 border-e-2 border-amber-400' : '', week.is_past && !week.is_current ? 'opacity-55' : '']">
            <div class="flex-shrink-0 w-8 text-center">
              <span :class="['text-xs font-bold rounded-full px-2 py-1', week.is_current ? 'bg-amber-500 text-white' : 'text-gray-500 dark:text-gray-400']">{{ week.week }}</span>
            </div>
            <div class="flex-shrink-0 text-xs text-gray-500 dark:text-gray-400 w-20">{{ week.start_date?.slice(5) }} →</div>
            <div class="flex-1 flex flex-wrap gap-1">
              <span v-if="!week.contracts.length" class="text-xs text-gray-400 dark:text-gray-400">—</span>
              <span v-for="c in week.contracts" :key="c.id" :class="['text-xs px-2 py-1 rounded-lg font-bold border', calContractClass(c)]">
                {{ c.customer_name.split(' ').slice(0, 2).join(' ') }}
                <span v-if="c.rci_included" class="ms-1">✦</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
