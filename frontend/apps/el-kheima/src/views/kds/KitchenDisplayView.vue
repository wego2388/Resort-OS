<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const token = localStorage.getItem('access_token') ?? ''
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const headers = computed(() => ({ Authorization: `Bearer ${token}` }))

interface TicketItem { name: string; name_ar: string; quantity: number; notes?: string }
interface Ticket {
  id: number; order_id: number; table_number?: string
  items: TicketItem[]; status: 'pending' | 'preparing' | 'ready'
  created_at: string; station?: string
}

const tickets = ref<Ticket[]>([])
const filterStatus = ref<string | null>(null)
const loading = ref(false)
const now = ref(new Date())
const isConnected = ref(true)
let refreshInterval: ReturnType<typeof setInterval>
let clockInterval: ReturnType<typeof setInterval>

const filteredTickets = computed(() =>
  filterStatus.value
    ? tickets.value.filter(t => t.status === filterStatus.value)
    : tickets.value
)

function minutesElapsed(createdAt: string) {
  return Math.floor((now.value.getTime() - new Date(createdAt).getTime()) / 60000)
}

function ticketAge(createdAt: string) {
  const mins = minutesElapsed(createdAt)
  if (mins >= 15) return 'urgent'
  if (mins >= 8)  return 'warning'
  return 'normal'
}

function ticketClasses(ticket: Ticket) {
  if (ticket.status === 'ready') return 'border-green-500 bg-green-900/30'
  const age = ticketAge(ticket.created_at)
  if (age === 'urgent')  return 'border-red-500 bg-red-900/30 animate-pulse'
  if (age === 'warning') return 'border-amber-500 bg-amber-900/30'
  return 'border-slate-600 bg-slate-800'
}

function statusLabel(status: string) {
  if (status === 'pending')   return { label: 'معلق',          color: 'bg-amber-500' }
  if (status === 'preparing') return { label: 'قيد التحضير',  color: 'bg-blue-500' }
  if (status === 'ready')     return { label: 'جاهز',          color: 'bg-green-500' }
  return { label: status, color: 'bg-gray-500' }
}

async function fetchTickets() {
  try {
    let ticketData: Ticket[] = []
    try {
      const res = await axios.get('/api/v1/restaurant/kitchen/tickets', {
        headers: headers.value,
        params: { branch_id: branchId, status: 'pending,preparing' }
      })
      ticketData = res.data.tickets ?? res.data.items ?? res.data
    } catch {
      const res = await axios.get('/api/v1/restaurant/orders', {
        headers: headers.value,
        params: { branch_id: branchId, status: 'pending,preparing', outlet_type: 'restaurant', limit: 50 }
      })
      const orders = res.data.orders ?? res.data.items ?? res.data
      ticketData = orders.map((o: any) => ({
        id: o.id,
        order_id: o.id,
        table_number: o.table_number ?? o.table_id?.toString(),
        items: o.items?.map((i: any) => ({
          name: i.name,
          name_ar: i.name_ar,
          quantity: i.quantity,
          notes: i.notes
        })) ?? [],
        status: o.status === 'pending' ? 'pending' : o.status === 'preparing' ? 'preparing' : 'ready',
        created_at: o.created_at,
      }))
    }
    tickets.value = ticketData
    isConnected.value = true
  } catch {
    isConnected.value = false
  }
}

async function markReady(ticketId: number) {
  try {
    await axios.patch(
      `/api/v1/restaurant/kitchen/tickets/${ticketId}`,
      { status: 'ready' },
      { headers: headers.value }
    )
    const t = tickets.value.find(t => t.id === ticketId)
    if (t) t.status = 'ready'
    setTimeout(() => { tickets.value = tickets.value.filter(t => t.id !== ticketId) }, 2000)
  } catch {
    try {
      await axios.patch(
        `/api/v1/restaurant/orders/${ticketId}/status`,
        { status: 'ready' },
        { headers: headers.value }
      )
      const t = tickets.value.find(t => t.id === ticketId)
      if (t) t.status = 'ready'
      setTimeout(() => { tickets.value = tickets.value.filter(t => t.id !== ticketId) }, 2000)
    } catch(e) { console.error(e) }
  }
}

const currentTime = computed(() =>
  now.value.toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
)
const pendingCount   = computed(() => tickets.value.filter(t => t.status === 'pending').length)
const preparingCount = computed(() => tickets.value.filter(t => t.status === 'preparing').length)

onMounted(() => {
  fetchTickets()
  refreshInterval = setInterval(fetchTickets, 15_000)
  clockInterval   = setInterval(() => { now.value = new Date() }, 1000)
})
onUnmounted(() => { clearInterval(refreshInterval); clearInterval(clockInterval) })
</script>

<template>
  <div class="min-h-screen bg-slate-900 text-white flex flex-col" dir="rtl">
    <!-- Header -->
    <header class="bg-slate-800 border-b border-slate-700 px-6 py-3 flex items-center justify-between flex-shrink-0">
      <div class="flex items-center gap-4">
        <div class="flex items-center gap-2">
          <div :class="['w-2.5 h-2.5 rounded-full', isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400']" />
          <span class="text-sm text-slate-300">{{ isConnected ? 'متصل' : 'منقطع' }}</span>
        </div>
        <h1 class="text-xl font-black tracking-wide">🍳 شاشة المطبخ — KDS</h1>
        <div class="flex gap-3 text-sm">
          <span class="px-2 py-0.5 bg-amber-600 rounded-full font-bold">معلق: {{ pendingCount }}</span>
          <span class="px-2 py-0.5 bg-blue-600 rounded-full font-bold">تحضير: {{ preparingCount }}</span>
        </div>
      </div>
      <div class="flex items-center gap-4">
        <span class="text-2xl font-mono font-bold text-amber-300">{{ currentTime }}</span>
        <button
          @click="fetchTickets"
          class="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm transition-colors"
        >🔄</button>
      </div>
    </header>

    <!-- Filter tabs -->
    <div class="bg-slate-800 border-b border-slate-700 px-6 py-2 flex gap-2">
      <button
        v-for="f in [
          { val: null,        label: `الكل (${tickets.length})` },
          { val: 'pending',   label: `معلق (${pendingCount})` },
          { val: 'preparing', label: `تحضير (${preparingCount})` },
          { val: 'ready',     label: 'جاهز' },
        ]"
        :key="String(f.val)"
        @click="filterStatus = f.val"
        :class="[
          'px-3 py-1 rounded-lg text-sm font-medium transition-colors',
          filterStatus === f.val
            ? 'bg-blue-600 text-white'
            : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
        ]"
      >{{ f.label }}</button>
    </div>

    <!-- Tickets -->
    <div class="flex-1 overflow-y-auto p-4">
      <div v-if="filteredTickets.length === 0" class="flex items-center justify-center h-64 text-slate-500">
        <div class="text-center">
          <div class="text-5xl mb-3">✅</div>
          <p class="text-lg">لا توجد طلبات معلقة</p>
        </div>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        <div
          v-for="ticket in filteredTickets"
          :key="ticket.id"
          :class="['rounded-2xl border-2 p-4 flex flex-col transition-all', ticketClasses(ticket)]"
        >
          <!-- Ticket header -->
          <div class="flex items-center justify-between mb-3">
            <div>
              <div class="text-2xl font-black">#{{ ticket.order_id }}</div>
              <div v-if="ticket.table_number" class="text-xs text-slate-400">طاولة {{ ticket.table_number }}</div>
            </div>
            <div class="text-left">
              <div :class="['text-xs px-2 py-0.5 rounded-full font-bold text-white mb-1', statusLabel(ticket.status).color]">
                {{ statusLabel(ticket.status).label }}
              </div>
              <div :class="[
                'text-lg font-black text-center',
                ticketAge(ticket.created_at) === 'urgent'  ? 'text-red-400'   :
                ticketAge(ticket.created_at) === 'warning' ? 'text-amber-400' :
                'text-green-400'
              ]">
                {{ minutesElapsed(ticket.created_at) }}د
              </div>
            </div>
          </div>

          <!-- Items -->
          <ul class="flex-1 space-y-1.5 mb-3">
            <li v-for="item in ticket.items" :key="item.name" class="text-sm">
              <div class="flex items-start gap-2">
                <span class="bg-white/20 text-white rounded px-1.5 py-0.5 text-xs font-bold flex-shrink-0">
                  {{ item.quantity }}
                </span>
                <span class="leading-tight">{{ item.name_ar || item.name }}</span>
              </div>
              <p v-if="item.notes" class="text-xs text-amber-300 mr-6 mt-0.5">⚠️ {{ item.notes }}</p>
            </li>
          </ul>

          <!-- Timer + Action -->
          <div class="space-y-2">
            <div class="text-xs text-slate-400 text-center">
              {{ new Date(ticket.created_at).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' }) }}
            </div>
            <button
              v-if="ticket.status !== 'ready'"
              @click="markReady(ticket.id)"
              class="w-full py-2 bg-green-600 hover:bg-green-500 rounded-xl text-sm font-bold transition-colors active:scale-95"
            >
              ✓ جاهز للتسليم
            </button>
            <div v-else class="w-full py-2 bg-green-700 rounded-xl text-sm font-bold text-center text-green-200">
              ✓ تم التسليم
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
