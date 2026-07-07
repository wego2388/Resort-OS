<script setup lang="ts">
/**
 * BeachMapView — خريطة الشاطئ الحية. قبل هذا التعديل، الشاطئ كان بيتتبّع
 * بس بعدّاد سعة مجمّع (BeachInventory.capacity_used/capacity_max) + سجل
 * عمليات بيع (BeachTransaction) — مفيش مفهوم "شمسية/برجولة فعلية" ولا شاشة
 * بصرية يقدر الموظف يبص عليها طول اليوم يشوف مين قاعد فين، نفس فئة الفجوة
 * اللي اتصلحت قبل كده للمطعم (TablesView.vue) بس الشاطئ ماكانش عنده حتى
 * نموذج بيانات لموقع فعلي واحد.
 *
 * تسجيل الدخول/الخروج هنا عملية بيع حقيقية عبر beach.services.checkin_location
 * (نفس sell_ticket الداخلي — تسعير/VAT/قيد محاسبي)، مش مجرد تلوين مربّع.
 * التحديثات الحية بتوصل لكل الكاشيرين/المشرفين الفاتحين الشاشة في نفس
 * الوقت عبر WebSocket (نفس نمط KDS/تنبيهات الضيوف — useResortWebSocket).
 */
import { ref, computed, onMounted } from 'vue'
import { api, useAuthStore, useResortWebSocket, ENDPOINTS } from '@resort-os/core'
import { AppModal, EmptyState, useConfirm, useToast } from '@resort-os/ui'

const auth = useAuthStore()
const toast = useToast()
const { confirm } = useConfirm()
const branchId = computed(() => auth.branchId ?? 1)
const isManager = computed(() => auth.hasRole('manager'))

interface BeachLocation {
  id: number
  branch_id: number
  location_type: string
  number: string
  grid_row: number
  grid_col: number
  status: 'available' | 'occupied' | 'out_of_service'
  current_transaction_id: number | null
  guest_name: string | null
  guest_phone: string | null
  guests_count: number
  towels_given: number
  checked_in_at: string | null
  checked_in_by: number | null
}

const TYPE_LABELS: Record<string, string> = {
  umbrella: 'شمسية', pergola: 'برجولة', sunbed: 'سرير شاطئ', cabana: 'كابانا',
}
function typeLabel(t: string) { return TYPE_LABELS[t] ?? t }

const TYPE_ICONS: Record<string, string> = {
  umbrella: '⛱️', pergola: '🏝️', sunbed: '🛏️', cabana: '🏖️',
}
function typeIcon(t: string) { return TYPE_ICONS[t] ?? '📍' }

const locations = ref<BeachLocation[]>([])
const loading = ref(false)

const sections = computed(() => {
  const map = new Map<string, BeachLocation[]>()
  for (const loc of locations.value) {
    if (!map.has(loc.location_type)) map.set(loc.location_type, [])
    map.get(loc.location_type)!.push(loc)
  }
  for (const list of map.values()) {
    list.sort((a, b) => a.grid_row - b.grid_row || a.grid_col - b.grid_col)
  }
  return Array.from(map.entries())
})

const stats = computed(() => ({
  total: locations.value.length,
  available: locations.value.filter(l => l.status === 'available').length,
  occupied: locations.value.filter(l => l.status === 'occupied').length,
  outOfService: locations.value.filter(l => l.status === 'out_of_service').length,
}))

async function fetchLocations() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.beach.locations, { params: { branch_id: branchId.value } })
    locations.value = data
  } catch (e) {
    console.error('Failed to load beach locations', e)
    toast.error('تعذّر تحميل خريطة الشاطئ')
  } finally {
    loading.value = false
  }
}

function upsertLocation(loc: BeachLocation) {
  const idx = locations.value.findIndex(l => l.id === loc.id)
  if (idx >= 0) locations.value[idx] = loc
  else locations.value.push(loc)
}

// اتصال لحظي — نفس نمط KDS/تنبيهات الضيوف (useResortWebSocket بيعيد
// الاتصال تلقائيًا لو النت اتقطع).
const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
const { status: wsStatus, onMessage } = useResortWebSocket(
  `${wsProtocol}//${location.host}/api/v1/beach/ws/map/${branchId.value}`,
)
onMessage((data: any) => {
  if (data?.type === 'map_update' && data.location) {
    upsertLocation(data.location)
  } else if (data?.type === 'locations_changed') {
    fetchLocations()
  }
})

function statusColor(loc: BeachLocation): string {
  if (loc.status === 'occupied') return 'bg-red-100 border-red-400 text-red-800 active:bg-red-200'
  if (loc.status === 'out_of_service') return 'bg-gray-100 border-gray-300 text-gray-400'
  return 'bg-green-100 border-green-400 text-green-800 active:bg-green-200'
}

function statusLabel(status: string): string {
  if (status === 'occupied') return 'مشغول'
  if (status === 'out_of_service') return 'خارج الخدمة'
  return 'فاضي'
}

// ── Check-in modal ──────────────────────────────────────────────────────
const checkinModalOpen = ref(false)
const checkinTarget = ref<BeachLocation | null>(null)
const checkinForm = ref({ guest_name: '', guest_phone: '', guests_count: 1, with_towel: false })
const checkinSubmitting = ref(false)

function openCheckin(loc: BeachLocation) {
  checkinTarget.value = loc
  checkinForm.value = { guest_name: '', guest_phone: '', guests_count: 1, with_towel: false }
  checkinModalOpen.value = true
}

async function submitCheckin() {
  if (!checkinTarget.value) return
  checkinSubmitting.value = true
  try {
    const { data } = await api.post(
      ENDPOINTS.beach.locationCheckin(checkinTarget.value.id),
      {
        guest_name: checkinForm.value.guest_name || null,
        guest_phone: checkinForm.value.guest_phone || null,
        guests_count: checkinForm.value.guests_count,
        with_towel: checkinForm.value.with_towel,
      },
      { params: { branch_id: branchId.value } },
    )
    upsertLocation(data)
    checkinModalOpen.value = false
    toast.success(`تم تسجيل الدخول — ${typeLabel(checkinTarget.value.location_type)} ${checkinTarget.value.number}`)
  } catch (e: any) {
    if (e?.response?.status === 409) {
      toast.error('الموقع اتشغل بالفعل من كاشير تاني — جاري التحديث')
      fetchLocations()
    } else {
      toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل الدخول')
    }
  } finally {
    checkinSubmitting.value = false
  }
}

// ── Occupied detail / checkout ───────────────────────────────────────────
const detailModalOpen = ref(false)
const detailTarget = ref<BeachLocation | null>(null)
const checkoutSubmitting = ref(false)

function openDetail(loc: BeachLocation) {
  detailTarget.value = loc
  detailModalOpen.value = true
}

async function submitCheckout() {
  if (!detailTarget.value) return
  const ok = await confirm({
    title: 'تأكيد تسجيل الخروج',
    message: `تسجيل خروج ${detailTarget.value.guest_name || 'الضيف'} من ${typeLabel(detailTarget.value.location_type)} ${detailTarget.value.number}؟`,
    confirmText: 'تسجيل الخروج', danger: true,
  })
  if (!ok) return
  checkoutSubmitting.value = true
  try {
    const { data } = await api.post(
      ENDPOINTS.beach.locationCheckout(detailTarget.value.id),
      {}, { params: { branch_id: branchId.value } },
    )
    upsertLocation(data)
    detailModalOpen.value = false
    toast.success('تم تسجيل الخروج')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل الخروج')
  } finally {
    checkoutSubmitting.value = false
  }
}

function onTileClick(loc: BeachLocation) {
  if (loc.status === 'available') openCheckin(loc)
  else if (loc.status === 'occupied') openDetail(loc)
  else if (isManager.value) toggleOutOfService(loc) // out_of_service — manager can reactivate
}

// ── Manager: reactivate / disable a single spot ─────────────────────────
async function toggleOutOfService(loc: BeachLocation) {
  const makeAvailable = loc.status === 'out_of_service'
  try {
    const { data } = await api.patch(
      ENDPOINTS.beach.locationUpdate(loc.id),
      { status: makeAvailable ? 'available' : 'out_of_service' },
      { params: { branch_id: branchId.value } },
    )
    upsertLocation(data)
    toast.success(makeAvailable ? 'تم إعادة تفعيل الموقع' : 'تم تعطيل الموقع')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحديث الموقع')
  }
}

// ── Manager: bulk add / reduce ───────────────────────────────────────────
const bulkAddModalOpen = ref(false)
const bulkAddForm = ref({ location_type: 'umbrella', count: 5 })
const bulkAddSubmitting = ref(false)

const bulkReduceModalOpen = ref(false)
const bulkReduceForm = ref({ location_type: '', count: 1 })
const bulkReduceSubmitting = ref(false)

const existingTypes = computed(() => Array.from(new Set(locations.value.map(l => l.location_type))))

async function submitBulkAdd() {
  bulkAddSubmitting.value = true
  try {
    await api.post(ENDPOINTS.beach.locationsBulk, {
      branch_id: branchId.value,
      location_type: bulkAddForm.value.location_type,
      count: bulkAddForm.value.count,
    })
    bulkAddModalOpen.value = false
    toast.success(`تم إضافة ${bulkAddForm.value.count} موقع`)
    fetchLocations()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر إضافة المواقع')
  } finally {
    bulkAddSubmitting.value = false
  }
}

function openBulkReduce() {
  bulkReduceForm.value = { location_type: existingTypes.value[0] ?? '', count: 1 }
  bulkReduceModalOpen.value = true
}

async function submitBulkReduce() {
  bulkReduceSubmitting.value = true
  try {
    await api.post(ENDPOINTS.beach.locationsReduce, {
      branch_id: branchId.value,
      location_type: bulkReduceForm.value.location_type,
      count: bulkReduceForm.value.count,
    })
    bulkReduceModalOpen.value = false
    toast.success(`تم حذف ${bulkReduceForm.value.count} موقع`)
    fetchLocations()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر حذف المواقع (تأكد إن العدد المطلوب متاح فعلاً)')
  } finally {
    bulkReduceSubmitting.value = false
  }
}

onMounted(fetchLocations)
</script>

<template>
  <div class="page-container" dir="rtl">
    <div class="flex items-center justify-between mb-4 gap-2 flex-wrap">
      <div class="flex items-center gap-3">
        <h1 class="section-title mb-0">خريطة الشاطئ</h1>
        <span
          class="w-2 h-2 rounded-full flex-shrink-0"
          :class="wsStatus === 'connected' ? 'bg-green-500' : 'bg-amber-500 animate-pulse'"
          :title="wsStatus === 'connected' ? 'تحديث حي متصل' : 'جاري إعادة الاتصال...'"
        />
      </div>
      <div v-if="isManager" class="flex items-center gap-2">
        <button
          @click="bulkAddModalOpen = true"
          class="px-4 py-2 bg-blue-700 text-white rounded-xl font-bold text-sm hover:bg-blue-800 active:scale-95 transition-all shadow-sm"
        >➕ إضافة مواقع</button>
        <button
          @click="openBulkReduce"
          :disabled="locations.length === 0"
          class="px-4 py-2 bg-white border-2 border-red-300 text-red-700 rounded-xl font-bold text-sm hover:bg-red-50 active:scale-95 transition-all shadow-sm disabled:opacity-40"
        >➖ حذف مواقع</button>
      </div>
    </div>

    <!-- Summary stats -->
    <div v-if="locations.length > 0" class="grid grid-cols-3 gap-3 mb-5">
      <div class="bg-green-50 rounded-xl p-3 text-center border border-green-100">
        <div class="text-2xl font-black text-green-700">{{ stats.available }}</div>
        <div class="text-xs text-green-600 mt-0.5">فاضي</div>
      </div>
      <div class="bg-red-50 rounded-xl p-3 text-center border border-red-100">
        <div class="text-2xl font-black text-red-700">{{ stats.occupied }}</div>
        <div class="text-xs text-red-600 mt-0.5">مشغول</div>
      </div>
      <div class="bg-gray-50 rounded-xl p-3 text-center border border-gray-200">
        <div class="text-2xl font-black text-gray-500">{{ stats.outOfService }}</div>
        <div class="text-xs text-gray-500 mt-0.5">خارج الخدمة</div>
      </div>
    </div>

    <div v-if="loading && locations.length === 0" class="flex items-center justify-center h-40">
      <div class="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
    </div>

    <EmptyState
      v-else-if="locations.length === 0"
      icon="🏖️"
      title="مفيش مواقع شاطئ مضافة لهذا الفرع"
      :description="isManager ? 'اضغط \'إضافة مواقع\' فوق عشان تبدأ' : 'اطلب من المدير إضافة مواقع الشاطئ الأول'"
    />

    <div v-else class="space-y-6">
      <div v-for="[type, typeLocations] in sections" :key="type">
        <h2 class="text-sm font-bold text-gray-500 uppercase tracking-wide mb-2">
          {{ typeIcon(type) }} {{ typeLabel(type) }} ({{ typeLocations.length }})
        </h2>
        <div class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
          <button
            v-for="loc in typeLocations"
            :key="loc.id"
            @click="onTileClick(loc)"
            :class="[
              'aspect-square rounded-2xl border-2 flex flex-col items-center justify-center gap-0.5 font-bold transition-all active:scale-95 shadow-sm relative',
              statusColor(loc),
            ]"
          >
            <span class="text-xl leading-none">{{ typeIcon(loc.location_type) }}</span>
            <span class="text-base leading-none">{{ loc.number }}</span>
            <span class="text-[10px] font-medium">{{ statusLabel(loc.status) }}</span>
            <span v-if="loc.status === 'occupied' && loc.guest_name" class="text-[9px] opacity-70 truncate max-w-full px-1">
              {{ loc.guest_name }}
            </span>
          </button>
        </div>
      </div>
    </div>

    <!-- ── Check-in modal ── -->
    <AppModal :open="checkinModalOpen" title="تسجيل دخول ضيف" size="sm" @close="checkinModalOpen = false">
      <div v-if="checkinTarget" class="space-y-3">
        <p class="text-sm text-gray-500">
          {{ typeIcon(checkinTarget.location_type) }} {{ typeLabel(checkinTarget.location_type) }} {{ checkinTarget.number }}
        </p>
        <div>
          <label class="block text-xs font-bold text-gray-600 mb-1">اسم الضيف (اختياري)</label>
          <input v-model="checkinForm.guest_name" type="text" class="w-full px-3 py-2 border border-stone-200 rounded-lg text-sm" />
        </div>
        <div>
          <label class="block text-xs font-bold text-gray-600 mb-1">رقم التليفون (اختياري)</label>
          <input v-model="checkinForm.guest_phone" type="text" class="w-full px-3 py-2 border border-stone-200 rounded-lg text-sm" dir="ltr" />
        </div>
        <div>
          <label class="block text-xs font-bold text-gray-600 mb-1">عدد الأفراد</label>
          <input v-model.number="checkinForm.guests_count" type="number" min="1" class="w-full px-3 py-2 border border-stone-200 rounded-lg text-sm" />
        </div>
        <label class="flex items-center gap-2 text-sm text-gray-700">
          <input v-model="checkinForm.with_towel" type="checkbox" class="rounded border-stone-300" />
          مع فوطة
        </label>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <button @click="checkinModalOpen = false" class="flex-1 py-2.5 rounded-xl border-2 border-stone-200 text-gray-600 font-semibold hover:bg-gray-50">إلغاء</button>
          <button
            @click="submitCheckin" :disabled="checkinSubmitting"
            class="flex-1 py-2.5 rounded-xl bg-blue-700 text-white font-bold hover:bg-blue-800 disabled:opacity-50"
          >{{ checkinSubmitting ? 'جاري...' : 'تسجيل الدخول' }}</button>
        </div>
      </template>
    </AppModal>

    <!-- ── Occupied detail / checkout modal ── -->
    <AppModal :open="detailModalOpen" title="بيانات الموقع" size="sm" @close="detailModalOpen = false">
      <div v-if="detailTarget" class="space-y-2 text-sm">
        <p class="font-bold text-gray-900">
          {{ typeIcon(detailTarget.location_type) }} {{ typeLabel(detailTarget.location_type) }} {{ detailTarget.number }}
        </p>
        <p v-if="detailTarget.guest_name"><span class="text-gray-500">الضيف:</span> {{ detailTarget.guest_name }}</p>
        <p v-if="detailTarget.guest_phone" dir="ltr" class="text-right"><span class="text-gray-500">التليفون:</span> {{ detailTarget.guest_phone }}</p>
        <p><span class="text-gray-500">عدد الأفراد:</span> {{ detailTarget.guests_count }}</p>
        <p><span class="text-gray-500">فوط:</span> {{ detailTarget.towels_given }}</p>
        <p v-if="detailTarget.checked_in_at"><span class="text-gray-500">وقت الدخول:</span> {{ new Date(detailTarget.checked_in_at).toLocaleTimeString('ar-EG') }}</p>
      </div>
      <template #footer>
        <button
          @click="submitCheckout" :disabled="checkoutSubmitting"
          class="w-full py-2.5 rounded-xl bg-red-600 text-white font-bold hover:bg-red-700 disabled:opacity-50"
        >{{ checkoutSubmitting ? 'جاري...' : 'تسجيل الخروج' }}</button>
      </template>
    </AppModal>

    <!-- ── Manager: bulk add modal ── -->
    <AppModal :open="bulkAddModalOpen" title="إضافة مواقع" size="sm" @close="bulkAddModalOpen = false">
      <div class="space-y-3">
        <div>
          <label class="block text-xs font-bold text-gray-600 mb-1">نوع الموقع</label>
          <input
            v-model="bulkAddForm.location_type" type="text" placeholder="umbrella / pergola / sunbed / cabana"
            class="w-full px-3 py-2 border border-stone-200 rounded-lg text-sm" dir="ltr"
          />
        </div>
        <div>
          <label class="block text-xs font-bold text-gray-600 mb-1">العدد</label>
          <input v-model.number="bulkAddForm.count" type="number" min="1" max="200" class="w-full px-3 py-2 border border-stone-200 rounded-lg text-sm" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <button @click="bulkAddModalOpen = false" class="flex-1 py-2.5 rounded-xl border-2 border-stone-200 text-gray-600 font-semibold hover:bg-gray-50">إلغاء</button>
          <button
            @click="submitBulkAdd" :disabled="bulkAddSubmitting"
            class="flex-1 py-2.5 rounded-xl bg-blue-700 text-white font-bold hover:bg-blue-800 disabled:opacity-50"
          >{{ bulkAddSubmitting ? 'جاري...' : 'إضافة' }}</button>
        </div>
      </template>
    </AppModal>

    <!-- ── Manager: bulk reduce modal ── -->
    <AppModal :open="bulkReduceModalOpen" title="حذف مواقع متاحة" size="sm" @close="bulkReduceModalOpen = false">
      <div class="space-y-3">
        <div>
          <label class="block text-xs font-bold text-gray-600 mb-1">نوع الموقع</label>
          <select v-model="bulkReduceForm.location_type" class="w-full px-3 py-2 border border-stone-200 rounded-lg text-sm">
            <option v-for="t in existingTypes" :key="t" :value="t">{{ typeLabel(t) }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-bold text-gray-600 mb-1">العدد</label>
          <input v-model.number="bulkReduceForm.count" type="number" min="1" class="w-full px-3 py-2 border border-stone-200 rounded-lg text-sm" />
        </div>
        <p class="text-xs text-amber-600">⚠️ بيحذف آخر المواقع المتاحة فقط — المواقع المشغولة لازم تتعمل لها checkout الأول.</p>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <button @click="bulkReduceModalOpen = false" class="flex-1 py-2.5 rounded-xl border-2 border-stone-200 text-gray-600 font-semibold hover:bg-gray-50">إلغاء</button>
          <button
            @click="submitBulkReduce" :disabled="bulkReduceSubmitting"
            class="flex-1 py-2.5 rounded-xl bg-red-600 text-white font-bold hover:bg-red-700 disabled:opacity-50"
          >{{ bulkReduceSubmitting ? 'جاري...' : 'حذف' }}</button>
        </div>
      </template>
    </AppModal>
  </div>
</template>
