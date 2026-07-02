<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

interface Table { id: number; table_number: string; status: string; capacity: number; section: string | null }

const router = useRouter()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const authHeaders = computed(() => ({ Authorization: `Bearer ${localStorage.getItem('access_token')}` }))

const tables = ref<Table[]>([])
const loading = ref(false)

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
    const { data } = await axios.get('/api/v1/restaurant/tables', {
      headers: authHeaders.value,
      params: { branch_id: branchId },
    })
    tables.value = data.tables ?? data.items ?? data
  } catch (e) {
    console.error('Failed to load tables', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadTables)
</script>

<template>
  <div class="page-container" dir="rtl">
    <div class="flex items-center justify-between mb-5">
      <h1 class="section-title mb-0">الطاولات</h1>
      <button
        @click="router.push('/waiter/order')"
        class="px-4 py-3 bg-blue-700 text-white rounded-xl font-bold text-sm hover:bg-blue-800 active:scale-95 transition-all shadow-sm"
      >📦 Takeaway (بدون طاولة)</button>
    </div>

    <div v-if="loading" class="flex items-center justify-center h-40">
      <div class="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
    </div>

    <div v-else-if="tables.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-400">
      <div class="text-4xl mb-2">🪑</div>
      <p class="text-sm">لا توجد طاولات مسجّلة لهذا الفرع</p>
    </div>

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
  </div>
</template>
