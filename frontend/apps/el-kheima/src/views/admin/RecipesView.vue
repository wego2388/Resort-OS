<script setup lang="ts">
// وصفات (Recipe/BOM) المطعم والكافيه — كل صنف كان معاه بس تكلفة يدوية (cost)
// + ربط اختياري 1:1 بمنتج مخزني واحد (linked_product_id)، مفيش أي طريقة
// تعبّر إن "برجر" بيستهلك لحم + رغيف + جبنة بكميات مختلفة من المخزون. الشاشة
// دي أول UI حقيقي لإدارة الوصفات — الـ backend (recipe-lines endpoints) كان
// موجود من غير أي واجهة تستخدمه خالص.
//
// Backend: app/modules/restaurant/api/router.py + app/modules/cafe/api/router.py
// (POST/PATCH/DELETE .../recipe-lines) — مستوى manager، نفس بوابة تعديل
// الصنف نفسه (create/update menu item).
import { ref, computed, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

type ModuleType = 'restaurant' | 'cafe'
const activeModule = ref<ModuleType>('restaurant')

interface RecipeLine {
  id: number; product_id: number; product_name: string; product_unit: string
  quantity_per_unit: number; unit_cost: number; line_cost: number; notes: string | null
}
interface Variant {
  id: number; name: string; name_ar: string | null; price: number
  is_available: boolean; sort_order: number
  recipe_lines: RecipeLine[]; computed_cost: number
}
interface MenuItem {
  id: number; name: string; name_ar: string | null; price: number
  cost: number | null; computed_cost: number; is_available: boolean
  recipe_lines: RecipeLine[]; variants: Variant[]
}
interface Product {
  id: number; name: string; name_ar: string | null; unit: string; cost_price: number
}

const items = ref<MenuItem[]>([])
const products = ref<Product[]>([])
const loading = ref(false)
const search = ref('')

const selectedItem = ref<MenuItem | null>(null)
const showRecipeModal = ref(false)

const newLineProductId = ref<number | ''>('')
const newLineQty = ref('')
const savingLine = ref(false)

const editingLineId = ref<number | null>(null)
const editingQty = ref('')

// ── متغيّرات (حجم/نوع حقيقي — سعر ووصفة مستقلين تمامًا عن الصنف الأساسي،
// مختلف عن extras اللي رسم إضافي بس فوق وصفة ثابتة) ─────────────────────
const newVariantName = ref('')
const newVariantPrice = ref('')
const savingVariant = ref(false)

const expandedVariantId = ref<number | null>(null)
const newVariantLineProductId = ref<number | ''>('')
const newVariantLineQty = ref('')
const savingVariantLine = ref(false)

const editingVariantLineId = ref<number | null>(null)
const editingVariantLineQty = ref('')

// ── مسارات API — مختلفة بين مطعم/كافيه (جداول منفصلة في الباك إند، نفس
// نمط ازدواجية extra-groups الموجود فعلاً) ─────────────────────────────
const itemsPath = computed(() =>
  activeModule.value === 'restaurant' ? '/api/v1/restaurant/menu/items' : '/api/v1/cafe/items')
const recipeLinesPath = (itemId: number) =>
  activeModule.value === 'restaurant'
    ? `/api/v1/restaurant/menu/items/${itemId}/recipe-lines`
    : `/api/v1/cafe/items/${itemId}/recipe-lines`
const recipeLinePath = (lineId: number) =>
  activeModule.value === 'restaurant'
    ? `/api/v1/restaurant/menu/recipe-lines/${lineId}`
    : `/api/v1/cafe/recipe-lines/${lineId}`
const variantsPath = (itemId: number) =>
  activeModule.value === 'restaurant'
    ? `/api/v1/restaurant/menu/items/${itemId}/variants`
    : `/api/v1/cafe/items/${itemId}/variants`
const variantPath = (variantId: number) =>
  activeModule.value === 'restaurant'
    ? `/api/v1/restaurant/menu/variants/${variantId}`
    : `/api/v1/cafe/variants/${variantId}`
const variantLinesPath = (variantId: number) =>
  activeModule.value === 'restaurant'
    ? `/api/v1/restaurant/menu/variants/${variantId}/recipe-lines`
    : `/api/v1/cafe/variants/${variantId}/recipe-lines`
const variantLinePath = (lineId: number) =>
  activeModule.value === 'restaurant'
    ? `/api/v1/restaurant/menu/variant-recipe-lines/${lineId}`
    : `/api/v1/cafe/variant-recipe-lines/${lineId}`

async function fetchItems() {
  loading.value = true
  try {
    const res = await api.get(itemsPath.value, { params: { branch_id: branchId, available_only: false } })
    items.value = res.data
  } catch {
    toast.error('تعذّر تحميل الأصناف — حاول تاني')
  } finally {
    loading.value = false
  }
}

async function fetchProducts() {
  try {
    const res = await api.get('/api/v1/inventory/products', { params: { branch_id: branchId, limit: 200 } })
    products.value = res.data.products ?? res.data.items ?? res.data
  } catch {
    // غير حرج للعرض — بس هيفضل الاختيار في فورم الإضافة فاضي
  }
}

function switchModule(m: ModuleType) {
  if (activeModule.value === m) return
  activeModule.value = m
  selectedItem.value = null
  showRecipeModal.value = false
  fetchItems()
}

const filtered = computed(() => {
  if (!search.value) return items.value
  const q = search.value.trim()
  return items.value.filter((i) => i.name.includes(q) || (i.name_ar ?? '').includes(q))
})

const recipeCount = computed(() => items.value.filter((i) => i.recipe_lines.length > 0).length)

function productLabel(p: Product) {
  return `${p.name_ar || p.name} (${p.unit}) — ${p.cost_price.toLocaleString('ar-EG')} ج`
}

function openRecipe(item: MenuItem) {
  selectedItem.value = item
  newLineProductId.value = ''
  newLineQty.value = ''
  editingLineId.value = null
  newVariantName.value = ''
  newVariantPrice.value = ''
  expandedVariantId.value = null
  editingVariantLineId.value = null
  showRecipeModal.value = true
}

async function refreshSelectedItem() {
  await fetchItems()
  if (selectedItem.value) {
    selectedItem.value = items.value.find((i) => i.id === selectedItem.value!.id) ?? null
  }
}

async function addLine() {
  if (!selectedItem.value) return
  if (!newLineProductId.value || !newLineQty.value || Number(newLineQty.value) <= 0) {
    toast.error('اختر منتج مخزني وحدد كمية أكبر من صفر')
    return
  }
  savingLine.value = true
  try {
    await api.post(recipeLinesPath(selectedItem.value.id), {
      product_id: newLineProductId.value,
      quantity_per_unit: newLineQty.value,
    })
    toast.success('تمت إضافة المكوّن للوصفة')
    newLineProductId.value = ''
    newLineQty.value = ''
    await refreshSelectedItem()
  } catch (e: unknown) {
    const message = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
    toast.error(message ?? 'تعذّرت إضافة المكوّن — تأكد إنه مش مضاف بالفعل')
  } finally {
    savingLine.value = false
  }
}

function startEdit(line: RecipeLine) {
  editingLineId.value = line.id
  editingQty.value = String(line.quantity_per_unit)
}

function cancelEdit() {
  editingLineId.value = null
}

async function saveEdit(line: RecipeLine) {
  if (!editingQty.value || Number(editingQty.value) <= 0) {
    toast.error('الكمية لازم تكون أكبر من صفر')
    return
  }
  try {
    await api.patch(recipeLinePath(line.id), { quantity_per_unit: editingQty.value })
    toast.success('تم تحديث الكمية')
    editingLineId.value = null
    await refreshSelectedItem()
  } catch {
    toast.error('تعذّر تحديث الكمية')
  }
}

async function removeLine(line: RecipeLine) {
  const ok = await confirm({
    title: 'حذف مكوّن من الوصفة',
    message: `متأكد من حذف "${line.product_name}" من وصفة "${selectedItem.value?.name_ar || selectedItem.value?.name}"؟`,
    confirmText: 'حذف', danger: true,
  })
  if (!ok) return
  try {
    await api.delete(recipeLinePath(line.id))
    toast.success('تم حذف المكوّن')
    await refreshSelectedItem()
  } catch {
    toast.error('تعذّر حذف المكوّن')
  }
}

// ── متغيّرات (حجم/نوع) ────────────────────────────────────────────────
// راجع app.modules.restaurant.models.MenuItemVariant — سعر ووصفة مستقلين
// تمامًا عن الصنف الأساسي لكل متغيّر، مش رسم إضافي فوق وصفة ثابتة.

async function addVariant() {
  if (!selectedItem.value) return
  if (!newVariantName.value.trim() || !newVariantPrice.value || Number(newVariantPrice.value) <= 0) {
    toast.error('اكتب اسم المتغيّر وسعر أكبر من صفر')
    return
  }
  savingVariant.value = true
  try {
    await api.post(variantsPath(selectedItem.value.id), {
      name: newVariantName.value.trim(),
      price: newVariantPrice.value,
    })
    toast.success('تمت إضافة المتغيّر')
    newVariantName.value = ''
    newVariantPrice.value = ''
    await refreshSelectedItem()
  } catch (e: unknown) {
    const message = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
    toast.error(message ?? 'تعذّرت إضافة المتغيّر — تأكد إن الاسم مش مكرر')
  } finally {
    savingVariant.value = false
  }
}

async function removeVariant(variant: Variant) {
  const ok = await confirm({
    title: 'حذف متغيّر',
    message: `متأكد من حذف "${variant.name_ar || variant.name}"؟ الطلبات القديمة اللي اختارت المتغيّر ده هتفضل زي ما هي (سجل تاريخي)، بس مش هيبقى متاح للطلبات الجديدة.`,
    confirmText: 'حذف', danger: true,
  })
  if (!ok) return
  try {
    await api.delete(variantPath(variant.id))
    toast.success('تم حذف المتغيّر')
    if (expandedVariantId.value === variant.id) expandedVariantId.value = null
    await refreshSelectedItem()
  } catch {
    toast.error('تعذّر حذف المتغيّر')
  }
}

function toggleVariantExpand(variant: Variant) {
  expandedVariantId.value = expandedVariantId.value === variant.id ? null : variant.id
  newVariantLineProductId.value = ''
  newVariantLineQty.value = ''
  editingVariantLineId.value = null
}

async function addVariantLine(variant: Variant) {
  if (!newVariantLineProductId.value || !newVariantLineQty.value || Number(newVariantLineQty.value) <= 0) {
    toast.error('اختر منتج مخزني وحدد كمية أكبر من صفر')
    return
  }
  savingVariantLine.value = true
  try {
    await api.post(variantLinesPath(variant.id), {
      product_id: newVariantLineProductId.value,
      quantity_per_unit: newVariantLineQty.value,
    })
    toast.success('تمت إضافة المكوّن لوصفة المتغيّر')
    newVariantLineProductId.value = ''
    newVariantLineQty.value = ''
    await refreshSelectedItem()
  } catch (e: unknown) {
    const message = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
    toast.error(message ?? 'تعذّرت إضافة المكوّن — تأكد إنه مش مضاف بالفعل')
  } finally {
    savingVariantLine.value = false
  }
}

function startEditVariantLine(line: RecipeLine) {
  editingVariantLineId.value = line.id
  editingVariantLineQty.value = String(line.quantity_per_unit)
}

function cancelEditVariantLine() {
  editingVariantLineId.value = null
}

async function saveEditVariantLine(line: RecipeLine) {
  if (!editingVariantLineQty.value || Number(editingVariantLineQty.value) <= 0) {
    toast.error('الكمية لازم تكون أكبر من صفر')
    return
  }
  try {
    await api.patch(variantLinePath(line.id), { quantity_per_unit: editingVariantLineQty.value })
    toast.success('تم تحديث الكمية')
    editingVariantLineId.value = null
    await refreshSelectedItem()
  } catch {
    toast.error('تعذّر تحديث الكمية')
  }
}

async function removeVariantLine(variant: Variant, line: RecipeLine) {
  const ok = await confirm({
    title: 'حذف مكوّن من وصفة المتغيّر',
    message: `متأكد من حذف "${line.product_name}" من وصفة "${variant.name_ar || variant.name}"؟`,
    confirmText: 'حذف', danger: true,
  })
  if (!ok) return
  try {
    await api.delete(variantLinePath(line.id))
    toast.success('تم حذف المكوّن')
    await refreshSelectedItem()
  } catch {
    toast.error('تعذّر حذف المكوّن')
  }
}

onMounted(() => { fetchItems(); fetchProducts() })
</script>

<template>
  <div dir="rtl">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-2xl font-black text-gray-900">وصفات الأصناف (Recipe / BOM)</h2>
        <p class="text-sm text-gray-500 mt-1">
          اربط كل صنف بمكوّناته المخزنية — البيع بيخصم المخزون تلقائيًا وبيحسب التكلفة الحقيقية.
        </p>
      </div>
      <AppButton variant="secondary" size="sm" @click="fetchItems">🔄</AppButton>
    </div>

    <!-- Module tabs -->
    <div class="flex gap-2 mb-4">
      <button
        v-for="m in (['restaurant', 'cafe'] as ModuleType[])" :key="m"
        @click="switchModule(m)"
        :class="['px-4 py-2 rounded-xl text-sm font-bold border-2 transition-colors',
                 activeModule === m ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-stone-200 text-gray-600 hover:border-blue-300']"
      >
        {{ m === 'restaurant' ? '🍽️ المطعم' : '☕ الكافيه' }}
      </button>
      <span class="self-center text-xs text-gray-400 mr-2">
        {{ recipeCount }} صنف من أصل {{ items.length }} معاه وصفة حقيقية
      </span>
    </div>

    <div class="mb-4">
      <input v-model="search" type="text" placeholder="ابحث عن صنف..."
        class="w-full max-w-sm border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"/>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>

    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-stone-50">
            <tr>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الصنف</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">السعر</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">التكلفة اليدوية</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">التكلفة المحسوبة</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الوصفة</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">المتغيّرات</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filtered" :key="item.id" class="border-t border-stone-100 hover:bg-stone-50">
              <td class="px-4 py-3 font-medium text-gray-900 text-sm">{{ item.name_ar || item.name }}</td>
              <td class="px-4 py-3 text-sm text-gray-700">{{ item.price.toLocaleString('ar-EG') }} ج</td>
              <td class="px-4 py-3 text-sm text-gray-500">{{ item.cost != null ? item.cost.toLocaleString('ar-EG') + ' ج' : '—' }}</td>
              <td class="px-4 py-3 text-sm font-bold text-gray-900">{{ item.computed_cost.toLocaleString('ar-EG') }} ج</td>
              <td class="px-4 py-3">
                <AppBadge size="sm" :variant="item.recipe_lines.length > 0 ? 'success' : 'neutral'">
                  {{ item.recipe_lines.length > 0 ? `${item.recipe_lines.length} مكوّن` : 'بدون وصفة' }}
                </AppBadge>
              </td>
              <td class="px-4 py-3">
                <AppBadge size="sm" :variant="item.variants.length > 0 ? 'info' : 'neutral'">
                  {{ item.variants.length > 0 ? `${item.variants.length} حجم/نوع` : 'صنف واحد' }}
                </AppBadge>
              </td>
              <td class="px-4 py-3 text-left">
                <AppButton variant="outline" size="sm" @click="openRecipe(item)">إدارة الوصفة</AppButton>
              </td>
            </tr>
            <tr v-if="filtered.length === 0">
              <td colspan="7" class="px-4 py-8">
                <EmptyState icon="🧾" title="لا توجد أصناف" subtitle="جرّب تغيير كلمة البحث أو التبويب" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>

    <!-- Recipe management modal -->
    <AppModal :open="showRecipeModal" :title="`وصفة: ${selectedItem?.name_ar || selectedItem?.name || ''}`"
      size="lg" @close="showRecipeModal = false">
      <div v-if="selectedItem" class="space-y-5">
        <div class="flex items-center justify-between bg-stone-50 rounded-xl p-3 text-sm">
          <span class="text-gray-500">التكلفة المحسوبة من الوصفة</span>
          <span class="font-black text-lg text-gray-900">{{ selectedItem.computed_cost.toLocaleString('ar-EG') }} ج</span>
        </div>

        <!-- Existing lines -->
        <div>
          <h4 class="text-sm font-bold text-gray-700 mb-2">المكوّنات الحالية</h4>
          <div v-if="selectedItem.recipe_lines.length === 0" class="text-sm text-gray-400 py-4 text-center">
            مفيش مكوّنات مضافة — الصنف بيستخدم التكلفة اليدوية بس.
          </div>
          <div v-else class="space-y-2">
            <div v-for="line in selectedItem.recipe_lines" :key="line.id"
              class="flex items-center justify-between border border-stone-200 rounded-xl px-3 py-2">
              <div class="flex-1">
                <div class="font-medium text-sm text-gray-900">{{ line.product_name }}</div>
                <div class="text-xs text-gray-500">
                  {{ line.quantity_per_unit }} {{ line.product_unit }} × {{ line.unit_cost.toLocaleString('ar-EG') }} ج
                  = <span class="font-bold text-gray-700">{{ line.line_cost.toLocaleString('ar-EG') }} ج</span>
                </div>
              </div>
              <div v-if="editingLineId === line.id" class="flex items-center gap-2">
                <input v-model="editingQty" type="number" step="0.001" min="0.001"
                  class="w-24 border border-stone-200 rounded-lg px-2 py-1 text-sm"/>
                <AppButton variant="primary" size="sm" @click="saveEdit(line)">حفظ</AppButton>
                <AppButton variant="ghost" size="sm" @click="cancelEdit">إلغاء</AppButton>
              </div>
              <div v-else class="flex items-center gap-2">
                <AppButton variant="ghost" size="sm" @click="startEdit(line)">✏️</AppButton>
                <AppButton variant="ghost" size="sm" @click="removeLine(line)">🗑️</AppButton>
              </div>
            </div>
          </div>
        </div>

        <!-- Add new line -->
        <div class="border-t border-stone-200 pt-4">
          <h4 class="text-sm font-bold text-gray-700 mb-2">إضافة مكوّن جديد</h4>
          <div class="flex items-end gap-2">
            <div class="flex-1">
              <label class="block text-xs text-gray-500 mb-1">المنتج المخزني</label>
              <select v-model="newLineProductId" class="w-full border border-stone-200 rounded-lg px-2 py-2 text-sm">
                <option value="" disabled>اختر منتج...</option>
                <option v-for="p in products" :key="p.id" :value="p.id">{{ productLabel(p) }}</option>
              </select>
            </div>
            <div class="w-32">
              <label class="block text-xs text-gray-500 mb-1">الكمية / وحدة</label>
              <input v-model="newLineQty" type="number" step="0.001" min="0.001" placeholder="0.150"
                class="w-full border border-stone-200 rounded-lg px-2 py-2 text-sm"/>
            </div>
            <AppButton variant="primary" size="sm" :disabled="savingLine" @click="addLine">
              {{ savingLine ? '...' : 'إضافة' }}
            </AppButton>
          </div>
        </div>

        <!-- المتغيّرات (حجم/نوع) — سعر ووصفة مستقلين تمامًا عن الصنف الأساسي،
             مختلف عن مكوّنات الوصفة فوق (بتاعت الصنف الأساسي بس). مثال:
             كابتشينو صغير/كبير — سعر مختلف واستهلاك حليب مختلف فعليًا. -->
        <div class="border-t border-stone-200 pt-4">
          <h4 class="text-sm font-bold text-gray-700 mb-1">المتغيّرات (أحجام/أنواع مختلفة — اختياري)</h4>
          <p class="text-xs text-gray-400 mb-3">
            لو الصنف بيتباع بأكتر من حجم/نوع بسعر ووصفة مختلفين (زي كابتشينو صغير/كبير)، أضف متغيّر لكل واحد.
            لو مفيش متغيّرات، الصنف بيتباع بسعره ووصفته الأساسية زي ما هو.
          </p>

          <div v-if="selectedItem.variants.length === 0" class="text-sm text-gray-400 py-3 text-center">
            مفيش متغيّرات — الصنف بيتباع بسعر واحد ثابت.
          </div>
          <div v-else class="space-y-2 mb-3">
            <div v-for="variant in selectedItem.variants" :key="variant.id"
              class="border border-stone-200 rounded-xl overflow-hidden">
              <div class="flex items-center justify-between px-3 py-2 bg-stone-50">
                <div class="flex-1 cursor-pointer" @click="toggleVariantExpand(variant)">
                  <div class="font-medium text-sm text-gray-900">
                    {{ variant.name_ar || variant.name }}
                    <span v-if="!variant.is_available" class="text-xs text-red-500 mr-1">(غير متاح)</span>
                  </div>
                  <div class="text-xs text-gray-500">
                    {{ variant.price.toLocaleString('ar-EG') }} ج · تكلفة {{ variant.computed_cost.toLocaleString('ar-EG') }} ج ·
                    {{ variant.recipe_lines.length > 0 ? `${variant.recipe_lines.length} مكوّن` : 'بدون وصفة (fallback لوصفة الصنف الأساسي)' }}
                  </div>
                </div>
                <div class="flex items-center gap-2">
                  <AppButton variant="ghost" size="sm" @click="toggleVariantExpand(variant)">
                    {{ expandedVariantId === variant.id ? '▲ وصفته' : '▼ وصفته' }}
                  </AppButton>
                  <AppButton variant="ghost" size="sm" @click="removeVariant(variant)">🗑️</AppButton>
                </div>
              </div>

              <!-- وصفة المتغيّر — نفس نمط وصفة الصنف الأساسي فوق بالظبط -->
              <div v-if="expandedVariantId === variant.id" class="p-3 space-y-2 bg-white">
                <div v-if="variant.recipe_lines.length === 0" class="text-xs text-gray-400 py-2 text-center">
                  مفيش مكوّنات مضافة لهذا المتغيّر — هيستخدم وصفة الصنف الأساسي (لو موجودة) عند البيع.
                </div>
                <div v-for="line in variant.recipe_lines" :key="line.id"
                  class="flex items-center justify-between border border-stone-100 rounded-lg px-2 py-1.5">
                  <div class="flex-1">
                    <div class="text-sm text-gray-900">{{ line.product_name }}</div>
                    <div class="text-xs text-gray-500">
                      {{ line.quantity_per_unit }} {{ line.product_unit }} × {{ line.unit_cost.toLocaleString('ar-EG') }} ج
                      = <span class="font-bold text-gray-700">{{ line.line_cost.toLocaleString('ar-EG') }} ج</span>
                    </div>
                  </div>
                  <div v-if="editingVariantLineId === line.id" class="flex items-center gap-2">
                    <input v-model="editingVariantLineQty" type="number" step="0.001" min="0.001"
                      class="w-20 border border-stone-200 rounded-lg px-2 py-1 text-sm"/>
                    <AppButton variant="primary" size="sm" @click="saveEditVariantLine(line)">حفظ</AppButton>
                    <AppButton variant="ghost" size="sm" @click="cancelEditVariantLine">إلغاء</AppButton>
                  </div>
                  <div v-else class="flex items-center gap-1">
                    <AppButton variant="ghost" size="sm" @click="startEditVariantLine(line)">✏️</AppButton>
                    <AppButton variant="ghost" size="sm" @click="removeVariantLine(variant, line)">🗑️</AppButton>
                  </div>
                </div>

                <div class="flex items-end gap-2 pt-1">
                  <div class="flex-1">
                    <select v-model="newVariantLineProductId" class="w-full border border-stone-200 rounded-lg px-2 py-1.5 text-sm">
                      <option value="" disabled>اختر منتج...</option>
                      <option v-for="p in products" :key="p.id" :value="p.id">{{ productLabel(p) }}</option>
                    </select>
                  </div>
                  <div class="w-24">
                    <input v-model="newVariantLineQty" type="number" step="0.001" min="0.001" placeholder="0.200"
                      class="w-full border border-stone-200 rounded-lg px-2 py-1.5 text-sm"/>
                  </div>
                  <AppButton variant="primary" size="sm" :disabled="savingVariantLine" @click="addVariantLine(variant)">
                    {{ savingVariantLine ? '...' : 'إضافة' }}
                  </AppButton>
                </div>
              </div>
            </div>
          </div>

          <div class="flex items-end gap-2">
            <div class="flex-1">
              <label class="block text-xs text-gray-500 mb-1">اسم المتغيّر</label>
              <input v-model="newVariantName" type="text" placeholder="كبير"
                class="w-full border border-stone-200 rounded-lg px-2 py-2 text-sm"/>
            </div>
            <div class="w-28">
              <label class="block text-xs text-gray-500 mb-1">السعر</label>
              <input v-model="newVariantPrice" type="number" step="0.01" min="0.01" placeholder="35.00"
                class="w-full border border-stone-200 rounded-lg px-2 py-2 text-sm"/>
            </div>
            <AppButton variant="primary" size="sm" :disabled="savingVariant" @click="addVariant">
              {{ savingVariant ? '...' : 'إضافة متغيّر' }}
            </AppButton>
          </div>
        </div>
      </div>
    </AppModal>
  </div>
</template>
