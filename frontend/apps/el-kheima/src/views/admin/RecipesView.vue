<script setup lang="ts">
// وصفات (Recipe/BOM) منافذ الدايننج — كل صنف كان معاه بس تكلفة يدوية (cost)
// + ربط اختياري 1:1 بمنتج مخزني واحد (linked_product_id)، مفيش أي طريقة
// تعبّر إن "برجر" بيستهلك لحم + رغيف + جبنة بكميات مختلفة من المخزون. الشاشة
// دي أول UI حقيقي لإدارة الوصفات — الـ backend (recipe-lines endpoints) كان
// موجود من غير أي واجهة تستخدمه خالص.
//
// Backend: app/modules/dining/api/router.py (POST/PATCH/DELETE .../
// recipe-lines) — مستوى manager، نفس بوابة تعديل الصنف نفسه. تابات المنافذ
// ديناميكية من /dining/outlets (DINING_CUTOVER_PLAN.md Batch 6 — كانت
// restaurant/cafe تابين ثابتين، دلوقتي أي عدد منافذ).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS , useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const auth = useAuthStore()
const branchId = auth.branchId

interface Outlet { id: number; name: string; name_ar: string | null; is_active: boolean }
const outlets = ref<Outlet[]>([])
const activeOutletId = ref<number | null>(null)
function outletLabel(o: Outlet): string { return o.name_ar || o.name }

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

// ── مسارات API — outlet_id-scoped (DINING_CUTOVER_PLAN.md Batch 6: كانت
// جداول منفصلة تمامًا لمطعم/كافيه، دلوقتي جدول dining واحد، فرق المنفذ
// بس رقم في المسار بدل موديول تاني بالكامل) ────────────────────────────
const recipeLinesPath = (itemId: number) => ENDPOINTS.dining.recipeLines(itemId)
const recipeLinePath  = (lineId: number)  => ENDPOINTS.dining.recipeLine(lineId)
const variantsPath    = (itemId: number)  => ENDPOINTS.dining.variants(itemId)
const variantPath     = (variantId: number) => ENDPOINTS.dining.variant(variantId)
const variantLinesPath = (variantId: number) => ENDPOINTS.dining.variantRecipeLines(variantId)
const variantLinePath  = (lineId: number)   => ENDPOINTS.dining.variantRecipeLine(lineId)

async function loadOutlets() {
  try {
    const { data } = await api.get(ENDPOINTS.dining.outlets, { params: { branch_id: branchId, active_only: true } })
    outlets.value = data?.items ?? data ?? []
    activeOutletId.value = outlets.value[0]?.id ?? null
  } catch {
    toast.error(t('backoffice.diningRecipes.msg.loadOutletsError'))
  }
}

async function fetchItems() {
  if (activeOutletId.value == null) { items.value = []; return }
  loading.value = true
  try {
    const res = await api.get(ENDPOINTS.dining.items(activeOutletId.value), { params: { available_only: false } })
    items.value = res.data
  } catch {
    toast.error(t('backoffice.diningRecipes.msg.loadItemsError'))
  } finally {
    loading.value = false
  }
}

async function fetchProducts() {
  try {
    const res = await api.get(ENDPOINTS.inventory.products, { params: { branch_id: branchId, limit: 200 } })
    products.value = res.data.products ?? res.data.items ?? res.data
  } catch {
    // غير حرج للعرض — بس هيفضل الاختيار في فورم الإضافة فاضي
  }
}

function switchOutlet(id: number) {
  if (activeOutletId.value === id) return
  activeOutletId.value = id
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
  return `${p.name_ar || p.name} (${p.unit}) — ${formatNumber(p.cost_price)} ${t('backoffice.diningRecipes.currency')}`
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
    toast.error(t('backoffice.diningRecipes.msg.selectProductAndQty'))
    return
  }
  savingLine.value = true
  try {
    await api.post(recipeLinesPath(selectedItem.value.id), {
      product_id: newLineProductId.value,
      quantity_per_unit: newLineQty.value,
    })
    toast.success(t('backoffice.diningRecipes.msg.lineAdded'))
    newLineProductId.value = ''
    newLineQty.value = ''
    await refreshSelectedItem()
  } catch (e: unknown) {
    const message = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
    toast.error(message ?? t('backoffice.diningRecipes.msg.lineAddError'))
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
    toast.error(t('backoffice.diningRecipes.msg.qtyMustBePositive'))
    return
  }
  try {
    await api.patch(recipeLinePath(line.id), { quantity_per_unit: editingQty.value })
    toast.success(t('backoffice.diningRecipes.msg.qtyUpdated'))
    editingLineId.value = null
    await refreshSelectedItem()
  } catch {
    toast.error(t('backoffice.diningRecipes.msg.qtyUpdateError'))
  }
}

async function removeLine(line: RecipeLine) {
  const ok = await confirm({
    title: t('backoffice.diningRecipes.deleteLineTitle'),
    message: t('backoffice.diningRecipes.confirmDeleteLine', { product: line.product_name, item: selectedItem.value?.name_ar || selectedItem.value?.name }),
    confirmText: t('backoffice.diningRecipes.delete'), danger: true,
  })
  if (!ok) return
  try {
    await api.delete(recipeLinePath(line.id))
    toast.success(t('backoffice.diningRecipes.msg.lineDeleted'))
    await refreshSelectedItem()
  } catch {
    toast.error(t('backoffice.diningRecipes.msg.lineDeleteError'))
  }
}

// ── متغيّرات (حجم/نوع) ────────────────────────────────────────────────
// راجع app.modules.dining.models.DiningItemVariant — سعر ووصفة مستقلين
// تمامًا عن الصنف الأساسي لكل متغيّر، مش رسم إضافي فوق وصفة ثابتة.

async function addVariant() {
  if (!selectedItem.value) return
  if (!newVariantName.value.trim() || !newVariantPrice.value || Number(newVariantPrice.value) <= 0) {
    toast.error(t('backoffice.diningRecipes.msg.enterVariantNameAndPrice'))
    return
  }
  savingVariant.value = true
  try {
    await api.post(variantsPath(selectedItem.value.id), {
      name: newVariantName.value.trim(),
      price: newVariantPrice.value,
    })
    toast.success(t('backoffice.diningRecipes.msg.variantAdded'))
    newVariantName.value = ''
    newVariantPrice.value = ''
    await refreshSelectedItem()
  } catch (e: unknown) {
    const message = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
    toast.error(message ?? t('backoffice.diningRecipes.msg.variantAddError'))
  } finally {
    savingVariant.value = false
  }
}

async function removeVariant(variant: Variant) {
  const ok = await confirm({
    title: t('backoffice.diningRecipes.deleteVariantTitle'),
    message: t('backoffice.diningRecipes.confirmDeleteVariant', { name: variant.name_ar || variant.name }),
    confirmText: t('backoffice.diningRecipes.delete'), danger: true,
  })
  if (!ok) return
  try {
    await api.delete(variantPath(variant.id))
    toast.success(t('backoffice.diningRecipes.msg.variantDeleted'))
    if (expandedVariantId.value === variant.id) expandedVariantId.value = null
    await refreshSelectedItem()
  } catch {
    toast.error(t('backoffice.diningRecipes.msg.variantDeleteError'))
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
    toast.error(t('backoffice.diningRecipes.msg.selectProductAndQty'))
    return
  }
  savingVariantLine.value = true
  try {
    await api.post(variantLinesPath(variant.id), {
      product_id: newVariantLineProductId.value,
      quantity_per_unit: newVariantLineQty.value,
    })
    toast.success(t('backoffice.diningRecipes.msg.variantLineAdded'))
    newVariantLineProductId.value = ''
    newVariantLineQty.value = ''
    await refreshSelectedItem()
  } catch (e: unknown) {
    const message = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
    toast.error(message ?? t('backoffice.diningRecipes.msg.lineAddError'))
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
    toast.error(t('backoffice.diningRecipes.msg.qtyMustBePositive'))
    return
  }
  try {
    await api.patch(variantLinePath(line.id), { quantity_per_unit: editingVariantLineQty.value })
    toast.success(t('backoffice.diningRecipes.msg.qtyUpdated'))
    editingVariantLineId.value = null
    await refreshSelectedItem()
  } catch {
    toast.error(t('backoffice.diningRecipes.msg.qtyUpdateError'))
  }
}

async function removeVariantLine(variant: Variant, line: RecipeLine) {
  const ok = await confirm({
    title: t('backoffice.diningRecipes.deleteVariantLineTitle'),
    message: t('backoffice.diningRecipes.confirmDeleteLine', { product: line.product_name, item: variant.name_ar || variant.name }),
    confirmText: t('backoffice.diningRecipes.delete'), danger: true,
  })
  if (!ok) return
  try {
    await api.delete(variantLinePath(line.id))
    toast.success(t('backoffice.diningRecipes.msg.lineDeleted'))
    await refreshSelectedItem()
  } catch {
    toast.error(t('backoffice.diningRecipes.msg.lineDeleteError'))
  }
}

onMounted(async () => { await loadOutlets(); await Promise.all([fetchItems(), fetchProducts()]) })
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.diningRecipes.title') }}</h2>
        <p class="text-sm text-gray-500 dark:text-gray-500 mt-1">
          {{ t('backoffice.diningRecipes.subtitle') }}
        </p>
      </div>
      <AppButton variant="secondary" size="sm" @click="fetchItems">🔄</AppButton>
    </div>

    <!-- Outlet tabs — ديناميكية من /dining/outlets -->
    <div v-if="outlets.length" class="flex gap-2 mb-4 flex-wrap">
      <button
        v-for="o in outlets" :key="o.id"
        @click="switchOutlet(o.id)"
        :class="['px-4 py-2 rounded-xl text-sm font-bold border-2 transition-colors',
                 activeOutletId === o.id ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-stone-200 dark:border-border text-gray-600 hover:border-blue-300']"
      >
        {{ outletLabel(o) }}
      </button>
      <span class="self-center text-xs text-gray-400 dark:text-gray-500 ms-2">
        {{ t('backoffice.diningRecipes.recipeCount', { withRecipe: recipeCount, total: items.length }) }}
      </span>
    </div>

    <div class="mb-4">
      <input v-model="search" type="text" :placeholder="t('backoffice.diningRecipes.searchItem')"
        class="w-full max-w-sm border border-stone-200 dark:border-border rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"/>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>

    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.diningRecipes.column.item') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.diningRecipes.column.price') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.diningRecipes.column.manualCost') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.diningRecipes.column.computedCost') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.diningRecipes.column.recipe') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.diningRecipes.column.variants') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filtered" :key="item.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
              <td class="px-4 py-3 font-medium text-gray-900 dark:text-gray-100 text-sm">{{ item.name_ar || item.name }}</td>
              <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ formatNumber(item.price) }} {{ t('backoffice.diningRecipes.currency') }}</td>
              <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-500">{{ item.cost != null ? `${formatNumber(item.cost)} ${t('backoffice.diningRecipes.currency')}` : '—' }}</td>
              <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(item.computed_cost) }} {{ t('backoffice.diningRecipes.currency') }}</td>
              <td class="px-4 py-3">
                <AppBadge size="sm" :variant="item.recipe_lines.length > 0 ? 'success' : 'neutral'">
                  {{ item.recipe_lines.length > 0 ? t('backoffice.diningRecipes.ingredientCount', { count: item.recipe_lines.length }) : t('backoffice.diningRecipes.noRecipe') }}
                </AppBadge>
              </td>
              <td class="px-4 py-3">
                <AppBadge size="sm" :variant="item.variants.length > 0 ? 'info' : 'neutral'">
                  {{ item.variants.length > 0 ? t('backoffice.diningRecipes.variantCount', { count: item.variants.length }) : t('backoffice.diningRecipes.singleItem') }}
                </AppBadge>
              </td>
              <td class="px-4 py-3 text-end">
                <AppButton variant="outline" size="sm" @click="openRecipe(item)">{{ t('backoffice.diningRecipes.manageRecipe') }}</AppButton>
              </td>
            </tr>
            <tr v-if="filtered.length === 0">
              <td colspan="7" class="px-4 py-8">
                <EmptyState icon="🧾" :title="t('backoffice.diningRecipes.noItems')" :subtitle="t('backoffice.diningRecipes.noItemsHint')" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>

    <!-- Recipe management modal -->
    <AppModal :open="showRecipeModal" :title="t('backoffice.diningRecipes.recipeModalTitle', { name: selectedItem?.name_ar || selectedItem?.name || '' })"
      size="lg" @close="showRecipeModal = false">
      <div v-if="selectedItem" class="space-y-5">
        <div class="flex items-center justify-between bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3 text-sm">
          <span class="text-gray-500 dark:text-gray-500">{{ t('backoffice.diningRecipes.costFromRecipe') }}</span>
          <span class="font-black text-lg text-gray-900 dark:text-gray-100">{{ formatNumber(selectedItem.computed_cost) }} {{ t('backoffice.diningRecipes.currency') }}</span>
        </div>

        <!-- Existing lines -->
        <div>
          <h4 class="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">{{ t('backoffice.diningRecipes.currentIngredients') }}</h4>
          <div v-if="selectedItem.recipe_lines.length === 0" class="text-sm text-gray-400 dark:text-gray-500 py-4 text-center">
            {{ t('backoffice.diningRecipes.noIngredients') }}
          </div>
          <div v-else class="space-y-2">
            <div v-for="line in selectedItem.recipe_lines" :key="line.id"
              class="flex items-center justify-between border border-stone-200 dark:border-border rounded-xl px-3 py-2">
              <div class="flex-1">
                <div class="font-medium text-sm text-gray-900 dark:text-gray-100">{{ line.product_name }}</div>
                <div class="text-xs text-gray-500 dark:text-gray-500">
                  {{ line.quantity_per_unit }} {{ line.product_unit }} × {{ formatNumber(line.unit_cost) }} {{ t('backoffice.diningRecipes.currency') }}
                  = <span class="font-bold text-gray-700 dark:text-gray-300">{{ formatNumber(line.line_cost) }} {{ t('backoffice.diningRecipes.currency') }}</span>
                </div>
              </div>
              <div v-if="editingLineId === line.id" class="flex items-center gap-2">
                <input v-model="editingQty" type="number" step="0.001" min="0.001"
                  class="w-24 border border-stone-200 dark:border-border rounded-lg px-2 py-1 text-sm"/>
                <AppButton variant="primary" size="sm" @click="saveEdit(line)">{{ t('backoffice.diningRecipes.save') }}</AppButton>
                <AppButton variant="ghost" size="sm" @click="cancelEdit">{{ t('backoffice.diningRecipes.cancel') }}</AppButton>
              </div>
              <div v-else class="flex items-center gap-2">
                <AppButton variant="ghost" size="sm" @click="startEdit(line)">✏️</AppButton>
                <AppButton variant="ghost" size="sm" @click="removeLine(line)">🗑️</AppButton>
              </div>
            </div>
          </div>
        </div>

        <!-- Add new line -->
        <div class="border-t border-stone-200 dark:border-border pt-4">
          <h4 class="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">{{ t('backoffice.diningRecipes.addIngredient') }}</h4>
          <div class="flex items-end gap-2">
            <div class="flex-1">
              <label class="block text-xs text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.diningRecipes.inventoryProduct') }}</label>
              <select v-model="newLineProductId" class="w-full border border-stone-200 dark:border-border rounded-lg px-2 py-2 text-sm">
                <option value="" disabled>{{ t('backoffice.diningRecipes.selectProduct') }}</option>
                <option v-for="p in products" :key="p.id" :value="p.id">{{ productLabel(p) }}</option>
              </select>
            </div>
            <div class="w-32">
              <label class="block text-xs text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.diningRecipes.qtyPerUnit') }}</label>
              <input v-model="newLineQty" type="number" step="0.001" min="0.001" placeholder="0.150"
                class="w-full border border-stone-200 dark:border-border rounded-lg px-2 py-2 text-sm"/>
            </div>
            <AppButton variant="primary" size="sm" :disabled="savingLine" @click="addLine">
              {{ savingLine ? '...' : t('backoffice.diningRecipes.add') }}
            </AppButton>
          </div>
        </div>

        <!-- المتغيّرات (حجم/نوع) — سعر ووصفة مستقلين تمامًا عن الصنف الأساسي،
             مختلف عن مكوّنات الوصفة فوق (بتاعت الصنف الأساسي بس). مثال:
             كابتشينو صغير/كبير — سعر مختلف واستهلاك حليب مختلف فعليًا. -->
        <div class="border-t border-stone-200 dark:border-border pt-4">
          <h4 class="text-sm font-bold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.diningRecipes.variantsTitle') }}</h4>
          <p class="text-xs text-gray-400 dark:text-gray-500 mb-3">
            {{ t('backoffice.diningRecipes.variantsHint') }}
          </p>

          <div v-if="selectedItem.variants.length === 0" class="text-sm text-gray-400 dark:text-gray-500 py-3 text-center">
            {{ t('backoffice.diningRecipes.noVariants') }}
          </div>
          <div v-else class="space-y-2 mb-3">
            <div v-for="variant in selectedItem.variants" :key="variant.id"
              class="border border-stone-200 dark:border-border rounded-xl overflow-hidden">
              <div class="flex items-center justify-between px-3 py-2 bg-stone-50 dark:bg-gray-800/60">
                <div class="flex-1 cursor-pointer" @click="toggleVariantExpand(variant)">
                  <div class="font-medium text-sm text-gray-900 dark:text-gray-100">
                    {{ variant.name_ar || variant.name }}
                    <span v-if="!variant.is_available" class="text-xs text-red-500 ms-1">({{ t('backoffice.diningRecipes.notAvailable') }})</span>
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-500">
                    {{ formatNumber(variant.price) }} {{ t('backoffice.diningRecipes.currency') }} · {{ t('backoffice.diningRecipes.costLabel') }} {{ formatNumber(variant.computed_cost) }} {{ t('backoffice.diningRecipes.currency') }} ·
                    {{ variant.recipe_lines.length > 0 ? t('backoffice.diningRecipes.ingredientCount', { count: variant.recipe_lines.length }) : t('backoffice.diningRecipes.noRecipeFallback') }}
                  </div>
                </div>
                <div class="flex items-center gap-2">
                  <AppButton variant="ghost" size="sm" @click="toggleVariantExpand(variant)">
                    {{ expandedVariantId === variant.id ? `▲ ${t('backoffice.diningRecipes.variantRecipe')}` : `▼ ${t('backoffice.diningRecipes.variantRecipe')}` }}
                  </AppButton>
                  <AppButton variant="ghost" size="sm" @click="removeVariant(variant)">🗑️</AppButton>
                </div>
              </div>

              <!-- وصفة المتغيّر — نفس نمط وصفة الصنف الأساسي فوق بالظبط -->
              <div v-if="expandedVariantId === variant.id" class="p-3 space-y-2 bg-white dark:bg-surface">
                <div v-if="variant.recipe_lines.length === 0" class="text-xs text-gray-400 dark:text-gray-500 py-2 text-center">
                  {{ t('backoffice.diningRecipes.noVariantIngredients') }}
                </div>
                <div v-for="line in variant.recipe_lines" :key="line.id"
                  class="flex items-center justify-between border border-stone-100 dark:border-border/50 rounded-lg px-2 py-1.5">
                  <div class="flex-1">
                    <div class="text-sm text-gray-900 dark:text-gray-100">{{ line.product_name }}</div>
                    <div class="text-xs text-gray-500 dark:text-gray-500">
                      {{ line.quantity_per_unit }} {{ line.product_unit }} × {{ formatNumber(line.unit_cost) }} {{ t('backoffice.diningRecipes.currency') }}
                      = <span class="font-bold text-gray-700 dark:text-gray-300">{{ formatNumber(line.line_cost) }} {{ t('backoffice.diningRecipes.currency') }}</span>
                    </div>
                  </div>
                  <div v-if="editingVariantLineId === line.id" class="flex items-center gap-2">
                    <input v-model="editingVariantLineQty" type="number" step="0.001" min="0.001"
                      class="w-20 border border-stone-200 dark:border-border rounded-lg px-2 py-1 text-sm"/>
                    <AppButton variant="primary" size="sm" @click="saveEditVariantLine(line)">{{ t('backoffice.diningRecipes.save') }}</AppButton>
                    <AppButton variant="ghost" size="sm" @click="cancelEditVariantLine">{{ t('backoffice.diningRecipes.cancel') }}</AppButton>
                  </div>
                  <div v-else class="flex items-center gap-1">
                    <AppButton variant="ghost" size="sm" @click="startEditVariantLine(line)">✏️</AppButton>
                    <AppButton variant="ghost" size="sm" @click="removeVariantLine(variant, line)">🗑️</AppButton>
                  </div>
                </div>

                <div class="flex items-end gap-2 pt-1">
                  <div class="flex-1">
                    <select v-model="newVariantLineProductId" class="w-full border border-stone-200 dark:border-border rounded-lg px-2 py-1.5 text-sm">
                      <option value="" disabled>{{ t('backoffice.diningRecipes.selectProduct') }}</option>
                      <option v-for="p in products" :key="p.id" :value="p.id">{{ productLabel(p) }}</option>
                    </select>
                  </div>
                  <div class="w-24">
                    <input v-model="newVariantLineQty" type="number" step="0.001" min="0.001" placeholder="0.200"
                      class="w-full border border-stone-200 dark:border-border rounded-lg px-2 py-1.5 text-sm"/>
                  </div>
                  <AppButton variant="primary" size="sm" :disabled="savingVariantLine" @click="addVariantLine(variant)">
                    {{ savingVariantLine ? '...' : t('backoffice.diningRecipes.add') }}
                  </AppButton>
                </div>
              </div>
            </div>
          </div>

          <div class="flex items-end gap-2">
            <div class="flex-1">
              <label class="block text-xs text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.diningRecipes.variantNameLabel') }}</label>
              <input v-model="newVariantName" type="text" :placeholder="t('backoffice.diningRecipes.variantNamePlaceholder')"
                class="w-full border border-stone-200 dark:border-border rounded-lg px-2 py-2 text-sm"/>
            </div>
            <div class="w-28">
              <label class="block text-xs text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.diningRecipes.priceLabel') }}</label>
              <input v-model="newVariantPrice" type="number" step="0.01" min="0.01" placeholder="35.00"
                class="w-full border border-stone-200 dark:border-border rounded-lg px-2 py-2 text-sm"/>
            </div>
            <AppButton variant="primary" size="sm" :disabled="savingVariant" @click="addVariant">
              {{ savingVariant ? '...' : t('backoffice.diningRecipes.addVariant') }}
            </AppButton>
          </div>
        </div>
      </div>
    </AppModal>
  </div>
</template>
