<script setup lang="ts">
/**
 * TablesAdminView — إدارة طاولات المطعم والكافيه (CRUD كامل)
 * مدير+ فقط — إضافة / تعديل / حذف طاولات + تحديد الـ section.
 * يدعم وضعين: module='restaurant' أو module='cafe'
 */
import { ref, computed, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { useToast } from '@resort-os/ui'

const toast    = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

// ── module selector ───────────────────────────────────────────────────
const activeModule = ref<'restaurant' | 'cafe'>('restaurant')

interface Table {
  id: number; table_number: string; capacity: number
  status: string; section: string | null; branch_id?: number
  grid_row?: number | null; grid_col?: number | null
}

// ── State ─────────────────────────────────────────────────────────────
const tables  = ref<Table[]>([])
const loading = ref(false)
const saving  = ref(false)

// ── Table form ─────────────────────────────────────────────────────────
const formOpen = ref(false)
const formEdit = ref<Table | null>(null)
const form     = ref({ table_number: '', capacity: 2, section: '' })

function openForm(table?: Table) {
  formEdit.value = table ?? null
  form.value = table
    ? { table_number: table.table_number, capacity: table.capacity, section: table.section ?? '' }
    : { table_number: '', capacity: 2, section: '' }
  formOpen.value = true
}

async function saveTable() {
  if (!form.value.table_number.trim()) { toast.error('رقم الطاولة مطلوب'); return }
  saving.value = true
  try {
    const payload = {
      table_number: form.value.table_number.trim(),
      capacity:     form.value.capacity,
      section:      form.value.section.trim() || null,
    }
    const base = `/api/v1/${activeModule.value}/tables`
    if (formEdit.value) {
      const { data } = await api.patch(`${base}/${formEdit.value.id}`, payload)
      const idx = tables.value.findIndex(t => t.id === formEdit.value!.id)
      if (idx >= 0) tables.value[idx] = data
    } else {
      const { data } = await api.post(base, { ...payload, branch_id: branchId })
      tables.value.push(data)
    }
    formOpen.value = false
    toast.success(formEdit.value ? 'تم تعديل الطاولة' : 'تم إضافة الطاولة')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحفظ')
  } finally {
    saving.value = false
  }
}

async function deleteTable(table: Table) {
  if (!confirm(`حذف طاولة "${table.table_number}"؟`)) return
  try {
    await api.delete(`/api/v1/${activeModule.value}/tables/${table.id}`)
    tables.value = tables.value.filter(t => t.id !== table.id)
    toast.success('تم حذف الطاولة')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحذف')
  }
}

// ── Load ───────────────────────────────────────────────────────────────
async function loadTables() {
  loading.value = true
  try {
    const { data } = await api.get(`/api/v1/${activeModule.value}/tables`, {
      params: { branch_id: branchId },
    })
    tables.value = data.tables ?? data.items ?? data
  } catch (e: any) {
    toast.error('تعذّر تحميل الطاولات')
  } finally {
    loading.value = false
  }
}

// grouped by section
const grouped = computed(() => {
  const map = new Map<string, Table[]>()
  for (const t of tables.value) {
    const key = t.section || 'بدون قسم'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(t)
  }
  return Array.from(map.entries())
})

function statusDot(status: string) {
  if (status === 'available') return 'bg-green-500'
  if (status === 'occupied')  return 'bg-red-500'
  return 'bg-amber-400'
}
function statusLabel(status: string) {
  if (status === 'available') return 'فارغة'
  if (status === 'occupied')  return 'مشغولة'
  if (status === 'reserved')  return 'محجوزة'
  return status
}

onMounted(loadTables)
</script>

<template>
  <div dir="rtl" class="p-6 max-w-5xl mx-auto">

    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-black text-gray-900">🪑 إدارة الطاولات</h1>
        <p class="text-xs text-gray-400 mt-1">إضافة وتعديل وحذف طاولات المطعم والكافيه</p>
      </div>
      <button
        @click="openForm()"
        class="px-4 py-2 bg-blue-700 text-white rounded-xl font-bold text-sm hover:bg-blue-800 transition-colors"
      >+ إضافة طاولة</button>
    </div>

    <!-- Module tabs -->
    <div class="flex gap-2 mb-6 bg-stone-100 p-1 rounded-xl w-fit">
      <button
        v-for="m in [{ val: 'restaurant', label: '🍽️ المطعم' }, { val: 'cafe', label: '☕ الكافيه' }]"
        :key="m.val"
        @click="activeModule = (m.val as 'restaurant' | 'cafe'); loadTables()"
        :class="[
          'px-5 py-2 rounded-lg text-sm font-bold transition-all',
          activeModule === m.val
            ? 'bg-white text-blue-700 shadow-sm'
            : 'text-gray-500 hover:text-gray-700',
        ]"
      >{{ m.label }}</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-16">
      <div class="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
    </div>

    <!-- Empty -->
    <div v-else-if="tables.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-400">
      <div class="text-5xl mb-4">🪑</div>
      <p class="font-medium text-gray-600">لا توجد طاولات مضافة بعد</p>
      <p class="text-sm mt-1">اضغط "إضافة طاولة" لإضافة أول طاولة</p>
    </div>

    <!-- Tables grouped by section -->
    <div v-else class="space-y-6">
      <div v-for="[section, sectionTables] in grouped" :key="section">
        <h2 class="text-sm font-bold text-gray-500 uppercase tracking-wide mb-3 flex items-center gap-2">
          <span class="flex-1 border-b border-stone-200" />
          <span>{{ section }}</span>
          <span class="flex-1 border-b border-stone-200" />
        </h2>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
          <div
            v-for="table in sectionTables"
            :key="table.id"
            class="bg-white rounded-2xl border-2 border-stone-200 p-4 flex flex-col gap-2 hover:border-blue-300 transition-colors"
          >
            <div class="flex items-center justify-between">
              <span class="font-black text-gray-900 text-lg">{{ table.table_number }}</span>
              <span class="flex items-center gap-1.5 text-xs text-gray-500">
                <span :class="['w-2 h-2 rounded-full', statusDot(table.status)]" />
                {{ statusLabel(table.status) }}
              </span>
            </div>
            <div class="text-xs text-gray-500">
              <span>👥 {{ table.capacity }} مقعد</span>
            </div>
            <div class="flex gap-1.5 mt-1">
              <button
                @click="openForm(table)"
                class="flex-1 py-1.5 bg-stone-100 hover:bg-stone-200 text-gray-600 text-xs font-semibold rounded-lg transition-colors"
              >تعديل</button>
              <button
                @click="deleteTable(table)"
                :disabled="table.status === 'occupied'"
                class="flex-1 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 text-xs font-semibold rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >حذف</button>
            </div>
            <!-- رابط QR مباشر — بدل ما المدير يروح صفحة QRGeneratorView منفصلة -->
            <router-link
              :to="`/admin/qr?module=${activeModule}&highlight=${table.id}`"
              class="w-full py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-semibold rounded-lg transition-colors text-center block"
            >📱 QR Code</router-link>
          </div>
        </div>
      </div>
    </div>

    <!-- Summary -->
    <div v-if="tables.length > 0" class="mt-6 bg-blue-50 rounded-2xl p-4 flex items-center gap-4 text-sm">
      <span class="text-blue-700 font-bold">إجمالي الطاولات: {{ tables.length }}</span>
      <span class="text-gray-500">|</span>
      <span class="text-green-600">فارغة: {{ tables.filter(t => t.status === 'available').length }}</span>
      <span class="text-red-600">مشغولة: {{ tables.filter(t => t.status === 'occupied').length }}</span>
    </div>

    <!-- ── Add/Edit Form Modal ── -->
    <Transition name="modal">
      <div
        v-if="formOpen"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="formOpen = false"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
          <div class="bg-blue-700 text-white px-6 py-4">
            <h2 class="font-black text-lg">{{ formEdit ? 'تعديل طاولة' : 'إضافة طاولة جديدة' }}</h2>
            <p class="text-xs text-blue-200 mt-0.5">{{ activeModule === 'restaurant' ? '🍽️ المطعم' : '☕ الكافيه' }}</p>
          </div>
          <div class="p-6 space-y-4">
            <div>
              <label class="block text-sm font-bold text-gray-700 mb-1.5">رقم/اسم الطاولة <span class="text-red-500">*</span></label>
              <input
                v-model="form.table_number"
                type="text"
                placeholder="مثال: T1 أو طاولة 1"
                class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                autofocus
              />
            </div>
            <div>
              <label class="block text-sm font-bold text-gray-700 mb-1.5">عدد المقاعد</label>
              <input
                v-model.number="form.capacity"
                type="number"
                min="1"
                max="20"
                class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label class="block text-sm font-bold text-gray-700 mb-1.5">القسم (section)</label>
              <input
                v-model="form.section"
                type="text"
                placeholder="مثال: Indoor أو Garden أو VIP"
                class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p class="text-xs text-gray-400 mt-1">اتركه فارغاً لو مش محتاج تقسيم</p>
            </div>
          </div>
          <div class="px-6 pb-6 flex gap-3">
            <button
              @click="formOpen = false"
              class="flex-1 py-3 border-2 border-stone-200 rounded-xl text-sm font-semibold text-gray-600 hover:bg-gray-50 transition-colors"
            >إلغاء</button>
            <button
              @click="saveTable"
              :disabled="saving"
              class="flex-1 py-3 bg-blue-700 text-white rounded-xl text-sm font-bold hover:bg-blue-800 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <div v-if="saving" class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              <span>{{ saving ? 'جاري الحفظ...' : (formEdit ? 'حفظ التعديلات' : 'إضافة الطاولة') }}</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>

  </div>
</template>

<style scoped>
.modal-enter-active, .modal-leave-active { transition: opacity 0.2s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-active > div, .modal-leave-active > div { transition: transform 0.2s ease; }
.modal-enter-from > div, .modal-leave-to > div { transform: scale(0.95) translateY(8px); }
</style>
