<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

// أسماء الحقول لازم تطابق ProductRead في الباك إند بالظبط:
// cost_price / reorder_point / category_id — قبل كده كانت الشاشة بتقرأ
// unit_cost / reorder_level / category (أسماء مش موجودة أصلاً)، يعني كشف
// المخزون المنخفض كان بيقارن بـ undefined فمكانش بيشتغل خالص، وعمود الفئة
// والتكلفة كانوا فاضيين دايمًا.
interface Product {
  id: number; name: string; sku: string; unit: string
  current_stock: number; reorder_point: number; category_id: number | null; cost_price: number | null
}

const products = ref<Product[]>([])
const categoryNames = ref<Record<number, string>>({})
const loading = ref(false)
const search = ref('')
const showLowStock = ref(false)

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
    const list: { id: number; name: string; name_ar: string | null }[] = res.data ?? []
    categoryNames.value = Object.fromEntries(list.map(c => [c.id, c.name_ar || c.name]))
  } catch {
    // غير حرج: أسماء الفئات مجرد عرض، بترجع لـ — لو فشلت
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

onMounted(() => { fetchCategories(); fetchProducts() })
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
            </tr>
            <tr v-if="filtered().length === 0">
              <td colspan="7" class="px-4 py-8">
                <EmptyState icon="📦" title="لا توجد أصناف" subtitle="جرّب تغيير كلمة البحث أو إلغاء فلتر المخزون المنخفض" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>
  </div>
</template>
