<script setup lang="ts">
/**
 * SearchOverlay — بحث عام واحد يدور في كل حاجة (أصناف، منتجات، موردين،
 * حسابات مصروف، موظفين) من غير ما تعرف هي في أنهي شاشة. بيتفتح من زرار
 * البحث في الهيدر (AppShell.vue). تدوس على نتيجة → بتفتح تفاصيلها مباشرة.
 */
import { ref, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useOwnerSearch, useDetailSheet } from '../composables/useOwnerData'
import { formatApiDateTime } from '../composables/useFormat'
import { fetchDiningItemDetail, fetchSupplierDetail, fetchExpenseDetail, fetchProductDetail } from '../api/owner'
import type {
  SearchResultItem,
  DiningItemDetailResponse, SupplierDetailResponse,
  ExpenseDetailResponse, ProductDetailResponse,
} from '../api/types'
import { formatMoney, formatMoneyFull } from '../composables/useFormat'
import DetailSheet from './DetailSheet.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const router = useRouter()
const { query, results, loading, onInput, clear } = useOwnerSearch()
const inputRef = ref<HTMLInputElement | null>(null)

watch(() => props.open, async (isOpen) => {
  if (isOpen) {
    await nextTick()
    inputRef.value?.focus()
  } else {
    clear()
  }
})

const typeIcon: Record<string, string> = {
  dining_item: '🍽',
  product: '📦',
  supplier: '🚚',
  expense_account: '💰',
  employee: '👤',
}
const typeLabel: Record<string, string> = {
  dining_item: 'صنف',
  product: 'منتج مخزون',
  supplier: 'مورد',
  expense_account: 'حساب مصروف',
  employee: 'موظف',
}

const itemDetail     = useDetailSheet<DiningItemDetailResponse>()
const supplierDetail = useDetailSheet<SupplierDetailResponse>()
const expenseDetail  = useDetailSheet<ExpenseDetailResponse>()
const productDetail  = useDetailSheet<ProductDetailResponse>()

function handleResultClick(r: SearchResultItem) {
  if (r.entity_type === 'dining_item') {
    itemDetail.open(() => fetchDiningItemDetail({ item_id: r.entity_id }))
  } else if (r.entity_type === 'supplier') {
    supplierDetail.open(() => fetchSupplierDetail({ supplier_id: r.entity_id }))
  } else if (r.entity_type === 'expense_account' && r.value_label) {
    expenseDetail.open(() => fetchExpenseDetail({ account_code: r.value_label as string }))
  } else if (r.entity_type === 'product') {
    productDetail.open(() => fetchProductDetail({ product_id: r.entity_id }))
  } else if (r.entity_type === 'employee') {
    emit('close')
    router.push('/hr')
  }
}

function formatDateTime(iso: string) {
  return formatApiDateTime(iso)
}
function formatDate(d: string) {
  return new Date(d).toLocaleDateString('ar-EG', { month: 'short', day: 'numeric' })
}
const movementTypeLabel: Record<string, string> = {
  purchase_in: 'شراء وارد', consumption: 'استهلاك', adjustment: 'تعديل جرد',
  transfer_in: 'تحويل وارد', transfer_out: 'تحويل صادر', spoilage: 'تالف',
}
</script>

<template>
  <Teleport to="body">
    <Transition name="search-fade">
      <div v-if="open" class="fixed inset-0 z-[60] bg-owner-bg flex flex-col" style="padding-top: env(safe-area-inset-top);">
        <!-- Header + input -->
        <div class="flex items-center gap-2 px-4 py-3 border-b border-owner-border shrink-0">
          <button class="touch-target text-owner-muted active:text-owner-text shrink-0" aria-label="رجوع" @click="emit('close')">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </button>
          <input
            ref="inputRef"
            :value="query"
            type="search"
            placeholder="ابحث عن أي صنف، منتج، مورد، مصروف، موظف..."
            class="flex-1 bg-owner-card border border-owner-border rounded-xl px-4 py-2.5 text-sm text-owner-text outline-none focus:border-owner-green"
            dir="rtl"
            @input="onInput(($event.target as HTMLInputElement).value)"
          />
        </div>

        <!-- Results -->
        <div class="flex-1 overflow-y-auto overscroll-contain">
          <div v-if="query.trim().length < 2" class="text-center text-xs text-owner-muted py-16 px-6">
            اكتب حرفين على الأقل — هيدور في كل الأصناف والمنتجات والموردين وحسابات المصروف والموظفين مرة واحدة
          </div>

          <div v-else-if="loading" class="p-4 space-y-2">
            <div v-for="i in 4" :key="i" class="skeleton h-14 rounded-xl" />
          </div>

          <div v-else-if="results.length === 0" class="text-center text-xs text-owner-muted py-16">
            لا توجد نتائج لـ"{{ query }}"
          </div>

          <div v-else class="p-2">
            <button
              v-for="r in results"
              :key="`${r.entity_type}-${r.entity_id}`"
              class="w-full flex items-center gap-3 py-3 px-2 border-b border-owner-border/50 last:border-0 text-right active:bg-owner-card transition-colors rounded-lg"
              @click="handleResultClick(r)"
            >
              <span class="text-xl shrink-0" aria-hidden="true">{{ typeIcon[r.entity_type] ?? '•' }}</span>
              <div class="min-w-0 flex-1">
                <div class="text-sm font-semibold text-owner-text truncate">{{ r.title }}</div>
                <div class="text-xs text-owner-muted">{{ r.subtitle ?? typeLabel[r.entity_type] ?? r.entity_type }}</div>
              </div>
              <span class="text-owner-muted shrink-0" aria-hidden="true">‹</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- تفاصيل النتائج -->
    <DetailSheet
      :open="itemDetail.isOpen.value" :title="itemDetail.data.value?.item_name ?? 'تفاصيل الصنف'"
      :subtitle="itemDetail.data.value ? `آخر 30 يوم · ${formatMoney(itemDetail.data.value.total_revenue)}` : undefined"
      :loading="itemDetail.loading.value" :error="itemDetail.error.value"
      @close="itemDetail.close()" @retry="itemDetail.retry()"
    >
      <div v-if="itemDetail.data.value?.transactions.length === 0" class="text-xs text-owner-muted text-center py-8">لا توجد طلبات</div>
      <div v-else class="space-y-1">
        <div v-for="tx in itemDetail.data.value?.transactions ?? []" :key="tx.order_id" class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs">
          <div class="min-w-0">
            <div class="font-semibold text-owner-text">{{ tx.order_number }}</div>
            <div class="text-owner-muted mt-0.5">{{ tx.outlet_name }} · {{ formatDateTime(tx.ordered_at) }}</div>
          </div>
          <div class="font-mono font-semibold text-owner-text shrink-0">{{ formatMoneyFull(tx.line_total) }}</div>
        </div>
      </div>
    </DetailSheet>

    <DetailSheet
      :open="supplierDetail.isOpen.value" :title="supplierDetail.data.value?.supplier_name ?? 'تفاصيل المورد'"
      :subtitle="supplierDetail.data.value ? `${supplierDetail.data.value.orders.length} أمر شراء · ${formatMoney(supplierDetail.data.value.total_amount)}` : undefined"
      :loading="supplierDetail.loading.value" :error="supplierDetail.error.value"
      @close="supplierDetail.close()" @retry="supplierDetail.retry()"
    >
      <div v-if="supplierDetail.data.value?.orders.length === 0" class="text-xs text-owner-muted text-center py-8">لا توجد أوامر شراء</div>
      <div v-else class="space-y-1">
        <div v-for="po in supplierDetail.data.value?.orders ?? []" :key="po.po_id" class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs">
          <div>
            <div class="font-semibold text-owner-text">{{ po.po_number }}</div>
            <div class="text-owner-muted mt-0.5">{{ po.item_count }} صنف · {{ formatDate(po.ordered_at) }}</div>
          </div>
          <div class="font-mono font-semibold text-owner-text">{{ formatMoneyFull(po.total_amount) }}</div>
        </div>
      </div>
    </DetailSheet>

    <DetailSheet
      :open="expenseDetail.isOpen.value" :title="expenseDetail.data.value?.account_name ?? 'تفاصيل المصروف'"
      :subtitle="expenseDetail.data.value ? formatMoney(expenseDetail.data.value.total_amount) : undefined"
      :loading="expenseDetail.loading.value" :error="expenseDetail.error.value"
      @close="expenseDetail.close()" @retry="expenseDetail.retry()"
    >
      <div v-if="expenseDetail.data.value?.lines.length === 0" class="text-xs text-owner-muted text-center py-8">لا توجد قيود</div>
      <div v-else class="space-y-1">
        <div v-for="line in expenseDetail.data.value?.lines ?? []" :key="line.entry_id" class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs">
          <div class="min-w-0">
            <div class="font-semibold text-owner-text truncate">{{ line.description }}</div>
            <div class="text-owner-muted mt-0.5">{{ line.reference }} · {{ formatDate(line.entry_date) }}</div>
          </div>
          <div class="font-mono font-semibold text-owner-text shrink-0">{{ formatMoneyFull(line.amount) }}</div>
        </div>
      </div>
    </DetailSheet>

    <DetailSheet
      :open="productDetail.isOpen.value" :title="productDetail.data.value?.product_name ?? 'تفاصيل المنتج'"
      :subtitle="productDetail.data.value ? `الرصيد الحالي: ${productDetail.data.value.current_stock} ${productDetail.data.value.unit}` : undefined"
      :loading="productDetail.loading.value" :error="productDetail.error.value"
      @close="productDetail.close()" @retry="productDetail.retry()"
    >
      <div v-if="productDetail.data.value?.movements.length === 0" class="text-xs text-owner-muted text-center py-8">لا توجد حركات مخزون في آخر 30 يوم</div>
      <div v-else class="space-y-1">
        <div v-for="m in productDetail.data.value?.movements ?? []" :key="m.movement_id" class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs">
          <div>
            <div class="font-semibold text-owner-text">{{ movementTypeLabel[m.movement_type] ?? m.movement_type }}</div>
            <div class="text-owner-muted mt-0.5">{{ m.warehouse_name }} · {{ formatDateTime(m.moved_at) }}</div>
          </div>
          <div class="font-mono font-semibold" :class="parseFloat(m.quantity) < 0 ? 'text-owner-red' : 'text-owner-green'">
            {{ parseFloat(m.quantity) > 0 ? '+' : '' }}{{ m.quantity }}
          </div>
        </div>
      </div>
    </DetailSheet>
  </Teleport>
</template>

<style scoped>
.search-fade-enter-active, .search-fade-leave-active { transition: opacity 0.15s ease; }
.search-fade-enter-from, .search-fade-leave-to { opacity: 0; }
@media (prefers-reduced-motion: reduce) {
  .search-fade-enter-active, .search-fade-leave-active { transition: none; }
}
</style>
