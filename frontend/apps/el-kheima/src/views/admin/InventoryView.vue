<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const auth = useAuthStore()
const branchId = auth.branchId

// أسماء الحقول لازم تطابق ProductRead في الباك إند بالظبط:
// cost_price / reorder_point / category_id — قبل كده كانت الشاشة بتقرأ
// unit_cost / reorder_level / category (أسماء مش موجودة أصلاً)، يعني كشف
// المخزون المنخفض كان بيقارن بـ undefined فمكانش بيشتغل خالص، وعمود الفئة
// والتكلفة كانوا فاضيين دايمًا.
interface Product {
  id: number; name: string; name_ar?: string | null; sku: string; unit: string
  current_stock: number; reorder_point: number; category_id: number | null; cost_price: number | null
  warehouse_id: number | null; min_stock: number; max_stock: number | null
  notes?: string | null; is_active: boolean
}
interface Warehouse { id: number; name: string; name_ar: string | null; code: string }
interface Supplier {
  id: number; name: string; name_ar?: string | null; contact_person?: string | null
  phone?: string | null; email?: string | null; address?: string | null; tax_number?: string | null
  category?: string | null; payment_terms_days: number; credit_limit?: number | null
  notes?: string | null; is_active: boolean
}

const UNIT_OPTIONS = ['piece', 'kg', 'liter', 'box', 'pack', 'dozen']
const unitLabel = (u: string) => t(`backoffice.inventory.unit.${u}`)

const products = ref<Product[]>([])
const warehouses = ref<Warehouse[]>([])
const suppliers = ref<Supplier[]>([])
const categoryNames = ref<Record<number, string>>({})
const categories = ref<{ id: number; name: string; name_ar: string | null }[]>([])
const loading = ref(false)
const search = ref('')
const showLowStock = ref(false)

// ── #6: إضافة/تعديل منتج ────────────────────────────────────────────────
const productModal = ref(false)
const editingProduct = ref<Product | null>(null)
const savingProduct = ref(false)
const productForm = ref({
  name: '', name_ar: '', sku: '', category_id: '' as number | '', warehouse_id: '' as number | '',
  unit: 'piece', cost_price: '0', min_stock: '0', max_stock: '', reorder_point: '0', notes: '',
})

function openCreateProduct() {
  editingProduct.value = null
  productForm.value = { name: '', name_ar: '', sku: '', category_id: '', warehouse_id: '', unit: 'piece', cost_price: '0', min_stock: '0', max_stock: '', reorder_point: '0', notes: '' }
  productModal.value = true
}
function openEditProduct(p: Product) {
  editingProduct.value = p
  productForm.value = {
    name: p.name, name_ar: p.name_ar ?? '', sku: p.sku,
    category_id: p.category_id ?? '', warehouse_id: p.warehouse_id ?? '',
    unit: p.unit, cost_price: String(p.cost_price ?? 0), min_stock: String(p.min_stock ?? 0),
    max_stock: p.max_stock != null ? String(p.max_stock) : '', reorder_point: String(p.reorder_point ?? 0),
    notes: p.notes ?? '',
  }
  productModal.value = true
}

async function saveProduct() {
  if (!productForm.value.name.trim()) { toast.error(t('backoffice.inventory.msg.productNameRequired')); return }
  if (!editingProduct.value && !productForm.value.sku.trim()) { toast.error(t('backoffice.inventory.msg.skuRequired')); return }
  savingProduct.value = true
  try {
    if (editingProduct.value) {
      await api.patch(`/api/v1/inventory/products/${editingProduct.value.id}`, {
        name: productForm.value.name,
        name_ar: productForm.value.name_ar || undefined,
        category_id: productForm.value.category_id || null,
        warehouse_id: productForm.value.warehouse_id || null,
        cost_price: productForm.value.cost_price,
        min_stock: productForm.value.min_stock,
        max_stock: productForm.value.max_stock || undefined,
        reorder_point: productForm.value.reorder_point,
        notes: productForm.value.notes || undefined,
      })
      toast.success(t('backoffice.inventory.msg.productUpdated'))
    } else {
      await api.post('/api/v1/inventory/products', {
        branch_id: branchId,
        name: productForm.value.name,
        name_ar: productForm.value.name_ar || undefined,
        sku: productForm.value.sku,
        category_id: productForm.value.category_id || undefined,
        warehouse_id: productForm.value.warehouse_id || undefined,
        unit: productForm.value.unit,
        cost_price: productForm.value.cost_price,
        min_stock: productForm.value.min_stock,
        max_stock: productForm.value.max_stock || undefined,
        reorder_point: productForm.value.reorder_point,
        notes: productForm.value.notes || undefined,
      })
      toast.success(t('backoffice.inventory.msg.productAdded'))
    }
    productModal.value = false
    await fetchProducts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.inventory.msg.saveProductError'))
  } finally {
    savingProduct.value = false
  }
}

// ── #6: تسجيل استلام بضاعة (Purchase Order) ─────────────────────────────
// إنشاء أمر شراء واستلامه فورًا بنفس الكميات — العملية دي بالنسبة للمستخدم
// "سجّلت بضاعة وصلت دلوقتي"، مش "افتح أمر شراء وسيبه معلّق لحد ما توصل لاحقًا"
// (الحالة التانية دي مش في نطاق wagdy.md #6). الباك إند بيتطلب الاتنين
// (create ثم receive) — مفيش endpoint واحد يعمل الاتنين مع بعض.
const poModal = ref(false)
const savingPO = ref(false)
const poForm = ref({
  supplier_id: '' as number | '', supplier_name: '', supplier_phone: '', warehouse_id: '' as number | '',
  lines: [] as { product_id: number | ''; quantity: string; unit_cost: string }[],
})
function openReceivePO() {
  poForm.value = { supplier_id: '', supplier_name: '', supplier_phone: '', warehouse_id: '', lines: [{ product_id: '', quantity: '', unit_cost: '' }] }
  poModal.value = true
}
function addPOLine() { poForm.value.lines.push({ product_id: '', quantity: '', unit_cost: '' }) }
function removePOLine(i: number) { poForm.value.lines.splice(i, 1) }

// اختيار مورد مسجّل بيعبّي الاسم/التليفون تلقائيًا (لقطة قابلة للتعديل) —
// لسه ممكن تكتب اسم حر لمورد مش مسجّل لو مفيش وقت/داعي لإضافته الآن
// (الباك إند بيقبل الاتنين، راجع PurchaseOrderCreate._require_a_supplier).
function onSelectSupplier() {
  const s = suppliers.value.find(x => x.id === poForm.value.supplier_id)
  if (s) {
    poForm.value.supplier_name = s.name_ar || s.name
    poForm.value.supplier_phone = s.phone || ''
  }
}

async function saveReceivePO() {
  if (!poForm.value.supplier_id && !poForm.value.supplier_name.trim()) {
    toast.error(t('backoffice.inventory.msg.selectOrEnterSupplier')); return
  }
  if (!poForm.value.warehouse_id) { toast.error(t('backoffice.inventory.msg.selectWarehouse')); return }
  const validLines = poForm.value.lines.filter(l => l.product_id && Number(l.quantity) > 0)
  if (validLines.length === 0) { toast.error(t('backoffice.inventory.msg.addAtLeastOneLine')); return }

  savingPO.value = true
  try {
    const { data: po } = await api.post('/api/v1/inventory/purchase-orders', {
      branch_id: branchId,
      supplier_id: poForm.value.supplier_id || undefined,
      supplier_name: poForm.value.supplier_name || undefined,
      supplier_phone: poForm.value.supplier_phone || undefined,
      ordered_at: new Date().toISOString().slice(0, 10),
      items: validLines.map(l => ({ product_id: l.product_id, ordered_qty: l.quantity, unit_cost: l.unit_cost || '0' })),
    })
    await api.post(`/api/v1/inventory/purchase-orders/${po.id}/receive`, {
      warehouse_id: poForm.value.warehouse_id,
      received_at: new Date().toISOString().slice(0, 10),
      items: po.items.map((it: { id: number; ordered_qty: number }) => ({ item_id: it.id, received_qty: it.ordered_qty })),
    })
    toast.success(t('backoffice.inventory.msg.receiptRecorded'))
    poModal.value = false
    await fetchProducts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.inventory.msg.receiptError'))
  } finally {
    savingPO.value = false
  }
}

// ── #6: تعديل مخزون يدوي ─────────────────────────────────────────────────
const adjustModal = ref(false)
const savingAdjust = ref(false)
const adjustForm = ref({ product_id: '' as number | '', warehouse_id: '' as number | '', quantity: '', notes: '' })
function openAdjustStock() {
  adjustForm.value = { product_id: '', warehouse_id: '', quantity: '', notes: '' }
  adjustModal.value = true
}
const adjustProduct = computed(() => products.value.find(p => p.id === adjustForm.value.product_id) ?? null)

async function saveAdjustStock() {
  if (!adjustForm.value.product_id) { toast.error(t('backoffice.inventory.msg.selectProduct')); return }
  if (!adjustForm.value.warehouse_id) { toast.error(t('backoffice.inventory.msg.selectWarehouse')); return }
  const qty = Number(adjustForm.value.quantity)
  if (!qty) { toast.error(t('backoffice.inventory.msg.enterAdjustQty')); return }
  savingAdjust.value = true
  try {
    await api.post('/api/v1/inventory/movements', {
      branch_id: branchId,
      product_id: adjustForm.value.product_id,
      warehouse_id: adjustForm.value.warehouse_id,
      movement_type: 'adjustment',
      quantity: adjustForm.value.quantity,
      unit_cost: adjustProduct.value?.cost_price ?? '0',
      notes: adjustForm.value.notes || undefined,
      moved_at: new Date().toISOString(),
    })
    toast.success(t('backoffice.inventory.msg.adjustmentRecorded'))
    adjustModal.value = false
    await fetchProducts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.inventory.msg.adjustmentError'))
  } finally {
    savingAdjust.value = false
  }
}

const categoryLabel = (p: Product) =>
  p.category_id != null ? (categoryNames.value[p.category_id] ?? '—') : '—'

const filtered = () => {
  let list = products.value
  if (showLowStock.value) list = list.filter(p => p.current_stock <= p.reorder_point)
  if (search.value) list = list.filter(p => p.name.includes(search.value) || p.sku.includes(search.value))
  return list
}

const lowStockCount = () => products.value.filter(p => p.current_stock <= p.reorder_point).length

async function fetchCategories() {
  try {
    const res = await api.get('/api/v1/inventory/categories', { params: { branch_id: branchId } })
    categories.value = res.data ?? []
    categoryNames.value = Object.fromEntries(categories.value.map(c => [c.id, c.name_ar || c.name]))
  } catch {
    // غير حرج: أسماء الفئات مجرد عرض، بترجع لـ — لو فشلت
  }
}

async function fetchWarehouses() {
  try {
    const res = await api.get('/api/v1/inventory/warehouses', { params: { branch_id: branchId } })
    warehouses.value = res.data ?? []
  } catch {
    // غير حرج لعرض قائمة المنتجات — بس هيمنع استلام البضاعة/التعديل اليدوي
    // (محتاجين warehouse_id) لو فشل، فبنسيب toast يبان لو المستخدم فتح مودال محتاجه
  }
}

async function fetchSuppliers() {
  try {
    const res = await api.get('/api/v1/inventory/suppliers', { params: { branch_id: branchId, active_only: false, size: 100 } })
    suppliers.value = res.data.items ?? []
  } catch {
    // غير حرج لعرض المنتجات — بس هيمنع اختيار مورد مسجّل وقت تسجيل استلام
  }
}

// ── الموردون — CRUD كامل (شاشة مصغّرة داخل نفس مودال المخزون) ──────────
const supplierListModal = ref(false)
const supplierModal = ref(false)
const editingSupplier = ref<Supplier | null>(null)
const savingSupplier = ref(false)
const supplierForm = ref({
  name: '', name_ar: '', contact_person: '', phone: '', email: '', address: '',
  tax_number: '', category: '', payment_terms_days: '0', credit_limit: '', notes: '',
})

function openCreateSupplier() {
  editingSupplier.value = null
  supplierForm.value = { name: '', name_ar: '', contact_person: '', phone: '', email: '', address: '', tax_number: '', category: '', payment_terms_days: '0', credit_limit: '', notes: '' }
  supplierModal.value = true
}
function openEditSupplier(s: Supplier) {
  editingSupplier.value = s
  supplierForm.value = {
    name: s.name, name_ar: s.name_ar ?? '', contact_person: s.contact_person ?? '',
    phone: s.phone ?? '', email: s.email ?? '', address: s.address ?? '',
    tax_number: s.tax_number ?? '', category: s.category ?? '',
    payment_terms_days: String(s.payment_terms_days ?? 0),
    credit_limit: s.credit_limit != null ? String(s.credit_limit) : '', notes: s.notes ?? '',
  }
  supplierModal.value = true
}

async function saveSupplier() {
  if (!supplierForm.value.name.trim()) { toast.error(t('backoffice.inventory.msg.supplierNameRequired')); return }
  savingSupplier.value = true
  try {
    const payload = {
      name: supplierForm.value.name,
      name_ar: supplierForm.value.name_ar || undefined,
      contact_person: supplierForm.value.contact_person || undefined,
      phone: supplierForm.value.phone || undefined,
      email: supplierForm.value.email || undefined,
      address: supplierForm.value.address || undefined,
      tax_number: supplierForm.value.tax_number || undefined,
      category: supplierForm.value.category || undefined,
      payment_terms_days: Number(supplierForm.value.payment_terms_days || 0),
      credit_limit: supplierForm.value.credit_limit || undefined,
      notes: supplierForm.value.notes || undefined,
    }
    if (editingSupplier.value) {
      await api.patch(`/api/v1/inventory/suppliers/${editingSupplier.value.id}`, payload)
      toast.success(t('backoffice.inventory.msg.supplierUpdated'))
    } else {
      await api.post('/api/v1/inventory/suppliers', { branch_id: branchId, ...payload })
      toast.success(t('backoffice.inventory.msg.supplierAdded'))
    }
    supplierModal.value = false
    await fetchSuppliers()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.inventory.msg.saveSupplierError'))
  } finally {
    savingSupplier.value = false
  }
}

async function toggleSupplierActive(s: Supplier) {
  try {
    await api.patch(`/api/v1/inventory/suppliers/${s.id}`, { is_active: !s.is_active })
    await fetchSuppliers()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.inventory.msg.supplierStatusError'))
  }
}

async function fetchProducts() {
  loading.value = true
  try {
    // الشاشة بتفلتر/تبحث client-side على القائمة كاملة (راجع filtered() فوق)،
    // والباك إند مش بيقبل limit — بس size (حد أقصى 100) — فلازم نلف على كل
    // الصفحات بدل ما نتوهم إن size=200 هيرجّع كل الأصناف مرة واحدة.
    const size = 100
    let page = 1
    let all: any[] = []
    while (true) {
      const res = await api.get('/api/v1/inventory/products', { params: { branch_id: branchId, page, size } })
      const items = res.data.items ?? []
      all = all.concat(items)
      if (all.length >= res.data.total || items.length < size) break
      page += 1
    }
    products.value = all
  } catch { toast.error(t('backoffice.inventory.msg.loadProductsError')) }
  finally { loading.value = false }
}

onMounted(() => { fetchCategories(); fetchWarehouses(); fetchSuppliers(); fetchProducts() })
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.inventory.title') }}</h2>
      <div class="flex items-center gap-2">
        <button @click="showLowStock = !showLowStock"
          :class="['rounded-xl border-2 px-3 py-1.5 text-sm font-medium transition-colors', showLowStock ? 'border-red-500 bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300' : 'border-stone-200 text-gray-600 hover:border-red-300 dark:border-border dark:text-gray-400']">
          ⚠️ {{ t('backoffice.inventory.lowStock') }} ({{ lowStockCount() }})
        </button>
        <AppButton variant="secondary" size="sm" @click="supplierListModal = true">🚚 {{ t('backoffice.inventory.suppliers') }}</AppButton>
        <AppButton variant="secondary" size="sm" @click="openAdjustStock">⚖️ {{ t('backoffice.inventory.manualAdjustment') }}</AppButton>
        <AppButton variant="secondary" size="sm" @click="openReceivePO">📦 {{ t('backoffice.inventory.recordReceipt') }}</AppButton>
        <AppButton size="sm" @click="openCreateProduct">+ {{ t('backoffice.inventory.newProduct') }}</AppButton>
        <AppButton variant="secondary" size="sm" @click="fetchProducts">🔄</AppButton>
      </div>
    </div>

    <!-- Search -->
    <div class="mb-4">
      <input v-model="search" type="text" :placeholder="t('backoffice.inventory.searchPlaceholder')"
        class="w-full max-w-sm border border-stone-200 dark:border-border rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"/>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>

    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.column.product') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">SKU</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.column.category') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.column.stock') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.column.reorderPoint') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.column.unitCost') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.column.status') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in filtered()" :key="p.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
              <td class="px-4 py-3 font-medium text-gray-900 dark:text-gray-100 text-sm">{{ p.name }}</td>
              <td class="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400">{{ p.sku }}</td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ categoryLabel(p) }}</td>
              <td class="px-4 py-3">
                <span :class="['text-sm font-bold', p.current_stock <= p.reorder_point ? 'text-red-600' : 'text-gray-900 dark:text-gray-100']">
                  {{ p.current_stock }} {{ unitLabel(p.unit) }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{{ p.reorder_point }} {{ unitLabel(p.unit) }}</td>
              <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ formatNumber(p.cost_price ?? 0) }} {{ t('backoffice.inventory.currency') }}</td>
              <td class="px-4 py-3">
                <AppBadge size="sm" :variant="p.current_stock <= 0 ? 'danger' : p.current_stock <= p.reorder_point ? 'warning' : 'success'">
                  {{ p.current_stock <= 0 ? t('backoffice.inventory.outOfStock') : p.current_stock <= p.reorder_point ? t('backoffice.inventory.low') : t('backoffice.inventory.available') }}
                </AppBadge>
              </td>
              <td class="px-4 py-3 text-end">
                <button @click="openEditProduct(p)" class="text-xs font-semibold text-primary-700 hover:underline">{{ t('backoffice.inventory.edit') }}</button>
              </td>
            </tr>
            <tr v-if="filtered().length === 0">
              <td colspan="8" class="px-4 py-8">
                <EmptyState icon="📦" :title="t('backoffice.inventory.noProducts')" :subtitle="t('backoffice.inventory.noProductsHint')" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>

    <!-- #6: إضافة/تعديل منتج -->
    <AppModal :open="productModal" :title="editingProduct ? t('backoffice.inventory.editProductTitle') : t('backoffice.inventory.newProductTitle')" @close="productModal = false">
      <div class="space-y-3">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input v-model="productForm.name" type="text" :placeholder="t('backoffice.inventory.nameEn')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.name_ar" type="text" :placeholder="t('backoffice.inventory.nameAr')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.sku" type="text" placeholder="SKU *" :disabled="!!editingProduct"
            class="rounded-xl border border-stone-200 px-3 py-2 text-sm disabled:bg-gray-50 dark:bg-surface-2 disabled:text-gray-400 dark:border-border dark:text-gray-400 dark:disabled:bg-gray-800" />
          <select v-model="productForm.unit" :disabled="!!editingProduct" class="rounded-xl border border-stone-200 px-3 py-2 text-sm disabled:bg-gray-50 dark:bg-surface-2 dark:border-border dark:disabled:bg-gray-800">
            <option v-for="u in UNIT_OPTIONS" :key="u" :value="u">{{ unitLabel(u) }}</option>
          </select>
          <select v-model="productForm.category_id" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
            <option value="">{{ t('backoffice.inventory.noCategory') }}</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name_ar || c.name }}</option>
          </select>
          <select v-model="productForm.warehouse_id" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
            <option value="">{{ t('backoffice.inventory.noSpecificWarehouse') }}</option>
            <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.name_ar || w.name }}</option>
          </select>
          <input v-model="productForm.cost_price" type="number" min="0" step="0.01" :placeholder="t('backoffice.inventory.unitCost')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.reorder_point" type="number" min="0" step="0.01" :placeholder="t('backoffice.inventory.reorderPoint')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.min_stock" type="number" min="0" step="0.01" :placeholder="t('backoffice.inventory.minStock')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.max_stock" type="number" min="0" step="0.01" :placeholder="t('backoffice.inventory.maxStockOptional')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.notes" type="text" :placeholder="t('backoffice.inventory.notes')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
        </div>
        <AppButton class="mt-1" size="sm" :loading="savingProduct" @click="saveProduct">
          {{ editingProduct ? t('backoffice.inventory.saveChanges') : t('backoffice.inventory.addProduct') }}
        </AppButton>
      </div>
    </AppModal>

    <!-- #6: تسجيل استلام بضاعة -->
    <AppModal :open="poModal" :title="t('backoffice.inventory.recordReceiptTitle')" size="lg" @close="poModal = false">
      <div class="space-y-3">
        <div>
          <label class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.supplier') }}</label>
          <select v-model="poForm.supplier_id" @change="onSelectSupplier"
            class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm mt-1">
            <option value="">{{ t('backoffice.inventory.unregisteredSupplier') }}</option>
            <option v-for="s in suppliers.filter(x => x.is_active)" :key="s.id" :value="s.id">
              {{ s.name_ar || s.name }}
            </option>
          </select>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <input v-model="poForm.supplier_name" type="text" :placeholder="t('backoffice.inventory.supplierName')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          <input v-model="poForm.supplier_phone" type="text" :placeholder="t('backoffice.inventory.supplierPhone')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        </div>
        <select v-model="poForm.warehouse_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.inventory.selectReceivingWarehouse') }}</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.name_ar || w.name }}</option>
        </select>

        <div class="border-t border-stone-100 dark:border-border/50 pt-3 space-y-2">
          <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.receivedItems') }}</div>
          <div v-for="(line, i) in poForm.lines" :key="i" class="grid grid-cols-12 gap-2 items-center">
            <select v-model="line.product_id" class="col-span-6 border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
              <option value="">{{ t('backoffice.inventory.selectProduct') }}</option>
              <option v-for="p in products" :key="p.id" :value="p.id">{{ p.name_ar || p.name }} ({{ p.sku }})</option>
            </select>
            <input v-model="line.quantity" type="number" min="0" step="0.01" :placeholder="t('backoffice.inventory.quantity')"
              class="col-span-3 border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            <input v-model="line.unit_cost" type="number" min="0" step="0.01" :placeholder="t('backoffice.inventory.unitPrice')"
              class="col-span-2 border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            <button @click="removePOLine(i)" class="col-span-1 text-lg text-red-400 hover:text-red-600 dark:hover:text-red-300">×</button>
          </div>
          <button @click="addPOLine" class="text-xs font-semibold text-primary-700 hover:underline">+ {{ t('backoffice.inventory.addItem') }}</button>
        </div>

        <AppButton class="mt-1" size="sm" :loading="savingPO" @click="saveReceivePO">{{ t('backoffice.inventory.recordReceiptAction') }}</AppButton>
      </div>
    </AppModal>

    <!-- #6: تعديل مخزون يدوي -->
    <AppModal :open="adjustModal" :title="t('backoffice.inventory.manualAdjustmentTitle')" @close="adjustModal = false">
      <div class="space-y-3">
        <select v-model="adjustForm.product_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.inventory.selectProductRequired') }}</option>
          <option v-for="p in products" :key="p.id" :value="p.id">{{ p.name_ar || p.name }} ({{ p.sku }}) — {{ t('backoffice.inventory.current') }}: {{ p.current_stock }} {{ unitLabel(p.unit) }}</option>
        </select>
        <select v-model="adjustForm.warehouse_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.inventory.selectWarehouseRequired') }}</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.name_ar || w.name }}</option>
        </select>
        <input v-model="adjustForm.quantity" type="number" step="0.01" :placeholder="t('backoffice.inventory.adjustQtyPlaceholder')"
          class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="adjustForm.notes" type="text" :placeholder="t('backoffice.inventory.adjustReasonPlaceholder')"
          class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <AppButton class="mt-1" size="sm" :loading="savingAdjust" @click="saveAdjustStock">{{ t('backoffice.inventory.recordAdjustment') }}</AppButton>
      </div>
    </AppModal>

    <!-- الموردون — قائمة كاملة -->
    <AppModal :open="supplierListModal" :title="t('backoffice.inventory.suppliers')" size="lg" @close="supplierListModal = false">
      <div class="space-y-3">
        <AppButton size="sm" @click="openCreateSupplier">+ {{ t('backoffice.inventory.newSupplier') }}</AppButton>
        <div class="overflow-x-auto border border-stone-100 dark:border-border/50 rounded-xl">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.name') }}</th>
                <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.contactPerson') }}</th>
                <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.phone') }}</th>
                <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.paymentTerms') }}</th>
                <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.inventory.column.status') }}</th>
                <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in suppliers" :key="s.id" class="border-t border-stone-100 dark:border-border/50">
                <td class="px-3 py-2 text-sm font-medium text-gray-900 dark:text-gray-100">{{ s.name_ar || s.name }}</td>
                <td class="px-3 py-2 text-sm text-gray-600 dark:text-gray-400">{{ s.contact_person || '—' }}</td>
                <td class="px-3 py-2 text-sm text-gray-600 dark:text-gray-400" dir="ltr">{{ s.phone || '—' }}</td>
                <td class="px-3 py-2 text-sm text-gray-600 dark:text-gray-400">{{ t('backoffice.inventory.daysCount', { days: s.payment_terms_days }) }}</td>
                <td class="px-3 py-2">
                  <AppBadge size="sm" :variant="s.is_active ? 'success' : 'neutral'">
                    {{ s.is_active ? t('backoffice.inventory.active') : t('backoffice.inventory.stopped') }}
                  </AppBadge>
                </td>
                <td class="px-3 py-2 text-end whitespace-nowrap">
                  <button @click="openEditSupplier(s)" class="text-xs font-semibold text-primary-700 hover:underline me-3">{{ t('backoffice.inventory.edit') }}</button>
                  <button @click="toggleSupplierActive(s)" class="text-xs font-semibold text-gray-500 dark:text-gray-400 hover:underline">
                    {{ s.is_active ? t('backoffice.inventory.stop') : t('backoffice.inventory.activate') }}
                  </button>
                </td>
              </tr>
              <tr v-if="suppliers.length === 0">
                <td colspan="6" class="px-4 py-8">
                  <EmptyState icon="🚚" :title="t('backoffice.inventory.noSuppliers')" :subtitle="t('backoffice.inventory.noSuppliersHint')" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </AppModal>

    <!-- الموردون — إضافة/تعديل -->
    <AppModal :open="supplierModal" :title="editingSupplier ? t('backoffice.inventory.editSupplierTitle') : t('backoffice.inventory.newSupplierTitle')" @close="supplierModal = false">
      <div class="space-y-3">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input v-model="supplierForm.name" type="text" :placeholder="t('backoffice.inventory.nameEn')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="supplierForm.name_ar" type="text" :placeholder="t('backoffice.inventory.nameAr')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="supplierForm.contact_person" type="text" :placeholder="t('backoffice.inventory.contactPerson')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="supplierForm.phone" type="text" :placeholder="t('backoffice.inventory.phone')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" dir="ltr" />
          <input v-model="supplierForm.email" type="email" :placeholder="t('backoffice.inventory.email')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" dir="ltr" />
          <input v-model="supplierForm.tax_number" type="text" :placeholder="t('backoffice.inventory.taxNumber')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="supplierForm.category" type="text" :placeholder="t('backoffice.inventory.categoryExample')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="supplierForm.payment_terms_days" type="number" min="0" :placeholder="t('backoffice.inventory.paymentTermsDays')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="supplierForm.credit_limit" type="number" min="0" step="0.01" :placeholder="t('backoffice.inventory.creditLimitOptional')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="supplierForm.address" type="text" :placeholder="t('backoffice.inventory.address')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          <input v-model="supplierForm.notes" type="text" :placeholder="t('backoffice.inventory.notes')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
        </div>
        <AppButton class="mt-1" size="sm" :loading="savingSupplier" @click="saveSupplier">
          {{ editingSupplier ? t('backoffice.inventory.saveChanges') : t('backoffice.inventory.addSupplier') }}
        </AppButton>
      </div>
    </AppModal>
  </div>
</template>
