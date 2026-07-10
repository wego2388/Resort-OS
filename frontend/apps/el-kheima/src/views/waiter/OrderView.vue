<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@resort-os/core'
import { useOfflineQueue } from '@resort-os/core/composables'
import { useToast } from '@resort-os/ui'
import ExtrasSelectionModal from '../../components/ExtrasSelectionModal.vue'

const props = defineProps<{ tableId?: string }>()

const router = useRouter()
const toast = useToast()
const { isOnline, pendingCount, submitOrder: submitOrderOnlineOrQueue } = useOfflineQueue()

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const tableId = computed(() => (props.tableId ? parseInt(props.tableId) : null))

interface ExtraOption { id: number; name: string; name_ar?: string | null; price_addition: number | string; is_available: boolean }
interface ExtraGroup  { id: number; name: string; name_ar?: string | null; min_select: number; max_select: number; options: ExtraOption[] }
interface Table    { id: number; table_number: string; status: string }
interface Category { id: number; name: string; name_ar: string }
interface MenuItem {
  id: number; name: string; name_ar: string; price: number; is_available: boolean
  category_id: number | null; extra_groups: ExtraGroup[]
}
interface CartItem {
  key: string; menu_item_id: number; name: string; name_ar: string; price: number
  quantity: number; notes: string; extra_ids: number[]; extras: ExtraOption[]
}

const table             = ref<Table | null>(null)
const categories        = ref<Category[]>([])
const menuItems         = ref<MenuItem[]>([])
const selectedCategoryId = ref<number | null>(null)
const cart              = ref<CartItem[]>([])
const covers            = ref(1)
const loading           = ref(false)
const submitting        = ref(false)
const holding           = ref(false)
const successMsg        = ref('')
const errorMsg          = ref('')

// Extras selection modal — opened instead of a direct add() when the tapped
// item has extra_groups (checked against MenuItemRead.extra_groups).
const extrasModalItem = ref<MenuItem | null>(null)

const filteredItems = computed(() =>
  selectedCategoryId.value !== null
    ? menuItems.value.filter(i => i.category_id === selectedCategoryId.value && i.is_available)
    : menuItems.value.filter(i => i.is_available)
)

function lineUnitPrice(item: CartItem): number {
  return item.price + item.extras.reduce((s, e) => s + Number(e.price_addition), 0)
}

const total    = computed(() => cart.value.reduce((s, i) => s + lineUnitPrice(i) * i.quantity, 0))
const hasItems = computed(() => cart.value.length > 0)

function onMenuItemTap(item: MenuItem) {
  if (item.extra_groups && item.extra_groups.length > 0) {
    extrasModalItem.value = item
  } else {
    addToCart(item, [], [])
  }
}

function addToCart(item: MenuItem, extraIds: number[], extras: ExtraOption[]) {
  const key = `${item.id}:${[...extraIds].sort((a, b) => a - b).join(',')}`
  const existing = cart.value.find(c => c.key === key)
  if (existing) { existing.quantity++; return }
  cart.value.push({
    key, menu_item_id: item.id, name: item.name, name_ar: item.name_ar,
    price: item.price, quantity: 1, notes: '', extra_ids: extraIds, extras,
  })
}

function onExtrasConfirm(extraIds: number[], extras: ExtraOption[]) {
  if (extrasModalItem.value) addToCart(extrasModalItem.value, extraIds, extras)
  extrasModalItem.value = null
}

function removeFromCart(key: string) {
  cart.value = cart.value.filter(c => c.key !== key)
}

function adjustQty(key: string, delta: number) {
  const item = cart.value.find(c => c.key === key)
  if (!item) return
  item.quantity = Math.max(0, item.quantity + delta)
  if (item.quantity === 0) removeFromCart(key)
}

async function loadData() {
  loading.value = true
  try {
    const requests = [
      api.get('/api/v1/restaurant/menu/categories', { params: { branch_id: branchId } }),
      api.get('/api/v1/restaurant/menu/items',      { params: { branch_id: branchId } }),
    ]
    if (tableId.value) {
      requests.push(api.get('/api/v1/restaurant/tables', { params: { branch_id: branchId } }))
    }
    const [catsRes, itemsRes, tablesRes] = await Promise.all(requests)

    categories.value = catsRes.data.categories ?? catsRes.data.items ?? catsRes.data
    menuItems.value  = itemsRes.data.items ?? itemsRes.data
    if (categories.value.length) selectedCategoryId.value = categories.value[0].id

    if (tablesRes) {
      const tables: Table[] = tablesRes.data.tables ?? tablesRes.data.items ?? tablesRes.data
      table.value = tables.find(t => t.id === tableId.value) ?? null
    }
  } catch {
    // من غير إشعار الجرسون كان بيشوف قائمة فاضية من غير أي تفسير
    toast.error('تعذّر تحميل قائمة الطعام — تأكد من الاتصال وحاول تاني')
  } finally {
    loading.value = false
  }
}

function buildOrderPayload() {
  return {
    table_id:     tableId.value,
    order_type:   tableId.value ? 'dine_in' : 'takeaway',
    guests_count: covers.value,
    items: cart.value.map(i => ({
      menu_item_id: i.menu_item_id,
      quantity:     i.quantity,
      notes:        i.notes || undefined,
      extra_ids:    i.extra_ids,
    })),
  }
}

async function sendToKitchen() {
  if (!hasItems.value || submitting.value) return
  submitting.value = true
  try {
    const payload = buildOrderPayload()
    const data = await submitOrderOnlineOrQueue(branchId, payload)

    if (data === null) {
      // Queued offline — /restaurant/orders/sync سيُنشئ الطلب ويرسله مباشرةً
      // للمطبخ (in_kitchen transition) أوتوماتيكياً بعد عودة الاتصال.
      successMsg.value = '📥 الطلب محفوظ محلياً — هيتبعت للمطبخ أول ما النت يرجع'
    } else {
      // Creating the order alone leaves it in status "open" — a
      // KitchenTicket is only ever created by the open→in_kitchen PATCH
      // (see services.update_order_status). Without this call the order
      // existed but the kitchen never saw it — a real pre-existing bug.
      await api.patch(
        `/api/v1/restaurant/orders/${data.id}/status`,
        { status: 'in_kitchen' },
        {},
      )
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

/** Hold order (احتفظ بالطلب) — POST /restaurant/orders/hold. Deliberately
 * NOT routed through useOfflineQueue: the offline sync contract
 * (OrderSyncRequest/sync_offline_order) has no "hold" flag at all, so a
 * queued "hold" would silently become a normal sent order once connectivity
 * returns — worse than just telling the waiter to wait for a connection. */
async function holdOrder() {
  if (!hasItems.value || holding.value) return
  holding.value = true
  try {
    await api.post(
      `/api/v1/restaurant/orders/hold?branch_id=${branchId}`,
      buildOrderPayload(),
      {},
    )
    successMsg.value = 'اتحفظ الطلب — هيلاقيه في "الطلبات المعلّقة" ✓'
    cart.value = []
    covers.value = 1
    setTimeout(() => {
      successMsg.value = ''
      router.push('/waiter/tables')
    }, 1500)
  } catch (e: any) {
    if (!isOnline.value || e?.code === 'ERR_NETWORK') {
      errorMsg.value = 'الاحتفاظ بالطلب محتاج اتصال بالإنترنت'
    } else {
      errorMsg.value = e?.response?.data?.detail ?? 'فشل الاحتفاظ بالطلب'
    }
    setTimeout(() => { errorMsg.value = '' }, 4000)
  } finally {
    holding.value = false
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
            @click="onMenuItemTap(item)"
            class="relative bg-white rounded-xl border border-stone-200 p-4 text-right hover:border-blue-400 active:scale-95 transition-all flex flex-col justify-between min-h-[96px] shadow-sm"
          >
            <span v-if="item.extra_groups?.length" class="absolute top-2 left-2 text-[10px] bg-blue-100 text-blue-700 rounded-full px-1.5 py-0.5 font-bold">+إضافات</span>
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

          <div v-for="item in cart" :key="item.key" class="bg-stone-50 rounded-lg p-3 border border-stone-200">
            <div class="flex items-start justify-between mb-2 gap-1">
              <span class="text-sm font-semibold text-gray-900 leading-tight flex-1">{{ item.name_ar || item.name }}</span>
              <button @click="removeFromCart(item.key)" class="text-red-400 hover:text-red-600 text-lg leading-none w-6 h-6 flex items-center justify-center rounded hover:bg-red-50">×</button>
            </div>
            <div v-if="item.extras.length" class="text-xs text-gray-500 mb-2">
              {{ item.extras.map(e => `${e.name_ar || e.name}${Number(e.price_addition) > 0 ? ' (+' + e.price_addition + 'ج)' : ''}`).join('، ') }}
            </div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5">
                <button @click="adjustQty(item.key, -1)" class="w-8 h-8 rounded bg-gray-200 text-base font-bold">−</button>
                <span class="text-sm font-bold w-6 text-center">{{ item.quantity }}</span>
                <button @click="adjustQty(item.key, 1)" class="w-8 h-8 rounded bg-blue-100 text-blue-700 text-base font-bold">+</button>
              </div>
              <span class="text-sm font-bold text-blue-700">{{ lineUnitPrice(item) * item.quantity }} ج</span>
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

          <div class="grid grid-cols-2 gap-2">
            <button
              @click="holdOrder"
              :disabled="!hasItems || submitting || holding"
              class="py-3.5 rounded-xl border-2 border-amber-400 text-amber-700 font-bold text-sm hover:bg-amber-50 disabled:opacity-40 active:scale-[0.98] transition-all"
            >
              {{ holding ? 'جاري الحفظ...' : '⏸️ احتفظ بالطلب' }}
            </button>
            <button
              @click="sendToKitchen"
              :disabled="!hasItems || submitting || holding"
              class="py-3.5 bg-blue-700 text-white rounded-xl font-bold text-sm hover:bg-blue-800 disabled:opacity-40 active:scale-[0.98] transition-all"
            >
              {{ submitting ? 'جاري الإرسال...' : '🍳 إرسال للمطبخ' }}
            </button>
          </div>
        </div>
      </div>

    </div>

    <ExtrasSelectionModal
      :item="extrasModalItem"
      @confirm="onExtrasConfirm"
      @close="extrasModalItem = null"
    />
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
