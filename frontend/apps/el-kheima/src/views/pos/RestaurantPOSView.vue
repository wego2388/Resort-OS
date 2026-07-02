<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { useOfflineQueue } from '@resort-os/core/composables'

const { isOnline, pendingCount, submitOrder: submitOrderOnlineOrQueue, lastPartialRejection } = useOfflineQueue()

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

// ── Types ──────────────────────────────────────────────────────────────────────
interface Table    { id: number; table_number: string; status: string; capacity: number }
interface Category { id: number; name: string; name_ar: string }
interface MenuItem { id: number; name: string; name_ar: string; price: number; is_available: boolean; category_id: number; description_ar?: string }
interface CartItem { menu_item_id: number; name: string; name_ar: string; price: number; quantity: number; notes: string }

// ── State ──────────────────────────────────────────────────────────────────────
const tables            = ref<Table[]>([])
const categories        = ref<Category[]>([])
const menuItems         = ref<MenuItem[]>([])
const selectedTable     = ref<Table | null>(null)
const selectedCategoryId = ref<number | null>(null)
const cart              = ref<CartItem[]>([])
const covers            = ref(1)
const paymentMethod     = ref<'cash' | 'card' | 'room'>('cash')
const loading           = ref(false)
const submitting        = ref(false)
const successMsg        = ref('')
const errorMsg          = ref('')

// Note editor modal
const editingNoteId  = ref<number | null>(null)
const tempNote       = ref('')

// ── Computed ───────────────────────────────────────────────────────────────────
const filteredItems = computed(() =>
  selectedCategoryId.value !== null
    ? menuItems.value.filter(i => i.category_id === selectedCategoryId.value && i.is_available)
    : menuItems.value.filter(i => i.is_available)
)

const total    = computed(() => cart.value.reduce((s, i) => s + i.price * i.quantity, 0))
const hasItems = computed(() => cart.value.length > 0)

// ── Cart actions ───────────────────────────────────────────────────────────────
function addToCart(item: MenuItem) {
  const existing = cart.value.find(c => c.menu_item_id === item.id)
  if (existing) { existing.quantity++; return }
  cart.value.push({
    menu_item_id: item.id,
    name:         item.name,
    name_ar:      item.name_ar,
    price:        item.price,
    quantity:     1,
    notes:        '',
  })
}

function removeFromCart(itemId: number) {
  cart.value = cart.value.filter(c => c.menu_item_id !== itemId)
}

function adjustQty(itemId: number, delta: number) {
  const item = cart.value.find(c => c.menu_item_id === itemId)
  if (!item) return
  item.quantity = Math.max(0, item.quantity + delta)
  if (item.quantity === 0) removeFromCart(itemId)
}

function clearOrder() {
  cart.value = []
  covers.value = 1
}

// ── Note editor ────────────────────────────────────────────────────────────────
function openNoteEditor(itemId: number, currentNote: string) {
  editingNoteId.value = itemId
  tempNote.value = currentNote
}

function saveNote() {
  const item = cart.value.find(c => c.menu_item_id === editingNoteId.value)
  if (item) item.notes = tempNote.value
  editingNoteId.value = null
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function tableStatusLabel(status: string): string {
  if (status === 'available') return 'فارغة'
  if (status === 'occupied')  return 'مشغولة'
  return 'محجوزة'
}

function tableStatusDot(status: string): string {
  if (status === 'available') return 'bg-green-500'
  if (status === 'occupied')  return 'bg-red-500'
  return 'bg-amber-500'
}

// ── API calls ──────────────────────────────────────────────────────────────────
async function loadData() {
  loading.value = true
  try {
    const [tablesRes, catsRes, itemsRes] = await Promise.all([
      api.get('/api/v1/restaurant/tables', {
        params: { branch_id: branchId },
      }),
      api.get('/api/v1/restaurant/menu/categories', {
        params: { branch_id: branchId },
      }),
      api.get('/api/v1/restaurant/menu/items', {
        params: { branch_id: branchId, limit: 200 },
      }),
    ])

    tables.value     = tablesRes.data.tables    ?? tablesRes.data.items    ?? tablesRes.data
    categories.value = catsRes.data.categories  ?? catsRes.data.items      ?? catsRes.data
    menuItems.value  = itemsRes.data.items       ?? itemsRes.data

    if (categories.value.length) {
      selectedCategoryId.value = categories.value[0].id
    }
  } catch (e) {
    console.error('Failed to load restaurant data', e)
  } finally {
    loading.value = false
  }
}

async function submitOrder() {
  if (!hasItems.value || submitting.value) return
  submitting.value = true
  try {
    const payload = {
      table_id:     selectedTable.value?.id ?? null,
      order_type:   selectedTable.value ? 'dine_in' : 'takeaway',
      guests_count: covers.value,
      items: cart.value.map(i => ({
        menu_item_id: i.menu_item_id,
        quantity:     i.quantity,
        notes:        i.notes || undefined,
      })),
    }

    const data = await submitOrderOnlineOrQueue(branchId, payload)

    if (data === null) {
      // مفيش نت — اتحفظ في IndexedDB، هيتزامن أوتوماتيك لما الاتصال يرجع
      clearOrder()
      successMsg.value = '📥 الطلب محفوظ — هيتبعت للمطبخ أول ما النت يرجع'
      setTimeout(() => { successMsg.value = '' }, 4000)
      return
    }

    const orderId = data.id ?? data.order_id
    if (orderId) {
      try {
        const receiptRes = await api.get(`/api/v1/restaurant/orders/${orderId}/receipt`, {
          responseType: 'blob',
        })
        const url = URL.createObjectURL(receiptRes.data)
        window.open(url, '_blank')
      } catch {
        // receipt optional
      }
    }

    clearOrder()
    successMsg.value = 'تم إرسال الطلب للمطبخ ✓'
    setTimeout(() => { successMsg.value = '' }, 3000)
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail ?? 'فشل في إرسال الطلب'
    setTimeout(() => { errorMsg.value = '' }, 4000)
  } finally {
    submitting.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div class="flex flex-col h-full" dir="rtl">

    <!-- ── Offline banner — visible الطول، مش toast بيختفي ── -->
    <div
      v-if="!isOnline"
      class="bg-amber-500 text-white text-xs font-bold px-4 py-1.5 flex items-center justify-center gap-2 flex-shrink-0"
    >
      <span>⚠️ وضع offline — الطلبات بتتحفظ محلياً وهتتبعت أول ما النت يرجع</span>
      <span v-if="pendingCount > 0" class="bg-amber-700 px-2 py-0.5 rounded-full">{{ pendingCount }} في الانتظار</span>
    </div>
    <div
      v-else-if="pendingCount > 0"
      class="bg-blue-500 text-white text-xs font-bold px-4 py-1.5 flex items-center justify-center gap-2 flex-shrink-0"
    >
      <span>⏳ جاري إرسال {{ pendingCount }} طلب محفوظ من فترة الانقطاع...</span>
    </div>
    <div
      v-if="lastPartialRejection && lastPartialRejection.length"
      class="bg-red-100 text-red-800 text-xs font-semibold px-4 py-2 flex-shrink-0 border-b border-red-200"
    >
      ⚠️ تم رفض بعض الأصناف من طلب محفوظ سابقاً (نفاد المخزون):
      {{ lastPartialRejection.map(i => `${i.name} (×${i.requested_qty})`).join('، ') }}
    </div>

    <!-- ── Top bar: table + covers + categories ── -->
    <div class="bg-white border-b border-stone-200 px-4 py-3 flex flex-wrap gap-3 items-center shadow-sm flex-shrink-0">

      <!-- Table selector -->
      <div class="flex items-center gap-2">
        <label class="text-sm font-semibold text-gray-700">الطاولة:</label>
        <div class="relative">
          <select
            v-model="selectedTable"
            class="border border-stone-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 appearance-none pr-7 bg-white cursor-pointer"
          >
            <option :value="null">Takeaway (بدون طاولة)</option>
            <option v-for="t in tables" :key="t.id" :value="t">
              طاولة {{ t.table_number }} — {{ tableStatusLabel(t.status) }}
            </option>
          </select>
          <!-- Status dot for selected table -->
          <span
            v-if="selectedTable"
            class="absolute left-2 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full"
            :class="tableStatusDot(selectedTable.status)"
          />
        </div>
      </div>

      <!-- Covers counter -->
      <div class="flex items-center gap-2">
        <label class="text-sm font-semibold text-gray-700">الغطاءات:</label>
        <div class="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5">
          <button
            @click="covers = Math.max(1, covers - 1)"
            class="w-7 h-7 rounded-md bg-white hover:bg-gray-50 text-sm font-bold shadow-sm transition-colors"
          >−</button>
          <span class="w-8 text-center font-bold text-sm">{{ covers }}</span>
          <button
            @click="covers++"
            class="w-7 h-7 rounded-md bg-white hover:bg-gray-50 text-sm font-bold shadow-sm transition-colors"
          >+</button>
        </div>
      </div>

      <!-- Category tabs -->
      <div class="flex gap-1 flex-wrap">
        <button
          @click="selectedCategoryId = null"
          :class="[
            'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
            selectedCategoryId === null
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
          ]"
        >الكل</button>
        <button
          v-for="cat in categories"
          :key="cat.id"
          @click="selectedCategoryId = cat.id"
          :class="[
            'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
            selectedCategoryId === cat.id
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
          ]"
        >{{ cat.name_ar || cat.name }}</button>
      </div>

    </div>

    <!-- ── Main split: menu + order ── -->
    <div class="flex flex-1 overflow-hidden">

      <!-- Menu grid (left/main area) -->
      <div class="flex-1 overflow-y-auto p-4 bg-stone-50">
        <div v-if="loading" class="flex items-center justify-center h-40">
          <div class="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
        </div>

        <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-3">
          <button
            v-for="item in filteredItems"
            :key="item.id"
            @click="addToCart(item)"
            class="bg-white rounded-xl border border-stone-200 p-4 text-right hover:border-blue-400 hover:shadow-md transition-all active:scale-95 active:shadow-sm flex flex-col justify-between min-h-[90px]"
          >
            <div class="font-semibold text-gray-900 text-sm leading-tight mb-2">
              {{ item.name_ar || item.name }}
            </div>
            <div class="text-lg font-black text-blue-700">
              {{ item.price }}<span class="text-xs font-normal text-gray-400 mr-0.5">ج</span>
            </div>
          </button>
        </div>

        <div v-if="!loading && filteredItems.length === 0" class="flex flex-col items-center justify-center py-16 text-gray-400">
          <div class="text-4xl mb-2">🍽️</div>
          <p class="text-sm">لا توجد أصناف في هذه الفئة</p>
        </div>
      </div>

      <!-- ── Order panel (right sidebar) ── -->
      <div class="w-72 bg-white border-r border-stone-200 flex flex-col flex-shrink-0 shadow-lg">

        <!-- Order header -->
        <div class="p-4 border-b border-stone-100 bg-gray-50">
          <div class="font-bold text-gray-900">
            {{ selectedTable ? `طاولة ${selectedTable.table_number}` : 'Takeaway' }}
          </div>
          <div class="text-xs text-gray-500 mt-0.5">
            {{ covers }} {{ covers === 1 ? 'غطاء' : 'غطاءات' }}
            <span v-if="selectedTable" :class="['inline-block w-2 h-2 rounded-full mr-1.5 mb-0.5', tableStatusDot(selectedTable.status)]" />
          </div>
        </div>

        <!-- Cart items -->
        <div class="flex-1 overflow-y-auto p-3 space-y-2">
          <div v-if="cart.length === 0" class="flex flex-col items-center justify-center py-10 text-gray-400">
            <div class="text-3xl mb-2">🛒</div>
            <p class="text-sm">اختر أصناف من القائمة</p>
          </div>

          <div
            v-for="item in cart"
            :key="item.menu_item_id"
            class="bg-stone-50 rounded-lg p-3 border border-stone-200"
          >
            <!-- Item name + remove -->
            <div class="flex items-start justify-between mb-2 gap-1">
              <span class="text-sm font-semibold text-gray-900 leading-tight flex-1">
                {{ item.name_ar || item.name }}
              </span>
              <button
                @click="removeFromCart(item.menu_item_id)"
                class="text-red-400 hover:text-red-600 text-lg leading-none flex-shrink-0 w-5 h-5 flex items-center justify-center rounded hover:bg-red-50 transition-colors"
              >×</button>
            </div>

            <!-- Qty controls + subtotal -->
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5">
                <button
                  @click="adjustQty(item.menu_item_id, -1)"
                  class="w-6 h-6 rounded bg-gray-200 hover:bg-gray-300 text-sm font-bold transition-colors leading-none"
                >−</button>
                <span class="text-sm font-bold w-5 text-center">{{ item.quantity }}</span>
                <button
                  @click="adjustQty(item.menu_item_id, 1)"
                  class="w-6 h-6 rounded bg-blue-100 hover:bg-blue-200 text-blue-700 text-sm font-bold transition-colors leading-none"
                >+</button>
              </div>
              <span class="text-sm font-bold text-blue-700">{{ item.price * item.quantity }} ج</span>
            </div>

            <!-- Notes -->
            <button
              @click="openNoteEditor(item.menu_item_id, item.notes)"
              class="mt-2 text-xs text-gray-400 hover:text-blue-600 transition-colors text-right w-full truncate"
            >
              {{ item.notes ? `📝 ${item.notes}` : '+ إضافة ملاحظة' }}
            </button>
          </div>
        </div>

        <!-- Footer: total + payment + submit -->
        <div class="border-t border-stone-200 p-3 space-y-3 bg-white">

          <!-- Total -->
          <div class="flex justify-between items-center">
            <span class="text-base font-bold text-gray-900">المجموع</span>
            <span class="text-xl font-black text-blue-700">{{ total }} ج</span>
          </div>

          <!-- Payment method -->
          <div class="grid grid-cols-3 gap-1">
            <button
              v-for="m in [{ val: 'cash', label: 'كاش' }, { val: 'card', label: 'كارت' }, { val: 'room', label: 'أوضة' }]"
              :key="m.val"
              @click="paymentMethod = (m.val as 'cash' | 'card' | 'room')"
              :class="[
                'py-1.5 rounded-lg text-xs font-semibold border-2 transition-all',
                paymentMethod === m.val
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-stone-200 text-gray-600 hover:border-blue-200',
              ]"
            >{{ m.label }}</button>
          </div>

          <!-- Messages -->
          <transition name="fade">
            <div v-if="successMsg" class="bg-green-100 text-green-700 text-xs px-2 py-2 rounded-lg text-center font-medium">
              {{ successMsg }}
            </div>
          </transition>
          <transition name="fade">
            <div v-if="errorMsg" class="bg-red-100 text-red-700 text-xs px-2 py-2 rounded-lg text-center font-medium">
              {{ errorMsg }}
            </div>
          </transition>

          <!-- Action buttons -->
          <div class="grid grid-cols-2 gap-2">
            <button
              @click="clearOrder"
              :disabled="!hasItems"
              class="py-2.5 rounded-xl border-2 border-stone-200 text-sm font-semibold text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition-colors"
            >مسح</button>
            <button
              @click="submitOrder"
              :disabled="!hasItems || submitting"
              class="py-2.5 rounded-xl bg-blue-700 text-white text-sm font-bold hover:bg-blue-800 disabled:opacity-50 transition-colors flex items-center justify-center gap-1.5"
            >
              <div v-if="submitting" class="animate-spin w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
              <span>{{ submitting ? 'جاري...' : 'إرسال للمطبخ' }}</span>
            </button>
          </div>

        </div>
      </div>
    </div>

    <!-- ── Note editor modal ── -->
    <Transition name="modal">
      <div
        v-if="editingNoteId !== null"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="editingNoteId = null"
      >
        <div class="bg-white rounded-2xl p-5 w-full max-w-sm shadow-2xl">
          <h3 class="font-bold text-gray-900 mb-1 text-base">ملاحظة على الصنف</h3>
          <p class="text-xs text-gray-400 mb-3">مثال: بدون ثوم، حار جداً، بدون خل</p>
          <textarea
            v-model="tempNote"
            rows="3"
            placeholder="اكتب الملاحظة هنا..."
            class="w-full border border-stone-300 rounded-xl p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            autofocus
          />
          <div class="flex gap-2 mt-3">
            <button
              @click="editingNoteId = null"
              class="flex-1 py-2.5 border-2 border-stone-200 rounded-xl text-sm font-semibold text-gray-600 hover:bg-gray-50 transition-colors"
            >إلغاء</button>
            <button
              @click="saveNote"
              class="flex-1 py-2.5 bg-blue-700 text-white rounded-xl text-sm font-bold hover:bg-blue-800 transition-colors"
            >حفظ الملاحظة</button>
          </div>
        </div>
      </div>
    </Transition>

  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-active > div,
.modal-leave-active > div {
  transition: transform 0.2s ease;
}
.modal-enter-from > div,
.modal-leave-to > div {
  transform: scale(0.95) translateY(8px);
}
</style>
