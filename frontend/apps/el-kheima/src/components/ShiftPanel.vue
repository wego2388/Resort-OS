<script setup lang="ts">
// ⚠️ باج حقيقي حقيقي اتكشف حي (2026-07-06، جولة اختبار كاشير كامل): الباك
// إند فيه دورة وردية كاشير كاملة وشغالة 100% (فتح/إغلاق/عدّ كاش بالفئة/
// تقرير نهاية وردية + PDF/ملاحظة تسليم — GET/POST /finance/shifts/*) لكن
// مفيش زر واحد أو شاشة واحدة في `el-kheima` بالكامل تستخدمها — يعني كاشير
// حقيقي كان مستحيل يفتح وردية أو يقفلها بعدّ الكاش من التطبيق نفسه من أول
// يوم PROJECT_STATUS.md اتكتب فيه إن "POS Money Count" ✅ مكتمل. نفس فئة
// باج "الموديل والـ API موجودين، الفرونت إند صفر" الموثّقة قبل كده لموديولات
// تانية — هنا الفجوة في الفرونت إند مش الباك إند.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppModal, AppButton, AppInput, useToast } from '@resort-os/ui'

const auth = useAuthStore()
const toast = useToast()
const { t } = useI18n()
const { formatMoney, formatTime } = useStaffFormat()

// branchId اختياري — لو مش ممرور يُقرأ من auth store (السلوك الافتراضي).
// تصريحه صريحًا هنا يسمح بـ: (1) استخدام الـ component في سياق branch محدد
// مختلف عن branch المستخدم الحالي (مثلًا: super admin يراقب فرع معين)،
// (2) unit tests تمرر branchId من غير ما تحتاج mock للـ store.
const props = withDefaults(defineProps<{ branchId?: number }>(), {
  branchId: undefined,
})

const resolvedBranchId = computed(() => props.branchId ?? auth.branchId ?? 1)

// بيتأشّر لأي parent مهتم (زي ShiftDashboardView، S-01) إن الوردية اتفتحت/
// اتقفلت — عشان يعيد تحميل ملخص المبيعات/سجل الفواتير بتاعه، من غير ما
// يحتاج polling دوري أو يكرر منطق الفتح/القفل بنفسه.
const emit = defineEmits<{ 'shift-changed': [] }>()

interface Shift {
  id: number; opened_at: string; opening_float: string | number
  status: string; expected_cash?: string | number | null
}

const shift = ref<Shift | null>(null)
const loading = ref(false)
const handoverNote = ref<string | null>(null)

const openModal = ref(false)
const openingFloat = ref('0')
const openNotes = ref('')
const opening = ref(false)

const closeModal = ref(false)
const closing = ref(false)
const closeNotes = ref('')
const closeHandoverNote = ref('')
// فئات العملات المتداولة — EGP ورق + عملات أجنبية شائعة في المنتجع
// كل عملة لها قائمة فئات خاصة بها وعدد منفصل
interface CurrencyGroup {
  code: string
  denominations: number[]
}
const CURRENCY_GROUPS: CurrencyGroup[] = [
  { code: 'EGP', denominations: [200, 100, 50, 20, 10, 5, 1] },
  { code: 'USD', denominations: [100, 50, 20, 10, 5, 1] },
  { code: 'EUR', denominations: [100, 50, 20, 10, 5, 1] },
]
// اسم العملة المترجم (مش رمزها ISO — الرمز نفسه بيتعرض زي ما هو دايمًا)
function currencyLabel(code: string): string {
  return t(`backoffice.shiftPanel.currency.${code}`, code)
}

// counts[currency][denomination] = quantity
const counts = ref<Record<string, Record<number, number>>>(
  Object.fromEntries(
    CURRENCY_GROUPS.map((g) => [g.code, Object.fromEntries(g.denominations.map((d) => [d, 0]))])
  )
)

// أسعار الصرف الحالية — تُجلب عند فتح modal القفل لعرض EGP equivalent تقريبي
// قبل التأكيد (القيمة الحقيقية تحسبها الباك إند عند القفل الفعلي)
const fxRates = ref<Record<string, number>>({})

async function fetchFxRates() {
  try {
    // نجلب كل أسعار الصرف (pagination كامل — size=200 يكفي لأي عدد عملات متوقع)
    const { data } = await api.get(ENDPOINTS.finance.exchangeRates, { params: { size: 200 } })
    const items: { from_currency: string; to_currency: string; rate: string | number }[] = data?.items ?? data ?? []
    const map: Record<string, number> = {}
    for (const r of items) {
      // السعر المباشر: USD→EGP
      if (r.to_currency === 'EGP' && !map[r.from_currency]) {
        map[r.from_currency] = Number(r.rate)
      }
      // السعر المعكوس: EGP→USD → نقلبه (inverse fallback مطابق للباك إند)
      if (r.from_currency === 'EGP' && r.to_currency !== 'EGP' && !map[r.to_currency]) {
        const invRate = Number(r.rate)
        if (invRate > 0) map[r.to_currency] = 1 / invRate
      }
    }
    fxRates.value = map
  } catch {
    // تجاهل هادئ — الـ EGP equivalent سيظهر فقط لو الأسعار متاحة
    fxRates.value = {}
  }
}

// إجمالي EGP فقط (للعرض السريع قبل القفل — الإجمالي الحقيقي يحسبه الباك إند بأسعار الصرف)
const countedTotalEGP = computed(() =>
  CURRENCY_GROUPS.find((g) => g.code === 'EGP')!.denominations
    .reduce((sum, d) => sum + d * (Number(counts.value['EGP'][d]) || 0), 0)
)
// هل في عملات أجنبية بلا سعر صرف معروف؟ — يمنع القفل قبل أن يفاجأ الكاشير بـ 400
const hasMissingFxRate = computed(() =>
  foreignCashPreview.value.some((fc) => fc.egp == null)
)

// إجمالي كل عملة أجنبية مع الـ EGP equivalent التقريبي (بناءً على أسعار الصرف المجلوبة)
// هذا تقريب للعرض فقط — القيمة الرسمية تحسبها الباك إند عند القفل
const foreignCashPreview = computed(() =>
  CURRENCY_GROUPS.filter((g) => g.code !== 'EGP').flatMap((g) => {
    const total = g.denominations.reduce(
      (sum, d) => sum + d * (Number(counts.value[g.code][d]) || 0),
      0
    )
    if (total === 0) return []
    const rate = fxRates.value[g.code]
    return [{ code: g.code, total, egp: rate ? total * rate : null }]
  })
)

// الإجمالي الكلي التقريبي بالجنيه (EGP + ما يعادله من العملات الأجنبية)
const grandTotalEGPApprox = computed(() => {
  const foreign = foreignCashPreview.value.reduce(
    (sum, fc) => (fc.egp != null ? sum + fc.egp : sum),
    0
  )
  const allForeignHaveRates = foreignCashPreview.value.every((fc) => fc.egp != null)
  if (!allForeignHaveRates) return null
  return countedTotalEGP.value + foreign
})
const lastCloseResult = ref<{
  variance: number; expected: number
  foreign_currency_summary?: { currency: string; total_foreign: number; egp_equivalent: number }[]
  counted_cash_egp?: number
  reconciliation_ok?: boolean | null
  reconciliation_warning?: string | null
} | null>(null)

// ملاحظة (جولة مراجعة Codex الأولى — M3): آلية رفض القفل بسبب فرق الكاش
// أُلغيت بالكامل من الباك إند (قرار Mohamed 2026-07-14: الوردية تُقفل دايمًا
// والفرق يُسجَّل كتحذير للمحاسب). فمسار "force_close + موافقة مدير لتخطي
// الرفض" اللي كان هنا بقى dead code (الباك إند عمره ما بيرجّع خطأ الفرق ده)
// — اتشال عشان الفرونت إند والباك إند يتفقوا. الفرق الكبير بيظهر كـ
// reconciliation_warning في applyCloseResult تحت.

async function fetchCurrentShift() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.shiftsCurrent, { params: { branch_id: resolvedBranchId.value } })
    shift.value = data
  } catch (e: any) {
    if (e?.response?.status === 404) shift.value = null
    else { toast.error(t('backoffice.shiftPanel.loadError')) }
  } finally { loading.value = false }
}

async function openOpenModal() {
  try {
    const { data } = await api.get(ENDPOINTS.finance.shiftHandoverNote, { params: { branch_id: resolvedBranchId.value } })
    handoverNote.value = data?.handover_note ?? null
  } catch { handoverNote.value = null }
  openingFloat.value = '0'
  openNotes.value = ''
  openModal.value = true
}

async function confirmOpen() {
  opening.value = true
  // تحقق صريح: opening_float لازم يكون رقم صحيح >= 0
  const floatVal = parseFloat(openingFloat.value)
  if (isNaN(floatVal) || floatVal < 0) {
    toast.error(t('backoffice.shiftPanel.invalidOpeningFloat'))
    opening.value = false
    return
  }
  try {
    const { data } = await api.post(ENDPOINTS.finance.shiftsOpen, {
      branch_id: resolvedBranchId.value,
      opening_float: floatVal,
      notes: openNotes.value || undefined,
    })
    shift.value = data
    openModal.value = false
    toast.success(t('backoffice.shiftPanel.openedSuccess'))
    emit('shift-changed')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.shiftPanel.openError'))
  } finally { opening.value = false }
}

function openCloseModalFn() {
  // إعادة تصفير عدّادات كل العملات
  for (const group of CURRENCY_GROUPS) {
    for (const d of group.denominations) counts.value[group.code][d] = 0
  }
  closeNotes.value = ''
  closeHandoverNote.value = ''
  lastCloseResult.value = null
  closeModal.value = true
  // نجلب أسعار الصرف بالتوازي لعرض EGP equivalent تقريبي
  fetchFxRates()
}

function applyCloseResult(data: any) {
  lastCloseResult.value = {
    variance:                Number(data.variance ?? 0),
    expected:                Number(data.expected_cash ?? 0),
    foreign_currency_summary: data.foreign_currency_summary ?? [],
    counted_cash_egp:        data.counted_cash_egp != null ? Number(data.counted_cash_egp) : undefined,
    reconciliation_ok:       data.reconciliation_ok ?? null,
    reconciliation_warning:  data.reconciliation_warning ?? null,
  }
  shift.value = null
  // فرق كاش خارج النطاق المقبول (مش كبير بما يكفي عشان يترفض القفل، لكن
  // يستاهل مراجعة مدير) — بيتحول لتحذير حقيقي للكاشير هنا، مش يتبلع بصمت.
  if (data.reconciliation_ok === false && data.reconciliation_warning) {
    toast.warning(data.reconciliation_warning)
  } else {
    toast.success(t('backoffice.shiftPanel.closedSuccess'))
  }
  emit('shift-changed')
}

async function confirmClose() {
  if (!shift.value) return
  closing.value = true
  try {
    // اجمع كل الفئات من كل العملات اللي عندها قيمة > 0
    const cash_count: { denomination: number; currency: string; quantity: number }[] = []
    for (const group of CURRENCY_GROUPS) {
      for (const d of group.denominations) {
        const qty = Number(counts.value[group.code][d]) || 0
        if (qty > 0) cash_count.push({ denomination: d, currency: group.code, quantity: qty })
      }
    }
    const payload = {
      cash_count,
      notes: closeNotes.value || undefined,
      handover_note: closeHandoverNote.value || undefined,
    }
    const { data } = await api.post(ENDPOINTS.finance.shiftClose(shift.value.id), payload)
    applyCloseResult(data)
  } catch (e: any) {
    // الوردية بتُقفل دايمًا الآن (مفيش رفض بسبب الفرق) — أي خطأ هنا حقيقي
    // (عدّ ناقص، سعر صرف مفقود، صلاحية) بيتعرض كتوست مباشر بالرسالة الكاملة.
    const detail: string = e?.response?.data?.detail ?? ''
    toast.error(detail || t('backoffice.shiftPanel.closeError'))
  } finally { closing.value = false }
}

onMounted(fetchCurrentShift)
</script>

<template>
  <div class="flex items-center gap-2">
    <template v-if="loading">
      <span class="text-xs text-gray-400">...</span>
    </template>
    <template v-else-if="shift">
      <span class="hidden items-center gap-1.5 rounded-full bg-green-50 px-2.5 py-1 text-xs font-bold text-green-700 dark:bg-green-950/40 dark:text-green-300 md:flex">
        🟢 {{ t('backoffice.shiftPanel.openLabel', { time: formatTime(shift.opened_at) }) }}
      </span>
      <AppButton size="sm" variant="outline" @click="openCloseModalFn">{{ t('backoffice.shiftPanel.closeButton') }}</AppButton>
    </template>
    <template v-else>
      <span class="hidden items-center gap-1.5 rounded-full bg-gray-100 px-2.5 py-1 text-xs font-bold text-gray-400 dark:bg-gray-800 dark:text-gray-400 md:flex">
        🔒 {{ t('backoffice.shiftDashboard.noOpenShift') }}
      </span>
      <AppButton size="sm" variant="primary" @click="openOpenModal">{{ t('backoffice.shiftPanel.openButton') }}</AppButton>
    </template>

    <!-- Open shift -->
    <AppModal :open="openModal" :title="t('backoffice.shiftPanel.openModalTitle')" size="sm" @close="openModal = false">
      <div class="space-y-3">
        <div v-if="handoverNote" class="rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          📋 {{ t('backoffice.shiftPanel.handoverNote', { note: handoverNote }) }}
        </div>
        <AppInput v-model="openingFloat" type="number" :label="t('backoffice.shiftPanel.openingFloatLabel')" placeholder="0" />
        <AppInput v-model="openNotes" :label="t('backoffice.shiftPanel.notesOptionalLabel')" placeholder="—" />
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <AppButton variant="ghost" size="sm" @click="openModal = false">{{ t('common.cancel') }}</AppButton>
          <AppButton size="sm" :loading="opening" @click="confirmOpen">{{ t('backoffice.shiftPanel.confirmOpenButton') }}</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- Close shift — cash count by denomination -->
    <AppModal :open="closeModal" :title="t('backoffice.shiftPanel.closeModalTitle')" size="md" @close="closeModal = false">
      <div v-if="lastCloseResult" class="space-y-3 py-2">
        <!-- ملخص الخزينة -->
        <div class="text-center space-y-1">
          <p class="text-sm text-gray-500">{{ t('backoffice.shiftPanel.expectedCashLabel', { amount: formatMoney(lastCloseResult.expected, 'EGP') }) }}</p>
          <p v-if="lastCloseResult.counted_cash_egp != null" class="text-sm text-gray-500">
            {{ t('backoffice.shiftPanel.totalTreasuryEGP', { amount: formatMoney(lastCloseResult.counted_cash_egp, 'EGP') }) }}
          </p>
          <p class="text-2xl font-black"
            :class="lastCloseResult.variance === 0
              ? 'text-green-600 dark:text-green-300'
              : lastCloseResult.variance > 0
                ? 'text-blue-600 dark:text-blue-300'
                : 'text-red-600 dark:text-red-300'">
            {{ lastCloseResult.variance > 0 ? t('backoffice.shiftPanel.varianceIncrease') : lastCloseResult.variance < 0 ? t('backoffice.shiftPanel.varianceShortage') : t('backoffice.shiftPanel.varianceMatch') }}
            {{ formatMoney(Math.abs(lastCloseResult.variance), 'EGP') }}
          </p>
        </div>
        <!-- تحذير مطابقة الكاش — فرق أكبر من الطبيعي، الوردية اتقفلت لكن
             لازم مدير يراجعها. ثابت في الشاشة (مش توست بس بيختفي). -->
        <div v-if="lastCloseResult.reconciliation_ok === false" class="rounded-lg border border-amber-200 bg-amber-50 p-2.5 dark:border-amber-800 dark:bg-amber-950/40">
          <p class="text-xs font-bold text-amber-800 dark:text-amber-300">{{ lastCloseResult.reconciliation_warning }}</p>
        </div>
        <!-- ملخص العملات الأجنبية لو موجودة -->
        <div v-if="lastCloseResult.foreign_currency_summary?.length" class="space-y-1 rounded-lg bg-blue-50 p-2.5 dark:bg-blue-950/40">
          <p class="text-xs font-bold text-blue-700 dark:text-blue-300">{{ t('backoffice.shiftPanel.foreignCurrenciesCounted') }}</p>
          <div v-for="fc in lastCloseResult.foreign_currency_summary" :key="fc.currency"
            class="flex justify-between text-xs text-blue-800 dark:text-blue-300">
            <span>{{ fc.currency }}: {{ formatMoney(fc.total_foreign, fc.currency) }}</span>
            <span>= {{ formatMoney(fc.egp_equivalent, 'EGP') }}</span>
          </div>
        </div>
      </div>
      <div v-else class="space-y-4">
        <!-- جدول عدّ لكل عملة -->
        <div v-for="group in CURRENCY_GROUPS" :key="group.code">
          <div class="flex items-center gap-2 mb-1.5">
            <span class="text-xs font-bold px-2 py-0.5 rounded-full"
              :class="group.code === 'EGP'
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300'
                : 'bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300'">
              {{ group.code }}
            </span>
            <span class="text-xs text-gray-500">{{ currencyLabel(group.code) }}</span>
          </div>
          <table class="w-full text-sm">
            <thead>
              <tr class="text-gray-400 text-xs">
                <th class="text-right py-1">{{ t('backoffice.shiftPanel.denominationCol') }}</th>
                <th class="text-right py-1">{{ t('backoffice.shiftPanel.countCol') }}</th>
                <th class="text-right py-1">{{ t('backoffice.shiftPanel.totalCol') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in group.denominations" :key="d" class="border-t border-stone-100 dark:border-stone-800">
                <td class="py-1 font-semibold text-gray-700 dark:text-gray-300">
                  {{ formatMoney(d, group.code) }}
                </td>
                <td class="py-1">
                  <AppInput
                    type="number"
                    :model-value="String(counts[group.code][d])"
                    @update:model-value="counts[group.code][d] = Number($event) || 0"
                    min="0"
                    class="w-20 text-center"
                  />
                </td>
                <td class="py-1 text-gray-500 dark:text-gray-400">
                  {{ formatMoney(d * (Number(counts[group.code][d]) || 0), group.code) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- إجمالي الجنيه + تنبيه لو في عملات أجنبية -->
        <div class="border-t border-stone-200 pt-2 space-y-1">
          <div class="flex justify-between items-center font-bold">
            <span>{{ t('backoffice.shiftPanel.totalEGP') }}</span>
            <span>{{ formatMoney(countedTotalEGP, 'EGP') }}</span>
          </div>
          <!-- عرض EGP equivalent تقريبي للعملات الأجنبية -->
          <template v-if="foreignCashPreview.length > 0">
            <div v-for="fc in foreignCashPreview" :key="fc.code"
              class="flex justify-between items-center text-sm text-blue-700 dark:text-blue-300">
              <span>{{ fc.code }}: {{ formatMoney(fc.total, fc.code) }}</span>
              <span v-if="fc.egp != null">≈ {{ formatMoney(fc.egp, 'EGP') }}</span>
              <span v-else class="text-xs text-amber-600 dark:text-amber-400">{{ t('backoffice.shiftPanel.missingFxRate') }}</span>
            </div>
            <div v-if="grandTotalEGPApprox != null"
              class="flex justify-between items-center font-bold text-green-700 dark:text-green-300 border-t border-stone-200 pt-1 mt-1">
              <span>{{ t('backoffice.shiftPanel.grandTotalApprox') }}</span>
              <span>≈ {{ formatMoney(grandTotalEGPApprox, 'EGP') }}</span>
            </div>
            <p v-if="foreignCashPreview.some(fc => fc.egp == null)"
              class="rounded bg-amber-50 px-2 py-1 text-xs text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
              ⚠️ {{ t('backoffice.shiftPanel.missingFxRateWarning') }}
            </p>
            <p v-else class="rounded bg-blue-50 px-2 py-1 text-xs text-blue-600 dark:bg-blue-950/40 dark:text-blue-300">
              💱 {{ t('backoffice.shiftPanel.approxNote') }}
            </p>
          </template>
        </div>
        <AppInput v-model="closeNotes" :label="t('backoffice.shiftPanel.notesOptionalLabel')" placeholder="—" />
        <AppInput v-model="closeHandoverNote" :label="t('backoffice.shiftPanel.handoverNoteOptionalLabel')" placeholder="—" />
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <AppButton variant="ghost" size="sm" @click="closeModal = false">{{ lastCloseResult ? t('common.close') : t('common.cancel') }}</AppButton>
          <AppButton v-if="!lastCloseResult" size="sm" :loading="closing" :disabled="hasMissingFxRate" @click="confirmClose">{{ t('backoffice.shiftPanel.confirmCloseButton') }}</AppButton>
        </div>
      </template>
    </AppModal>
  </div>
</template>
