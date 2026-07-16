<script setup lang="ts">
// الفاتورة الإلكترونية (ETA) — رفع فواتير لمصلحة الضرائب المصرية وتتبّع حالتها.
// ملاحظة: ETA_ENABLED=false افتراضياً في .env. الباك إند مش بيتحقق من الإعداد ده
// إلا وقت إرسال فاتورة فعلاً (POST /finance/eta/invoices) — لو كان متعطّل، بيرجّع
// 400 برسالة واضحة فيها "ETA_ENABLED" (أو ETA_CLIENT_ID/ETA_TAXPAYER لو الاعتماد
// ناقص). قائمة الفواتير (GET) مبتتحققش من الإعداد ده خالص فمفيش إشارة "غير مفعّل"
// وقت فتح الشاشة — الإشارة الوحيدة الحقيقية بتظهر أول ما حد يحاول يبعت فاتورة.
// notEnabledError بيتفعّل من رد الإرسال ده ويعرض بانر واضح فوق الصفحة.
import { ref, reactive, computed, onMounted } from 'vue'
import { api, useAuthStore } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppSpinner, AppModal, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()

const auth = useAuthStore()
const branchId = auth.branchId

interface ETAInvoice {
  id: number; branch_id: number; folio_id: number | null
  internal_id: string; submission_uuid: string | null; long_id: string | null
  status: string; error_message: string | null
  submitted_at: string | null; created_at: string
}

const invoices = ref<ETAInvoice[]>([])
const total = ref(0)
const loading = ref(true)
const statusFilter = ref('')
const notEnabledError = ref('')

const STATUS_CONFIG: Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }> = {
  pending:   { label: 'قيد الانتظار', variant: 'neutral' },
  submitted: { label: 'مُرسلة',        variant: 'info' },
  valid:     { label: 'مقبولة ✓',      variant: 'success' },
  invalid:   { label: 'مرفوضة',        variant: 'danger' },
  failed:    { label: 'فشل الإرسال',   variant: 'warning' },
}

// ── Submit modal ─────────────────────────────────────────────────────
const submitModal = reactive({
  open: false, saving: false, error: '',
  receiver_name: '', receiver_rin: '', folio_id: '' as string | number,
  items: [{ description: '', quantity: 1, unit_price: 0 }] as { description: string; quantity: number; unit_price: number }[],
})

function openSubmitModal() {
  submitModal.open = true
  submitModal.error = ''
  submitModal.receiver_name = ''
  submitModal.receiver_rin = ''
  submitModal.folio_id = ''
  submitModal.items = [{ description: '', quantity: 1, unit_price: 0 }]
}
function addLine() { submitModal.items.push({ description: '', quantity: 1, unit_price: 0 }) }
function removeLine(i: number) { submitModal.items.splice(i, 1) }

// wagdy.md #14: الرقم الضريبي الموحّد المصري (RIN) 9 أرقام بالظبط — فاضي
// = B2C (اختياري فعلاً، راجع eta_service.build_invoice_document: receiver.type
// بيبقى "P" لو مفيش receiver_rin) لكن لو المستخدم كتب حاجة، لازم تبقى صحيحة
// الشكل قبل ما نبعتها لبوابة الضرائب أصلاً — كانت بتتقبل أي نص وتترفض بعيد
// (فشل إرسال كامل) بدل تنبيه فوري وواضح جوه المودال.
const rinError = computed(() => {
  const v = submitModal.receiver_rin.trim()
  if (!v) return ''
  return /^\d{9}$/.test(v) ? '' : 'الرقم الضريبي لازم يكون 9 أرقام بالظبط'
})

async function loadInvoices() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/finance/eta/invoices', {
      params: { branch_id: branchId, status: statusFilter.value || undefined },
    })
    invoices.value = res.data.items ?? []
    total.value = res.data.total ?? 0
  } catch {
    toast.error('تعذّر تحميل الفواتير الإلكترونية — حاول تاني')
  } finally {
    loading.value = false
  }
}

// الباك إند بيرجّع رسالة فيها اسم متغير البيئة الناقص لما ETA مش مهيأ —
// ده الإشارة الوحيدة الحقيقية المتاحة من الـ API للتفريق بين "الإعداد غير
// مفعّل" وأي خطأ 400 تاني (بيانات فاتورة ناقصة، إلخ).
const ETA_CONFIG_MARKERS = ['ETA_ENABLED', 'ETA_CLIENT_ID', 'ETA_TAXPAYER']

async function submitInvoice() {
  if (rinError.value) { submitModal.error = rinError.value; return }
  submitModal.saving = true
  submitModal.error = ''
  try {
    await api.post('/api/v1/finance/eta/invoices', {
      branch_id: branchId,
      receiver_name: submitModal.receiver_name,
      receiver_rin: submitModal.receiver_rin || null,
      folio_id: submitModal.folio_id ? Number(submitModal.folio_id) : null,
      line_items: submitModal.items.map(i => ({
        description: i.description, quantity: i.quantity, unit_price: i.unit_price,
      })),
    })
    notEnabledError.value = ''
    submitModal.open = false
    await loadInvoices()
  } catch (e: any) {
    const detail = e?.response?.data?.detail ?? 'تعذّر إرسال الفاتورة'
    if (typeof detail === 'string' && ETA_CONFIG_MARKERS.some(marker => detail.includes(marker))) {
      notEnabledError.value = detail
      submitModal.open = false
    } else {
      submitModal.error = detail
    }
  } finally {
    submitModal.saving = false
  }
}

onMounted(loadInvoices)
</script>

<template>
  <div dir="rtl" class="p-6 max-w-5xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-black text-gray-900 dark:text-gray-100">🧾 الفاتورة الإلكترونية (ETA)</h1>
        <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">رفع الفواتير لمصلحة الضرائب المصرية ومتابعة حالتها</p>
      </div>
      <AppButton @click="openSubmitModal">+ فاتورة جديدة</AppButton>
    </div>

    <!-- بانر "غير مفعّل" — بيظهر لما الباك إند يرجّع إشارة حقيقية إن ETA مش مهيأ
         (اتفعّل من submitInvoice، راجع الملاحظة أعلى الملف). -->
    <div v-if="notEnabledError" class="mb-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 flex items-start gap-2">
      <span class="text-lg leading-none">⚠️</span>
      <div>
        <p class="font-bold">الفاتورة الإلكترونية غير مفعّلة حاليًا</p>
        <p class="text-xs text-amber-700 mt-0.5">{{ notEnabledError }}</p>
      </div>
    </div>

    <div class="flex gap-2 mb-4">
      <button v-for="s in [{v:'',l:'الكل'},{v:'pending',l:'قيد الانتظار'},{v:'submitted',l:'مُرسلة'},{v:'valid',l:'مقبولة'},{v:'invalid',l:'مرفوضة'},{v:'failed',l:'فشل'}]"
              :key="s.v" @click="statusFilter = s.v; loadInvoices()"
              :class="['px-3 py-1.5 rounded-lg text-xs font-bold', statusFilter === s.v ? 'bg-primary text-white' : 'bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-600 dark:text-gray-500']">
        {{ s.l }}
      </button>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الرقم الداخلي</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">UUID</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحالة</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">تاريخ الإرسال</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">خطأ</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inv in invoices" :key="inv.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
              <td class="px-4 py-3 font-mono text-sm text-gray-900 dark:text-gray-100">{{ inv.internal_id }}</td>
              <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-500 font-mono">{{ inv.submission_uuid ?? '—' }}</td>
              <td class="px-4 py-3">
                <AppBadge size="sm" :variant="STATUS_CONFIG[inv.status]?.variant ?? 'neutral'">
                  {{ STATUS_CONFIG[inv.status]?.label ?? inv.status }}
                </AppBadge>
              </td>
              <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-500">
                {{ inv.submitted_at ? new Date(inv.submitted_at).toLocaleString('ar-EG') : '—' }}
              </td>
              <td class="px-4 py-3 text-xs text-red-500 max-w-xs truncate" :title="inv.error_message ?? ''">
                {{ inv.error_message ?? '—' }}
              </td>
            </tr>
            <tr v-if="invoices.length === 0">
              <td colspan="5" class="px-4 py-8">
                <EmptyState icon="🧾" title="لا توجد فواتير إلكترونية بعد" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>

    <!-- Submit Modal -->
    <AppModal :open="submitModal.open" title="فاتورة إلكترونية جديدة" @close="submitModal.open = false">
      <div class="space-y-3">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-500 mb-1">اسم العميل</label>
          <input v-model="submitModal.receiver_name" type="text"
                 class="w-full border border-stone-200 dark:border-border rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-500 mb-1">الرقم الضريبي (اختياري — فاضي = B2C)</label>
          <input v-model="submitModal.receiver_rin" type="text" maxlength="9"
                 :class="['w-full border rounded-lg px-3 py-2 text-sm', rinError ? 'border-red-400' : 'border-stone-200 dark:border-border']" />
          <p v-if="rinError" class="text-[11px] text-red-600 mt-1">{{ rinError }}</p>
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-500 mb-1">رقم الفوليو (اختياري)</label>
          <input v-model="submitModal.folio_id" type="number"
                 class="w-full border border-stone-200 dark:border-border rounded-lg px-3 py-2 text-sm" />
        </div>

        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-500 mb-2">بنود الفاتورة</label>
          <div v-for="(item, i) in submitModal.items" :key="i" class="flex gap-2 mb-2">
            <input v-model="item.description" placeholder="الوصف" class="flex-1 border border-stone-200 dark:border-border rounded-lg px-2 py-1.5 text-xs" />
            <input v-model.number="item.quantity" type="number" placeholder="كمية" class="w-16 border border-stone-200 dark:border-border rounded-lg px-2 py-1.5 text-xs" />
            <input v-model.number="item.unit_price" type="number" placeholder="السعر" class="w-20 border border-stone-200 dark:border-border rounded-lg px-2 py-1.5 text-xs" />
            <button @click="removeLine(i)" class="text-red-400 text-xs px-1">✕</button>
          </div>
          <button @click="addLine" class="text-xs text-primary font-bold">+ إضافة بند</button>
        </div>

        <p v-if="submitModal.error" class="text-red-600 text-xs bg-red-50 rounded-lg p-2">{{ submitModal.error }}</p>
      </div>

      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="outline" block @click="submitModal.open = false">إلغاء</AppButton>
          <AppButton block :disabled="!!rinError" :loading="submitModal.saving" @click="submitInvoice">
            {{ submitModal.saving ? 'جاري الإرسال...' : 'إرسال لمصلحة الضرائب' }}
          </AppButton>
        </div>
      </template>
    </AppModal>
  </div>
</template>
