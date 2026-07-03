<script setup lang="ts">
// SettingsView — إدارة إعدادات الفرع (admin فقط، مطابق لبوابة الراوتر requiredRole: 'admin')
//
// Endpoints حقيقية من core/api/router.py:
//   GET /api/v1/settings?branch_id=X       ← قائمة الإعدادات (crud.list_settings يفلتر بالمطابقة
//                                             التامة لـ branch_id، من غير fallback للعام/global هنا)
//   PUT /api/v1/settings/{key}?branch_id=X ← upsert (يُنشئ لو مش موجود، يُحدّث لو موجود) — get_admin_user
//
// كل الإعدادات هنا مربوطة بالفرع الحالي (نفس نمط باقي شاشات admin) — إعداد
// "عام" (branch_id=null) مش هيظهر في القايمة إلا لو اتعمله PUT بدون branch_id.
import { ref, reactive, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { AppCard, AppButton, AppInput, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface SettingRow {
  id:         number
  key:        string
  value:      string
  branch_id:  number | null
  updated_at: string
}

const settings   = ref<SettingRow[]>([])
const loading    = ref(true)
const loadError  = ref('')
const edited     = reactive<Record<string, string>>({})
const savingKey  = ref<string | null>(null)

const newKey    = ref('')
const newValue  = ref('')
const creating  = ref(false)

function isDirty(row: SettingRow) {
  return edited[row.key] !== undefined && edited[row.key] !== row.value
}

async function loadSettings() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await api.get('/api/v1/settings', { params: { branch_id: branchId } })
    settings.value = res.data
    for (const row of res.data as SettingRow[]) {
      edited[row.key] = row.value
    }
  } catch {
    loadError.value = 'تعذّر تحميل الإعدادات — تأكد من اتصالك وحاول تاني'
  } finally {
    loading.value = false
  }
}

async function saveSetting(row: SettingRow) {
  const value = edited[row.key] ?? row.value
  savingKey.value = row.key
  try {
    const res = await api.put(
      `/api/v1/settings/${encodeURIComponent(row.key)}`,
      { value },
      { params: { branch_id: branchId } },
    )
    const updated: SettingRow = res.data
    const idx = settings.value.findIndex((s) => s.key === row.key)
    if (idx !== -1) settings.value[idx] = updated
    edited[row.key] = updated.value
    toast.success(`تم حفظ "${row.key}" بنجاح`)
  } catch (e: any) {
    toast.error(e?.response?.data?.detail?.message ?? `تعذّر حفظ "${row.key}" — حاول تاني`)
  } finally {
    savingKey.value = null
  }
}

async function createSetting() {
  const key = newKey.value.trim()
  if (!key) {
    toast.error('لازم تدخل اسم المفتاح (key) أولاً')
    return
  }
  if (settings.value.some((s) => s.key === key)) {
    toast.error(`المفتاح "${key}" موجود بالفعل — عدّله من الجدول تحت`)
    return
  }
  creating.value = true
  try {
    const res = await api.put(
      `/api/v1/settings/${encodeURIComponent(key)}`,
      { value: newValue.value },
      { params: { branch_id: branchId } },
    )
    settings.value = [...settings.value, res.data].sort((a, b) => a.key.localeCompare(b.key))
    edited[res.data.key] = res.data.value
    toast.success(`تم إنشاء الإعداد "${key}" بنجاح`)
    newKey.value = ''
    newValue.value = ''
  } catch (e: any) {
    toast.error(e?.response?.data?.detail?.message ?? 'تعذّر إنشاء الإعداد الجديد — حاول تاني')
  } finally {
    creating.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <div dir="rtl" class="space-y-5">
    <div>
      <h1 class="text-2xl font-black text-gray-800">الإعدادات</h1>
      <p class="text-sm text-gray-500 mt-1">إعدادات الفرع الحالي — تعديل القيم يُحفظ فورًا عند الضغط على "حفظ"</p>
    </div>

    <div v-if="loadError" class="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm flex items-center justify-between">
      <span>⚠️ {{ loadError }}</span>
      <button @click="loadSettings" class="font-semibold underline hover:no-underline">إعادة المحاولة</button>
    </div>

    <!-- إضافة إعداد جديد -->
    <AppCard title="إضافة إعداد جديد">
      <div class="flex flex-col md:flex-row md:items-end gap-3">
        <div class="flex-1">
          <AppInput v-model="newKey" label="المفتاح (key)" placeholder="مثال: check_in_time" :disabled="creating" />
        </div>
        <div class="flex-1">
          <AppInput v-model="newValue" label="القيمة" placeholder="مثال: 14:00" :disabled="creating" />
        </div>
        <AppButton variant="primary" :loading="creating" @click="createSetting">إضافة</AppButton>
      </div>
    </AppCard>

    <!-- قائمة الإعدادات -->
    <AppCard title="الإعدادات الحالية" padding="none">
      <div v-if="loading" class="p-10 flex justify-center">
        <AppSpinner size="lg" />
      </div>
      <EmptyState
        v-else-if="settings.length === 0"
        icon="⚙️"
        title="لا توجد إعدادات لهذا الفرع بعد"
        subtitle="أضف أول إعداد من النموذج أعلاه"
      />
      <div v-else class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-stone-50">
            <tr>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">المفتاح</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">القيمة</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">آخر تحديث</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">إجراء</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in settings" :key="row.id" class="border-t border-stone-100 hover:bg-stone-50">
              <td class="px-4 py-3 font-mono text-sm text-gray-800 align-top pt-4">{{ row.key }}</td>
              <td class="px-4 py-3 min-w-[240px]">
                <AppInput v-model="edited[row.key]" :disabled="savingKey === row.key" />
              </td>
              <td class="px-4 py-3 text-sm text-gray-500 align-top pt-4">
                {{ new Date(row.updated_at).toLocaleString('ar-EG') }}
              </td>
              <td class="px-4 py-3 align-top">
                <AppButton
                  variant="primary"
                  size="sm"
                  :loading="savingKey === row.key"
                  :disabled="!isDirty(row) || savingKey === row.key"
                  @click="saveSetting(row)"
                >
                  حفظ
                </AppButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>
  </div>
</template>
