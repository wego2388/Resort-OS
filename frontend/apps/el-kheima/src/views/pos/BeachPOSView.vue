<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import axios from 'axios'

interface BeachInventory {
  adult_capacity: number
  child_capacity: number
  adult_sold: number
  child_sold: number
  adult_price: number
  child_price: number
  resident_price: number
  towel_price: number
  surge_active: boolean
  surge_multiplier: number
}

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const inventory = ref<BeachInventory | null>(null)
const loading = ref(false)
const submitting = ref(false)
const successMsg = ref('')
const errorMsg = ref('')

// Cart state
const adultQty = ref(0)
const childQty = ref(0)
const residentQty = ref(0)
const towelQty = ref(0)
const paymentMethod = ref<'cash' | 'card' | 'wallet'>('cash')

// Ref for auto-focus after sale
const firstButtonRef = ref<HTMLButtonElement | null>(null)

const prices = computed(() => {
  if (!inventory.value) return { adult: 0, child: 0, resident: 0, towel: 0 }
  const m = inventory.value.surge_active ? inventory.value.surge_multiplier : 1
  return {
    adult:    Math.round(inventory.value.adult_price * m),
    child:    Math.round(inventory.value.child_price * m),
    resident: Math.round(inventory.value.resident_price * m),
    towel:    inventory.value.towel_price, // towels no surge
  }
})

const total = computed(() =>
  adultQty.value * prices.value.adult +
  childQty.value * prices.value.child +
  residentQty.value * prices.value.resident +
  towelQty.value * prices.value.towel
)

const hasItems = computed(() => total.value > 0)

const availableAdults = computed(() =>
  (inventory.value?.adult_capacity ?? 0) - (inventory.value?.adult_sold ?? 0)
)
const availableChildren = computed(() =>
  (inventory.value?.child_capacity ?? 0) - (inventory.value?.child_sold ?? 0)
)
const occupancyPct = computed(() => {
  if (!inventory.value || !inventory.value.adult_capacity) return 0
  return Math.round((inventory.value.adult_sold / inventory.value.adult_capacity) * 100)
})

function adjust(type: 'adult' | 'child' | 'resident' | 'towel', delta: number) {
  if (type === 'adult')    adultQty.value    = Math.max(0, adultQty.value + delta)
  if (type === 'child')    childQty.value    = Math.max(0, childQty.value + delta)
  if (type === 'resident') residentQty.value = Math.max(0, residentQty.value + delta)
  if (type === 'towel')    towelQty.value    = Math.max(0, towelQty.value + delta)
}

function clearCart() {
  adultQty.value = 0
  childQty.value = 0
  residentQty.value = 0
  towelQty.value = 0
}

async function fetchInventory() {
  loading.value = true
  try {
    const { data } = await axios.get(`/api/v1/beach/inventory/${branchId}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
    })
    inventory.value = data
  } catch (e) {
    console.error('Failed to fetch beach inventory', e)
  } finally {
    loading.value = false
  }
}

async function completeSale() {
  if (!hasItems.value || submitting.value) return
  submitting.value = true
  try {
    const entries: { type: string; quantity: number; unit_price: number }[] = []
    if (adultQty.value > 0)    entries.push({ type: 'adult',    quantity: adultQty.value,    unit_price: prices.value.adult })
    if (childQty.value > 0)    entries.push({ type: 'child',    quantity: childQty.value,    unit_price: prices.value.child })
    if (residentQty.value > 0) entries.push({ type: 'resident', quantity: residentQty.value, unit_price: prices.value.resident })

    const authHeaders = { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
    const { data } = await axios.post(
      '/api/v1/beach/sell',
      {
        branch_id: branchId,
        entries,
        towels: towelQty.value,
        towel_price: prices.value.towel,
        payment_method: paymentMethod.value,
      },
      { headers: authHeaders }
    )

    // Print ticket PDF
    const txId = data.transaction_id ?? data.id
    if (txId) {
      try {
        const ticketRes = await axios.get(`/api/v1/beach/transactions/${txId}/ticket`, {
          headers: authHeaders,
          responseType: 'blob',
        })
        const url = URL.createObjectURL(ticketRes.data)
        const w = window.open(url, '_blank')
        if (!w) {
          const a = document.createElement('a')
          a.href = url
          a.download = `ticket-${txId}.pdf`
          a.click()
        }
      } catch {
        // ticket printing is optional — don't block success
      }
    }

    clearCart()
    await fetchInventory()
    successMsg.value = 'تم البيع بنجاح ✓'
    setTimeout(() => { successMsg.value = '' }, 3000)

    // Auto-focus back to first price button
    await nextTick()
    firstButtonRef.value?.focus()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail ?? 'حدث خطأ في البيع'
    setTimeout(() => { errorMsg.value = '' }, 4000)
  } finally {
    submitting.value = false
  }
}

let refreshInterval: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  fetchInventory()
  refreshInterval = setInterval(fetchInventory, 30_000)
})

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval)
})
</script>

<template>
  <div class="p-4 h-full" dir="rtl">
    <!-- Loading splash -->
    <div v-if="loading && !inventory" class="flex items-center justify-center h-64">
      <div class="animate-spin w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full" />
    </div>

    <!-- No connection -->
    <div v-else-if="!inventory && !loading" class="flex flex-col items-center justify-center h-64 text-gray-500 gap-3">
      <div class="text-5xl">⚠️</div>
      <p class="font-medium">لا يمكن الاتصال بالسيرفر</p>
      <button @click="fetchInventory" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
        إعادة المحاولة
      </button>
    </div>

    <!-- Main content -->
    <div v-else-if="inventory" class="grid grid-cols-1 lg:grid-cols-2 gap-4 h-full">

      <!-- ═══ LEFT: Status + Price Cards ═══ -->
      <div class="space-y-4 overflow-y-auto">

        <!-- Beach status card -->
        <div class="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
          <div class="flex items-center justify-between mb-3">
            <h2 class="font-bold text-gray-900 text-base">حالة الشاطئ</h2>
            <div class="flex items-center gap-2">
              <span
                v-if="inventory.surge_active"
                class="px-2.5 py-1 bg-amber-100 text-amber-700 text-xs font-bold rounded-full animate-pulse"
              >🌊 SURGE ×{{ inventory.surge_multiplier }}</span>
              <button
                @click="fetchInventory"
                :class="['text-gray-400 hover:text-blue-600 transition-colors', loading ? 'animate-spin' : '']"
                title="تحديث"
              >↻</button>
            </div>
          </div>

          <!-- Occupancy bar -->
          <div class="mb-3">
            <div class="flex justify-between text-sm text-gray-600 mb-1">
              <span>الإشغال</span>
              <span class="font-medium">
                {{ inventory.adult_sold }} / {{ inventory.adult_capacity }}
                <span class="text-xs text-gray-400">({{ occupancyPct }}%)</span>
              </span>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-3">
              <div
                class="h-3 rounded-full transition-all duration-500"
                :class="occupancyPct >= 90 ? 'bg-red-500' : occupancyPct >= 70 ? 'bg-amber-500' : 'bg-green-500'"
                :style="{ width: Math.min(occupancyPct, 100) + '%' }"
              />
            </div>
          </div>

          <!-- Available slots -->
          <div class="grid grid-cols-2 gap-2">
            <div class="bg-blue-50 rounded-lg p-2.5 text-center">
              <div class="text-2xl font-black text-blue-700">{{ availableAdults }}</div>
              <div class="text-xs text-blue-600 mt-0.5">متاح (بالغ)</div>
            </div>
            <div class="bg-green-50 rounded-lg p-2.5 text-center">
              <div class="text-2xl font-black text-green-700">{{ availableChildren }}</div>
              <div class="text-xs text-green-600 mt-0.5">متاح (طفل)</div>
            </div>
          </div>
        </div>

        <!-- Price cards grid -->
        <div class="grid grid-cols-2 gap-3">

          <!-- Adult -->
          <div class="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
            <div class="text-center mb-3">
              <div class="text-3xl mb-1">👤</div>
              <div class="font-bold text-gray-900 text-sm">بالغ</div>
              <div class="text-2xl font-black text-blue-700 mt-1">
                {{ prices.adult }}<span class="text-xs font-normal text-gray-500 mr-1">ج</span>
              </div>
              <div v-if="inventory.surge_active" class="text-xs text-amber-600 mt-0.5">
                (أصل: {{ inventory.adult_price }} ج)
              </div>
            </div>
            <div class="flex items-center justify-center gap-3">
              <button
                @click="adjust('adult', -1)"
                :disabled="adultQty === 0"
                class="w-9 h-9 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40 font-bold text-lg transition-colors leading-none"
              >−</button>
              <span class="text-xl font-black w-8 text-center text-gray-900">{{ adultQty }}</span>
              <button
                ref="firstButtonRef"
                @click="adjust('adult', 1)"
                class="w-9 h-9 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-bold text-lg transition-colors leading-none"
              >+</button>
            </div>
          </div>

          <!-- Child -->
          <div class="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
            <div class="text-center mb-3">
              <div class="text-3xl mb-1">🧒</div>
              <div class="font-bold text-gray-900 text-sm">طفل</div>
              <div class="text-2xl font-black text-green-700 mt-1">
                {{ prices.child }}<span class="text-xs font-normal text-gray-500 mr-1">ج</span>
              </div>
              <div v-if="inventory.surge_active" class="text-xs text-amber-600 mt-0.5">
                (أصل: {{ inventory.child_price }} ج)
              </div>
            </div>
            <div class="flex items-center justify-center gap-3">
              <button
                @click="adjust('child', -1)"
                :disabled="childQty === 0"
                class="w-9 h-9 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40 font-bold text-lg transition-colors leading-none"
              >−</button>
              <span class="text-xl font-black w-8 text-center text-gray-900">{{ childQty }}</span>
              <button
                @click="adjust('child', 1)"
                class="w-9 h-9 rounded-lg bg-green-600 hover:bg-green-700 text-white font-bold text-lg transition-colors leading-none"
              >+</button>
            </div>
          </div>

          <!-- Resident -->
          <div class="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
            <div class="text-center mb-3">
              <div class="text-3xl mb-1">🏠</div>
              <div class="font-bold text-gray-900 text-sm">مقيم</div>
              <div class="text-2xl font-black text-purple-700 mt-1">
                {{ prices.resident }}<span class="text-xs font-normal text-gray-500 mr-1">ج</span>
              </div>
              <div v-if="inventory.surge_active" class="text-xs text-amber-600 mt-0.5">
                (أصل: {{ inventory.resident_price }} ج)
              </div>
            </div>
            <div class="flex items-center justify-center gap-3">
              <button
                @click="adjust('resident', -1)"
                :disabled="residentQty === 0"
                class="w-9 h-9 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40 font-bold text-lg transition-colors leading-none"
              >−</button>
              <span class="text-xl font-black w-8 text-center text-gray-900">{{ residentQty }}</span>
              <button
                @click="adjust('resident', 1)"
                class="w-9 h-9 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-bold text-lg transition-colors leading-none"
              >+</button>
            </div>
          </div>

          <!-- Towel -->
          <div class="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
            <div class="text-center mb-3">
              <div class="text-3xl mb-1">🏊</div>
              <div class="font-bold text-gray-900 text-sm">فوطة</div>
              <div class="text-2xl font-black text-amber-700 mt-1">
                {{ prices.towel }}<span class="text-xs font-normal text-gray-500 mr-1">ج</span>
              </div>
              <div class="text-xs text-gray-400 mt-0.5">بدون surge</div>
            </div>
            <div class="flex items-center justify-center gap-3">
              <button
                @click="adjust('towel', -1)"
                :disabled="towelQty === 0"
                class="w-9 h-9 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40 font-bold text-lg transition-colors leading-none"
              >−</button>
              <span class="text-xl font-black w-8 text-center text-gray-900">{{ towelQty }}</span>
              <button
                @click="adjust('towel', 1)"
                class="w-9 h-9 rounded-lg bg-amber-500 hover:bg-amber-600 text-white font-bold text-lg transition-colors leading-none"
              >+</button>
            </div>
          </div>

        </div>
      </div>

      <!-- ═══ RIGHT: Order Summary ═══ -->
      <div class="bg-white rounded-xl border border-stone-200 shadow-sm flex flex-col min-h-[480px]">

        <!-- Header -->
        <div class="p-4 border-b border-stone-100">
          <h2 class="font-bold text-gray-900">ملخص الطلب</h2>
        </div>

        <!-- Cart items list -->
        <div class="flex-1 p-4 space-y-2 overflow-y-auto">
          <div
            v-if="adultQty > 0"
            class="flex items-center justify-between py-2.5 border-b border-dashed border-stone-200"
          >
            <span class="text-gray-700">👤 بالغ × {{ adultQty }}</span>
            <span class="font-semibold text-gray-900">{{ adultQty * prices.adult }} ج</span>
          </div>
          <div
            v-if="childQty > 0"
            class="flex items-center justify-between py-2.5 border-b border-dashed border-stone-200"
          >
            <span class="text-gray-700">🧒 طفل × {{ childQty }}</span>
            <span class="font-semibold text-gray-900">{{ childQty * prices.child }} ج</span>
          </div>
          <div
            v-if="residentQty > 0"
            class="flex items-center justify-between py-2.5 border-b border-dashed border-stone-200"
          >
            <span class="text-gray-700">🏠 مقيم × {{ residentQty }}</span>
            <span class="font-semibold text-gray-900">{{ residentQty * prices.resident }} ج</span>
          </div>
          <div
            v-if="towelQty > 0"
            class="flex items-center justify-between py-2.5 border-b border-dashed border-stone-200"
          >
            <span class="text-gray-700">🏊 فوطة × {{ towelQty }}</span>
            <span class="font-semibold text-gray-900">{{ towelQty * prices.towel }} ج</span>
          </div>

          <!-- Empty state -->
          <div v-if="!hasItems" class="flex flex-col items-center justify-center py-12 text-gray-400">
            <div class="text-5xl mb-3">🏖️</div>
            <p class="text-sm">لم يتم اختيار أي صنف</p>
            <p class="text-xs mt-1">اضغط + على أي سعر للإضافة</p>
          </div>
        </div>

        <!-- Footer: total + payment + buttons -->
        <div class="p-4 border-t border-stone-200 space-y-3">

          <!-- Total -->
          <div class="flex items-center justify-between">
            <span class="text-lg font-bold text-gray-900">المجموع</span>
            <span class="text-2xl font-black text-blue-700">{{ total }} <span class="text-sm font-normal">ج</span></span>
          </div>

          <!-- Payment method selector -->
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="m in [
                { val: 'cash',   label: 'كاش',   icon: '💵' },
                { val: 'card',   label: 'كارت',  icon: '💳' },
                { val: 'wallet', label: 'محفظة', icon: '📱' },
              ]"
              :key="m.val"
              @click="paymentMethod = (m.val as 'cash' | 'card' | 'wallet')"
              :class="[
                'py-2 rounded-lg text-sm font-medium transition-all border-2',
                paymentMethod === m.val
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-stone-200 text-gray-600 hover:border-blue-300 hover:bg-gray-50',
              ]"
            >{{ m.icon }} {{ m.label }}</button>
          </div>

          <!-- Feedback messages -->
          <transition name="fade">
            <div
              v-if="successMsg"
              class="bg-green-100 text-green-700 px-3 py-2 rounded-lg text-sm font-medium text-center"
            >{{ successMsg }}</div>
          </transition>
          <transition name="fade">
            <div
              v-if="errorMsg"
              class="bg-red-100 text-red-700 px-3 py-2 rounded-lg text-sm font-medium text-center"
            >{{ errorMsg }}</div>
          </transition>

          <!-- Action buttons -->
          <div class="grid grid-cols-2 gap-2">
            <button
              @click="clearCart"
              :disabled="!hasItems"
              class="py-3 rounded-xl border-2 border-stone-200 text-gray-600 font-semibold hover:bg-gray-50 disabled:opacity-40 transition-colors"
            >مسح الطلب</button>
            <button
              @click="completeSale"
              :disabled="!hasItems || submitting"
              class="py-3 rounded-xl bg-blue-700 text-white font-bold hover:bg-blue-800 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
            >
              <div
                v-if="submitting"
                class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"
              />
              <span>{{ submitting ? 'جاري...' : 'إتمام البيع' }}</span>
            </button>
          </div>

        </div>
      </div>

    </div>
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
</style>
