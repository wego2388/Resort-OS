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
import { api } from '@resort-os/core'
import { useAuthStore } from '@resort-os/core'
import { AppModal, AppButton, AppInput, useToast } from '@resort-os/ui'
import PinGuardModal from './PinGuardModal.vue'

const auth = useAuthStore()
const toast = useToast()
const branchId = computed(() => auth.branchId ?? 1)

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
  label: string
  denominations: number[]
}
const CURRENCY_GROUPS: CurrencyGroup[] = [
  { code: 'EGP', label: 'جنيه مصري',    denominations: [200, 100, 50, 20, 10, 5, 1] },
  { code: 'USD', label: 'دولار أمريكي', denominations: [100, 50, 20, 10, 5, 1] },
  { code: 'EUR', label: 'يورو',         denominations: [100, 50, 20, 10, 5, 1] },
]

// counts[currency][denomination] = quantity
const counts = ref<Record<string, Record<number, number>>>(
  Object.fromEntries(
    CURRENCY_GROUPS.map((g) => [g.code, Object.fromEntries(g.denominations.map((d) => [d, 0]))])
  )
)

// إجمالي EGP فقط (للعرض السريع قبل القفل — الإجمالي الحقيقي يحسبه الباك إند بأسعار الصرف)
const countedTotalEGP = computed(() =>
  CURRENCY_GROUPS.find((g) => g.code === 'EGP')!.denominations
    .reduce((sum, d) => sum + d * (Number(counts.value['EGP'][d]) || 0), 0)
)
// هل في عملات أجنبية تم إدخالها؟
const hasForeignCash = computed(() =>
  CURRENCY_GROUPS.filter((g) => g.code !== 'EGP').some((g) =>
    g.denominations.some((d) => (Number(counts.value[g.code][d]) || 0) > 0)
  )
)
const lastCloseResult = ref<{
  variance: number; expected: number
  foreign_currency_summary?: { currency: string; total_foreign: number; egp_equivalent: number }[]
  counted_cash_egp?: number
  reconciliation_ok?: boolean | null
  reconciliation_warning?: string | null
} | null>(null)

// فرق كاش أكبر من الحد المسموح (services.close_shift) بيترفض القفل بـ 400
// — بدل ما يفضل الكاشير معلّق لحد ما مدير يتفرّغ، بوابة PIN (wagdy.md بند
// S-06) بتسمح بتخطي الرفض فورًا لو مدير حاضر فعليًا. نفس payload القفل
// الأصلي بيتبعت تاني مع force_close=true + موافقة المدير.
const varianceOverride = ref(false)
const forceCloseError = ref('')
const pendingClosePayload = ref<Record<string, unknown> | null>(null)

async function fetchCurrentShift() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/finance/shifts/current', { params: { branch_id: branchId.value } })
    shift.value = data
  } catch (e: any) {
    if (e?.response?.status === 404) shift.value = null
    else { console.error(e); toast.error('تعذّر تحميل حالة الوردية') }
  } finally { loading.value = false }
}

async function openOpenModal() {
  try {
    const { data } = await api.get('/api/v1/finance/shifts/handover-note', { params: { branch_id: branchId.value } })
    handoverNote.value = data?.handover_note ?? null
  } catch { handoverNote.value = null }
  openingFloat.value = '0'
  openNotes.value = ''
  openModal.value = true
}

async function confirmOpen() {
  opening.value = true
  try {
    const { data } = await api.post('/api/v1/finance/shifts/open', {
      branch_id: branchId.value,
      opening_float: Number(openingFloat.value) || 0,
      notes: openNotes.value || undefined,
    })
    shift.value = data
    openModal.value = false
    toast.success('تم فتح الوردية')
    emit('shift-changed')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر فتح الوردية')
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
  varianceOverride.value = false
  forceCloseError.value = ''
  pendingClosePayload.value = null
  closeModal.value = true
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
  varianceOverride.value = false
  pendingClosePayload.value = null
  // فرق كاش خارج النطاق المقبول (مش كبير بما يكفي عشان يترفض القفل، لكن
  // يستاهل مراجعة مدير) — بيتحول لتحذير حقيقي للكاشير هنا، مش يتبلع بصمت.
  if (data.reconciliation_ok === false && data.reconciliation_warning) {
    toast.warning(data.reconciliation_warning)
  } else {
    toast.success('تم قفل الوردية')
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
    pendingClosePayload.value = payload
    const { data } = await api.post(`/api/v1/finance/shifts/${shift.value.id}/close`, payload)
    applyCloseResult(data)
  } catch (e: any) {
    const detail: string = e?.response?.data?.detail ?? ''
    // فرق كاش كبير جدًا نسبةً لمبيعات الوردية بيترفض بالكامل من الباك إند
    // (400، services.close_shift) — بدل ما نرفض للأبد، افتح بوابة موافقة
    // مدير بالـ PIN لتخطي الحد (wagdy.md بند S-06) بدل التوست العادي.
    if (e?.response?.status === 400 && detail.includes('يتخطى الحد المسموح')) {
      varianceOverride.value = true
    } else {
      toast.error(detail || 'تعذّر قفل الوردية — تأكد من عدّ الكاش')
    }
  } finally { closing.value = false }
}

async function onForceCloseApproved(payload: { approverUserId: number | null; approverPin: string | null }) {
  if (!shift.value || !pendingClosePayload.value) return
  closing.value = true
  forceCloseError.value = ''
  try {
    const { data } = await api.post(`/api/v1/finance/shifts/${shift.value.id}/close`, {
      ...pendingClosePayload.value,
      force_close: true,
      approver_user_id: payload.approverUserId,
      approver_pin: payload.approverPin,
    })
    applyCloseResult(data)
  } catch (e: any) {
    // varianceOverride يفضل true — المستخدم يقدر يصحح الـ PIN ويحاول تاني
    forceCloseError.value = e?.response?.data?.detail ?? 'تعذّر تخطي الفرق — تأكد من الـ PIN'
  } finally { closing.value = false }
}

function fmtTime(iso?: string) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' })
}

onMounted(fetchCurrentShift)
</script>

<template>
  <div class="flex items-center gap-2">
    <template v-if="loading">
      <span class="text-xs text-gray-400">...</span>
    </template>
    <template v-else-if="shift">
      <span class="hidden md:flex items-center gap-1.5 text-xs font-bold text-green-700 bg-green-50 px-2.5 py-1 rounded-full">
        🟢 وردية مفتوحة — {{ fmtTime(shift.opened_at) }}
      </span>
      <AppButton size="sm" variant="outline" @click="openCloseModalFn">قفل الوردية</AppButton>
    </template>
    <template v-else>
      <span class="hidden md:flex items-center gap-1.5 text-xs font-bold text-gray-400 bg-gray-100 px-2.5 py-1 rounded-full">
        🔒 لا توجد وردية مفتوحة
      </span>
      <AppButton size="sm" variant="primary" @click="openOpenModal">فتح وردية</AppButton>
    </template>

    <!-- Open shift -->
    <AppModal :open="openModal" title="فتح وردية جديدة" size="sm" @close="openModal = false">
      <div class="space-y-3">
        <div v-if="handoverNote" class="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-2.5">
          📋 ملاحظة تسليم من آخر وردية: {{ handoverNote }}
        </div>
        <AppInput v-model="openingFloat" type="number" label="رصيد الافتتاح (كاش)" placeholder="0" />
        <AppInput v-model="openNotes" label="ملاحظات (اختياري)" placeholder="—" />
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <AppButton variant="ghost" size="sm" @click="openModal = false">إلغاء</AppButton>
          <AppButton size="sm" :loading="opening" @click="confirmOpen">فتح الوردية</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- Close shift — cash count by denomination -->
    <AppModal :open="closeModal" title="قفل الوردية — عدّ الكاش" size="md" @close="closeModal = false">
      <div v-if="lastCloseResult" class="space-y-3 py-2">
        <!-- ملخص الخزينة -->
        <div class="text-center space-y-1">
          <p class="text-sm text-gray-500">الكاش المتوقع: {{ lastCloseResult.expected.toFixed(2) }} ج</p>
          <p v-if="lastCloseResult.counted_cash_egp != null" class="text-sm text-gray-500">
            إجمالي الخزينة (EGP): {{ lastCloseResult.counted_cash_egp.toFixed(2) }} ج
          </p>
          <p class="text-2xl font-black"
            :class="lastCloseResult.variance === 0 ? 'text-green-600' : lastCloseResult.variance > 0 ? 'text-blue-600' : 'text-red-600'">
            {{ lastCloseResult.variance > 0 ? '▲ زيادة' : lastCloseResult.variance < 0 ? '▼ عجز' : '✓ مطابق' }}
            {{ Math.abs(lastCloseResult.variance).toFixed(2) }} ج
          </p>
        </div>
        <!-- تحذير مطابقة الكاش — فرق أكبر من الطبيعي، الوردية اتقفلت لكن
             لازم مدير يراجعها. ثابت في الشاشة (مش توست بس بيختفي). -->
        <div v-if="lastCloseResult.reconciliation_ok === false" class="bg-amber-50 border border-amber-200 rounded-lg p-2.5">
          <p class="text-xs font-bold text-amber-800">{{ lastCloseResult.reconciliation_warning }}</p>
        </div>
        <!-- ملخص العملات الأجنبية لو موجودة -->
        <div v-if="lastCloseResult.foreign_currency_summary?.length" class="bg-blue-50 rounded-lg p-2.5 space-y-1">
          <p class="text-xs font-bold text-blue-700">💱 العملات الأجنبية المعدودة</p>
          <div v-for="fc in lastCloseResult.foreign_currency_summary" :key="fc.currency"
            class="flex justify-between text-xs text-blue-800">
            <span>{{ fc.currency }}: {{ fc.total_foreign.toFixed(2) }}</span>
            <span>= {{ fc.egp_equivalent.toFixed(2) }} ج</span>
          </div>
        </div>
      </div>
      <div v-else class="space-y-4">
        <!-- جدول عدّ لكل عملة -->
        <div v-for="group in CURRENCY_GROUPS" :key="group.code">
          <div class="flex items-center gap-2 mb-1.5">
            <span class="text-xs font-bold px-2 py-0.5 rounded-full"
              :class="group.code === 'EGP' ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'">
              {{ group.code }}
            </span>
            <span class="text-xs text-gray-500">{{ group.label }}</span>
          </div>
          <table class="w-full text-sm">
            <thead>
              <tr class="text-gray-400 text-xs">
                <th class="text-right py-1">الفئة</th>
                <th class="text-right py-1">العدد</th>
                <th class="text-right py-1">الإجمالي</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in group.denominations" :key="d" class="border-t border-stone-100">
                <td class="py-1 font-semibold text-gray-700">
                  {{ d }} {{ group.code === 'EGP' ? 'ج' : group.code }}
                </td>
                <td class="py-1">
                  <input type="number" min="0" v-model.number="counts[group.code][d]"
                    class="w-20 px-2 py-1 rounded-lg border border-stone-200 text-center" />
                </td>
                <td class="py-1 text-gray-500">
                  {{ (d * (Number(counts[group.code][d]) || 0)).toFixed(2) }}
                  {{ group.code === 'EGP' ? 'ج' : group.code }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- إجمالي الجنيه + تنبيه لو في عملات أجنبية -->
        <div class="border-t border-stone-200 pt-2 space-y-1">
          <div class="flex justify-between items-center font-bold">
            <span>إجمالي الجنيه المصري</span>
            <span>{{ countedTotalEGP.toFixed(2) }} ج</span>
          </div>
          <p v-if="hasForeignCash" class="text-xs text-blue-600 bg-blue-50 rounded px-2 py-1">
            💱 يوجد عملات أجنبية — الإجمالي الكلي بالجنيه سيحسبه النظام بأسعار الصرف عند القفل
          </p>
        </div>
        <AppInput v-model="closeNotes" label="ملاحظات (اختياري)" placeholder="—" />
        <AppInput v-model="closeHandoverNote" label="ملاحظة تسليم للوردية الجاية (اختياري)" placeholder="—" />
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <AppButton variant="ghost" size="sm" @click="closeModal = false">{{ lastCloseResult ? 'إغلاق' : 'إلغاء' }}</AppButton>
          <AppButton v-if="!lastCloseResult" size="sm" :loading="closing" @click="confirmClose">تأكيد القفل</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- فرق كاش أكبر من الحد المسموح — بوابة موافقة مدير لتخطي الرفض (S-06) -->
    <PinGuardModal
      v-if="varianceOverride"
      :min-level="60"
      title="فرق كاش كبير — تخطي بموافقة مدير"
      message="الفرق بين الكاش المتوقع والمعدود أكبر من الحد المسموح لهذه الوردية. مدير+ يقدر يعتمد القفل رغم كده."
      :loading="closing"
      :error-message="forceCloseError"
      @approved="onForceCloseApproved"
      @cancel="varianceOverride = false"
    />
  </div>
</template>
