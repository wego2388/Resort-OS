<script setup lang="ts">
// الفاتورة الإلكترونية (ETA) — رفع فواتير لمصلحة الضرائب المصرية وتتبّع حالتها.
// ملاحظة: ETA_ENABLED=false افتراضياً في .env — الشاشة دي بتشتغل وتعرض حالة
// "غير مفعّل" بوضوح بدل ما تفشل بصمت، وتشتغل فوراً لو حد فعّل بيانات اعتماد حقيقية.
import { ref, reactive, onMounted } from 'vue'
import { api } from '@resort-os/core'

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

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

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  pending:   { label: 'قيد الانتظار', color: 'bg-gray-100 text-gray-700' },
  submitted: { label: 'مُرسلة',        color: 'bg-blue-100 text-blue-700' },
  valid:     { label: 'مقبولة ✓',      color: 'bg-green-100 text-green-700' },
  invalid:   { label: 'مرفوضة',        color: 'bg-red-100 text-red-700' },
  failed:    { label: 'فشل الإرسال',   color: 'bg-amber-100 text-amber-700' },
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

async function loadInvoices() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/finance/eta/invoices', {
      params: { branch_id: branchId, status: statusFilter.value || undefined },
    })
    invoices.value = res.data.items ?? []
    total.value = res.data.total ?? 0
    notEnabledError.value = ''
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function submitInvoice() {
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
    submitModal.open = false
    await loadInvoices()
  } catch (e: any) {
    submitModal.error = e?.response?.data?.detail ?? 'تعذّر إرسال الفاتورة'
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
        <h1 class="text-xl font-black text-gray-900">🧾 الفاتورة الإلكترونية (ETA)</h1>
        <p class="text-xs text-gray-400 mt-1">رفع الفواتير لمصلحة الضرائب المصرية ومتابعة حالتها</p>
      </div>
      <button @click="openSubmitModal" class="px-4 py-2 rounded-xl bg-primary text-white text-sm font-bold">
        + فاتورة جديدة
      </button>
    </div>

    <div class="flex gap-2 mb-4">
      <button v-for="s in [{v:'',l:'الكل'},{v:'pending',l:'قيد الانتظار'},{v:'submitted',l:'مُرسلة'},{v:'valid',l:'مقبولة'},{v:'invalid',l:'مرفوضة'},{v:'failed',l:'فشل'}]"
              :key="s.v" @click="statusFilter = s.v; loadInvoices()"
              :class="['px-3 py-1.5 rounded-lg text-xs font-bold', statusFilter === s.v ? 'bg-primary text-white' : 'bg-white border border-stone-200 text-gray-600']">
        {{ s.l }}
      </button>
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-400">جاري التحميل...</div>
    <div v-else class="bg-white rounded-2xl border border-stone-200 overflow-hidden shadow-sm">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-stone-50">
            <tr>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الرقم الداخلي</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">UUID</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الحالة</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">تاريخ الإرسال</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">خطأ</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inv in invoices" :key="inv.id" class="border-t border-stone-100 hover:bg-stone-50">
              <td class="px-4 py-3 font-mono text-sm text-gray-900">{{ inv.internal_id }}</td>
              <td class="px-4 py-3 text-xs text-gray-500 font-mono">{{ inv.submission_uuid ?? '—' }}</td>
              <td class="px-4 py-3">
                <span :class="['px-2 py-1 rounded-full text-xs font-medium', STATUS_CONFIG[inv.status]?.color ?? 'bg-gray-100 text-gray-600']">
                  {{ STATUS_CONFIG[inv.status]?.label ?? inv.status }}
                </span>
              </td>
              <td class="px-4 py-3 text-xs text-gray-500">
                {{ inv.submitted_at ? new Date(inv.submitted_at).toLocaleString('ar-EG') : '—' }}
              </td>
              <td class="px-4 py-3 text-xs text-red-500 max-w-xs truncate" :title="inv.error_message ?? ''">
                {{ inv.error_message ?? '—' }}
              </td>
            </tr>
            <tr v-if="invoices.length === 0">
              <td colspan="5" class="px-4 py-12 text-center text-gray-400">لا توجد فواتير إلكترونية بعد</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Submit Modal -->
    <div v-if="submitModal.open" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-2xl p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto">
        <h3 class="font-black text-gray-900 mb-4">فاتورة إلكترونية جديدة</h3>

        <div class="space-y-3">
          <div>
            <label class="block text-xs text-gray-400 mb-1">اسم العميل</label>
            <input v-model="submitModal.receiver_name" type="text"
                   class="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">الرقم الضريبي (اختياري — فاضي = B2C)</label>
            <input v-model="submitModal.receiver_rin" type="text"
                   class="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">رقم الفوليو (اختياري)</label>
            <input v-model="submitModal.folio_id" type="number"
                   class="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm" />
          </div>

          <div>
            <label class="block text-xs text-gray-400 mb-2">بنود الفاتورة</label>
            <div v-for="(item, i) in submitModal.items" :key="i" class="flex gap-2 mb-2">
              <input v-model="item.description" placeholder="الوصف" class="flex-1 border border-stone-200 rounded-lg px-2 py-1.5 text-xs" />
              <input v-model.number="item.quantity" type="number" placeholder="كمية" class="w-16 border border-stone-200 rounded-lg px-2 py-1.5 text-xs" />
              <input v-model.number="item.unit_price" type="number" placeholder="السعر" class="w-20 border border-stone-200 rounded-lg px-2 py-1.5 text-xs" />
              <button @click="removeLine(i)" class="text-red-400 text-xs px-1">✕</button>
            </div>
            <button @click="addLine" class="text-xs text-primary font-bold">+ إضافة بند</button>
          </div>

          <p v-if="submitModal.error" class="text-red-600 text-xs bg-red-50 rounded-lg p-2">{{ submitModal.error }}</p>

          <div class="flex gap-2 pt-2">
            <button @click="submitModal.open = false" class="flex-1 py-2 rounded-xl border border-stone-200 text-sm font-bold text-gray-600">إلغاء</button>
            <button @click="submitInvoice" :disabled="submitModal.saving"
                    class="flex-1 py-2 rounded-xl bg-primary text-white text-sm font-bold disabled:opacity-50">
              {{ submitModal.saving ? '...جاري الإرسال' : 'إرسال لمصلحة الضرائب' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
