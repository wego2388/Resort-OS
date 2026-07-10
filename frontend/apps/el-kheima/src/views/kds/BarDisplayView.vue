<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, useResortWebSocket, parseApiTimestamp } from '@resort-os/core'
import { useToast } from '@resort-os/ui'

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const toast = useToast()

type TicketStatus = 'pending' | 'in_progress' | 'done'
interface TicketItem { order_item_id: number; name: string; quantity: number; notes?: string | null }
interface BarTicket {
  id: number; order_id: number; module: string
  items_snapshot: TicketItem[]; status: TicketStatus
  created_at: string
}

const tickets = ref<BarTicket[]>([])
const filterStatus = ref<TicketStatus | null>(null)
const now = ref(new Date())
const isConnected = ref(true)
let refreshInterval: ReturnType<typeof setInterval>
let clockInterval: ReturnType<typeof setInterval>

// نفس مبدأ KitchenDisplayView: WebSocket لحظي بإعادة اتصال تلقائية + polling
// كل 15 ثانية كـ fallback احتياطي
const wsProtocol = (
  window.location.protocol === 'https:' ||
  document.querySelector('meta[name="x-forwarded-proto"]')?.getAttribute('content') === 'https'
) ? 'wss:' : 'ws:'
const wsBase = import.meta.env.VITE_WS_BASE ?? `${wsProtocol}//${window.location.host}`
const { status: wsStatus, onMessage } = useResortWebSocket(
  `${wsBase}/api/v1/restaurant/ws/kds/${branchId}`,
)
onMessage((data: any) => {
  if (data?.type === 'tickets_updated') fetchTickets()
})

const filteredTickets = computed(() =>
  filterStatus.value
    ? tickets.value.filter(t => t.status === filterStatus.value)
    : tickets.value
)

function minutesElapsed(createdAt: string) {
  return Math.floor((now.value.getTime() - parseApiTimestamp(createdAt).getTime()) / 60000)
}

function ticketAge(createdAt: string) {
  const mins = minutesElapsed(createdAt)
  if (mins >= 10) return 'urgent'
  if (mins >= 5)  return 'warning'
  return 'normal'
}

function ticketClasses(ticket: BarTicket) {
  if (ticket.status === 'done') return 'border-cyan-500 bg-cyan-900/30'
  const age = ticketAge(ticket.created_at)
  if (age === 'urgent')  return 'border-red-500 bg-red-900/30 animate-pulse'
  if (age === 'warning') return 'border-amber-500 bg-amber-900/30'
  return 'border-slate-600 bg-slate-800'
}

function statusBadge(status: TicketStatus) {
  if (status === 'pending')     return { label: 'معلق',         color: 'bg-amber-500' }
  if (status === 'in_progress') return { label: 'جاري التحضير', color: 'bg-cyan-600' }
  return { label: 'جاهز', color: 'bg-green-500' }
}

async function fetchTickets() {
  try {
    // البار بيستقبل من مصدرين: طلبات الكافيه كلها (مفيش تقسيم محطات فيها) + أصناف
    // البار اللي اتطلبت من قائمة المطعم نفسها (مشروبات على طاولة مطعم مثلاً).
    const [cafeRes, restaurantBarRes] = await Promise.all([
      api.get('/api/v1/restaurant/kitchen/tickets', {
        params: { branch_id: branchId, module: 'cafe' },
      }),
      api.get('/api/v1/restaurant/kitchen/tickets', {
        params: { branch_id: branchId, module: 'restaurant', stations: 'bar' },
      }),
    ])
    tickets.value = [...cafeRes.data, ...restaurantBarRes.data].sort(
      (a: BarTicket, b: BarTicket) => a.created_at.localeCompare(b.created_at)
    )
    isConnected.value = true
  } catch {
    isConnected.value = false
  }
}

async function advanceStatus(ticket: BarTicket) {
  const next: TicketStatus = ticket.status === 'pending' ? 'in_progress' : 'done'
  try {
    await api.patch(
      `/api/v1/restaurant/kitchen/tickets/${ticket.id}/status`,
      { status: next })
    ticket.status = next
    if (next === 'done') {
      setTimeout(() => { tickets.value = tickets.value.filter(t => t.id !== ticket.id) }, 1800)
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحديث حالة التذكرة — حاول تاني')
  }
}

// ── تحصيل من شاشة البار (للكافيه بس) ──────────────────────────────────
// الباريستا في الكافيه الصغيرة بيكون هو الكاشير — يقدر يحصّل مباشرة بعد ما
// الطلب "جاهز" بدل ما يكمّل على شاشة CafePOS تانية. مش متاحة لطلبات المطعم
// (module='restaurant') لأن المطبخ والكاشير دايمًا منفصلين هناك.
const collectingOrderId = ref<number | null>(null)
const collectMethod = ref<'cash' | 'card' | 'wallet'>('cash')
const collectError  = ref('')

function openCollect(ticket: BarTicket) {
  if (ticket.module !== 'cafe') return
  collectingOrderId.value = ticket.order_id
  collectMethod.value = 'cash'
  collectError.value  = ''
}

function cancelCollect() {
  collectingOrderId.value = null
  collectError.value = ''
}

async function confirmCollect() {
  if (!collectingOrderId.value) return
  try {
    await api.patch(
      `/api/v1/cafe/orders/${collectingOrderId.value}/status`,
      { status: 'paid', payment_method: collectMethod.value },
    )
    toast.success('تم التحصيل ✓')
    cancelCollect()
    await fetchTickets()
  } catch (e: any) {
    collectError.value = e?.response?.data?.detail ?? 'تعذّر إتمام التحصيل'
  }
}

const currentTime = computed(() =>
  now.value.toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
)
const pendingCount    = computed(() => tickets.value.filter(t => t.status === 'pending').length)
const inProgressCount = computed(() => tickets.value.filter(t => t.status === 'in_progress').length)

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
    <header class="bg-slate-800 border-b border-cyan-800 px-6 py-3 flex items-center justify-between flex-shrink-0">
      <div class="flex items-center gap-4">
        <div class="flex items-center gap-2">
          <div :class="['w-2.5 h-2.5 rounded-full', isConnected ? 'bg-cyan-400 animate-pulse' : 'bg-red-400']" />
          <span class="text-sm text-slate-300">{{ isConnected ? 'متصل' : 'منقطع' }}</span>
        </div>
        <div class="flex items-center gap-1.5" :title="wsStatus === 'connected' ? 'تحديث لحظي شغال' : 'بيحاول يعيد الاتصال...'">
          <div :class="['w-2 h-2 rounded-full', wsStatus === 'connected' ? 'bg-cyan-300' : 'bg-slate-500 animate-pulse']" />
          <span class="text-xs text-slate-400">{{ wsStatus === 'connected' ? 'لحظي' : '...جاري إعادة الاتصال' }}</span>
        </div>
        <h1 class="text-xl font-black tracking-wide">🥤 شاشة البار — Bar KDS</h1>
        <div class="flex gap-3 text-sm">
          <span class="px-2 py-0.5 bg-amber-600 rounded-full font-bold">معلق: {{ pendingCount }}</span>
          <span class="px-2 py-0.5 bg-cyan-700 rounded-full font-bold">تحضير: {{ inProgressCount }}</span>
        </div>
      </div>
      <div class="flex items-center gap-4">
        <span class="text-2xl font-mono font-bold text-cyan-300">{{ currentTime }}</span>
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
          { val: null,          label: `الكل (${tickets.length})` },
          { val: 'pending',     label: `معلق (${pendingCount})` },
          { val: 'in_progress', label: `تحضير (${inProgressCount})` },
        ]"
        :key="String(f.val)"
        @click="filterStatus = f.val as TicketStatus | null"
        :class="[
          'px-3 py-1 rounded-lg text-sm font-medium transition-colors',
          filterStatus === f.val
            ? 'bg-cyan-700 text-white'
            : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
        ]"
      >{{ f.label }}</button>
    </div>

    <!-- Tickets grid -->
    <div class="flex-1 overflow-y-auto p-4">
      <div v-if="filteredTickets.length === 0" class="flex items-center justify-center h-64 text-slate-500">
        <div class="text-center">
          <div class="text-5xl mb-3">🥂</div>
          <p class="text-lg">لا توجد طلبات بار معلقة</p>
        </div>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        <div
          v-for="ticket in filteredTickets"
          :key="`${ticket.module}-${ticket.id}`"
          :class="['rounded-2xl border-2 p-4 flex flex-col transition-all', ticketClasses(ticket)]"
        >
          <!-- Ticket header -->
          <div class="flex items-center justify-between mb-3">
            <div>
              <div class="text-2xl font-black">#{{ ticket.order_id }}</div>
              <div class="text-xs text-slate-400">{{ ticket.module === 'cafe' ? 'كافيه' : 'مطعم' }}</div>
            </div>
            <div class="text-center">
              <div :class="['text-xs px-2 py-0.5 rounded-full font-bold text-white mb-1', statusBadge(ticket.status).color]">
                {{ statusBadge(ticket.status).label }}
              </div>
              <div :class="[
                'text-lg font-black',
                ticketAge(ticket.created_at) === 'urgent'  ? 'text-red-400'   :
                ticketAge(ticket.created_at) === 'warning' ? 'text-amber-400' :
                'text-cyan-400'
              ]">
                {{ minutesElapsed(ticket.created_at) }}د
              </div>
            </div>
          </div>

          <!-- Drinks list -->
          <ul class="flex-1 space-y-2 mb-3">
            <li
              v-for="item in ticket.items_snapshot"
              :key="item.order_item_id"
              class="flex items-start gap-2 text-sm"
            >
              <span class="bg-cyan-700/60 text-white rounded-lg px-2 py-0.5 text-xs font-black flex-shrink-0 min-w-[1.5rem] text-center">
                {{ item.quantity }}
              </span>
              <div class="flex-1">
                <span class="font-medium leading-tight">{{ item.name }}</span>
                <p v-if="item.notes" class="text-xs text-amber-300 mt-0.5">⚠️ {{ item.notes }}</p>
              </div>
            </li>
          </ul>

          <!-- Timestamp + Action -->
          <div class="space-y-2">
            <div class="text-xs text-slate-400 text-center">
              {{ parseApiTimestamp(ticket.created_at).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' }) }}
            </div>
            <button
              v-if="ticket.status === 'pending'"
              @click="advanceStatus(ticket)"
              class="w-full py-3 bg-cyan-600 hover:bg-cyan-500 rounded-xl text-sm font-black transition-colors active:scale-95 tracking-wide"
            >
              ▶ بدء التحضير
            </button>
            <button
              v-else-if="ticket.status === 'in_progress'"
              @click="advanceStatus(ticket)"
              class="w-full py-3 bg-cyan-600 hover:bg-cyan-500 rounded-xl text-sm font-black transition-colors active:scale-95 tracking-wide"
            >
              ✓ جاهز
            </button>
            <template v-else>
              <div class="w-full py-3 bg-cyan-800 rounded-xl text-sm font-bold text-center text-cyan-200">
                ✓ تم التسليم
              </div>
              <!-- زر تحصيل — للكافيه بس (الباريستا = الكاشير في الكافيه الصغيرة) -->
              <button
                v-if="ticket.module === 'cafe'"
                @click="openCollect(ticket)"
                class="w-full py-2.5 bg-green-600 hover:bg-green-500 rounded-xl text-sm font-black transition-colors active:scale-95"
              >
                💳 تحصيل
              </button>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Collect Modal ── -->
  <Teleport to="body">
    <div v-if="collectingOrderId !== null" class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" dir="rtl">
      <div class="bg-slate-800 rounded-2xl border border-slate-600 p-6 w-full max-w-xs space-y-4">
        <h3 class="text-lg font-black text-white text-center">💳 تحصيل الطلب</h3>

        <!-- طريقة الدفع -->
        <div class="grid grid-cols-3 gap-2">
          <button
            v-for="m in [{ val: 'cash', label: 'كاش' }, { val: 'card', label: 'كارت' }, { val: 'wallet', label: 'محفظة' }]"
            :key="m.val"
            @click="collectMethod = (m.val as 'cash' | 'card' | 'wallet')"
            :class="[
              'py-2 rounded-xl text-sm font-bold border-2 transition-all',
              collectMethod === m.val
                ? 'border-cyan-400 bg-cyan-900 text-cyan-200'
                : 'border-slate-600 text-slate-300',
            ]"
          >{{ m.label }}</button>
        </div>

        <p v-if="collectError" class="text-xs text-red-400 text-center">{{ collectError }}</p>

        <div class="flex gap-2">
          <button
            @click="cancelCollect"
            class="flex-1 py-2.5 rounded-xl border border-slate-600 text-slate-300 text-sm font-bold"
          >إلغاء</button>
          <button
            @click="confirmCollect"
            class="flex-1 py-2.5 rounded-xl bg-green-600 hover:bg-green-500 text-white text-sm font-black"
          >تأكيد التحصيل</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
