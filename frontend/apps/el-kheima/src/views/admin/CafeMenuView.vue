<script setup lang="ts">
/**
 * CafeMenuView — إدارة قائمة الكافيه (categories + items + toggle availability).
 * نفس بالضبط MenuView لكن تارجت /cafe/* endpoints.
 * مدير/admin بس — CRUD كامل.
 */
import { ref, computed, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { useToast } from '@resort-os/ui'

const toast    = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

// ── Types ─────────────────────────────────────────────────────────────
interface Category {
  id: number; name: string; name_ar: string | null
  sort_order: number; is_active: boolean
}
interface MenuItemVariant {
  id: number; name: string; name_ar: string | null
}
interface MenuItem {
  id: number; name: string; name_ar: string | null
  price: number; cost: number | null; is_available: boolean
  category_id: number | null; station: string
  preparation_minutes: number; image_url: string | null
  variants?: MenuItemVariant[]
}

// ── State ─────────────────────────────────────────────────────────────
const categories    = ref<Category[]>([])
const menuItems     = ref<MenuItem[]>([])
const selectedCatId = ref<number | null>(null)
const loading       = ref(false)
const saving        = ref(false)

// ── Category form ──────────────────────────────────────────────────────
const catFormOpen = ref(false)
const catFormEdit = ref<Category | null>(null)
const catForm     = ref({ name: '', name_ar: '', sort_order: 0, is_active: true })

function openCatForm(cat?: Category) {
  catFormEdit.value = cat ?? null
  catForm.value = cat
    ? { name: cat.name, name_ar: cat.name_ar ?? '', sort_order: cat.sort_order, is_active: cat.is_active }
    : { name: '', name_ar: '', sort_order: categories.value.length * 10, is_active: true }
  catFormOpen.value = true
}

async function saveCat() {
  if (!catForm.value.name.trim()) { toast.error('اسم الفئة مطلوب'); return }
  saving.value = true
  try {
    const payload = {
      name:       catForm.value.name.trim(),
      name_ar:    catForm.value.name_ar.trim() || null,
      sort_order: catForm.value.sort_order,
      is_active:  catForm.value.is_active,
    }
    if (catFormEdit.value) {
      // ⚠️ cafe categories PATCH not yet in backend — use full create for now
      // (الـ API عنده POST بس، مفيش PATCH للـ category — نعيد تحميل القائمة بعد الإضافة)
      await api.patch(`/api/v1/cafe/categories/${catFormEdit.value.id}`, payload)
      const idx = categories.value.findIndex(c => c.id === catFormEdit.value!.id)
      if (idx >= 0) categories.value[idx] = { ...categories.value[idx], ...payload }
    } else {
      const { data } = await api.post('/api/v1/cafe/categories', { ...payload, branch_id: branchId })
      categories.value.push(data)
    }
    catFormOpen.value = false
    toast.success(catFormEdit.value ? 'تم تعديل الفئة' : 'تم إضافة الفئة')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحفظ')
  } finally {
    saving.value = false
  }
}

async function deleteCat(cat: Category) {
  if (!confirm(`حذف فئة "${cat.name_ar || cat.name}"؟`)) return
  try {
    await api.delete(`/api/v1/cafe/categories/${cat.id}`)
    categories.value = categories.value.filter(c => c.id !== cat.id)
    menuItems.value  = menuItems.value.filter(i => i.category_id !== cat.id)
    if (selectedCatId.value === cat.id) selectedCatId.value = null
    toast.success('تم حذف الفئة')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحذف')
  }
}

// ── Item form ──────────────────────────────────────────────────────────
const itemFormOpen = ref(false)
const itemFormEdit = ref<MenuItem | null>(null)
const itemForm     = ref({
  name: '', name_ar: '', price: 0, cost: '',
  is_available: true, category_id: null as number | null,
  station: 'bar', preparation_minutes: 5, image_url: '',
})

const STATIONS = [
  { val: 'bar',     label: 'بار ☕' },
  { val: 'hot',     label: 'ساخن 🔥' },
  { val: 'cold',    label: 'بارد 🥤' },
  { val: 'dessert', label: 'حلويات 🍰' },
]

function stationLabel(station: string) {
  return STATIONS.find(s => s.val === station)?.label ?? station
}

function openItemForm(item?: MenuItem) {
  itemFormEdit.value = item ?? null
  itemForm.value = item ? {
    name: item.name, name_ar: item.name_ar ?? '', price: item.price,
    cost: item.cost != null ? String(item.cost) : '',
    is_available: item.is_available, category_id: item.category_id,
    station: item.station, preparation_minutes: item.preparation_minutes,
    image_url: item.image_url ?? '',
  } : {
    name: '', name_ar: '', price: 0, cost: '', is_available: true,
    category_id: selectedCatId.value, station: 'bar', preparation_minutes: 5, image_url: '',
  }
  itemFormOpen.value = true
}

async function saveItem() {
  if (!itemForm.value.name.trim())  { toast.error('اسم الصنف مطلوب'); return }
  if (itemForm.value.price <= 0)    { toast.error('السعر لازم أكبر من صفر'); return }
  // #10: تحذير صريح لو name_ar فاضي — الضيوف العرب هيشوفوا الاسم الإنجليزي
  if (!itemForm.value.name_ar.trim()) {
    const proceed = confirm('تحذير: الاسم العربي فاضي — الضيوف العرب هيشوفوا الاسم الإنجليزي.\nتريد المتابعة بدون اسم عربي؟')
    if (!proceed) return
  }
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      name:                itemForm.value.name.trim(),
      name_ar:             itemForm.value.name_ar.trim() || null,
      price:               itemForm.value.price,
      cost:                itemForm.value.cost !== '' ? parseFloat(itemForm.value.cost as string) : null,
      is_available:        itemForm.value.is_available,
      category_id:         itemForm.value.category_id,
      station:             itemForm.value.station,
      preparation_minutes: itemForm.value.preparation_minutes,
      image_url:           itemForm.value.image_url.trim() || null,
    }
    if (itemFormEdit.value) {
      const { data } = await api.patch(`/api/v1/cafe/items/${itemFormEdit.value.id}`, payload)
      const idx = menuItems.value.findIndex(i => i.id === itemFormEdit.value!.id)
      if (idx >= 0) menuItems.value[idx] = data
    } else {
      const { data } = await api.post('/api/v1/cafe/items', { ...payload, branch_id: branchId })
      menuItems.value.push(data)
    }
    itemFormOpen.value = false
    toast.success(itemFormEdit.value ? 'تم تعديل الصنف' : 'تم إضافة الصنف')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحفظ')
  } finally {
    saving.value = false
  }
}

async function toggleAvailable(item: MenuItem) {
  try {
    const { data } = await api.patch(`/api/v1/cafe/items/${item.id}`, { is_available: !item.is_available })
    const idx = menuItems.value.findIndex(i => i.id === item.id)
    if (idx >= 0) menuItems.value[idx] = data
    toast.success(data.is_available ? 'تم تفعيل الصنف' : 'تم إيقاف الصنف')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تغيير الحالة')
  }
}

async function deleteItem(item: MenuItem) {
  if (!confirm(`حذف "${item.name_ar || item.name}"؟`)) return
  try {
    await api.delete(`/api/v1/cafe/items/${item.id}`)
    menuItems.value = menuItems.value.filter(i => i.id !== item.id)
    toast.success('تم حذف الصنف')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحذف')
  }
}

// ── Computed ───────────────────────────────────────────────────────────
const searchQuery = ref('')

const filteredItems = computed(() => {
  let items = selectedCatId.value !== null
    ? menuItems.value.filter(i => i.category_id === selectedCatId.value)
    : menuItems.value
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    items = items.filter(i =>
      i.name.toLowerCase().includes(q) ||
      (i.name_ar ?? '').includes(q) ||
      // #18: بحث في أسماء المتغيّرات (حجم/نوع)
      (i.variants ?? []).some(
        v => v.name.toLowerCase().includes(q) || (v.name_ar ?? '').includes(q)
      )
    )
  }
  return items
})

// #10: أصناف الكافيه بدون name_ar — نفس تحذير MenuView للمطعم
const itemsMissingAr = computed(() => menuItems.value.filter(i => !i.name_ar).length)

// ── Load ───────────────────────────────────────────────────────────────
async function loadData() {
  loading.value = true
  try {
    const [catsRes, itemsRes] = await Promise.all([
      api.get('/api/v1/cafe/categories', { params: { branch_id: branchId } }),
      api.get('/api/v1/cafe/items', { params: { branch_id: branchId, available_only: false } }),
    ])
    categories.value = catsRes.data.categories ?? catsRes.data.items ?? catsRes.data
    menuItems.value  = itemsRes.data.items ?? itemsRes.data
  } catch (e: any) {
    toast.error('تعذّر تحميل قائمة الكافيه')
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div class="page-container" dir="rtl">
    <div class="flex items-center justify-between mb-5 flex-wrap gap-2">
      <h1 class="section-title mb-0">☕ إدارة قائمة الكافيه</h1>
      <div class="flex gap-2">
        <button @click="openCatForm()"
          class="px-4 py-2 bg-amber-600 text-white rounded-xl font-bold text-sm hover:bg-amber-700 active:scale-95">
          + فئة جديدة
        </button>
        <button @click="openItemForm()"
          class="px-4 py-2 bg-blue-700 text-white rounded-xl font-bold text-sm hover:bg-blue-800 active:scale-95">
          + صنف جديد
        </button>
      </div>
    </div>

    <div v-if="loading" class="flex items-center justify-center h-40">
      <div class="animate-spin w-8 h-8 border-4 border-amber-600 border-t-transparent rounded-full"/>
    </div>

    <div v-else class="flex gap-5 overflow-hidden" style="min-height: 70vh">

      <!-- ── Sidebar: Categories ── -->
      <div class="w-56 flex-shrink-0 space-y-1">
        <div class="text-xs font-bold text-gray-500 uppercase tracking-wide mb-3">الفئات</div>

        <button
          @click="selectedCatId = null"
          :class="['w-full text-right px-3 py-2.5 rounded-xl text-sm font-medium transition-colors',
            selectedCatId === null ? 'bg-amber-600 text-white' : 'bg-white hover:bg-gray-50 text-gray-700 border border-stone-200']"
        >
          الكل ({{ menuItems.length }})
        </button>

        <div
          v-for="cat in categories"
          :key="cat.id"
          :class="['group relative flex items-center justify-between rounded-xl text-sm transition-colors px-3 py-2.5',
            selectedCatId === cat.id ? 'bg-amber-600 text-white' : 'bg-white hover:bg-gray-50 text-gray-700 border border-stone-200',
            !cat.is_active ? 'opacity-50' : '']"
        >
          <button class="flex-1 text-right font-medium" @click="selectedCatId = cat.id">
            {{ cat.name_ar || cat.name }}
            <span class="text-xs opacity-70 mr-1">({{ menuItems.filter(i => i.category_id === cat.id).length }})</span>
          </button>
          <div class="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <button @click.stop="openCatForm(cat)" class="p-1 rounded hover:bg-black/10">✏️</button>
            <button @click.stop="deleteCat(cat)" class="p-1 rounded hover:bg-red-100 text-red-500">🗑</button>
          </div>
        </div>

        <div v-if="categories.length === 0" class="text-sm text-gray-400 text-center py-4">
          لا توجد فئات بعد
        </div>
      </div>

      <!-- ── Main: Items ── -->
      <div class="flex-1 overflow-y-auto">
        <div class="flex items-center justify-between mb-3 gap-3">
          <span class="text-sm text-gray-500 flex-shrink-0">
            {{ filteredItems.length }} صنف
            {{ selectedCatId !== null ? '— ' + (categories.find(c => c.id === selectedCatId)?.name_ar || '') : '' }}
          </span>
          <!-- #10: تحذير أصناف الكافيه بدون name_ar -->
          <span
            v-if="itemsMissingAr > 0"
            class="text-xs bg-amber-100 text-amber-700 border border-amber-200 px-2 py-1 rounded-lg font-semibold flex-shrink-0"
            :title="`${itemsMissingAr} صنف بدون اسم عربي — الضيوف العرب سيرون الاسم الإنجليزي`"
          >
            ⚠️ {{ itemsMissingAr }} صنف بدون اسم عربي
          </span>
          <!-- حقل البحث السريع -->
          <div class="relative flex-1 max-w-xs">
            <input
              v-model="searchQuery"
              type="text"
              placeholder="🔍 بحث عن صنف..."
              class="w-full border border-stone-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 bg-stone-50"
            />
            <button
              v-if="searchQuery"
              @click="searchQuery = ''"
              class="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-lg leading-none"
            >×</button>
          </div>
        </div>

        <div v-if="filteredItems.length === 0" class="flex flex-col items-center justify-center py-16 text-gray-400">
          <div class="text-4xl mb-2">☕</div>
          <p>{{ searchQuery ? `لا نتائج لـ "${searchQuery}"` : 'لا توجد أصناف — اضغط "+ صنف جديد"' }}</p>
        </div>

        <div class="space-y-2">
          <div
            v-for="item in filteredItems"
            :key="item.id"
            class="bg-white rounded-xl border border-stone-200 p-3 flex items-center gap-3 hover:border-amber-300 transition-colors group"
          >
            <!-- availability toggle -->
            <button
              @click="toggleAvailable(item)"
              :class="['w-10 h-6 rounded-full transition-colors flex-shrink-0',
                item.is_available ? 'bg-green-500' : 'bg-gray-300']"
              :title="item.is_available ? 'متاح — اضغط لإيقاف' : 'غير متاح — اضغط لتفعيل'"
            >
              <div :class="['w-5 h-5 bg-white rounded-full shadow transition-transform mx-0.5',
                item.is_available ? 'translate-x-4' : 'translate-x-0']"/>
            </button>

            <!-- info -->
            <div class="flex-1 min-w-0">
              <div class="font-bold text-gray-900 text-sm truncate flex items-center gap-1.5">
                {{ item.name_ar || item.name }}
                <!-- #10: تحذير بدون name_ar في كل صنف -->
                <span
                  v-if="!item.name_ar"
                  class="text-[10px] bg-amber-100 text-amber-600 px-1.5 py-0.5 rounded font-semibold flex-shrink-0"
                  title="لا يوجد اسم عربي — الضيوف العرب سيرون الاسم الإنجليزي"
                >بدون AR</span>
              </div>
              <div class="text-xs text-gray-400 flex items-center gap-2 mt-0.5">
                <span>{{ stationLabel(item.station) }}</span>
                <span>·</span>
                <span>{{ item.preparation_minutes }}د تحضير</span>
                <span v-if="item.category_id">·</span>
                <span v-if="item.category_id">{{ categories.find(c => c.id === item.category_id)?.name_ar || '' }}</span>
              </div>
            </div>

            <!-- price -->
            <div class="text-right flex-shrink-0">
              <div class="font-black text-amber-700">{{ item.price }} ج</div>
              <div v-if="item.cost" class="text-xs text-gray-400">تكلفة: {{ item.cost }} ج</div>
            </div>

            <!-- actions -->
            <div class="flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
              <button
                @click="openItemForm(item)"
                class="p-2 rounded-lg bg-stone-100 hover:bg-stone-200 text-gray-600 text-xs font-semibold transition-colors"
              >✏️ تعديل</button>
              <button
                @click="deleteItem(item)"
                class="p-2 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 text-xs font-semibold transition-colors"
              >🗑</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Category Form Modal ── -->
    <Transition name="modal">
      <div v-if="catFormOpen"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="catFormOpen = false"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
          <div class="bg-amber-600 text-white px-5 py-4">
            <h2 class="font-black text-lg">{{ catFormEdit ? 'تعديل فئة' : 'إضافة فئة جديدة' }}</h2>
          </div>
          <div class="p-5 space-y-4">
            <div>
              <label class="block text-sm font-bold text-gray-700 mb-1.5">الاسم بالإنجليزي <span class="text-red-500">*</span></label>
              <input v-model="catForm.name" type="text" placeholder="Coffee" autofocus
                class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500" />
            </div>
            <div>
              <label class="block text-sm font-bold text-gray-700 mb-1.5">الاسم بالعربي</label>
              <input v-model="catForm.name_ar" type="text" placeholder="قهوة"
                class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500" />
            </div>
            <div>
              <label class="block text-sm font-bold text-gray-700 mb-1.5">ترتيب العرض</label>
              <input v-model.number="catForm.sort_order" type="number"
                class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500" />
            </div>
            <label class="flex items-center gap-3 cursor-pointer">
              <input v-model="catForm.is_active" type="checkbox" class="w-4 h-4 accent-amber-600" />
              <span class="text-sm font-medium text-gray-700">فئة نشطة (مرئية في القائمة)</span>
            </label>
          </div>
          <div class="px-5 pb-5 flex gap-3">
            <button @click="catFormOpen = false"
              class="flex-1 py-3 border-2 border-stone-200 rounded-xl text-sm font-semibold text-gray-600 hover:bg-gray-50">إلغاء</button>
            <button @click="saveCat" :disabled="saving"
              class="flex-1 py-3 bg-amber-600 text-white rounded-xl text-sm font-bold hover:bg-amber-700 disabled:opacity-50 flex items-center justify-center gap-2">
              <div v-if="saving" class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              {{ saving ? 'جاري الحفظ...' : (catFormEdit ? 'حفظ' : 'إضافة') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ── Item Form Modal ── -->
    <Transition name="modal">
      <div v-if="itemFormOpen"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="itemFormOpen = false"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden max-h-screen overflow-y-auto">
          <div class="bg-blue-700 text-white px-5 py-4">
            <h2 class="font-black text-lg">{{ itemFormEdit ? 'تعديل صنف' : 'إضافة صنف جديد' }}</h2>
          </div>
          <div class="p-5 space-y-4">
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-bold text-gray-700 mb-1.5">الاسم بالإنجليزي <span class="text-red-500">*</span></label>
                <input v-model="itemForm.name" type="text" placeholder="Cappuccino" autofocus
                  class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label class="block text-sm font-bold text-gray-700 mb-1.5">الاسم بالعربي</label>
                <input v-model="itemForm.name_ar" type="text" placeholder="كابتشينو"
                  :class="[
                    'w-full border rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2',
                    itemForm.name_ar.trim() ? 'border-stone-300 focus:ring-blue-500' : 'border-amber-400 focus:ring-amber-400'
                  ]" />
                <p v-if="!itemForm.name_ar.trim()" class="text-[11px] text-amber-600 mt-1 flex items-center gap-1">
                  <span>⚠️</span> الضيوف العرب هيشوفوا الاسم الإنجليزي
                </p>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-bold text-gray-700 mb-1.5">السعر (ج) <span class="text-red-500">*</span></label>
                <input v-model.number="itemForm.price" type="number" min="0" step="0.5"
                  class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label class="block text-sm font-bold text-gray-700 mb-1.5">التكلفة (ج) — اختياري</label>
                <input v-model="itemForm.cost" type="number" min="0" step="0.5" placeholder="0"
                  class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
            </div>
            <div>
              <label class="block text-sm font-bold text-gray-700 mb-1.5">الفئة</label>
              <select v-model="itemForm.category_id"
                class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option :value="null">بدون فئة</option>
                <option v-for="cat in categories" :key="cat.id" :value="cat.id">
                  {{ cat.name_ar || cat.name }}
                </option>
              </select>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-bold text-gray-700 mb-1.5">المحطة (Station)</label>
                <select v-model="itemForm.station"
                  class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                  <option v-for="s in STATIONS" :key="s.val" :value="s.val">{{ s.label }}</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-bold text-gray-700 mb-1.5">وقت التحضير (دقيقة)</label>
                <input v-model.number="itemForm.preparation_minutes" type="number" min="1"
                  class="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
            </div>
            <label class="flex items-center gap-3 cursor-pointer">
              <input v-model="itemForm.is_available" type="checkbox" class="w-4 h-4 accent-amber-600" />
              <span class="text-sm font-medium text-gray-700">الصنف متاح (يظهر في قائمة POS)</span>
            </label>
          </div>
          <div class="px-5 pb-5 flex gap-3">
            <button @click="itemFormOpen = false"
              class="flex-1 py-3 border-2 border-stone-200 rounded-xl text-sm font-semibold text-gray-600 hover:bg-gray-50">إلغاء</button>
            <button @click="saveItem" :disabled="saving"
              class="flex-1 py-3 bg-blue-700 text-white rounded-xl text-sm font-bold hover:bg-blue-800 disabled:opacity-50 flex items-center justify-center gap-2">
              <div v-if="saving" class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              {{ saving ? 'جاري الحفظ...' : (itemFormEdit ? 'حفظ التعديلات' : 'إضافة الصنف') }}
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
