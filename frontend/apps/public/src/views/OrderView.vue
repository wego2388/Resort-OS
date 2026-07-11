<script setup lang="ts">
/**
 * OrderView — قائمة الطعام/الكافيه للضيف عبر QR (طاولة أو شمسية).
 *
 * دمج frontend/apps/qr → apps/public (2026-07-06): كان فيه تطبيق مستقل
 * بالكامل (apps/qr، بورت 3005) لسكانر الـ QR بس، رغم إنه زي apps/public
 * تمامًا ضيف بدون تسجيل دخول — الدمج قلل تطبيق كامل (build/deploy/nginx)
 * من غير أي فايدة معمارية حقيقية (لسه مفيش أكواد QR مطبوعة فعليًا وقت الدمج).
 *
 * الـ outlet (مطعم/كافيه) والرقم (طاولة أو شمسية) بييجوا من الـ QR نفسه:
 *   /order/restaurant/5   → قائمة المطعم، طاولة 5
 *   /order/cafe/12        → قائمة الكافيه، طاولة/شمسية 12
 * الشمسيات مُمثَّلة بنفس صفوف cafe_tables برقم مميز (زي "شمسية 12") —
 * مفيش موديل "sunbed" منفصل، راجع CLAUDE.md §13.
 *
 * يستخدم (بدون auth):
 *   GET  /api/v1/{outlet}/public/menu
 *   POST /api/v1/{outlet}/public/orders
 *   GET  /api/v1/{outlet}/public/orders/:id  (polling حالة الطلب)
 *   POST /api/v1/public/alerts               (نادِ الجرسون / هات الفاتورة)
 *
 * تنبيهات الضيف (guest alerts): قناة منفصلة تمامًا عن الطلبات نفسها —
 * الضيف يقدر "ينادي" طاقم الخدمة مباشرة من غير ما يحتاج يطلب صنف أصلاً.
 * context_type بيفرّق بين طاولة مطعم/كافيه (نفس الفكرة اللي بتفرّق menu_item_id
 * عن item_id فوق في placeOrder) لأن الـ backend مفيهوش FK حقيقي على
 * context_id — راجع app/modules/core/models.py::GuestAlert للتفاصيل.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import LanguageSelector from '../components/LanguageSelector.vue'
import { PUBLIC_BRANCH_ID } from '../constants/resort'

const route = useRoute()
const { locale, t } = useI18n()

const outlet   = computed(() => (route.params.outlet === 'cafe' ? 'cafe' : 'restaurant') as 'restaurant' | 'cafe')
const tableId  = computed(() => route.params.tableId as string)
const branchId = computed(() => parseInt((route.query.branch as string) ?? '') || PUBLIC_BRANCH_ID)
const apiBase  = computed(() => `/api/v1/${outlet.value}/public`)

const outletLabel = computed(() =>
  outlet.value === 'cafe' ? t('qr.outlet_cafe') : t('qr.outlet_restaurant')
)

// ── Types ──────────────────────────────────────────────────────────────
interface ExtraOption  { id: number; name: string; name_ar: string | null; price_addition: number }
interface ExtraGroup   { id: number; name: string; name_ar: string | null; min_select: number; max_select: number; options: ExtraOption[] }
// #20: صغير/كبير إلخ — سعر ووصفة مستقلين تمامًا لكل حجم (راجع POS الداخلي
// RestaurantPOSView/CafePOSView.variantPickerItem لنفس المنطق بالظبط)، مش
// رسم إضافي فوق سعر ثابت زي ExtraOption. الباك إند (PublicMenuItemRead/
// CafePublicMenuItemRead) كان بيرجّعهم بالفعل من غير ما الشاشة تعرضهم خالص.
interface Variant      { id: number; name: string; name_ar: string | null; price: number; is_available: boolean }
interface MenuItem     { id: number; name: string; name_ar: string | null; price: number; category_id: number | null; extra_groups: ExtraGroup[]; variants: Variant[] }
interface Category     { id: number; name: string; name_ar: string | null }

interface CartItem {
  item:        MenuItem
  variant:     Variant | null
  qty:         number
  notes:       string
  selectedExtras: Record<number, number[]>  // group_id → [extra_id, ...]
}

// ── State ──────────────────────────────────────────────────────────────
const categories   = ref<Category[]>([])
const menuItems    = ref<MenuItem[]>([])
const cart         = ref<CartItem[]>([])
const activeCategory = ref<number | null>(null)
const loading      = ref(true)
const loadError    = ref('')

const showCart     = ref(false)
const placing      = ref(false)
const placeError   = ref('')

// بعد تقديم الطلب
const orderId      = ref<number | null>(null)
const orderNumber  = ref('')
const orderStatus  = ref('')
const orderMessage = ref('')
const orderPlaced  = ref(false)
let   pollTimer:    ReturnType<typeof setInterval> | null = null

// فشل الـ polling (مثلاً الضيف فقد اتصال الشبكة أثناء الانتظار) — راجع pollOrderStatus تحت.
// pollError بيفضل true لحد ما محاولة (تلقائية أو يدوية) تنجح، عشان الرسالة تفضل ظاهرة طول
// فترة الانقطاع من غير ما نكرر toasts لكل محاولة فاشلة جديدة (حالة واحدة مستمرة، مش سبام).
const pollError    = ref(false)
const pollChecking = ref(false)  // يمنع تداخل محاولة تلقائية مع محاولة يدوية في نفس اللحظة

// ── Extras/Variant modal ─────────────────────────────────────────────────
const extrasModal = ref<{ open: boolean; item: MenuItem | null }>({ open: false, item: null })
const tempExtras  = ref<Record<number, number[]>>({})  // group_id → [extra_id]
const tempNotes   = ref('')
const tempVariant = ref<Variant | null>(null)
const variantRequiredError = ref(false)

// ── Computed ───────────────────────────────────────────────────────────
const filteredItems = computed(() =>
  menuItems.value.filter(i =>
    activeCategory.value === null || i.category_id === activeCategory.value
  )
)

const cartCount = computed(() => cart.value.reduce((s, c) => s + c.qty, 0))
const cartTotal = computed(() =>
  cart.value.reduce((sum, c) => {
    const basePrice = c.variant?.price ?? c.item.price
    const extrasPrice = Object.entries(c.selectedExtras).flatMap(([gid, eids]) => {
      const group = c.item.extra_groups.find(g => g.id === parseInt(gid))
      return eids.map(eid => group?.options.find(o => o.id === eid)?.price_addition ?? 0)
    }).reduce((a, b) => a + b, 0)
    return sum + (basePrice + extrasPrice) * c.qty
  }, 0)
)

// إجمالي عدد النسخ من نفس الصنف في السلة (كل المتغيّرات مع بعض) — مستخدم
// بس لعرض عداد سريع في قائمة الأصناف؛ الأصناف اللي عندها متغيّرات دايمًا
// بتفتح المودال بدل +/- سريع (راجع openItem) لأن ممكن يبقى أكتر من سطر
// سلة منفصل لنفس الصنف (حجم مختلف).
function itemInCart(itemId: number) {
  return cart.value.find(c => c.item.id === itemId && !c.variant)
}
function itemTotalQtyInCart(itemId: number) {
  return cart.value.filter(c => c.item.id === itemId).reduce((s, c) => s + c.qty, 0)
}

// ── Helpers ────────────────────────────────────────────────────────────
// عرض الاسم حسب اللغة المختارة فعلياً (مش existence-based fallback) —
// عربي لو اللغة الحالية عربي وموجود name_ar، وإلا الاسم الأساسي (name) لأي لغة تانية.
function localizedName(entity: { name: string; name_ar: string | null }) {
  return locale.value === 'ar' ? (entity.name_ar ?? entity.name) : entity.name
}

function itemDisplayName(item: MenuItem) {
  return localizedName(item)
}

function categoryDisplayName(cat: Category) {
  return localizedName(cat)
}

function extraGroupDisplayName(group: ExtraGroup) {
  return localizedName(group)
}

function extraOptionDisplayName(opt: ExtraOption) {
  return localizedName(opt)
}

// ── Data Loading ───────────────────────────────────────────────────────
async function fetchMenu() {
  loading.value = true
  loadError.value = ''
  cart.value = []
  orderPlaced.value = false
  try {
    const { data } = await axios.get(`${apiBase.value}/menu`, {
      params: { branch_id: branchId.value, table_id: tableId.value || undefined },
    })
    categories.value  = data.categories ?? []
    menuItems.value   = data.items ?? []
    activeCategory.value = categories.value[0]?.id ?? null
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail ?? 'تعذّر تحميل القائمة، حاول مجدداً'
  } finally {
    loading.value = false
  }
}

// ── Cart ───────────────────────────────────────────────────────────────
function openItem(item: MenuItem) {
  const availableVariants = item.variants.filter(v => v.is_available)
  if (availableVariants.length > 0 || item.extra_groups.length > 0) {
    extrasModal.value = { open: true, item }
    tempExtras.value  = {}
    tempNotes.value   = ''
    // اختيار المتغيّر إجباري لو الصنف عنده متغيّرات متاحة — نفس قاعدة
    // POS الداخلي بالظبط (والباك إند برضو بيرفض الطلب من غيره، راجع
    // restaurant/cafe services.create_order). صنف بمتغيّر واحد بس نختاره
    // تلقائيًا (تجربة أسهل، مفيش قرار حقيقي هيتاخد).
    tempVariant.value = availableVariants.length === 1 ? availableVariants[0] : null
    variantRequiredError.value = false
  } else {
    addToCartDirect(item, null, {}, '')
  }
}

function addToCartDirect(item: MenuItem, variant: Variant | null, extras: Record<number, number[]>, notes: string) {
  const existing = cart.value.find(c => c.item.id === item.id && (c.variant?.id ?? null) === (variant?.id ?? null))
  if (existing) {
    existing.qty++
    existing.selectedExtras = extras
    existing.notes = notes
  } else {
    cart.value.push({ item, variant, qty: 1, notes, selectedExtras: extras })
  }
}

function confirmExtras() {
  const item = extrasModal.value.item
  if (!item) return
  const availableVariants = item.variants.filter(v => v.is_available)
  if (availableVariants.length > 0 && !tempVariant.value) {
    variantRequiredError.value = true
    return
  }
  addToCartDirect(item, tempVariant.value, { ...tempExtras.value }, tempNotes.value)
  extrasModal.value = { open: false, item: null }
}

function toggleExtra(groupId: number, extraId: number, maxSelect: number) {
  if (!tempExtras.value[groupId]) tempExtras.value[groupId] = []
  const arr = tempExtras.value[groupId]
  const idx = arr.indexOf(extraId)
  if (idx >= 0) {
    arr.splice(idx, 1)
  } else {
    if (arr.length >= maxSelect) arr.splice(0, 1)  // استبدل الأول لو max=1
    arr.push(extraId)
  }
}

// بياخد الـ CartItem نفسه (مش itemId) عشان يميّز بين أكتر من سطر لنفس
// الصنف بمتغيّرات مختلفة (راجع addToCartDirect) — itemId لوحده كان كافي
// قبل دعم المتغيّرات لما كل صنف سطر واحد بالضبط في السلة.
function adjustQtyLine(line: CartItem, delta: number) {
  const idx = cart.value.indexOf(line)
  if (idx < 0) return
  cart.value[idx].qty = Math.max(0, cart.value[idx].qty + delta)
  if (cart.value[idx].qty === 0) cart.value.splice(idx, 1)
}

function adjustQty(itemId: number, delta: number) {
  const line = cart.value.find(c => c.item.id === itemId && !c.variant)
  if (line) adjustQtyLine(line, delta)
}

function removeFromCartLine(line: CartItem) {
  const idx = cart.value.indexOf(line)
  if (idx >= 0) cart.value.splice(idx, 1)
}

// ── Place Order ────────────────────────────────────────────────────────
async function placeOrder() {
  if (cart.value.length === 0 || placing.value) return
  placing.value = true
  placeError.value = ''
  try {
    const items = cart.value.map(c => ({
      // المطعم بيسميها menu_item_id، الكافيه بيسميها item_id — نفس الفكرة
      [outlet.value === 'cafe' ? 'item_id' : 'menu_item_id']: c.item.id,
      variant_id: c.variant?.id ?? undefined,
      quantity: c.qty,
      notes:    c.notes || undefined,
      extra_ids: Object.values(c.selectedExtras).flat(),
    }))

    const payload: Record<string, unknown> = {
      branch_id: branchId.value,
      table_id:  tableId.value ? parseInt(tableId.value) : null,
      items,
    }
    if (outlet.value === 'restaurant') payload.guests_count = 1

    const { data } = await axios.post(`${apiBase.value}/orders`, payload)

    orderId.value     = data.order_id
    orderNumber.value = data.order_number
    orderStatus.value = data.status
    orderMessage.value = data.message
    orderPlaced.value = true
    showCart.value    = false
    cart.value        = []
    pollError.value   = false

    pollTimer = setInterval(pollOrderStatus, 10_000)

  } catch (e: any) {
    placeError.value = e?.response?.data?.detail ?? 'تعذّر إرسال الطلب، حاول مجدداً'
  } finally {
    placing.value = false
  }
}

async function pollOrderStatus() {
  // pollChecking بيمنع تداخل: تيك تلقائي أثناء ما محاولة يدوية (أو تيك سابق بطيء) لسه شغالة
  if (!orderId.value || pollChecking.value) return
  pollChecking.value = true
  try {
    const { data } = await axios.get(`${apiBase.value}/orders/${orderId.value}`)
    orderStatus.value  = data.status
    orderMessage.value = data.message
    pollError.value    = false
    if (data.status === 'served' || data.status === 'paid' || data.status === 'cancelled') {
      if (pollTimer) clearInterval(pollTimer)
    }
  } catch {
    // شبكة قطعت / timeout / رد غير ناجح — الـ polling التلقائي فضل شغال في الخلفية
    // (setInterval ماتوقفش)، والضيف بيشوف رسالة + زرار "إعادة التحقق" في الـ template
    pollError.value = true
  } finally {
    pollChecking.value = false
  }
}

// ── Guest Alerts (نادِ الجرسون / هات الفاتورة) ──────────────────────────
const sendingAlert  = ref<'call_waiter' | 'request_bill' | null>(null)
const alertBanner   = ref('')
const alertBannerErr = ref(false)
let   alertBannerTimer: ReturnType<typeof setTimeout> | null = null

async function sendGuestAlert(alertType: 'call_waiter' | 'request_bill') {
  if (!tableId.value || sendingAlert.value) return
  sendingAlert.value = alertType
  try {
    const { data } = await axios.post('/api/v1/public/alerts', {
      branch_id: branchId.value,
      context_type: outlet.value === 'cafe' ? 'cafe_table' : 'restaurant_table',
      context_id: parseInt(tableId.value),
      alert_type: alertType,
    })
    alertBannerErr.value = false
    alertBanner.value = data.message
  } catch (e: any) {
    alertBannerErr.value = true
    alertBanner.value = e?.response?.data?.detail ?? 'تعذّر إرسال الطلب، حاول مجدداً'
  } finally {
    sendingAlert.value = null
    if (alertBannerTimer) clearTimeout(alertBannerTimer)
    alertBannerTimer = setTimeout(() => { alertBanner.value = '' }, 6000)
  }
}

// ── Status UI ──────────────────────────────────────────────────────────
const STATUS_UI: Record<string, { icon: string; color: string }> = {
  held:       { icon: '📋', color: 'text-amber-600' },
  open:       { icon: '📋', color: 'text-amber-600' },
  in_kitchen: { icon: '👨‍🍳', color: 'text-blue-600' },
  served:     { icon: '🎉', color: 'text-green-600' },
  paid:       { icon: '✨', color: 'text-green-700' },
  cancelled:  { icon: '❌', color: 'text-red-500' },
}

function statusUI(s: string) {
  return STATUS_UI[s] ?? { icon: '⏳', color: 'text-gray-500' }
}

function statusMessage(s: string): string {
  const map: Record<string, string> = {
    held:       t('qr.status_pending'),
    open:       t('qr.status_pending'),
    in_kitchen: t('qr.status_in_kitchen'),
    served:     t('qr.status_served'),
    paid:       t('qr.status_paid'),
    cancelled:  t('qr.status_cancelled'),
  }
  return map[s] ?? orderMessage.value
}

onMounted(fetchMenu)
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (alertBannerTimer) clearTimeout(alertBannerTimer)
})
</script>

<template>
  <div dir="rtl" class="min-h-screen bg-stone-50 pb-24">

    <!-- Header -->
    <div class="sticky top-0 z-30 bg-white border-b border-stone-200 px-4 py-3 shadow-sm">
      <div class="flex items-center justify-between">
        <div>
          <div class="font-black text-gray-900 text-lg">{{ t('qr.menu_title', { outlet: outletLabel }) }}</div>
          <div class="text-xs text-gray-400">{{ t('qr.table_label', { tableId: tableId }) }}</div>
        </div>

        <div class="flex items-center gap-2">
          <LanguageSelector />

          <button
            v-if="!orderPlaced"
            @click="showCart = true"
            class="relative flex items-center gap-2 bg-blue-700 text-white px-4 py-2.5 rounded-xl font-bold text-sm active:scale-95 transition-transform"
          >
            <span>🛒</span>
            <span v-if="cartCount > 0">{{ cartCount }}</span>
            <span
              v-if="cartCount > 0"
              class="absolute -top-2 -left-2 w-5 h-5 bg-red-500 rounded-full text-[11px] flex items-center justify-center font-black"
            >{{ cartCount }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- ── Order Placed State ─────────────────────────────────────────── -->
    <div v-if="orderPlaced" class="p-5">
      <div class="bg-white rounded-2xl p-8 text-center shadow-sm border border-stone-200 space-y-3">
        <div class="text-5xl">{{ statusUI(orderStatus).icon }}</div>
        <div class="text-2xl font-black text-gray-900">{{ t('qr.order_received') }}</div>
        <div class="text-sm text-gray-500">{{ t('qr.order_number', { number: orderNumber }) }}</div>
        <div :class="['text-lg font-bold', statusUI(orderStatus).color]">
          {{ statusMessage(orderStatus) }}
        </div>
        <template v-if="orderStatus !== 'served' && orderStatus !== 'paid'">
          <!-- الـ polling التلقائي شغال وناجح -->
          <div v-if="!pollError" class="text-xs text-gray-400 flex items-center justify-center gap-1">
            <div class="w-3 h-3 rounded-full border-2 border-blue-400 border-t-transparent animate-spin" />
            {{ t('qr.auto_update') }}
          </div>
          <!-- آخر محاولة فشلت (شبكة الضيف قطعت وقت الانتظار) — الـ polling التلقائي فضل
               شغال في الخلفية (pollTimer مايتوقفش)، وده زرار إعادة تحقق فوري بدل الانتظار
               للتيك الجاي كل 10 ثواني -->
          <div v-else class="bg-red-50 rounded-xl p-3 space-y-2">
            <p class="text-red-600 text-xs font-semibold">{{ t('qr.poll_error') }}</p>
            <button
              @click="pollOrderStatus"
              :disabled="pollChecking"
              class="px-5 py-2 bg-red-600 text-white rounded-lg font-bold text-xs disabled:opacity-50 active:scale-95 transition-transform"
            >
              {{ pollChecking ? t('qr.poll_checking') : t('qr.poll_retry') }}
            </button>
          </div>
        </template>
        <button
          @click="orderPlaced = false; orderId = null; pollError = false"
          class="mt-2 px-6 py-2.5 border-2 border-blue-700 text-blue-700 rounded-xl font-bold text-sm"
        >
          {{ t('qr.new_order') }}
        </button>
      </div>
    </div>

    <!-- ── Menu ──────────────────────────────────────────────────────── -->
    <template v-else>

      <!-- Loading -->
      <div v-if="loading" class="flex flex-col items-center justify-center py-20 text-gray-400 gap-3">
        <div class="w-10 h-10 rounded-full border-4 border-blue-500 border-t-transparent animate-spin" />
        <p class="text-sm">{{ t('qr.loading') }}</p>
      </div>

      <!-- Error -->
      <div v-else-if="loadError" class="p-6 text-center">
        <div class="text-4xl mb-3">⚠️</div>
        <p class="text-gray-700 font-medium mb-4">{{ loadError }}</p>
        <button @click="fetchMenu" class="px-5 py-2.5 bg-blue-700 text-white rounded-xl font-bold text-sm">
          {{ t('qr.retry') }}
        </button>
      </div>

      <!-- Content -->
      <template v-else>
        <!-- Category tabs -->
        <div v-if="categories.length > 0" class="flex gap-2 overflow-x-auto px-4 py-3 scrollbar-hide">
          <button
            @click="activeCategory = null"
            :class="['flex-shrink-0 px-4 py-1.5 rounded-full text-sm font-semibold transition-colors whitespace-nowrap',
              activeCategory === null ? 'bg-blue-700 text-white' : 'bg-white text-gray-600 border border-stone-200']"
          >{{ t('qr.all_categories') }}</button>
          <button
            v-for="cat in categories" :key="cat.id"
            @click="activeCategory = cat.id"
            :class="['flex-shrink-0 px-4 py-1.5 rounded-full text-sm font-semibold transition-colors whitespace-nowrap',
              activeCategory === cat.id ? 'bg-blue-700 text-white' : 'bg-white text-gray-600 border border-stone-200']"
          >{{ categoryDisplayName(cat) }}</button>
        </div>

        <!-- Items grid -->
        <div class="px-4 grid grid-cols-1 gap-3">
          <div
            v-for="item in filteredItems" :key="item.id"
            class="bg-white rounded-2xl border border-stone-200 p-4 flex gap-3 shadow-sm active:scale-[0.99] transition-transform"
          >
            <div class="w-14 h-14 bg-stone-100 rounded-xl flex items-center justify-center text-2xl flex-shrink-0">
              {{ outlet === 'cafe' ? '☕' : '🍽️' }}
            </div>

            <div class="flex-1 min-w-0">
              <div class="font-bold text-gray-900 text-sm">{{ itemDisplayName(item) }}</div>
              <div v-if="item.variants.filter(v => v.is_available).length" class="text-xs text-blue-500 mt-0.5">
                {{ t('qr.has_variants') }}
              </div>
              <div v-else-if="item.extra_groups.length" class="text-xs text-blue-500 mt-0.5">
                {{ t('qr.customizable') }}
              </div>
              <div class="text-blue-700 font-black mt-1.5">
                {{ Number(item.price).toLocaleString('ar-EG') }} ج
              </div>
            </div>

            <div class="flex flex-col items-center justify-center gap-1 flex-shrink-0">
              <template v-if="itemInCart(item.id)">
                <button @click="adjustQty(item.id, -1)" class="w-8 h-8 bg-stone-100 rounded-full font-black flex items-center justify-center text-lg">−</button>
                <span class="font-black text-blue-700 w-5 text-center">{{ itemInCart(item.id)!.qty }}</span>
                <button @click="openItem(item)" class="w-8 h-8 bg-blue-700 rounded-full text-white font-black flex items-center justify-center text-lg">+</button>
              </template>
              <template v-else-if="itemTotalQtyInCart(item.id) > 0">
                <span class="text-[10px] text-gray-400">{{ itemTotalQtyInCart(item.id) }} {{ t('qr.in_cart') }}</span>
                <button @click="openItem(item)" class="w-8 h-8 bg-blue-700 rounded-full text-white font-black flex items-center justify-center text-xl">+</button>
              </template>
              <button
                v-else
                @click="openItem(item)"
                class="w-8 h-8 bg-blue-700 rounded-full text-white font-black flex items-center justify-center text-xl"
              >+</button>
            </div>
          </div>

          <div v-if="filteredItems.length === 0" class="text-center py-16 text-gray-400">
            <div class="text-4xl mb-2">{{ outlet === 'cafe' ? '☕' : '🍽️' }}</div>
            <p class="text-sm">{{ t('qr.no_items') }}</p>
          </div>
        </div>
      </template>
    </template>

    <!-- ══ Extras Modal ══════════════════════════════════════════════ -->
    <Teleport to="body">
      <div
        v-if="extrasModal.open && extrasModal.item"
        class="fixed inset-0 bg-black/50 z-50 flex items-end"
        @click.self="extrasModal.open = false"
      >
        <div class="bg-white w-full rounded-t-3xl max-h-[85vh] flex flex-col" dir="rtl">
          <div class="flex items-center justify-between px-5 py-4 border-b border-stone-100">
            <h3 class="font-black text-gray-900">{{ itemDisplayName(extrasModal.item) }}</h3>
            <button @click="extrasModal.open = false" class="text-gray-400 text-2xl leading-none">×</button>
          </div>

          <div class="overflow-y-auto flex-1 px-5 py-4 space-y-5">
            <!-- #20: اختيار الحجم/النوع — سعر مستقل تمامًا لكل متغيّر، إجباري
                 لو الصنف عنده متغيّرات متاحة (نفس قاعدة POS الداخلي) -->
            <div v-if="extrasModal.item.variants.filter(v => v.is_available).length">
              <div class="font-bold text-gray-800 mb-2 text-sm">
                {{ t('qr.choose_variant') }}
                <span class="text-xs text-red-500 font-normal mr-1">({{ t('qr.required') }})</span>
              </div>
              <div class="space-y-2">
                <button
                  v-for="v in extrasModal.item.variants.filter(v => v.is_available)" :key="v.id"
                  @click="tempVariant = v; variantRequiredError = false"
                  :class="['w-full flex items-center justify-between px-4 py-3 rounded-xl border-2 transition-colors text-sm',
                    tempVariant?.id === v.id ? 'border-blue-600 bg-blue-50 text-blue-700 font-semibold' : 'border-stone-200 text-gray-700']"
                >
                  <span>{{ localizedName(v) }}</span>
                  <span class="font-bold">{{ Number(v.price).toLocaleString('ar-EG') }} ج</span>
                </button>
              </div>
              <p v-if="variantRequiredError" class="text-xs text-red-600 mt-1.5">{{ t('qr.variant_required_error') }}</p>
            </div>

            <div v-for="group in extrasModal.item.extra_groups" :key="group.id">
              <div class="font-bold text-gray-800 mb-2 text-sm">
                {{ extraGroupDisplayName(group) }}
                <span class="text-xs text-gray-400 font-normal mr-1">
                  ({{ group.min_select === 0 ? t('qr.optional') : t('qr.required') }}{{ group.max_select > 1 ? ` — ${t('qr.choose_up_to', { max: group.max_select })}` : '' }})
                </span>
              </div>
              <div class="space-y-2">
                <button
                  v-for="opt in group.options" :key="opt.id"
                  @click="toggleExtra(group.id, opt.id, group.max_select)"
                  :class="['w-full flex items-center justify-between px-4 py-3 rounded-xl border-2 transition-colors text-sm',
                    (tempExtras[group.id] ?? []).includes(opt.id)
                      ? 'border-blue-600 bg-blue-50 text-blue-700 font-semibold'
                      : 'border-stone-200 text-gray-700']"
                >
                  <span>{{ extraOptionDisplayName(opt) }}</span>
                  <span class="font-bold">
                    {{ opt.price_addition > 0 ? `+${Number(opt.price_addition).toLocaleString('ar-EG')} ج` : t('qr.free') }}
                  </span>
                </button>
              </div>
            </div>

            <div>
              <label class="block font-bold text-gray-800 mb-1.5 text-sm">{{ t('qr.special_notes') }}</label>
              <textarea
                v-model="tempNotes"
                rows="2"
                :placeholder="t('qr.notes_placeholder')"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 resize-none"
              />
            </div>
          </div>

          <div class="px-5 py-4 border-t border-stone-100">
            <button
              @click="confirmExtras"
              class="w-full py-4 bg-blue-700 text-white rounded-2xl font-black text-base"
            >
              {{ t('qr.add_to_order') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ══ Cart Sheet ════════════════════════════════════════════════ -->
    <Teleport to="body">
      <div
        v-if="showCart"
        class="fixed inset-0 bg-black/50 z-50 flex items-end"
        @click.self="showCart = false"
      >
        <div class="bg-white w-full rounded-t-3xl max-h-[85vh] flex flex-col" dir="rtl">
          <div class="flex items-center justify-between px-5 py-4 border-b border-stone-100">
            <h3 class="font-black text-gray-900 text-lg">
              {{ t('qr.cart_title', { count: cartCount }) }}
            </h3>
            <button @click="showCart = false" class="text-gray-400 text-2xl leading-none">×</button>
          </div>

          <div class="overflow-y-auto flex-1 px-5 py-3 space-y-3">
            <div
              v-for="(ci, ciIdx) in cart" :key="`${ci.item.id}-${ci.variant?.id ?? 'novariant'}-${ciIdx}`"
              class="bg-stone-50 rounded-xl p-3 border border-stone-100"
            >
              <div class="flex items-start justify-between mb-2 gap-2">
                <div class="flex-1">
                  <div class="font-semibold text-sm text-gray-900">
                    {{ itemDisplayName(ci.item) }}<span v-if="ci.variant"> — {{ localizedName(ci.variant) }}</span>
                  </div>
                  <div
                    v-if="Object.values(ci.selectedExtras).flat().length > 0"
                    class="text-xs text-blue-500 mt-0.5"
                  >
                    {{ Object.entries(ci.selectedExtras).flatMap(([gid, eids]) =>
                      eids.map(eid => {
                        const group = ci.item.extra_groups.find(g => g.id === parseInt(gid))
                        const opt = group?.options.find(o => o.id === eid)
                        return opt ? extraOptionDisplayName(opt) : ''
                      })
                    ).filter(Boolean).join('، ') }}
                  </div>
                  <div v-if="ci.notes" class="text-xs text-gray-400 mt-0.5 italic">{{ ci.notes }}</div>
                </div>
                <button @click="removeFromCartLine(ci)" class="text-red-400 hover:text-red-600 text-xl leading-none">×</button>
              </div>
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <button @click="adjustQtyLine(ci, -1)" class="w-8 h-8 rounded-lg bg-stone-200 font-black flex items-center justify-center">−</button>
                  <span class="font-black w-5 text-center">{{ ci.qty }}</span>
                  <button @click="adjustQtyLine(ci, 1)" class="w-8 h-8 rounded-lg bg-blue-100 text-blue-700 font-black flex items-center justify-center">+</button>
                </div>
                <span class="font-black text-blue-700 text-sm">
                  {{ Number((ci.variant?.price ?? ci.item.price) * ci.qty).toLocaleString('ar-EG') }} ج
                </span>
              </div>
            </div>
          </div>

          <div class="px-5 py-4 border-t border-stone-100 space-y-3">
            <div class="flex justify-between items-center">
              <span class="font-black text-gray-900 text-lg">{{ t('qr.total') }}</span>
              <span class="font-black text-blue-700 text-xl">
                {{ cartTotal.toLocaleString('ar-EG') }} ج
              </span>
            </div>

            <p v-if="placeError" class="text-red-600 text-xs text-center bg-red-50 py-2 rounded-lg">
              {{ placeError }}
            </p>

            <button
              @click="placeOrder"
              :disabled="placing || cart.length === 0"
              class="w-full py-4 bg-blue-700 text-white rounded-2xl font-black text-lg disabled:opacity-50 active:scale-[0.98] transition-transform"
            >
              {{ placing ? t('qr.placing') : `🍳 ${t('qr.place_order', { outlet: outletLabel })}` }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ══ Guest Alerts — نادِ الجرسون / هات الفاتورة ═══════════════════ -->
    <!-- ثابتة أسفل الشاشة، ظاهرة دايمًا لو فيه رقم طاولة حقيقي (مش takeaway) —
         الضيف يقدر ينادي الطاقم في أي وقت، مش بس وقت تصفح القائمة. -->
    <Teleport to="body">
      <div v-if="tableId" class="fixed bottom-0 inset-x-0 z-40 bg-white border-t border-stone-200 px-4 py-3 shadow-[0_-4px_12px_rgba(0,0,0,0.06)]" dir="rtl">
        <div
          v-if="alertBanner"
          :class="['mb-2 text-center text-sm font-bold rounded-xl py-2 px-3',
            alertBannerErr ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-700']"
        >{{ alertBanner }}</div>

        <div class="flex gap-2">
          <button
            @click="sendGuestAlert('call_waiter')"
            :disabled="sendingAlert !== null"
            class="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border-2 border-blue-700 text-blue-700 font-bold text-sm disabled:opacity-50 active:scale-[0.98] transition-transform"
          >
            <span>🧑‍🍳</span>
            <span>{{ sendingAlert === 'call_waiter' ? t('qr.sending') : t('qr.call_waiter') }}</span>
          </button>
          <button
            @click="sendGuestAlert('request_bill')"
            :disabled="sendingAlert !== null"
            class="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border-2 border-blue-700 text-blue-700 font-bold text-sm disabled:opacity-50 active:scale-[0.98] transition-transform"
          >
            <span>🧾</span>
            <span>{{ sendingAlert === 'request_bill' ? t('qr.sending') : t('qr.request_bill') }}</span>
          </button>
        </div>
      </div>
    </Teleport>

  </div>
</template>

<style scoped>
.scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }
.scrollbar-hide::-webkit-scrollbar { display: none; }
</style>
