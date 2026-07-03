<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@resort-os/core'
import { AppModal, AppBadge, EmptyState, useToast } from '@resort-os/ui'
import OrderDetailModal from '../../components/OrderDetailModal.vue'

const toast = useToast()

interface Table { id: number; table_number: string; status: string; capacity: number; section: string | null }
interface HeldOrder {
  id: number; order_number: string; table_id: number | null
  guests_count: number; total: number | string; order_type: string
}

const router = useRouter()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

const tables = ref<Table[]>([])
const loading = ref(false)

// ── Held orders (الطلبات المعلّقة) ─────────────────────────────────────
const heldOrders    = ref<HeldOrder[]>([])
const heldListOpen  = ref(false)
const selectedOrderId = ref<number | null>(null)

function tableLabel(order: HeldOrder): string {
  if (!order.table_id) return 'Takeaway'
  const t = tables.value.find(t => t.id === order.table_id)
  return t ? `طاولة ${t.table_number}` : `طاولة #${order.table_id}`
}

async function loadHeldOrders() {
  try {
    const { data } = await api.get('/api/v1/restaurant/orders/held', {
      params: { branch_id: branchId },
    })
    heldOrders.value = data.items ?? data
  } catch (e) {
    console.error('Failed to load held orders', e)
    toast.error('تعذّر تحميل الطلبات المعلّقة')
  }
}

function openHeldOrder(orderId: number) {
  selectedOrderId.value = orderId
}

function onOrderDetailClosed() {
  selectedOrderId.value = null
  loadHeldOrders()
  loadTables()
}

const sections = computed(() => {
  const map = new Map<string, Table[]>()
  for (const t of tables.value) {
    const key = t.section || 'عام'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(t)
  }
  return Array.from(map.entries())
})

function statusColor(status: string): string {
  if (status === 'available')      return 'bg-green-100 border-green-400 text-green-800 active:bg-green-200'
  if (status === 'occupied')       return 'bg-red-100 border-red-400 text-red-800 active:bg-red-200'
  if (status === 'reserved')       return 'bg-amber-100 border-amber-400 text-amber-800 active:bg-amber-200'
  return 'bg-gray-100 border-gray-300 text-gray-400 cursor-not-allowed'
}

function statusLabel(status: string): string {
  if (status === 'available') return 'فارغة'
  if (status === 'occupied')  return 'مشغولة'
  if (status === 'reserved')  return 'محجوزة'
  return 'خارج الخدمة'
}

function openTable(table: Table) {
  if (table.status === 'out_of_service') return
  router.push(`/waiter/order/${table.id}`)
}

async function loadTables() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/restaurant/tables', {
      params: { branch_id: branchId },
    })
    tables.value = data.tables ?? data.items ?? data
  } catch (e) {
    console.error('Failed to load tables', e)
    toast.error('تعذّر تحميل قائمة الطاولات')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadTables()
  loadHeldOrders()
})
</script>

<template>
  <div class="page-container" dir="rtl">
    <div class="flex items-center justify-between mb-5 gap-2 flex-wrap">
      <h1 class="section-title mb-0">الطاولات</h1>
      <div class="flex items-center gap-2">
        <button
          @click="heldListOpen = true"
          class="relative px-4 py-3 bg-white border-2 border-amber-400 text-amber-700 rounded-xl font-bold text-sm hover:bg-amber-50 active:scale-95 transition-all shadow-sm"
        >
          ⏸️ الطلبات المعلّقة
          <AppBadge v-if="heldOrders.length" variant="warning" size="sm" class="mr-1.5">{{ heldOrders.length }}</AppBadge>
        </button>
        <button
          @click="router.push('/waiter/order')"
          class="px-4 py-3 bg-blue-700 text-white rounded-xl font-bold text-sm hover:bg-blue-800 active:scale-95 transition-all shadow-sm"
        >📦 Takeaway (بدون طاولة)</button>
      </div>
    </div>

    <div v-if="loading" class="flex items-center justify-center h-40">
      <div class="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
    </div>

    <EmptyState v-else-if="tables.length === 0" icon="🪑" title="لا توجد طاولات مسجّلة لهذا الفرع" />

    <div v-else class="space-y-6">
      <div v-for="[sectionName, sectionTables] in sections" :key="sectionName">
        <h2 class="text-sm font-bold text-gray-500 uppercase tracking-wide mb-2">{{ sectionName }}</h2>
        <div class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3">
          <button
            v-for="table in sectionTables"
            :key="table.id"
            @click="openTable(table)"
            :disabled="table.status === 'out_of_service'"
            :class="[
              'aspect-square rounded-2xl border-2 flex flex-col items-center justify-center gap-1 font-bold transition-all active:scale-95 shadow-sm',
              statusColor(table.status),
            ]"
          >
            <span class="text-2xl leading-none">{{ table.table_number }}</span>
            <span class="text-[11px] font-medium">{{ statusLabel(table.status) }}</span>
            <span class="text-[10px] opacity-70">👥 {{ table.capacity }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- ── Held orders list ── -->
    <AppModal :open="heldListOpen" title="الطلبات المعلّقة" size="sm" @close="heldListOpen = false">
      <EmptyState v-if="heldOrders.length === 0" icon="⏸️" title="مفيش طلبات معلّقة دلوقتي" />
      <div v-else class="space-y-2">
        <button
          v-for="order in heldOrders"
          :key="order.id"
          @click="heldListOpen = false; openHeldOrder(order.id)"
          class="w-full flex items-center justify-between gap-2 p-3 rounded-xl border-2 border-amber-200 bg-amber-50 hover:border-amber-400 transition-all text-right"
        >
          <div>
            <div class="font-bold text-gray-900 text-sm">{{ order.order_number }}</div>
            <div class="text-xs text-gray-500">{{ tableLabel(order) }} — {{ order.guests_count }} غطاء</div>
          </div>
          <div class="font-bold text-amber-700">{{ order.total }} ج</div>
        </button>
      </div>
    </AppModal>

    <OrderDetailModal
      :order-id="selectedOrderId"
      @close="onOrderDetailClosed"
      @changed="loadHeldOrders"
    />
  </div>
</template>
