<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

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

const UNIT_OPTIONS = ['piece', 'kg', 'liter', 'box', 'pack', 'dozen']

const products = ref<Product[]>([])
const warehouses = ref<Warehouse[]>([])
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
  if (!productForm.value.name.trim()) { toast.error('اسم المنتج مطلوب'); return }
  if (!editingProduct.value && !productForm.value.sku.trim()) { toast.error('SKU مطلوب'); return }
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
      toast.success('تم تعديل المنتج')
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
      toast.success('تم إضافة المنتج')
    }
    productModal.value = false
    await fetchProducts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر حفظ المنتج')
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
  supplier_name: '', supplier_phone: '', warehouse_id: '' as number | '',
  lines: [] as { product_id: number | ''; quantity: string; unit_cost: string }[],
})
function openReceivePO() {
  poForm.value = { supplier_name: '', supplier_phone: '', warehouse_id: '', lines: [{ product_id: '', quantity: '', unit_cost: '' }] }
  poModal.value = true
}
function addPOLine() { poForm.value.lines.push({ product_id: '', quantity: '', unit_cost: '' }) }
function removePOLine(i: number) { poForm.value.lines.splice(i, 1) }

async function saveReceivePO() {
  if (!poForm.value.supplier_name.trim()) { toast.error('اسم المورد مطلوب'); return }
  if (!poForm.value.warehouse_id) { toast.error('اختر المخزن'); return }
  const validLines = poForm.value.lines.filter(l => l.product_id && Number(l.quantity) > 0)
  if (validLines.length === 0) { toast.error('أضف صنف واحد على الأقل بكمية أكبر من صفر'); return }

  savingPO.value = true
  try {
    const { data: po } = await api.post('/api/v1/inventory/purchase-orders', {
      branch_id: branchId,
      supplier_name: poForm.value.supplier_name,
      supplier_phone: poForm.value.supplier_phone || undefined,
      ordered_at: new Date().toISOString().slice(0, 10),
      items: validLines.map(l => ({ product_id: l.product_id, ordered_qty: l.quantity, unit_cost: l.unit_cost || '0' })),
    })
    await api.post(`/api/v1/inventory/purchase-orders/${po.id}/receive`, {
      warehouse_id: poForm.value.warehouse_id,
      received_at: new Date().toISOString().slice(0, 10),
      items: po.items.map((it: { id: number; ordered_qty: number }) => ({ item_id: it.id, received_qty: it.ordered_qty })),
    })
    toast.success('تم تسجيل استلام البضاعة وتحديث المخزون')
    poModal.value = false
    await fetchProducts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل الاستلام')
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
  if (!adjustForm.value.product_id) { toast.error('اختر المنتج'); return }
  if (!adjustForm.value.warehouse_id) { toast.error('اختر المخزن'); return }
  const qty = Number(adjustForm.value.quantity)
  if (!qty) { toast.error('أدخل كمية التعديل (موجب = إضافة، سالب = خصم)'); return }
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
    toast.success('تم تسجيل تعديل المخزون')
    adjustModal.value = false
    await fetchProducts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل التعديل')
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

async function fetchProducts() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/inventory/products', { params: { branch_id: branchId, limit: 200 } })
    products.value = res.data.products ?? res.data.items ?? res.data
  } catch { toast.error('تعذّر تحميل الأصناف — حاول تاني') }
  finally { loading.value = false }
}

onMounted(() => { fetchCategories(); fetchWarehouses(); fetchProducts() })
</script>

<template>
  <div dir="rtl">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-black text-gray-900">المخزون</h2>
      <div class="flex items-center gap-2">
        <button @click="showLowStock = !showLowStock"
          :class="['px-3 py-1.5 rounded-xl text-sm font-medium border-2 transition-colors', showLowStock ? 'border-red-500 bg-red-50 text-red-700' : 'border-stone-200 text-gray-600 hover:border-red-300']">
          ⚠️ منخفض ({{ lowStockCount() }})
        </button>
        <AppButton variant="secondary" size="sm" @click="openAdjustStock">⚖️ تعديل يدوي</AppButton>
        <AppButton variant="secondary" size="sm" @click="openReceivePO">📦 تسجيل استلام بضاعة</AppButton>
        <AppButton size="sm" @click="openCreateProduct">+ منتج جديد</AppButton>
        <AppButton variant="secondary" size="sm" @click="fetchProducts">🔄</AppButton>
      </div>
    </div>

    <!-- Search -->
    <div class="mb-4">
      <input v-model="search" type="text" placeholder="ابحث عن منتج أو SKU..."
        class="w-full max-w-sm border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"/>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>

    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-stone-50">
            <tr>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">المنتج</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">SKU</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الفئة</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">المخزون</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">حد الطلب</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">تكلفة الوحدة</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الحالة</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in filtered()" :key="p.id" class="border-t border-stone-100 hover:bg-stone-50">
              <td class="px-4 py-3 font-medium text-gray-900 text-sm">{{ p.name }}</td>
              <td class="px-4 py-3 font-mono text-xs text-gray-500">{{ p.sku }}</td>
              <td class="px-4 py-3 text-sm text-gray-600">{{ categoryLabel(p) }}</td>
              <td class="px-4 py-3">
                <span :class="['text-sm font-bold', p.current_stock <= p.reorder_point ? 'text-red-600' : 'text-gray-900']">
                  {{ p.current_stock }} {{ p.unit }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-500">{{ p.reorder_point }} {{ p.unit }}</td>
              <td class="px-4 py-3 text-sm text-gray-700">{{ (p.cost_price ?? 0).toLocaleString('ar-EG') }} ج</td>
              <td class="px-4 py-3">
                <AppBadge size="sm" :variant="p.current_stock <= 0 ? 'danger' : p.current_stock <= p.reorder_point ? 'warning' : 'success'">
                  {{ p.current_stock <= 0 ? 'نفد' : p.current_stock <= p.reorder_point ? 'منخفض' : 'متاح' }}
                </AppBadge>
              </td>
              <td class="px-4 py-3 text-left">
                <button @click="openEditProduct(p)" class="text-xs font-semibold text-primary-700 hover:underline">تعديل</button>
              </td>
            </tr>
            <tr v-if="filtered().length === 0">
              <td colspan="8" class="px-4 py-8">
                <EmptyState icon="📦" title="لا توجد أصناف" subtitle="جرّب تغيير كلمة البحث أو إلغاء فلتر المخزون المنخفض" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>

    <!-- #6: إضافة/تعديل منتج -->
    <AppModal :open="productModal" :title="editingProduct ? 'تعديل منتج' : 'منتج جديد'" @close="productModal = false">
      <div class="space-y-3">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input v-model="productForm.name" type="text" placeholder="الاسم (إنجليزي) *"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.name_ar" type="text" placeholder="الاسم (عربي)"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.sku" type="text" placeholder="SKU *" :disabled="!!editingProduct"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm disabled:bg-gray-50 disabled:text-gray-400" />
          <select v-model="productForm.unit" :disabled="!!editingProduct" class="border border-stone-200 rounded-xl px-3 py-2 text-sm disabled:bg-gray-50">
            <option v-for="u in UNIT_OPTIONS" :key="u" :value="u">{{ u }}</option>
          </select>
          <select v-model="productForm.category_id" class="border border-stone-200 rounded-xl px-3 py-2 text-sm">
            <option value="">بدون فئة</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name_ar || c.name }}</option>
          </select>
          <select v-model="productForm.warehouse_id" class="border border-stone-200 rounded-xl px-3 py-2 text-sm">
            <option value="">بدون مخزن محدد</option>
            <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.name_ar || w.name }}</option>
          </select>
          <input v-model="productForm.cost_price" type="number" min="0" step="0.01" placeholder="تكلفة الوحدة"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.reorder_point" type="number" min="0" step="0.01" placeholder="حد إعادة الطلب"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.min_stock" type="number" min="0" step="0.01" placeholder="الحد الأدنى"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.max_stock" type="number" min="0" step="0.01" placeholder="الحد الأقصى (اختياري)"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="productForm.notes" type="text" placeholder="ملاحظات"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm sm:col-span-2" />
        </div>
        <AppButton class="mt-1" size="sm" :loading="savingProduct" @click="saveProduct">
          {{ editingProduct ? 'حفظ التعديلات' : 'إضافة المنتج' }}
        </AppButton>
      </div>
    </AppModal>

    <!-- #6: تسجيل استلام بضاعة -->
    <AppModal :open="poModal" title="تسجيل استلام بضاعة" size="lg" @close="poModal = false">
      <div class="space-y-3">
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <input v-model="poForm.supplier_name" type="text" placeholder="اسم المورد *"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          <input v-model="poForm.supplier_phone" type="text" placeholder="تليفون المورد"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
        </div>
        <select v-model="poForm.warehouse_id" class="w-full border border-stone-200 rounded-xl px-3 py-2 text-sm">
          <option value="">اختر المخزن المستلم إليه *</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.name_ar || w.name }}</option>
        </select>

        <div class="border-t border-stone-100 pt-3 space-y-2">
          <div class="text-xs font-semibold text-gray-500 uppercase">الأصناف المستلمة</div>
          <div v-for="(line, i) in poForm.lines" :key="i" class="grid grid-cols-12 gap-2 items-center">
            <select v-model="line.product_id" class="col-span-6 border border-stone-200 rounded-xl px-3 py-2 text-sm">
              <option value="">اختر منتج</option>
              <option v-for="p in products" :key="p.id" :value="p.id">{{ p.name_ar || p.name }} ({{ p.sku }})</option>
            </select>
            <input v-model="line.quantity" type="number" min="0" step="0.01" placeholder="الكمية"
              class="col-span-3 border border-stone-200 rounded-xl px-3 py-2 text-sm" />
            <input v-model="line.unit_cost" type="number" min="0" step="0.01" placeholder="سعر الوحدة"
              class="col-span-2 border border-stone-200 rounded-xl px-3 py-2 text-sm" />
            <button @click="removePOLine(i)" class="col-span-1 text-red-400 hover:text-red-600 text-lg">×</button>
          </div>
          <button @click="addPOLine" class="text-xs font-semibold text-primary-700 hover:underline">+ إضافة صنف</button>
        </div>

        <AppButton class="mt-1" size="sm" :loading="savingPO" @click="saveReceivePO">تسجيل الاستلام</AppButton>
      </div>
    </AppModal>

    <!-- #6: تعديل مخزون يدوي -->
    <AppModal :open="adjustModal" title="تعديل مخزون يدوي" @close="adjustModal = false">
      <div class="space-y-3">
        <select v-model="adjustForm.product_id" class="w-full border border-stone-200 rounded-xl px-3 py-2 text-sm">
          <option value="">اختر المنتج *</option>
          <option v-for="p in products" :key="p.id" :value="p.id">{{ p.name_ar || p.name }} ({{ p.sku }}) — الحالي: {{ p.current_stock }} {{ p.unit }}</option>
        </select>
        <select v-model="adjustForm.warehouse_id" class="w-full border border-stone-200 rounded-xl px-3 py-2 text-sm">
          <option value="">اختر المخزن *</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.name_ar || w.name }}</option>
        </select>
        <input v-model="adjustForm.quantity" type="number" step="0.01" placeholder="كمية التعديل (موجب = إضافة، سالب = خصم) *"
          class="w-full border border-stone-200 rounded-xl px-3 py-2 text-sm" />
        <input v-model="adjustForm.notes" type="text" placeholder="سبب التعديل (جرد، تلف، غلط عدّ...)"
          class="w-full border border-stone-200 rounded-xl px-3 py-2 text-sm" />
        <AppButton class="mt-1" size="sm" :loading="savingAdjust" @click="saveAdjustStock">تسجيل التعديل</AppButton>
      </div>
    </AppModal>
  </div>
</template>
