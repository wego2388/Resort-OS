<script setup lang="ts">
/**
 * DiningMenuView — manager+ admin screen for the unified `dining` API:
 * outlets, categories, items (incl. the new group_type="text" free-text
 * extra-group prompts), and tables. First real showcase of @resort-os/ui
 * components (Drawer, DataTable, Tabs, StatusBadge, MoneyInput, ...) — no
 * existing screen used them before this batch.
 *
 * Reachable today only via the manager-only "Dining موحّد (تجريبي)" nav
 * section (BackOfficeLayout.vue) — additive, not a replacement for
 * MenuView.vue/CafeMenuView.vue/TablesAdminView.vue (DINING_CUTOVER_PLAN.md).
 */
import { ref, computed, onMounted, watch } from 'vue'
import { api, ENDPOINTS } from '@resort-os/core'
import {
  AppButton, AppInput, AppTextarea, AppSelect, MoneyInput, AppTabs,
  AppBadge, StatusBadge, AppDrawer, DataTable, SearchInput, IconButton,
  EmptyState, LoadingState, useToast, useConfirm,
} from '@resort-os/ui'
import type { TabItem, SelectOption, DataTableColumn } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

// ── Types ────────────────────────────────────────────────────────────────
interface Outlet {
  id: number; name: string; name_ar: string | null; outlet_type: string
  revenue_account_code: string; default_service_charge_pct: number | string | null
  is_active: boolean
}
interface Category { id: number; outlet_id: number; name: string; name_ar: string | null; sort_order: number; is_active: boolean }
interface ExtraOption { id: number; name: string; name_ar: string | null; price_addition: number | string; is_available: boolean }
interface ExtraGroup { id: number; name: string; name_ar: string | null; group_type: 'pick_list' | 'text'; min_select: number; max_select: number; options: ExtraOption[] }
interface DiningItemRow {
  id: number; outlet_id: number; category_id: number | null
  name: string; name_ar: string | null; price: number | string; cost: number | string | null
  is_available: boolean; station: string; preparation_minutes: number
  available_from_time: string | null; available_until_time: string | null
  extra_groups: ExtraGroup[]
}
interface VenueTable { id: number; outlet_id: number; table_number: string; capacity: number; section: string | null; status: string }

const MAIN_TABS: TabItem[] = [
  { value: 'outlets', label: 'المنافذ' },
  { value: 'menu', label: 'القائمة' },
  { value: 'tables', label: 'الطاولات' },
]
const activeTab = ref('outlets')

const STATIONS: SelectOption[] = [
  { value: 'hot', label: '🔥 ساخن' }, { value: 'grill', label: '🥩 شواية' },
  { value: 'cold', label: '🥗 بارد' }, { value: 'bar', label: '🍹 بار' },
  { value: 'dessert', label: '🍰 حلويات' },
]
const OUTLET_TYPES: SelectOption[] = [
  { value: 'restaurant', label: 'مطعم' }, { value: 'cafe', label: 'كافيه' },
  { value: 'bar', label: 'بار' }, { value: 'buffet', label: 'بوفيه' },
  { value: 'pool_bar', label: 'بار المسبح' }, { value: 'rooftop', label: 'روف توب' },
  { value: 'beach_service', label: 'خدمة الشاطئ' },
]
const GROUP_TYPES: SelectOption[] = [
  { value: 'pick_list', label: 'قائمة اختيارات' }, { value: 'text', label: 'نص حر (Free text)' },
]

// ── Outlets ──────────────────────────────────────────────────────────────
const outlets = ref<Outlet[]>([])
const selectedOutletId = ref<number | null>(null)
const outletDrawerOpen = ref(false)
const outletEdit = ref<Outlet | null>(null)
const outletForm = ref({ name: '', name_ar: '', outlet_type: 'restaurant', revenue_account_code: '4200', default_service_charge_pct: '', is_active: true })
const saving = ref(false)
const loading = ref(false)

const outletOptions = computed<SelectOption[]>(() => outlets.value.map(o => ({ value: o.id, label: o.name_ar || o.name })))
// AppSelect's modelValue is `string | number | undefined` (native <select>
// values are always strings) — selectedOutletId stays `number | null`
// everywhere else in this file (API params, comparisons), so this proxy is
// the only place the null<->undefined/string<->number conversion happens.
const selectedOutletIdOption = computed<string | number | undefined>({
  get: () => selectedOutletId.value ?? undefined,
  set: (v) => { selectedOutletId.value = v !== undefined && v !== '' ? Number(v) : null },
})

function openOutletForm(o?: Outlet) {
  outletEdit.value = o ?? null
  outletForm.value = o
    ? { name: o.name, name_ar: o.name_ar ?? '', outlet_type: o.outlet_type, revenue_account_code: o.revenue_account_code, default_service_charge_pct: o.default_service_charge_pct != null ? String(o.default_service_charge_pct) : '', is_active: o.is_active }
    : { name: '', name_ar: '', outlet_type: 'restaurant', revenue_account_code: '4200', default_service_charge_pct: '', is_active: true }
  outletDrawerOpen.value = true
}

async function saveOutlet() {
  if (!outletForm.value.name.trim()) { toast.error('اسم المنفذ مطلوب'); return }
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      name: outletForm.value.name.trim(),
      name_ar: outletForm.value.name_ar.trim() || null,
      outlet_type: outletForm.value.outlet_type,
      revenue_account_code: outletForm.value.revenue_account_code.trim(),
      default_service_charge_pct: outletForm.value.default_service_charge_pct !== '' ? Number(outletForm.value.default_service_charge_pct) : null,
      is_active: outletForm.value.is_active,
    }
    if (outletEdit.value) {
      const { data } = await api.patch(ENDPOINTS.dining.outlet(outletEdit.value.id), payload)
      const idx = outlets.value.findIndex(o => o.id === outletEdit.value!.id)
      if (idx >= 0) outlets.value[idx] = data
    } else {
      const { data } = await api.post(ENDPOINTS.dining.outlets, { ...payload, branch_id: branchId })
      outlets.value.push(data)
      if (selectedOutletId.value === null) selectedOutletId.value = data.id
    }
    outletDrawerOpen.value = false
    toast.success(outletEdit.value ? 'تم تعديل المنفذ' : 'تم إضافة المنفذ — بدون أي migration أو كود جديد')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحفظ')
  } finally {
    saving.value = false
  }
}

async function loadOutlets() {
  const { data } = await api.get(ENDPOINTS.dining.outlets, { params: { branch_id: branchId } })
  outlets.value = data
  if (data.length && selectedOutletId.value === null) selectedOutletId.value = data[0].id
}

// ── Categories ───────────────────────────────────────────────────────────
const categories = ref<Category[]>([])
const selectedCategoryId = ref<number | null>(null)
const catDrawerOpen = ref(false)
const catEdit = ref<Category | null>(null)
const catForm = ref({ name: '', name_ar: '', sort_order: 0, is_active: true })

function openCatForm(cat?: Category) {
  catEdit.value = cat ?? null
  catForm.value = cat
    ? { name: cat.name, name_ar: cat.name_ar ?? '', sort_order: cat.sort_order, is_active: cat.is_active }
    : { name: '', name_ar: '', sort_order: categories.value.length * 10, is_active: true }
  catDrawerOpen.value = true
}

async function saveCat() {
  if (!selectedOutletId.value || !catForm.value.name.trim()) { toast.error('اسم الفئة مطلوب'); return }
  saving.value = true
  try {
    const payload = { name: catForm.value.name.trim(), name_ar: catForm.value.name_ar.trim() || null, sort_order: Number(catForm.value.sort_order), is_active: catForm.value.is_active }
    if (catEdit.value) {
      const { data } = await api.patch(ENDPOINTS.dining.category(catEdit.value.id), payload)
      const idx = categories.value.findIndex(c => c.id === catEdit.value!.id)
      if (idx >= 0) categories.value[idx] = data
    } else {
      const { data } = await api.post(ENDPOINTS.dining.categories(selectedOutletId.value), { ...payload, branch_id: branchId, outlet_id: selectedOutletId.value })
      categories.value.push(data)
    }
    catDrawerOpen.value = false
    toast.success(catEdit.value ? 'تم تعديل الفئة' : 'تم إضافة الفئة')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحفظ')
  } finally {
    saving.value = false
  }
}

async function deleteCat(cat: Category) {
  if (!await confirm({ message: `حذف فئة "${cat.name_ar || cat.name}"؟ هتتشال من كل أصنافها.`, danger: true })) return
  try {
    await api.delete(ENDPOINTS.dining.category(cat.id))
    categories.value = categories.value.filter(c => c.id !== cat.id)
    if (selectedCategoryId.value === cat.id) selectedCategoryId.value = null
    toast.success('تم حذف الفئة')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحذف')
  }
}

// ── Items ────────────────────────────────────────────────────────────────
const items = ref<DiningItemRow[]>([])
const itemSearch = ref('')
const itemDrawerOpen = ref(false)
const itemEdit = ref<DiningItemRow | null>(null)
const itemForm = ref({
  name: '', name_ar: '', price: '', cost: '', is_available: true,
  category_id: null as number | null, station: 'hot', preparation_minutes: 10,
  available_from_time: '', available_until_time: '',
})
// Same null<->undefined proxy rationale as selectedOutletIdOption above.
const itemCategoryIdOption = computed<string | number | undefined>({
  get: () => itemForm.value.category_id ?? undefined,
  set: (v) => { itemForm.value.category_id = v !== undefined && v !== '' ? Number(v) : null },
})

const itemColumns: DataTableColumn[] = [
  { key: 'name', label: 'الصنف' },
  { key: 'category', label: 'الفئة' },
  { key: 'station', label: 'المحطة' },
  { key: 'price', label: 'السعر', align: 'end' },
  { key: 'status', label: 'الحالة' },
  { key: 'actions', label: '', align: 'end' },
]

const filteredItems = computed(() => {
  let list = items.value
  if (selectedCategoryId.value !== null) list = list.filter(i => i.category_id === selectedCategoryId.value)
  const q = itemSearch.value.trim().toLowerCase()
  if (q) list = list.filter(i => i.name.toLowerCase().includes(q) || (i.name_ar ?? '').includes(q))
  return list
})

function categoryName(id: number | null) {
  return categories.value.find(c => c.id === id)?.name_ar || categories.value.find(c => c.id === id)?.name || '—'
}
const stationLabel = (s: string) => STATIONS.find(st => st.value === s)?.label ?? s

function openItemForm(item?: DiningItemRow) {
  itemEdit.value = item ?? null
  itemForm.value = item
    ? { name: item.name, name_ar: item.name_ar ?? '', price: String(item.price), cost: item.cost != null ? String(item.cost) : '', is_available: item.is_available, category_id: item.category_id, station: item.station, preparation_minutes: item.preparation_minutes, available_from_time: item.available_from_time?.slice(0, 5) ?? '', available_until_time: item.available_until_time?.slice(0, 5) ?? '' }
    : { name: '', name_ar: '', price: '', cost: '', is_available: true, category_id: selectedCategoryId.value, station: 'hot', preparation_minutes: 10, available_from_time: '', available_until_time: '' }
  itemDrawerOpen.value = true
}

async function saveItem() {
  if (!selectedOutletId.value) return
  if (!itemForm.value.name.trim()) { toast.error('اسم الصنف مطلوب'); return }
  const price = Number(itemForm.value.price)
  if (!(price > 0)) { toast.error('السعر لازم يكون أكبر من صفر'); return }
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      name: itemForm.value.name.trim(), name_ar: itemForm.value.name_ar.trim() || null,
      price, cost: itemForm.value.cost !== '' ? Number(itemForm.value.cost) : null,
      is_available: itemForm.value.is_available, category_id: itemForm.value.category_id,
      station: itemForm.value.station, preparation_minutes: Number(itemForm.value.preparation_minutes),
      available_from_time: itemForm.value.available_from_time || null,
      available_until_time: itemForm.value.available_until_time || null,
    }
    if (itemEdit.value) {
      const { data } = await api.patch(ENDPOINTS.dining.item(itemEdit.value.id), payload)
      const idx = items.value.findIndex(i => i.id === itemEdit.value!.id)
      if (idx >= 0) items.value[idx] = { ...items.value[idx], ...data }
    } else {
      const { data } = await api.post(ENDPOINTS.dining.items(selectedOutletId.value), { ...payload, branch_id: branchId, outlet_id: selectedOutletId.value })
      items.value.push(data)
    }
    itemDrawerOpen.value = false
    toast.success(itemEdit.value ? 'تم تعديل الصنف' : 'تم إضافة الصنف')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحفظ')
  } finally {
    saving.value = false
  }
}

async function deleteItem(item: DiningItemRow) {
  if (!await confirm({ message: `حذف "${item.name_ar || item.name}"؟`, danger: true })) return
  try {
    await api.delete(ENDPOINTS.dining.item(item.id))
    items.value = items.value.filter(i => i.id !== item.id)
    toast.success('تم حذف الصنف')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحذف')
  }
}

// ── Extra groups (within item drawer — free-text group_type showcase) ────
const extraGroupForm = ref({ name: '', name_ar: '', group_type: 'pick_list' as 'pick_list' | 'text', min_select: 0, max_select: 1 })
const extraOptionsDraft = ref<{ name: string; price_addition: string }[]>([])

function addOptionDraft() {
  extraOptionsDraft.value.push({ name: '', price_addition: '0' })
}
function removeOptionDraft(idx: number) {
  extraOptionsDraft.value.splice(idx, 1)
}
function resetExtraGroupForm() {
  extraGroupForm.value = { name: '', name_ar: '', group_type: 'pick_list', min_select: 0, max_select: 1 }
  extraOptionsDraft.value = []
}

async function addExtraGroup() {
  if (!itemEdit.value) return
  if (!extraGroupForm.value.name.trim()) { toast.error('اسم المجموعة مطلوب'); return }
  saving.value = true
  try {
    const payload = {
      name: extraGroupForm.value.name.trim(),
      name_ar: extraGroupForm.value.name_ar.trim() || null,
      group_type: extraGroupForm.value.group_type,
      min_select: Number(extraGroupForm.value.min_select),
      max_select: Number(extraGroupForm.value.max_select),
      sort_order: itemEdit.value.extra_groups.length * 10,
      options: extraGroupForm.value.group_type === 'pick_list'
        ? extraOptionsDraft.value.filter(o => o.name.trim()).map(o => ({ name: o.name.trim(), price_addition: Number(o.price_addition || 0) }))
        : [],
    }
    const { data } = await api.post(ENDPOINTS.dining.extraGroups(itemEdit.value.id), payload)
    itemEdit.value.extra_groups.push(data)
    const idx = items.value.findIndex(i => i.id === itemEdit.value!.id)
    if (idx >= 0) items.value[idx]!.extra_groups.push(data)
    resetExtraGroupForm()
    toast.success('تم إضافة مجموعة الإضافات')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الإضافة')
  } finally {
    saving.value = false
  }
}

async function deleteExtraGroup(group: ExtraGroup) {
  if (!itemEdit.value) return
  if (!await confirm({ message: `حذف مجموعة "${group.name_ar || group.name}"؟`, danger: true })) return
  try {
    await api.delete(ENDPOINTS.dining.extraGroup(group.id))
    itemEdit.value.extra_groups = itemEdit.value.extra_groups.filter(g => g.id !== group.id)
    const idx = items.value.findIndex(i => i.id === itemEdit.value!.id)
    if (idx >= 0) items.value[idx]!.extra_groups = items.value[idx]!.extra_groups.filter(g => g.id !== group.id)
    toast.success('تم حذف المجموعة')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحذف')
  }
}

// ── Tables ───────────────────────────────────────────────────────────────
const tables = ref<VenueTable[]>([])
const tableDrawerOpen = ref(false)
const tableEdit = ref<VenueTable | null>(null)
const tableForm = ref({ table_number: '', capacity: 4, section: '' })

function openTableForm(t?: VenueTable) {
  tableEdit.value = t ?? null
  tableForm.value = t ? { table_number: t.table_number, capacity: t.capacity, section: t.section ?? '' } : { table_number: '', capacity: 4, section: '' }
  tableDrawerOpen.value = true
}

async function saveTable() {
  if (!selectedOutletId.value || !tableForm.value.table_number.trim()) { toast.error('رقم الطاولة مطلوب'); return }
  saving.value = true
  try {
    const payload = { table_number: tableForm.value.table_number.trim(), capacity: Number(tableForm.value.capacity), section: tableForm.value.section.trim() || null }
    if (tableEdit.value) {
      const { data } = await api.patch(ENDPOINTS.dining.table(tableEdit.value.id), payload)
      const idx = tables.value.findIndex(t => t.id === tableEdit.value!.id)
      if (idx >= 0) tables.value[idx] = data
    } else {
      const { data } = await api.post(ENDPOINTS.dining.tables(selectedOutletId.value), { ...payload, branch_id: branchId, outlet_id: selectedOutletId.value })
      tables.value.push(data)
    }
    tableDrawerOpen.value = false
    toast.success(tableEdit.value ? 'تم تعديل الطاولة' : 'تم إضافة الطاولة')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحفظ')
  } finally {
    saving.value = false
  }
}

async function deleteTable(t: VenueTable) {
  if (!await confirm({ message: `حذف طاولة "${t.table_number}"؟`, danger: true })) return
  try {
    await api.delete(ENDPOINTS.dining.table(t.id))
    tables.value = tables.value.filter(x => x.id !== t.id)
    toast.success('تم حذف الطاولة')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر الحذف — تأكد إنها مش مشغولة')
  }
}

// ── Data loading ─────────────────────────────────────────────────────────
async function loadOutletScopedData() {
  if (!selectedOutletId.value) return
  loading.value = true
  try {
    const [catsRes, itemsRes, tablesRes] = await Promise.all([
      api.get(ENDPOINTS.dining.categories(selectedOutletId.value)),
      api.get(ENDPOINTS.dining.items(selectedOutletId.value), { params: { available_only: false } }),
      api.get(ENDPOINTS.dining.tables(selectedOutletId.value)),
    ])
    categories.value = catsRes.data
    items.value = itemsRes.data
    tables.value = tablesRes.data
    selectedCategoryId.value = null
  } catch {
    toast.error('تعذّر تحميل بيانات المنفذ')
  } finally {
    loading.value = false
  }
}

watch(selectedOutletId, loadOutletScopedData)

onMounted(async () => {
  loading.value = true
  try {
    await loadOutlets()
    await loadOutletScopedData()
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page-container" dir="rtl">
    <div class="flex items-center justify-between mb-5 flex-wrap gap-2">
      <div>
        <h1 class="section-title mb-0">🍽️ إدارة الدايننج الموحّدة</h1>
        <p class="text-xs text-muted mt-1">شاشة تجريبية — API dining فقط، مش بديل عن قوائم المطعم/الكافيه الحالية بعد.</p>
      </div>
      <div class="w-56" v-if="outletOptions.length">
        <AppSelect v-model="selectedOutletIdOption" :options="outletOptions" placeholder="اختر المنفذ" />
      </div>
    </div>

    <AppTabs v-model="activeTab" :tabs="MAIN_TABS" class="mb-5" />

    <LoadingState v-if="loading" />

    <template v-else>
      <!-- ══════════════════ Outlets tab ══════════════════ -->
      <div v-if="activeTab === 'outlets'" class="space-y-3">
        <div class="flex justify-end">
          <AppButton variant="primary" @click="openOutletForm()">+ منفذ جديد</AppButton>
        </div>
        <EmptyState v-if="outlets.length === 0" icon="🏪" title="لا توجد منافذ بعد" />
        <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <div v-for="o in outlets" :key="o.id" class="bg-white rounded-xl border border-stone-200 p-4 flex flex-col gap-2">
            <div class="flex items-start justify-between">
              <div>
                <div class="font-bold text-gray-900">{{ o.name_ar || o.name }}</div>
                <div class="text-xs text-muted">{{ OUTLET_TYPES.find(t => t.value === o.outlet_type)?.label ?? o.outlet_type }}</div>
              </div>
              <AppBadge :variant="o.is_active ? 'success' : 'neutral'" size="sm">{{ o.is_active ? 'مفعّل' : 'موقوف' }}</AppBadge>
            </div>
            <div class="text-xs text-muted">حساب الإيراد: {{ o.revenue_account_code }}</div>
            <IconButton icon="edit" label="تعديل المنفذ" size="sm" class="self-end" @click="openOutletForm(o)" />
          </div>
        </div>
      </div>

      <!-- ══════════════════ Menu tab ══════════════════ -->
      <div v-else-if="activeTab === 'menu'" class="flex gap-5" style="min-height: 60vh">
        <!-- Categories sidebar -->
        <div class="w-56 flex-shrink-0 space-y-1">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-bold text-muted uppercase tracking-wide">الفئات</span>
            <IconButton icon="add" label="فئة جديدة" size="sm" @click="openCatForm()" />
          </div>
          <button
            type="button"
            @click="selectedCategoryId = null"
            :class="['w-full text-start px-3 py-2.5 rounded-xl text-sm font-medium transition-colors min-h-[44px]',
              selectedCategoryId === null ? 'bg-primary-600 text-white' : 'bg-white hover:bg-background text-gray-700 border border-stone-200']"
          >الكل ({{ items.length }})</button>
          <div
            v-for="cat in categories" :key="cat.id"
            :class="['group flex items-center justify-between px-3 py-2.5 rounded-xl text-sm transition-colors',
              selectedCategoryId === cat.id ? 'bg-primary-600 text-white' : 'bg-white hover:bg-background text-gray-700 border border-stone-200',
              !cat.is_active ? 'opacity-50' : '']"
          >
            <button type="button" class="flex-1 text-start font-medium min-h-[44px]" @click="selectedCategoryId = cat.id">
              {{ cat.name_ar || cat.name }}
              <span class="text-xs opacity-70 ms-1">({{ items.filter(i => i.category_id === cat.id).length }})</span>
            </button>
            <div class="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <IconButton icon="edit" label="تعديل الفئة" size="sm" @click.stop="openCatForm(cat)" />
              <IconButton icon="delete" label="حذف الفئة" size="sm" variant="danger" @click.stop="deleteCat(cat)" />
            </div>
          </div>
          <EmptyState v-if="categories.length === 0" title="لا توجد فئات بعد" />
        </div>

        <!-- Items -->
        <div class="flex-1 min-w-0">
          <div class="flex items-center justify-between mb-3 gap-3">
            <div class="w-64"><SearchInput v-model="itemSearch" placeholder="بحث عن صنف..." /></div>
            <AppButton variant="primary" @click="openItemForm()">+ صنف جديد</AppButton>
          </div>
          <DataTable
            :columns="itemColumns"
            :items="filteredItems"
            :row-key="(i: DiningItemRow) => i.id"
            empty-title="لا توجد أصناف — اضغط + صنف جديد"
            @row-click="openItemForm"
          >
            <template #cell-name="{ item }">
              <div class="font-semibold text-gray-900">{{ item.name_ar || item.name }}</div>
              <div v-if="item.extra_groups.length" class="text-xs text-muted mt-0.5">
                {{ item.extra_groups.length }} مجموعة إضافات
                <AppBadge v-if="item.extra_groups.some((g: ExtraGroup) => g.group_type === 'text')" variant="info" size="sm" class="ms-1">نص حر</AppBadge>
              </div>
            </template>
            <template #cell-category="{ item }">{{ categoryName(item.category_id) }}</template>
            <template #cell-station="{ item }">{{ stationLabel(item.station) }}</template>
            <template #cell-price="{ item }">{{ item.price }} ج</template>
            <template #cell-status="{ item }"><StatusBadge :status="item.is_available ? 'active' : 'draft'" :map="{ active: { label: 'متاح', variant: 'success' }, draft: { label: 'موقوف', variant: 'neutral' } }" /></template>
            <template #cell-actions="{ item }">
              <div class="flex justify-end gap-1" @click.stop>
                <IconButton icon="edit" label="تعديل" size="sm" @click="openItemForm(item)" />
                <IconButton icon="delete" label="حذف" size="sm" variant="danger" @click="deleteItem(item)" />
              </div>
            </template>
          </DataTable>
        </div>
      </div>

      <!-- ══════════════════ Tables tab ══════════════════ -->
      <div v-else class="space-y-3">
        <div class="flex justify-end">
          <AppButton variant="primary" @click="openTableForm()">+ طاولة جديدة</AppButton>
        </div>
        <EmptyState v-if="tables.length === 0" icon="🪑" title="لا توجد طاولات لهذا المنفذ بعد" />
        <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <div v-for="t in tables" :key="t.id" class="bg-white rounded-xl border border-stone-200 p-3 flex flex-col gap-1.5">
            <div class="flex items-center justify-between">
              <span class="font-bold text-gray-900">{{ t.table_number }}</span>
              <StatusBadge :status="t.status" :map="{ available: { label: 'فارغة', variant: 'success' }, occupied: { label: 'مشغولة', variant: 'danger' }, reserved: { label: 'محجوزة', variant: 'warning' }, out_of_service: { label: 'خارج الخدمة', variant: 'neutral' } }" size="sm" />
            </div>
            <div class="text-xs text-muted">{{ t.section || 'بدون قسم' }} · {{ t.capacity }} أشخاص</div>
            <div class="flex justify-end gap-1">
              <IconButton icon="edit" label="تعديل" size="sm" @click="openTableForm(t)" />
              <IconButton icon="delete" label="حذف" size="sm" variant="danger" @click="deleteTable(t)" />
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ══════════════════ Outlet drawer ══════════════════ -->
    <AppDrawer :open="outletDrawerOpen" :title="outletEdit ? 'تعديل منفذ' : 'منفذ جديد'" @close="outletDrawerOpen = false">
      <div class="space-y-3">
        <AppInput v-model="outletForm.name" label="الاسم (EN)" required />
        <AppInput v-model="outletForm.name_ar" label="الاسم (AR)" />
        <AppSelect v-model="outletForm.outlet_type" :options="OUTLET_TYPES" label="نوع المنفذ" />
        <AppInput v-model="outletForm.revenue_account_code" label="حساب الإيراد (Chart of Accounts)" />
        <AppInput v-model="outletForm.default_service_charge_pct" type="number" label="نسبة رسم الخدمة (اختياري — فاضي = الإعداد العام)" />
        <label class="flex items-center gap-2 text-sm font-medium text-gray-700">
          <input type="checkbox" v-model="outletForm.is_active" class="rounded" /> مفعّل
        </label>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="ghost" block @click="outletDrawerOpen = false">إلغاء</AppButton>
          <AppButton variant="primary" block :loading="saving" @click="saveOutlet">حفظ</AppButton>
        </div>
      </template>
    </AppDrawer>

    <!-- ══════════════════ Category drawer ══════════════════ -->
    <AppDrawer :open="catDrawerOpen" :title="catEdit ? 'تعديل فئة' : 'فئة جديدة'" width="sm" @close="catDrawerOpen = false">
      <div class="space-y-3">
        <AppInput v-model="catForm.name" label="الاسم (EN)" required />
        <AppInput v-model="catForm.name_ar" label="الاسم (AR)" />
        <AppInput v-model.number="catForm.sort_order" type="number" label="الترتيب" />
        <label class="flex items-center gap-2 text-sm font-medium text-gray-700">
          <input type="checkbox" v-model="catForm.is_active" class="rounded" /> مفعّلة
        </label>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="ghost" block @click="catDrawerOpen = false">إلغاء</AppButton>
          <AppButton variant="primary" block :loading="saving" @click="saveCat">حفظ</AppButton>
        </div>
      </template>
    </AppDrawer>

    <!-- ══════════════════ Item drawer (incl. extra groups) ══════════════════ -->
    <AppDrawer :open="itemDrawerOpen" :title="itemEdit ? 'تعديل صنف' : 'صنف جديد'" width="lg" @close="itemDrawerOpen = false; resetExtraGroupForm()">
      <div class="space-y-4">
        <div class="grid grid-cols-2 gap-3">
          <AppInput v-model="itemForm.name" label="الاسم (EN)" required />
          <AppInput v-model="itemForm.name_ar" label="الاسم (AR)" />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <MoneyInput v-model="itemForm.price" label="السعر" required />
          <MoneyInput v-model="itemForm.cost" label="التكلفة (اختياري)" />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <AppSelect v-model="itemCategoryIdOption" :options="categories.map(c => ({ value: c.id, label: c.name_ar || c.name }))" label="الفئة" placeholder="بدون فئة" />
          <AppSelect v-model="itemForm.station" :options="STATIONS" label="المحطة (KDS)" />
        </div>
        <AppInput v-model.number="itemForm.preparation_minutes" type="number" label="وقت التحضير (دقيقة)" />

        <!-- ── نافذة تقديم الصنف (wagdy.md P-03، dining parity — DINING_CUTOVER_PLAN.md
             Batch 1) — إفطار 7-11، غداء 12-4، عشاء 7-11. فاضي/فاضي = بدون قيد وقتي. ── -->
        <div class="grid grid-cols-2 gap-3">
          <AppInput v-model="itemForm.available_from_time" type="time" label="متاح من (اختياري)" />
          <AppInput v-model="itemForm.available_until_time" type="time" label="متاح حتى (اختياري)" />
        </div>
        <p v-if="itemForm.available_from_time || itemForm.available_until_time" class="text-[11px] text-gray-400 -mt-2">
          الصنف هيبقى غير متاح للطلب برّه النافذة دي — سيب الحقلين فاضيين لإتاحته طول اليوم.
        </p>

        <label class="flex items-center gap-2 text-sm font-medium text-gray-700">
          <input type="checkbox" v-model="itemForm.is_available" class="rounded" /> متاح للطلب
        </label>

        <!-- ── Extra groups — showcase of the new free-text group_type ── -->
        <div v-if="itemEdit" class="border-t border-stone-200 pt-4 space-y-3">
          <h3 class="text-sm font-bold text-gray-800">مجموعات الإضافات</h3>

          <div v-for="g in itemEdit.extra_groups" :key="g.id" class="bg-background rounded-xl p-3 space-y-1.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="font-semibold text-sm text-gray-900">{{ g.name_ar || g.name }}</span>
                <AppBadge :variant="g.group_type === 'text' ? 'info' : 'neutral'" size="sm">{{ g.group_type === 'text' ? 'نص حر' : 'قائمة اختيارات' }}</AppBadge>
                <AppBadge v-if="g.min_select >= 1" variant="warning" size="sm">إجباري</AppBadge>
              </div>
              <IconButton icon="delete" label="حذف المجموعة" size="sm" variant="danger" @click="deleteExtraGroup(g)" />
            </div>
            <div v-if="g.group_type === 'pick_list' && g.options.length" class="text-xs text-muted">
              {{ g.options.map(o => `${o.name_ar || o.name} (+${o.price_addition} ج)`).join('، ') }}
            </div>
          </div>

          <div class="bg-white border-2 border-dashed border-stone-200 rounded-xl p-3 space-y-2.5">
            <div class="text-xs font-bold text-muted uppercase tracking-wide">مجموعة جديدة</div>
            <div class="grid grid-cols-2 gap-2">
              <AppInput v-model="extraGroupForm.name" label="الاسم (EN)" />
              <AppInput v-model="extraGroupForm.name_ar" label="الاسم (AR) — مثال: كام سمكة؟" />
            </div>
            <AppSelect v-model="extraGroupForm.group_type" :options="GROUP_TYPES" label="النوع" />
            <div v-if="extraGroupForm.group_type === 'pick_list'" class="grid grid-cols-2 gap-2">
              <AppInput v-model.number="extraGroupForm.min_select" type="number" label="أقل عدد اختيار" />
              <AppInput v-model.number="extraGroupForm.max_select" type="number" label="أقصى عدد اختيار" />
            </div>
            <div v-else class="flex items-center gap-2 text-xs text-muted">
              <input type="checkbox" :checked="extraGroupForm.min_select >= 1" @change="extraGroupForm.min_select = extraGroupForm.min_select >= 1 ? 0 : 1" class="rounded" />
              إجباري (لازم الموظف يدخل قيمة)
            </div>

            <div v-if="extraGroupForm.group_type === 'pick_list'" class="space-y-2">
              <div v-for="(opt, idx) in extraOptionsDraft" :key="idx" class="flex items-center gap-2">
                <AppInput v-model="opt.name" placeholder="اسم الاختيار" class="flex-1" />
                <MoneyInput v-model="opt.price_addition" class="w-28" />
                <IconButton icon="close" label="حذف" size="sm" @click="removeOptionDraft(idx)" />
              </div>
              <AppButton variant="ghost" size="sm" @click="addOptionDraft">+ اختيار</AppButton>
            </div>

            <AppButton variant="secondary" size="sm" block :loading="saving" @click="addExtraGroup">إضافة المجموعة</AppButton>
          </div>
        </div>
        <p v-else class="text-xs text-muted border-t border-stone-200 pt-3">احفظ الصنف الأول عشان تقدر تضيف مجموعات إضافات.</p>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="ghost" block @click="itemDrawerOpen = false; resetExtraGroupForm()">إغلاق</AppButton>
          <AppButton variant="primary" block :loading="saving" @click="saveItem">حفظ الصنف</AppButton>
        </div>
      </template>
    </AppDrawer>

    <!-- ══════════════════ Table drawer ══════════════════ -->
    <AppDrawer :open="tableDrawerOpen" :title="tableEdit ? 'تعديل طاولة' : 'طاولة جديدة'" width="sm" @close="tableDrawerOpen = false">
      <div class="space-y-3">
        <AppInput v-model="tableForm.table_number" label="رقم الطاولة" required />
        <AppInput v-model.number="tableForm.capacity" type="number" label="السعة (أشخاص)" />
        <AppInput v-model="tableForm.section" label="القسم/المنطقة (اختياري)" placeholder="مثال: تراس، صالة داخلية" />
      </div>
      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="ghost" block @click="tableDrawerOpen = false">إلغاء</AppButton>
          <AppButton variant="primary" block :loading="saving" @click="saveTable">حفظ</AppButton>
        </div>
      </template>
    </AppDrawer>
  </div>
</template>
