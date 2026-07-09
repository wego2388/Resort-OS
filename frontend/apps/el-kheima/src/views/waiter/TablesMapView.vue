<script setup lang="ts">
/**
 * TablesMapView — خريطة الطاولات الحية (Grid بإحداثيات حقيقية).
 *
 * الوايتر يشوف الطاولات في مكانها الحقيقي في القاعة — مش بس قائمة.
 * المدير يقدر يحرّك الطاولات بـ drag & drop وتتحفظ فوراً (PATCH /grid).
 *
 * حالة الطاولات بتتحدّث لحظياً عبر WebSocket /restaurant/ws/tables/{branch_id}
 * (نفس نمط KDS/BeachMap) مع polling كل 20 ثانية كـ fallback.
 *
 * الطاولات اللي مفهاش grid_row/grid_col بتظهر في قسم "غير محدد المكان"
 * في أسفل الشاشة — الوايتر يقدر يضغط عليها عادي، المدير يقدر يسحبها
 * للخريطة من هناك.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, useAuthStore, useResortWebSocket } from '@resort-os/core'
import { useToast } from '@resort-os/ui'

const router   = useRouter()
const auth     = useAuthStore()
const toast    = useToast()
const branchId = computed(() => auth.branchId ?? parseInt(localStorage.getItem('branch_id') ?? '1'))
const isManager = computed(() => auth.hasRole('manager'))

// ── Types ──────────────────────────────────────────────────────────────
interface Table {
  id:           number
  table_number: string
  capacity:     number
  status:       'available' | 'occupied' | 'reserved' | 'out_of_service'
  section:      string | null
  grid_row:     number | null
  grid_col:     number | null
  occupied_at:  string | null
}

// ── State ──────────────────────────────────────────────────────────────
const tables    = ref<Table[]>([])
const loading   = ref(false)
let   pollTimer: ReturnType<typeof setInterval>

// drag state (manager only)
const dragging       = ref<Table | null>(null)
const dragOverCell   = ref<{ row: number; col: number } | null>(null)

// #20: undo stack — بيحفظ آخر حركة drag & drop عشان المدير يقدر يرجعها
interface MoveRecord { tableId: number; fromRow: number; fromCol: number }
const lastMove  = ref<MoveRecord | null>(null)
const undoing   = ref(false)
const saving         = ref(false)

// ── Grid dimensions — تتحسب تلقائياً من أكبر إحداثي موجود ──────────────
const GRID_ROWS = computed(() => {
  const placed = tables.value.filter(t => t.grid_row !== null)
  return placed.length ? Math.max(...placed.map(t => t.grid_row!)) + 2 : 6
})
const GRID_COLS = computed(() => {
  const placed = tables.value.filter(t => t.grid_col !== null)
  return placed.length ? Math.max(...placed.map(t => t.grid_col!)) + 2 : 8
})

// ── Computed ───────────────────────────────────────────────────────────
const placedTables = computed(() =>
  tables.value.filter(t => t.grid_row !== null && t.grid_col !== null)
)
const unplacedTables = computed(() =>
  tables.value.filter(t => t.grid_row === null || t.grid_col === null)
)

function tableAt(row: number, col: number): Table | undefined {
  return placedTables.value.find(t => t.grid_row === row && t.grid_col === col)
}

// ── Status helpers ─────────────────────────────────────────────────────
function statusColor(status: string) {
  if (status === 'available')     return 'bg-emerald-100 border-emerald-400 text-emerald-900 hover:bg-emerald-200'
  if (status === 'occupied')      return 'bg-red-100 border-red-400 text-red-900 hover:bg-red-200'
  if (status === 'reserved')      return 'bg-amber-100 border-amber-400 text-amber-900 hover:bg-amber-200'
  return 'bg-gray-100 border-gray-300 text-gray-400'
}
function statusIcon(status: string) {
  if (status === 'available')  return '🟢'
  if (status === 'occupied')   return '🔴'
  if (status === 'reserved')   return '🟡'
  return '⛔'
}
function statusLabel(status: string) {
  if (status === 'available')  return 'فارغة'
  if (status === 'occupied')   return 'مشغولة'
  if (status === 'reserved')   return 'محجوزة'
  return 'خارج الخدمة'
}
function minutesSince(iso: string | null) {
  if (!iso) return 0
  return Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
}

// ── WebSocket ───────────────────────────────────────────────────────────
const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
const { status: wsStatus, onMessage } = useResortWebSocket(
  `${wsProtocol}//${location.host}/api/v1/restaurant/ws/tables/${branchId.value}`,
)
onMessage((data: any) => {
  if (data?.type === 'table_updated') {
    // نحدّث الطاولة المتأثرة فقط — مش نعيد تحميل الكل
    fetchOneTable(data.table_id)
  }
})

// ── Data Loading ───────────────────────────────────────────────────────
async function fetchTables() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/restaurant/tables', {
      params: { branch_id: branchId.value },
    })
    tables.value = data.tables ?? data.items ?? data
  } catch {
    toast.error('تعذّر تحميل الطاولات')
  } finally {
    loading.value = false
  }
}

async function fetchOneTable(tableId: number) {
  try {
    const { data } = await api.get('/api/v1/restaurant/tables', {
      params: { branch_id: branchId.value },
    })
    const all: Table[] = data.tables ?? data.items ?? data
    const updated = all.find(t => t.id === tableId)
    if (updated) {
      const idx = tables.value.findIndex(t => t.id === tableId)
      if (idx >= 0) tables.value[idx] = updated
      else tables.value.push(updated)
    }
  } catch { /* silent — fallback polling سيعوّض */ }
}

// ── Navigation ─────────────────────────────────────────────────────────
function openTable(table: Table) {
  if (table.status === 'out_of_service') return
  router.push(`/waiter/order/${table.id}`)
}

// ── Drag & Drop (Manager) ───────────────────────────────────────────────
function onDragStart(table: Table, e: DragEvent) {
  if (!isManager.value) return
  dragging.value = table
  e.dataTransfer!.effectAllowed = 'move'
}

function onDragOver(row: number, col: number, e: DragEvent) {
  if (!isManager.value || !dragging.value) return
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'move'
  dragOverCell.value = { row, col }
}

function onDragLeave() {
  dragOverCell.value = null
}

async function onDrop(row: number, col: number) {
  dragOverCell.value = null
  if (!isManager.value || !dragging.value || saving.value) return

  // منع وضع طاولتين على نفس الخلية
  const occupant = tableAt(row, col)
  if (occupant && occupant.id !== dragging.value.id) {
    toast.error(`الخلية مشغولة بطاولة ${occupant.table_number}`)
    dragging.value = null
    return
  }

  const table = dragging.value
  dragging.value = null

  // لو نفس المكان — مافيش تغيير
  if (table.grid_row === row && table.grid_col === col) return

  saving.value = true

  // #20: احفظ الموضع القديم للـ undo قبل أي تغيير
  lastMove.value = { tableId: table.id, fromRow: table.grid_row ?? -1, fromCol: table.grid_col ?? -1 }

  // optimistic update
  const idx = tables.value.findIndex(t => t.id === table.id)
  if (idx >= 0) {
    tables.value[idx] = { ...tables.value[idx], grid_row: row, grid_col: col }
  }

  try {
    await api.patch(`/api/v1/restaurant/tables/${table.id}/grid`, {
      grid_row: row, grid_col: col,
    })
    // #1 fix: useToast بيقبل string فقط — الزر موجود في الـ header كـ fallback
    toast.success(`📌 طاولة ${table.table_number} انتقلت — اضغط "↩ تراجع" في الأعلى لو اتغلطت`)
  } catch (e: any) {
    // rollback
    if (idx >= 0) tables.value[idx] = table
    lastMove.value = null
    toast.error(e?.response?.data?.detail ?? 'تعذّر حفظ موضع الطاولة')
  } finally {
    saving.value = false
  }
}

// #20: تراجع عن آخر حركة drag
async function undoLastMove() {
  if (!lastMove.value || undoing.value) return
  const { tableId, fromRow, fromCol } = lastMove.value
  if (fromRow < 0) return // كانت غير موضوعة — مش ممكن نرجعها لـ null عبر PATCH
  undoing.value = true
  const idx = tables.value.findIndex(t => t.id === tableId)
  const prev = idx >= 0 ? { ...tables.value[idx] } : null
  if (idx >= 0) tables.value[idx] = { ...tables.value[idx], grid_row: fromRow, grid_col: fromCol }
  try {
    await api.patch(`/api/v1/restaurant/tables/${tableId}/grid`, { grid_row: fromRow, grid_col: fromCol })
    lastMove.value = null
    toast.success('↩ تم التراجع')
  } catch {
    if (prev && idx >= 0) tables.value[idx] = prev
    toast.error('تعذّر التراجع')
  } finally {
    undoing.value = false
  }
}

// سحب طاولة "غير محدد المكان" لأول خلية فارغة في الشبكة
async function autoPlaceTable(table: Table) {
  if (!isManager.value) return
  // إيجاد أول خلية فارغة
  for (let r = 0; r < GRID_ROWS.value; r++) {
    for (let c = 0; c < GRID_COLS.value; c++) {
      if (!tableAt(r, c)) {
        const idx = tables.value.findIndex(t => t.id === table.id)
        if (idx >= 0) tables.value[idx] = { ...tables.value[idx], grid_row: r, grid_col: c }
        try {
          await api.patch(`/api/v1/restaurant/tables/${table.id}/grid`, { grid_row: r, grid_col: c })
          toast.success(`تم وضع طاولة ${table.table_number} في الخريطة`)
        } catch {
          if (idx >= 0) tables.value[idx] = table
          toast.error('تعذّر وضع الطاولة')
        }
        return
      }
    }
  }
  toast.error('الشبكة ممتلئة — كبّرها أولاً')
}

// إزالة طاولة من الخريطة (manager)
async function removeFromGrid(table: Table) {
  const idx = tables.value.findIndex(t => t.id === table.id)
  if (idx >= 0) tables.value[idx] = { ...tables.value[idx], grid_row: null, grid_col: null }
  try {
    await api.patch(`/api/v1/restaurant/tables/${table.id}/grid`, { grid_row: null, grid_col: null })
  } catch {
    if (idx >= 0) tables.value[idx] = table
    toast.error('تعذّر إزالة الطاولة من الخريطة')
  }
}

onMounted(() => {
  fetchTables()
  pollTimer = setInterval(fetchTables, 20_000)
})
onUnmounted(() => clearInterval(pollTimer))
</script>

<template>
  <div class="flex flex-col h-full bg-stone-50" dir="rtl">

    <!-- Header -->
    <div class="bg-white border-b border-stone-200 px-4 py-3 flex items-center justify-between flex-shrink-0 shadow-sm">
      <div class="flex items-center gap-3">
        <button @click="$router.push('/waiter/tables')"
          class="text-blue-700 font-bold text-sm px-2 py-1.5 hover:bg-blue-50 rounded-lg">
          ← قائمة
        </button>
        <h1 class="font-black text-gray-900">🗺️ خريطة القاعة</h1>
        <div class="flex items-center gap-1.5" :title="wsStatus === 'connected' ? 'تحديث لحظي' : 'polling فقط'">
          <div :class="['w-2 h-2 rounded-full', wsStatus === 'connected' ? 'bg-green-500' : 'bg-amber-400']" />
          <span class="text-xs text-gray-400">{{ wsStatus === 'connected' ? 'لحظي' : 'polling' }}</span>
        </div>
      </div>

      <!-- Legend -->
      <div class="flex items-center gap-3 text-xs">
        <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-emerald-400 inline-block"/><span>فارغة ({{ tables.filter(t=>t.status==='available').length }})</span></span>
        <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-red-400 inline-block"/><span>مشغولة ({{ tables.filter(t=>t.status==='occupied').length }})</span></span>
        <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-amber-400 inline-block"/><span>محجوزة ({{ tables.filter(t=>t.status==='reserved').length }})</span></span>
        <span v-if="isManager" class="text-gray-400 border-r pr-3">اسحب لتغيير المكان</span>
        <!-- #20: زر تراجع عن آخر drag — visible فقط لما يكون في حركة محفوظة -->
        <button
          v-if="isManager && lastMove"
          @click="undoLastMove"
          :disabled="undoing"
          class="flex items-center gap-1 bg-amber-100 hover:bg-amber-200 text-amber-800 font-bold text-xs px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
        >
          <span v-if="undoing" class="w-3 h-3 border-2 border-amber-700 border-t-transparent rounded-full animate-spin"/>
          ↩ تراجع
        </button>
      </div>
    </div>

    <div v-if="loading && tables.length === 0" class="flex-1 flex items-center justify-center">
      <div class="animate-spin w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full"/>
    </div>

    <div v-else class="flex-1 overflow-auto p-4">

      <!-- ── Grid ── -->
      <div
        class="inline-grid gap-2 p-4 bg-white rounded-2xl border border-stone-200 shadow-sm"
        :style="`grid-template-columns: repeat(${GRID_COLS}, minmax(80px, 1fr)); grid-template-rows: repeat(${GRID_ROWS}, 80px);`"
      >
        <template v-for="row in GRID_ROWS" :key="`row-${row}`">
          <div
            v-for="col in GRID_COLS"
            :key="`cell-${row}-${col}`"
            class="relative rounded-xl border-2 transition-all"
            :class="[
              tableAt(row-1, col-1)
                ? [statusColor(tableAt(row-1, col-1)!.status), 'cursor-pointer border-solid']
                : 'border-dashed border-stone-200 bg-stone-50',
              dragOverCell?.row === row-1 && dragOverCell?.col === col-1
                ? 'border-blue-500 bg-blue-50 scale-105'
                : '',
            ]"
            @dragover="onDragOver(row-1, col-1, $event)"
            @dragleave="onDragLeave"
            @drop.prevent="onDrop(row-1, col-1)"
            @click="tableAt(row-1, col-1) && openTable(tableAt(row-1, col-1)!)"
          >
            <!-- طاولة موجودة في الخلية — نستخدم v-for على array من عنصر واحد
                 كـ workaround لـ TS-safe variable binding بدل "v-if as" -->
            <template v-for="cellTable in (tableAt(row-1, col-1) ? [tableAt(row-1, col-1)!] : [])" :key="cellTable.id">
              <div
                class="w-full h-full flex flex-col items-center justify-center p-1 select-none"
                :draggable="isManager"
                @dragstart="onDragStart(cellTable, $event)"
              >
                <div class="text-lg font-black leading-none">{{ cellTable.table_number }}</div>
                <div class="text-[10px] font-medium mt-0.5">{{ statusLabel(cellTable.status) }}</div>
                <div class="text-[10px] text-gray-500">👥{{ cellTable.capacity }}</div>
                <!-- مدة الجلوس لو مشغولة -->
                <div v-if="cellTable.status === 'occupied' && cellTable.occupied_at"
                  class="text-[10px] font-bold text-red-600 mt-0.5">
                  {{ minutesSince(cellTable.occupied_at) }}د
                </div>
              </div>
              <!-- زر إزالة من الخريطة (manager) -->
              <button
                v-if="isManager"
                @click.stop="removeFromGrid(cellTable)"
                class="absolute top-0.5 left-0.5 w-4 h-4 bg-gray-400 hover:bg-red-500 text-white rounded-full text-[9px] flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                title="إزالة من الخريطة"
              >×</button>
            </template>

            <!-- خلية فارغة — نعرض إحداثيات صغيرة للمدير -->
            <div v-if="!tableAt(row-1, col-1) && isManager" class="absolute inset-0 flex items-center justify-center">
              <span class="text-[9px] text-stone-300">{{ row-1 }},{{ col-1 }}</span>
            </div>
          </div>
        </template>
      </div>

      <!-- ── Unplaced tables ── -->
      <div v-if="unplacedTables.length > 0" class="mt-6">
        <h2 class="text-sm font-bold text-gray-500 mb-3 flex items-center gap-2">
          <span>📦 غير محدد المكان ({{ unplacedTables.length }})</span>
          <span v-if="isManager" class="text-xs font-normal text-blue-600">— اضغط لوضعها تلقائياً أو اسحبها للخريطة</span>
        </h2>
        <div class="flex flex-wrap gap-3">
          <div
            v-for="table in unplacedTables"
            :key="table.id"
            :draggable="isManager"
            @dragstart="onDragStart(table, $event)"
            :class="[
              'relative w-20 h-20 rounded-xl border-2 flex flex-col items-center justify-center p-1 select-none transition-all',
              statusColor(table.status),
              table.status !== 'out_of_service' ? 'cursor-pointer active:scale-95' : '',
              isManager ? 'cursor-grab active:cursor-grabbing' : '',
            ]"
            @click="isManager ? autoPlaceTable(table) : openTable(table)"
          >
            <div class="text-lg font-black leading-none">{{ table.table_number }}</div>
            <div class="text-[10px] font-medium mt-0.5">{{ statusLabel(table.status) }}</div>
            <div class="text-[10px] text-gray-500">👥{{ table.capacity }}</div>
          </div>
        </div>
      </div>

      <!-- saving indicator -->
      <div v-if="saving"
        class="fixed bottom-4 left-1/2 -translate-x-1/2 bg-blue-700 text-white text-sm font-bold px-4 py-2 rounded-xl shadow-lg flex items-center gap-2">
        <div class="animate-spin w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full"/>
        جاري الحفظ...
      </div>

    </div>
  </div>
</template>
