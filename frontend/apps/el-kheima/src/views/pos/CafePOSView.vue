<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const authHeaders = computed(() => ({
  Authorization: `Bearer ${localStorage.getItem('access_token')}`,
}))

// ── Types ──────────────────────────────────────────────────────────────────────
interface Category { id: number; name: string; name_ar: string }
interface MenuItem { id: number; name: string; name_ar: string; price: number; is_available: boolean; category_id: number }
interface CartItem { menu_item_id: number; name: string; name_ar: string; price: number; quantity: number; notes: string }

// ── State ──────────────────────────────────────────────────────────────────────
const categories         = ref<Category[]>([])
const menuItems          = ref<MenuItem[]>([])
const selectedCategoryId = ref<number | null>(null)
const cart               = ref<CartItem[]>([])
const paymentMethod      = ref<'cash' | 'card' | 'wallet'>('cash')
const loading            = ref(false)
const submitting         = ref(false)
const successMsg         = ref('')
const errorMsg           = ref('')

// Quick-qty pad: when user long-presses or uses number-pad modal
const qtyPadItem   = ref<MenuItem | null>(null)
const qtyPadValue  = ref('1')

// Note editor
const editingNoteId = ref<number | null>(null)
const tempNote      = ref('')

// ── Computed ───────────────────────────────────────────────────────────────────
const filteredItems = computed(() =>
  selectedCategoryId.value !== null
    ? menuItems.value.filter(i => i.category_id === selectedCategoryId.value && i.is_available)
    : menuItems.value.filter(i => i.is_available)
)

const total    = computed(() => cart.value.reduce((s, i) => s + i.price * i.quantity, 0))
const hasItems = computed(() => cart.value.length > 0)

// ── Cart actions ───────────────────────────────────────────────────────────────
function addToCart(item: MenuItem, qty = 1) {
  const existing = cart.value.find(c => c.menu_item_id === item.id)
  if (existing) {
    existing.quantity += qty
    return
  }
  cart.value.push({
    menu_item_id: item.id,
    name:         item.name,
    name_ar:      item.name_ar,
    price:        item.price,
    quantity:     qty,
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
}

// ── Quick qty pad ──────────────────────────────────────────────────────────────
function openQtyPad(item: MenuItem) {
  qtyPadItem.value  = item
  qtyPadValue.value = '1'
}

function qtyPadPress(char: string) {
  if (char === 'C') { qtyPadValue.value = '1'; return }
  if (char === '⌫') {
    qtyPadValue.value = qtyPadValue.value.length > 1
      ? qtyPadValue.value.slice(0, -1)
      : '1'
    return
  }
  if (qtyPadValue.value === '1' && char !== '0') {
    qtyPadValue.value = char
  } else if (qtyPadValue.value.length < 3) {
    qtyPadValue.value += char
  }
}

function confirmQtyPad() {
  const qty = parseInt(qtyPadValue.value) || 1
  if (qtyPadItem.value) addToCart(qtyPadItem.value, qty)
  qtyPadItem.value = null
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

// ── API ────────────────────────────────────────────────────────────────────────
async function loadData() {
  loading.value = true
  try {
    const [catsRes, itemsRes] = await Promise.all([
      axios.get('/api/v1/cafe/categories', {
        headers: authHeaders.value,
        params: { branch_id: branchId },
      }),
      axios.get('/api/v1/cafe/items', {
        headers: authHeaders.value,
        params: { branch_id: branchId },
      }),
    ])

    categories.value = catsRes.data.categories  ?? catsRes.data.items  ?? catsRes.data
    menuItems.value  = itemsRes.data.items       ?? itemsRes.data

    if (categories.value.length) {
      selectedCategoryId.value = categories.value[0].id
    }
  } catch (e) {
    console.error('Failed to load cafe data', e)
  } finally {
    loading.value = false
  }
}

async function submitOrder() {
  if (!hasItems.value || submitting.value) return
  submitting.value = true
  try {
    const payload = {
      branch_id:      branchId,
      outlet_type:    'cafe',
      payment_method: paymentMethod.value,
      items: cart.value.map(i => ({
        menu_item_id: i.menu_item_id,
        quantity:     i.quantity,
        unit_price:   i.price,
        notes:        i.notes || undefined,
      })),
    }

    const { data } = await axios.post('/api/v1/cafe/orders', payload, {
      headers: authHeaders.value,
    })

    const orderId = data.id ?? data.order_id
    if (orderId) {
      try {
        const receiptRes = await axios.get(`/api/v1/cafe/orders/${orderId}/receipt`, {
          headers: authHeaders.value,
          responseType: 'blob',
        })
        const url = URL.createObjectURL(receiptRes.data)
        window.open(url, '_blank')
      } catch {
        // receipt optional
      }
    }

    clearOrder()
    successMsg.value = 'تم إرسال الطلب ✓'
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

    <!-- ── Category tabs ── -->
    <div class="bg-white border-b border-stone-200 px-4 py-3 flex gap-2 flex-wrap items-center shadow-sm flex-shrink-0">
      <span class="text-sm font-bold text-gray-700 ml-2">☕ الكافيه</span>

      <button
        @click="selectedCategoryId = null"
        :class="[
          'px-4 py-1.5 rounded-full text-sm font-medium transition-colors',
          selectedCategoryId === null
            ? 'bg-amber-600 text-white shadow-sm'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
        ]"
      >الكل</button>

      <button
        v-for="cat in categories"
        :key="cat.id"
        @click="selectedCategoryId = cat.id"
        :class="[
          'px-4 py-1.5 rounded-full text-sm font-medium transition-colors',
          selectedCategoryId === cat.id
            ? 'bg-amber-600 text-white shadow-sm'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
        ]"
      >{{ cat.name_ar || cat.name }}</button>
    </div>

    <!-- ── Main split ── -->
    <div class="flex flex-1 overflow-hidden">

      <!-- Menu tiles (larger, café style) -->
      <div class="flex-1 overflow-y-auto p-4 bg-stone-50">
        <div v-if="loading" class="flex items-center justify-center h-40">
          <div class="animate-spin w-8 h-8 border-4 border-amber-600 border-t-transparent rounded-full" />
        </div>

        <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-3">
          <button
            v-for="item in filteredItems"
            :key="item.id"
            @click="addToCart(item)"
            @contextmenu.prevent="openQtyPad(item)"
            class="group bg-white rounded-2xl border border-stone-200 p-5 text-right hover:border-amber-400 hover:shadow-lg transition-all active:scale-95 flex flex-col justify-between min-h-[110px]"
          >
            <div class="font-bold text-gray-900 leading-tight text-sm mb-2">
              {{ item.name_ar || item.name }}
            </div>
            <div class="flex items-end justify-between">
              <div class="text-xl font-black text-amber-700">
                {{ item.price }}<span class="text-xs font-normal text-gray-400 mr-0.5">ج</span>
              </div>
              <!-- Quick add indicator -->
              <div class="w-7 h-7 rounded-full bg-amber-100 group-hover:bg-amber-600 flex items-center justify-center transition-colors">
                <span class="text-amber-700 group-hover:text-white font-bold text-lg leading-none">+</span>
              </div>
            </div>
          </button>
        </div>

        <div v-if="!loading && filteredItems.length === 0" class="flex flex-col items-center justify-center py-16 text-gray-400">
          <div class="text-4xl mb-2">☕</div>
          <p class="text-sm">لا توجد أصناف في هذه الفئة</p>
        </div>

        <!-- Hint -->
        <p v-if="!loading && filteredItems.length > 0" class="text-center text-xs text-gray-300 mt-4">
          اضغط مرة لإضافة واحدة · كليك يمين لتحديد الكمية
        </p>
      </div>

      <!-- ── Order panel ── -->
      <div class="w-72 bg-white border-r border-stone-200 flex flex-col flex-shrink-0 shadow-lg">

        <!-- Header -->
        <div class="p-4 border-b border-stone-100 bg-amber-50">
          <div class="font-bold text-amber-900 flex items-center gap-2">
            <span>☕</span>
            <span>الطلب الحالي</span>
          </div>
        </div>

        <!-- Cart items -->
        <div class="flex-1 overflow-y-auto p-3 space-y-2">
          <div v-if="cart.length === 0" class="flex flex-col items-center justify-center py-10 text-gray-400">
            <div class="text-4xl mb-2">☕</div>
            <p class="text-sm">اختر أصناف من القائمة</p>
            <p class="text-xs mt-1 text-gray-300">كليك يمين لتحديد الكمية</p>
          </div>

          <div
            v-for="item in cart"
            :key="item.menu_item_id"
            class="bg-amber-50 rounded-xl p-3 border border-amber-100"
          >
            <div class="flex items-start justify-between mb-2 gap-1">
              <span class="text-sm font-semibold text-gray-900 leading-tight flex-1">
                {{ item.name_ar || item.name }}
              </span>
              <button
                @click="removeFromCart(item.menu_item_id)"
                class="text-red-400 hover:text-red-600 text-lg leading-none w-5 h-5 flex items-center justify-center rounded hover:bg-red-50 transition-colors flex-shrink-0"
              >×</button>
            </div>

            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5">
                <button
                  @click="adjustQty(item.menu_item_id, -1)"
                  class="w-7 h-7 rounded-lg bg-white border border-amber-200 hover:bg-amber-100 text-sm font-bold transition-colors leading-none"
                >−</button>
                <span class="text-sm font-black w-6 text-center text-gray-900">{{ item.quantity }}</span>
                <button
                  @click="adjustQty(item.menu_item_id, 1)"
                  class="w-7 h-7 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm font-bold transition-colors leading-none"
                >+</button>
              </div>
              <span class="text-sm font-black text-amber-700">{{ item.price * item.quantity }} ج</span>
            </div>

            <button
              @click="openNoteEditor(item.menu_item_id, item.notes)"
              class="mt-1.5 text-xs text-gray-400 hover:text-amber-600 transition-colors text-right w-full truncate"
            >
              {{ item.notes ? `📝 ${item.notes}` : '+ ملاحظة' }}
            </button>
          </div>
        </div>

        <!-- Footer -->
        <div class="border-t border-stone-200 p-3 space-y-3 bg-white">

          <!-- Total -->
          <div class="flex justify-between items-center">
            <span class="text-base font-bold text-gray-900">المجموع</span>
            <span class="text-xl font-black text-amber-700">{{ total }} ج</span>
          </div>

          <!-- Payment method -->
          <div class="grid grid-cols-3 gap-1">
            <button
              v-for="m in [{ val: 'cash', label: 'كاش' }, { val: 'card', label: 'كارت' }, { val: 'wallet', label: 'محفظة' }]"
              :key="m.val"
              @click="paymentMethod = (m.val as 'cash' | 'card' | 'wallet')"
              :class="[
                'py-1.5 rounded-lg text-xs font-semibold border-2 transition-all',
                paymentMethod === m.val
                  ? 'border-amber-600 bg-amber-50 text-amber-700'
                  : 'border-stone-200 text-gray-600 hover:border-amber-200',
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

          <!-- Buttons -->
          <div class="grid grid-cols-2 gap-2">
            <button
              @click="clearOrder"
              :disabled="!hasItems"
              class="py-2.5 rounded-xl border-2 border-stone-200 text-sm font-semibold text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition-colors"
            >مسح</button>
            <button
              @click="submitOrder"
              :disabled="!hasItems || submitting"
              class="py-2.5 rounded-xl bg-amber-600 text-white text-sm font-bold hover:bg-amber-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-1.5"
            >
              <div v-if="submitting" class="animate-spin w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
              <span>{{ submitting ? 'جاري...' : 'تأكيد الطلب' }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Quick Qty Pad Modal ── -->
    <Transition name="modal">
      <div
        v-if="qtyPadItem"
        class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
        @click.self="qtyPadItem = null"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-64 overflow-hidden">
          <!-- Header -->
          <div class="bg-amber-600 text-white px-4 py-3 text-center">
            <div class="font-bold">{{ qtyPadItem.name_ar || qtyPadItem.name }}</div>
            <div class="text-xs text-amber-100 mt-0.5">{{ qtyPadItem.price }} ج × {{ qtyPadValue }} = {{ qtyPadItem.price * (parseInt(qtyPadValue) || 1) }} ج</div>
          </div>

          <!-- Display -->
          <div class="bg-gray-50 px-4 py-3 text-center">
            <div class="text-4xl font-black text-gray-900">{{ qtyPadValue }}</div>
          </div>

          <!-- Number pad -->
          <div class="grid grid-cols-3 gap-px bg-stone-200 border-t border-stone-200">
            <button
              v-for="key in ['7','8','9','4','5','6','1','2','3','C','0','⌫']"
              :key="key"
              @click="qtyPadPress(key)"
              :class="[
                'py-4 text-lg font-bold bg-white hover:bg-amber-50 transition-colors',
                key === 'C' ? 'text-red-500' : key === '⌫' ? 'text-gray-500' : 'text-gray-900',
              ]"
            >{{ key }}</button>
          </div>

          <!-- Confirm -->
          <button
            @click="confirmQtyPad"
            class="w-full py-4 bg-amber-600 text-white font-bold text-lg hover:bg-amber-700 transition-colors"
          >إضافة {{ qtyPadValue }} قطعة</button>
        </div>
      </div>
    </Transition>

    <!-- ── Note Editor Modal ── -->
    <Transition name="modal">
      <div
        v-if="editingNoteId !== null"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="editingNoteId = null"
      >
        <div class="bg-white rounded-2xl p-5 w-full max-w-sm shadow-2xl">
          <h3 class="font-bold text-gray-900 mb-1">ملاحظة على الصنف</h3>
          <p class="text-xs text-gray-400 mb-3">مثال: بدون سكر، ثلج كتير، ساخن جداً</p>
          <textarea
            v-model="tempNote"
            rows="3"
            placeholder="اكتب الملاحظة هنا..."
            class="w-full border border-stone-300 rounded-xl p-3 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none"
          />
          <div class="flex gap-2 mt-3">
            <button
              @click="editingNoteId = null"
              class="flex-1 py-2.5 border-2 border-stone-200 rounded-xl text-sm font-semibold text-gray-600 hover:bg-gray-50"
            >إلغاء</button>
            <button
              @click="saveNote"
              class="flex-1 py-2.5 bg-amber-600 text-white rounded-xl text-sm font-bold hover:bg-amber-700"
            >حفظ</button>
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
