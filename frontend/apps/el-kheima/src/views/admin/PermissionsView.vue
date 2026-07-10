<script setup lang="ts">
// PermissionsView — إدارة الصلاحيات التفصيلية (super_admin فقط).
//
// يعرض كتالوج الصلاحيات (GET /permissions/catalog) كمصفوفة × قائمة الموظفين
// (GET /users)، ولكل خلية (موظف × صلاحية) 3 حالات: منح صريح / افتراضي (حسب
// الدور)/ منع صريح. اختيار "منح" أو "منع" بيعمل POST /permissions، والرجوع
// لـ"افتراضي" بيعمل DELETE /permissions/{id} على أي استثناء موجود.
//
// أول شاشة في المشروع تستخدم مكتبة المكونات المشتركة بالكامل (AppCard,
// AppBadge, AppSpinner, AppInput, useToast) بدل إعادة اختراعهم محليًا —
// راجع تقرير مراجعة الفرونت إند (2026-07-03) لسياق ليه ده مهم.
import { ref, computed, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { AppCard, AppBadge, AppSpinner, AppInput, useToast } from '@resort-os/ui'

interface CatalogEntry {
  resource: string
  action: string
  label_ar: string
  module: string
  min_role_level: number
  endpoint: string
}
interface UserRow {
  id: number
  email: string
  full_name: string
  role: string
  is_active: boolean
}
interface ExplicitPermission {
  id: number
  user_id: number
  resource: string
  action: string
  allowed: boolean
  branch_id: number | null
}

const toast = useToast()

const catalog = ref<CatalogEntry[]>([])
const users = ref<UserRow[]>([])
const search = ref('')
const selectedUserId = ref<number | null>(null)
const explicitPerms = ref<ExplicitPermission[]>([])

const loadingCatalog = ref(true)
const loadingUsers = ref(true)
const loadingUserPerms = ref(false)
const savingKey = ref<string | null>(null)   // "resource:action" الجاري حفظه دلوقتي
const loadError = ref('')
const needs2FA  = ref(false)

const roleLabels: Record<string, string> = {
  super_admin: 'مدير عام', admin: 'إداري', accountant: 'محاسب', hr_manager: 'مسؤول موارد بشرية',
  manager: 'مدير', supervisor: 'مشرف', receptionist: 'استقبال', cashier: 'كاشير',
  waiter: 'جرسون', chef: 'شيف', kitchen: 'مطبخ', employee: 'موظف',
}

const filteredUsers = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return users.value
  return users.value.filter(
    (u) => u.full_name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
  )
})

const selectedUser = computed(() => users.value.find((u) => u.id === selectedUserId.value) ?? null)

const catalogByModule = computed(() => {
  const groups: Record<string, CatalogEntry[]> = {}
  for (const entry of catalog.value) {
    ;(groups[entry.module] ??= []).push(entry)
  }
  return groups
})

function moduleLabel(m: string) {
  const labels: Record<string, string> = {
    finance: 'الحسابات', restaurant: 'المطعم', cafe: 'الكافيه', beach: 'الشاطئ',
    hr: 'الموارد البشرية', timeshare: 'التايم شير', pms: 'الفنادق', inventory: 'المخزون', crm: 'العملاء',
  }
  return labels[m] ?? m
}

function stateFor(entry: CatalogEntry): 'granted' | 'denied' | 'default' {
  const explicit = explicitPerms.value.find(
    (p) => p.resource === entry.resource && p.action === entry.action && p.branch_id === null,
  )
  if (!explicit) return 'default'
  return explicit.allowed ? 'granted' : 'denied'
}

function explicitRowFor(entry: CatalogEntry): ExplicitPermission | undefined {
  return explicitPerms.value.find(
    (p) => p.resource === entry.resource && p.action === entry.action && p.branch_id === null,
  )
}

async function loadCatalog() {
  loadingCatalog.value = true
  loadError.value = ''
  needs2FA.value = false
  try {
    const res = await api.get('/api/v1/permissions/catalog')
    catalog.value = res.data
  } catch (e: any) {
    const code = e?.response?.data?.detail?.code ?? e?.response?.data?.code
    if (code === '2FA_REQUIRED') {
      needs2FA.value = true
    } else {
      loadError.value = 'تعذّر تحميل كتالوج الصلاحيات — تأكد من اتصالك وحاول تاني'
    }
  } finally {
    loadingCatalog.value = false
  }
}

async function loadUsers() {
  loadingUsers.value = true
  loadError.value = ''
  try {
    const res = await api.get('/api/v1/users', { params: { page: 1, size: 100 } })
    users.value = res.data.items
  } catch (e: any) {
    const code = e?.response?.data?.detail?.code ?? e?.response?.data?.code
    if (code !== '2FA_REQUIRED') {
      loadError.value = 'تعذّر تحميل قائمة الموظفين — تأكد من اتصالك وحاول تاني'
    }
  } finally {
    loadingUsers.value = false
  }
}

async function selectUser(userId: number) {
  selectedUserId.value = userId
  loadingUserPerms.value = true
  try {
    const res = await api.get('/api/v1/permissions', { params: { user_id: userId } })
    explicitPerms.value = res.data
  } catch {
    toast.error('تعذّر تحميل صلاحيات هذا الموظف')
    explicitPerms.value = []
  } finally {
    loadingUserPerms.value = false
  }
}

async function setState(entry: CatalogEntry, newState: 'granted' | 'denied' | 'default') {
  if (!selectedUserId.value) return
  const key = `${entry.resource}:${entry.action}`
  savingKey.value = key
  try {
    if (newState === 'default') {
      const existing = explicitRowFor(entry)
      if (existing) {
        await api.delete(`/api/v1/permissions/${existing.id}`)
        explicitPerms.value = explicitPerms.value.filter((p) => p.id !== existing.id)
      }
      toast.success(`رجع "${entry.label_ar}" للسلوك الافتراضي حسب الدور`)
    } else {
      const res = await api.post('/api/v1/permissions', {
        user_id: selectedUserId.value,
        resource: entry.resource,
        action: entry.action,
        allowed: newState === 'granted',
        branch_id: null,
      })
      explicitPerms.value = [
        ...explicitPerms.value.filter((p) => !(p.resource === entry.resource && p.action === entry.action)),
        res.data,
      ]
      toast.success(newState === 'granted' ? `تم منح "${entry.label_ar}"` : `تم منع "${entry.label_ar}"`)
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail?.message ?? 'حصل خطأ أثناء الحفظ — حاول تاني')
  } finally {
    savingKey.value = null
  }
}

onMounted(() => {
  loadCatalog()
  loadUsers()
})
</script>

<template>
  <div dir="rtl" class="space-y-5">
    <div>
      <h1 class="text-2xl font-black text-gray-800">الصلاحيات التفصيلية</h1>
      <p class="text-sm text-gray-500 mt-1">
        امنح استثناء لموظف معيّن فوق صلاحيات دوره العادية، أو امنعه من إجراء
        عادةً مسموح له بيه — بيسري فورًا من غير ما تغيّر دوره الأساسي.
      </p>
    </div>

    <div v-if="loadError" class="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm flex items-center justify-between">
      <span>⚠️ {{ loadError }}</span>
      <button @click="loadCatalog(); loadUsers()" class="font-semibold underline hover:no-underline">إعادة المحاولة</button>
    </div>

    <!-- 2FA required banner -->
    <div v-if="needs2FA" class="bg-amber-50 border border-amber-300 rounded-xl p-5 text-center">
      <div class="text-3xl mb-2">🔐</div>
      <h2 class="font-black text-amber-800 text-lg mb-1">التحقق بخطوتين مطلوب</h2>
      <p class="text-amber-700 text-sm mb-3">
        حسابك يتطلب تفعيل التحقق بخطوتين (2FA) قبل الوصول لإدارة الصلاحيات.
      </p>
      <p class="text-amber-600 text-xs">
        اذهب إلى <strong>الإعدادات ← الأمان</strong> وفعّل التحقق بخطوتين، ثم ارجع لهذه الصفحة.
      </p>
      <router-link
        to="/settings"
        class="inline-block mt-3 px-5 py-2 bg-amber-600 text-white rounded-lg font-bold text-sm hover:bg-amber-700 transition-colors"
      >الذهاب للإعدادات</router-link>
    </div>

    <div v-if="!needs2FA" class="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-5">
      <!-- قائمة الموظفين -->
      <AppCard title="الموظفون" padding="none">
        <div class="p-3 border-b border-stone-100">
          <AppInput v-model="search" placeholder="ابحث بالاسم أو الإيميل..." />
        </div>
        <div v-if="loadingUsers" class="p-8 flex justify-center">
          <AppSpinner />
        </div>
        <div v-else-if="filteredUsers.length === 0" class="p-8 text-center text-gray-400 text-sm">
          <div class="text-3xl mb-2">🔍</div>
          لا يوجد موظفون مطابقون
        </div>
        <ul v-else class="max-h-[65vh] overflow-y-auto divide-y divide-stone-100">
          <li
            v-for="u in filteredUsers"
            :key="u.id"
            @click="selectUser(u.id)"
            :class="[
              'px-4 py-3 cursor-pointer transition-colors',
              selectedUserId === u.id ? 'bg-blue-50' : 'hover:bg-stone-50',
            ]"
          >
            <div class="font-medium text-gray-800 text-sm">{{ u.full_name }}</div>
            <div class="flex items-center gap-2 mt-1">
              <span class="text-xs text-gray-400">{{ u.email }}</span>
              <AppBadge size="sm" :variant="u.is_active ? 'info' : 'neutral'">
                {{ roleLabels[u.role] ?? u.role }}
              </AppBadge>
            </div>
          </li>
        </ul>
      </AppCard>

      <!-- مصفوفة الصلاحيات -->
      <AppCard :title="selectedUser ? `صلاحيات ${selectedUser.full_name}` : 'اختر موظف'" padding="sm">
        <div v-if="!selectedUserId" class="p-10 text-center text-gray-400">
          <div class="text-4xl mb-3">👈</div>
          اختر موظف من القائمة عشان تشوف وتعدّل صلاحياته
        </div>

        <div v-else-if="loadingCatalog || loadingUserPerms" class="p-10 flex justify-center">
          <AppSpinner size="lg" />
        </div>

        <div v-else class="space-y-5">
          <div v-for="(entries, module) in catalogByModule" :key="module">
            <div class="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2 px-1">
              {{ moduleLabel(module) }}
            </div>
            <div class="space-y-1.5">
              <div
                v-for="entry in entries"
                :key="`${entry.resource}:${entry.action}`"
                class="flex items-center justify-between bg-stone-50 rounded-xl px-4 py-3"
              >
                <div>
                  <div class="text-sm font-medium text-gray-800">{{ entry.label_ar }}</div>
                  <div class="text-xs text-gray-400 font-mono mt-0.5">{{ entry.endpoint }}</div>
                </div>

                <div class="flex items-center gap-1.5 flex-shrink-0">
                  <AppSpinner v-if="savingKey === `${entry.resource}:${entry.action}`" size="sm" />
                  <template v-else>
                    <button
                      @click="setState(entry, 'granted')"
                      :class="[
                        'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors',
                        stateFor(entry) === 'granted'
                          ? 'bg-green-600 text-white'
                          : 'bg-white text-green-700 border border-green-200 hover:bg-green-50',
                      ]"
                    >✓ منح</button>
                    <button
                      @click="setState(entry, 'default')"
                      :class="[
                        'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors',
                        stateFor(entry) === 'default'
                          ? 'bg-gray-600 text-white'
                          : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50',
                      ]"
                    >افتراضي</button>
                    <button
                      @click="setState(entry, 'denied')"
                      :class="[
                        'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors',
                        stateFor(entry) === 'denied'
                          ? 'bg-red-600 text-white'
                          : 'bg-white text-red-700 border border-red-200 hover:bg-red-50',
                      ]"
                    >✕ منع</button>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </div>
      </AppCard>
    </div>
  </div>
</template>
