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

const auth = useAuthStore()
const toast = useToast()
const branchId = computed(() => auth.branchId ?? 1)

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
// فئات الجنيه المصري المتداولة فعليًا (ورق) — نفس القائمة المتوقعة في
// CashCountLine الباك إند (denomination + quantity لكل فئة).
const DENOMINATIONS = [200, 100, 50, 20, 10, 5, 1]
const counts = ref<Record<number, number>>(Object.fromEntries(DENOMINATIONS.map((d) => [d, 0])))
const countedTotal = computed(() =>
  DENOMINATIONS.reduce((sum, d) => sum + d * (Number(counts.value[d]) || 0), 0),
)
const lastCloseResult = ref<{ variance: number; expected: number } | null>(null)

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
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر فتح الوردية')
  } finally { opening.value = false }
}

function openCloseModalFn() {
  for (const d of DENOMINATIONS) counts.value[d] = 0
  closeNotes.value = ''
  closeHandoverNote.value = ''
  lastCloseResult.value = null
  closeModal.value = true
}

async function confirmClose() {
  if (!shift.value) return
  closing.value = true
  try {
    const cash_count = DENOMINATIONS
      .filter((d) => (Number(counts.value[d]) || 0) > 0)
      .map((d) => ({ denomination: d, quantity: Number(counts.value[d]) }))
    const { data } = await api.post(`/api/v1/finance/shifts/${shift.value.id}/close`, {
      cash_count,
      notes: closeNotes.value || undefined,
      handover_note: closeHandoverNote.value || undefined,
    })
    lastCloseResult.value = {
      variance: Number(data.variance ?? 0),
      expected: Number(data.expected_cash ?? 0),
    }
    shift.value = null
    toast.success('تم قفل الوردية')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر قفل الوردية — تأكد من عدّ الكاش')
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
      <div v-if="lastCloseResult" class="space-y-2 text-center py-4">
        <p class="text-sm text-gray-500">المتوقع: {{ lastCloseResult.expected.toFixed(2) }} ج</p>
        <p class="text-2xl font-black" :class="lastCloseResult.variance === 0 ? 'text-green-600' : lastCloseResult.variance > 0 ? 'text-blue-600' : 'text-red-600'">
          الفرق: {{ lastCloseResult.variance.toFixed(2) }} ج
        </p>
      </div>
      <div v-else class="space-y-3">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-gray-400 text-xs">
              <th class="text-right py-1.5">الفئة</th>
              <th class="text-right py-1.5">العدد</th>
              <th class="text-right py-1.5">الإجمالي</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in DENOMINATIONS" :key="d" class="border-t border-stone-100">
              <td class="py-1.5 font-semibold text-gray-700">{{ d }} ج</td>
              <td class="py-1.5">
                <input type="number" min="0" v-model.number="counts[d]"
                  class="w-20 px-2 py-1 rounded-lg border border-stone-200 text-center" />
              </td>
              <td class="py-1.5 text-gray-500">{{ (d * (Number(counts[d]) || 0)).toFixed(2) }} ج</td>
            </tr>
          </tbody>
        </table>
        <div class="flex justify-between items-center font-bold border-t border-stone-200 pt-2">
          <span>الإجمالي المعدود</span>
          <span>{{ countedTotal.toFixed(2) }} ج</span>
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
  </div>
</template>
