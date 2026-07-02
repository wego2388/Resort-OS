<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useOfflineQueue } from '@resort-os/core/composables'

const props = defineProps<{ tableId?: string }>()

const router = useRouter()
const { isOnline, pendingCount, submitOrder: submitOrderOnlineOrQueue } = useOfflineQueue()

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const authHeaders = computed(() => ({ Authorization: `Bearer ${localStorage.getItem('access_token')}` }))
const tableId = computed(() => (props.tableId ? parseInt(props.tableId) : null))

interface Table    { id: number; table_number: string; status: string }
interface Category { id: number; name: string; name_ar: string }
interface MenuItem { id: number; name: string; name_ar: string; price: number; is_available: boolean; category_id: number | null }
interface CartItem { menu_item_id: number; name: string; name_ar: string; price: number; quantity: number; notes: string }

const table             = ref<Table | null>(null)
const categories        = ref<Category[]>([])
const menuItems         = ref<MenuItem[]>([])
const selectedCategoryId = ref<number | null>(null)
const cart              = ref<CartItem[]>([])
const covers            = ref(1)
const loading           = ref(false)
const submitting        = ref(false)
const successMsg        = ref('')
const errorMsg          = ref('')

const filteredItems = computed(() =>
  selectedCategoryId.value !== null
    ? menuItems.value.filter(i => i.category_id === selectedCategoryId.value && i.is_available)
    : menuItems.value.filter(i => i.is_available)
)

const total    = computed(() => cart.value.reduce((s, i) => s + i.price * i.quantity, 0))
const hasItems = computed(() => cart.value.length > 0)

function addToCart(item: MenuItem) {
  const existing = cart.value.find(c => c.menu_item_id === item.id)
  if (existing) { existing.quantity++; return }
  cart.value.push({ menu_item_id: item.id, name: item.name, name_ar: item.name_ar, price: item.price, quantity: 1, notes: '' })
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

async function loadData() {
  loading.value = true
  try {
    const requests = [
      axios.get('/api/v1/restaurant/menu/categories', { headers: authHeaders.value, params: { branch_id: branchId } }),
      axios.get('/api/v1/restaurant/menu/items',      { headers: authHeaders.value, params: { branch_id: branchId } }),
    ]
    if (tableId.value) {
      requests.push(axios.get('/api/v1/restaurant/tables', { headers: authHeaders.value, params: { branch_id: branchId } }))
    }
    const [catsRes, itemsRes, tablesRes] = await Promise.all(requests)

    categories.value = catsRes.data.categories ?? catsRes.data.items ?? catsRes.data
    menuItems.value  = itemsRes.data.items ?? itemsRes.data
    if (categories.value.length) selectedCategoryId.value = categories.value[0].id

    if (tablesRes) {
      const tables: Table[] = tablesRes.data.tables ?? tablesRes.data.items ?? tablesRes.data
      table.value = tables.find(t => t.id === tableId.value) ?? null
    }
  } catch (e) {
    console.error('Failed to load menu', e)
  } finally {
    loading.value = false
  }
}

async function sendToKitchen() {
  if (!hasItems.value || submitting.value) return
  submitting.value = true
  try {
    const payload = {
      table_id:     tableId.value,
      order_type:   tableId.value ? 'dine_in' : 'takeaway',
      guests_count: covers.value,
      items: cart.value.map(i => ({
        menu_item_id: i.menu_item_id,
        quantity:     i.quantity,
        notes:        i.notes || undefined,
      })),
    }

    const data = await submitOrderOnlineOrQueue(branchId, payload)

    if (data === null) {
      successMsg.value = '📥 الطلب محفوظ محلياً — هيتبعت للمطبخ أول ما النت يرجع'
    } else {
      successMsg.value = 'تم إرسال الطلب للمطبخ ✓'
    }
    cart.value = []
    covers.value = 1
    setTimeout(() => {
      successMsg.value = ''
      router.push('/waiter/tables')
    }, 1500)
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

    <div v-if="!isOnline" class="bg-amber-500 text-white text-xs font-bold px-4 py-1.5 flex items-center justify-center gap-2 flex-shrink-0">
      <span>⚠️ وضع offline — الطلب هيتحفظ محلياً وهيتبعت أول ما النت يرجع</span>
      <span v-if="pendingCount > 0" class="bg-amber-700 px-2 py-0.5 rounded-full">{{ pendingCount }} في الانتظار</span>
    </div>

    <div class="bg-white border-b border-stone-200 px-4 py-3 flex flex-wrap gap-3 items-center shadow-sm flex-shrink-0">
      <button @click="router.push('/waiter/tables')" class="text-blue-700 font-bold text-sm px-2 py-1.5 hover:bg-blue-50 rounded-lg">
        ← الطاولات
      </button>

      <div class="font-bold text-gray-900">
        {{ table ? `طاولة ${table.table_number}` : 'Takeaway' }}
      </div>

      <div v-if="tableId" class="flex items-center gap-2">
        <label class="text-sm font-semibold text-gray-700">الغطاءات:</label>
        <div class="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5">
          <button @click="covers = Math.max(1, covers - 1)" class="w-8 h-8 rounded-md bg-white text-base font-bold shadow-sm">−</button>
          <span class="w-8 text-center font-bold">{{ covers }}</span>
          <button @click="covers++" class="w-8 h-8 rounded-md bg-white text-base font-bold shadow-sm">+</button>
        </div>
      </div>

      <div class="flex gap-1.5 flex-wrap mr-auto">
        <button
          @click="selectedCategoryId = null"
          :class="['px-3 py-2 rounded-lg text-sm font-medium transition-colors', selectedCategoryId === null ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600']"
        >الكل</button>
        <button
          v-for="cat in categories" :key="cat.id"
          @click="selectedCategoryId = cat.id"
          :class="['px-3 py-2 rounded-lg text-sm font-medium transition-colors', selectedCategoryId === cat.id ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600']"
        >{{ cat.name_ar || cat.name }}</button>
      </div>
    </div>

    <div class="flex flex-1 overflow-hidden">

      <div class="flex-1 overflow-y-auto p-4 bg-stone-50">
        <div v-if="loading" class="flex items-center justify-center h-40">
          <div class="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
        </div>

        <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          <button
            v-for="item in filteredItems" :key="item.id"
            @click="addToCart(item)"
            class="bg-white rounded-xl border border-stone-200 p-4 text-right hover:border-blue-400 active:scale-95 transition-all flex flex-col justify-between min-h-[96px] shadow-sm"
          >
            <div class="font-semibold text-gray-900 text-sm leading-tight mb-2">{{ item.name_ar || item.name }}</div>
            <div class="text-lg font-black text-blue-700">{{ item.price }}<span class="text-xs font-normal text-gray-400 mr-0.5">ج</span></div>
          </button>
        </div>

        <div v-if="!loading && filteredItems.length === 0" class="flex flex-col items-center justify-center py-16 text-gray-400">
          <div class="text-4xl mb-2">🍽️</div>
          <p class="text-sm">لا توجد أصناف في هذه الفئة</p>
        </div>
      </div>

      <div class="w-80 bg-white border-r border-stone-200 flex flex-col flex-shrink-0 shadow-lg">
        <div class="p-4 border-b border-stone-100 bg-gray-50 font-bold text-gray-900">
          الطلب الحالي ({{ cart.reduce((s, i) => s + i.quantity, 0) }})
        </div>

        <div class="flex-1 overflow-y-auto p-3 space-y-2">
          <div v-if="cart.length === 0" class="flex flex-col items-center justify-center py-10 text-gray-400">
            <div class="text-3xl mb-2">🛒</div>
            <p class="text-sm">اختر أصناف من القائمة</p>
          </div>

          <div v-for="item in cart" :key="item.menu_item_id" class="bg-stone-50 rounded-lg p-3 border border-stone-200">
            <div class="flex items-start justify-between mb-2 gap-1">
              <span class="text-sm font-semibold text-gray-900 leading-tight flex-1">{{ item.name_ar || item.name }}</span>
              <button @click="removeFromCart(item.menu_item_id)" class="text-red-400 hover:text-red-600 text-lg leading-none w-6 h-6 flex items-center justify-center rounded hover:bg-red-50">×</button>
            </div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5">
                <button @click="adjustQty(item.menu_item_id, -1)" class="w-8 h-8 rounded bg-gray-200 text-base font-bold">−</button>
                <span class="text-sm font-bold w-6 text-center">{{ item.quantity }}</span>
                <button @click="adjustQty(item.menu_item_id, 1)" class="w-8 h-8 rounded bg-blue-100 text-blue-700 text-base font-bold">+</button>
              </div>
              <span class="text-sm font-bold text-blue-700">{{ item.price * item.quantity }} ج</span>
            </div>
          </div>
        </div>

        <div class="border-t border-stone-200 p-3 space-y-3 bg-white">
          <div class="flex justify-between items-center">
            <span class="text-base font-bold text-gray-900">المجموع</span>
            <span class="text-xl font-black text-blue-700">{{ total }} ج</span>
          </div>

          <transition name="fade">
            <div v-if="successMsg" class="bg-green-100 text-green-700 text-xs px-2 py-2 rounded-lg text-center font-medium">{{ successMsg }}</div>
          </transition>
          <transition name="fade">
            <div v-if="errorMsg" class="bg-red-100 text-red-700 text-xs px-2 py-2 rounded-lg text-center font-medium">{{ errorMsg }}</div>
          </transition>

          <button
            @click="sendToKitchen"
            :disabled="!hasItems || submitting"
            class="w-full py-4 bg-blue-700 text-white rounded-xl font-bold text-base hover:bg-blue-800 disabled:opacity-40 active:scale-[0.98] transition-all"
          >
            {{ submitting ? 'جاري الإرسال...' : '🍳 إرسال للمطبخ' }}
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
