<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore, useResortWebSocket } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { useOfflineQueue, useOrderDiscount, usePrintDocument } from '@resort-os/core/composables'
import {
  AppBadge,
  AppButton,
  AppIcon,
  AppSelect,
  EmptyState,
  LoadingState,
  SearchInput,
  useConfirm,
  useToast,
} from '@resort-os/ui'
import type { SelectOption } from '@resort-os/ui'
import DiningExtrasModal, { type DiningExtrasItem } from '../../components/DiningExtrasModal.vue'
import DiningOrderDetailModal from '../../components/DiningOrderDetailModal.vue'
import PinGuardModal from '../../components/PinGuardModal.vue'
import POSActiveOrdersWorkspace from '../../components/dining-pos/POSActiveOrdersWorkspace.vue'
import POSCartPanel from '../../components/dining-pos/POSCartPanel.vue'
import POSCustomerModal from '../../components/dining-pos/POSCustomerModal.vue'
import POSPaymentModal from '../../components/dining-pos/POSPaymentModal.vue'
import POSTablesWorkspace from '../../components/dining-pos/POSTablesWorkspace.vue'
import type {
  ActiveOrder,
  CartLine,
  DiningCategory,
  DiningItemRow,
  DiningOrderDetail,
  DiningOutlet,
  OrderType,
  POSCustomer,
  POSWorkspace,
  VenueTable,
} from '../../components/dining-pos/types'

const { t, locale } = useI18n()
const { formatMoney } = useStaffFormat()
const toast = useToast()
const { confirm } = useConfirm()
const { printBlob } = usePrintDocument()
const auth = useAuthStore()
const branchId = auth.branchId
const currency = 'EGP'
const {
  isOnline,
  pendingCount,
  submitOrder: submitOrderOnlineOrQueue,
  lastPartialRejection,
} = useOfflineQueue('dining')
const { applyingDiscount, discountError, applyDiscount: applyDiscountRule } = useOrderDiscount()

const workspace = ref<POSWorkspace>('tables')
const outlets = ref<DiningOutlet[]>([])
const selectedOutletId = ref<number | null>(null)
const categories = ref<DiningCategory[]>([])
const items = ref<DiningItemRow[]>([])
const tables = ref<VenueTable[]>([])
const activeOrders = ref<ActiveOrder[]>([])
const activeOrdersLoading = ref(false)
const menuLoading = ref(false)
const submitting = ref(false)

const orderType = ref<OrderType>('dine_in')
const selectedTableId = ref<number | null>(null)
const selectedCategoryId = ref('all')
const searchQuery = ref('')
const covers = ref(1)
const extraNote = ref('')
const cart = ref<CartLine[]>([])
const selectedCustomer = ref<POSCustomer | null>(null)
const extrasModalItem = ref<DiningItemRow | null>(null)
const customerModalOpen = ref(false)
const mobileCartOpen = ref(false)

const pendingOrderId = ref<number | null>(null)
const pendingOrderNumber = ref('')
const pendingOrderStatus = ref<'held' | 'open' | null>(null)
const pendingOrderSummary = ref<{ discount_amount: number | string; total: number | string } | null>(null)
const showDiscountPinGuard = ref(false)

const selectedOrderId = ref<number | null>(null)
const directPaymentOrder = ref<DiningOrderDetail | null>(null)
const paymentOpen = ref(false)
const searchInputEl = ref<InstanceType<typeof SearchInput> | null>(null)

const { status: wsStatus, onMessage: onWsMessage } = useResortWebSocket(ENDPOINTS.dining.tablesWs(branchId))
onWsMessage((message: any) => {
  if (message?.type === 'table_updated' || message?.type === 'tables_updated') {
    loadTables()
    loadActiveOrders()
  }
})

const listSeparator = computed(() => locale.value === 'ar' ? '، ' : ', ')
const cartLocked = computed(() => pendingOrderId.value !== null)
const hasItems = computed(() => cart.value.length > 0)
const cartSubtotal = computed(() => cart.value.reduce((sum, line) => sum + line.unitPrice * line.quantity, 0))

const outletOptions = computed<SelectOption[]>(() => outlets.value.map(outlet => ({
  value: outlet.id,
  label: localizedName(outlet),
})))

const orderTypeOptions = computed<Array<{ value: OrderType; label: string; icon: string }>>(() => [
  { value: 'dine_in', label: t('backoffice.pos.orderTypes.dineIn'), icon: '🍽️' },
  { value: 'takeaway', label: t('backoffice.pos.orderTypes.takeaway'), icon: '🥡' },
  { value: 'delivery', label: t('backoffice.pos.orderTypes.delivery'), icon: '🛵' },
  { value: 'room_service', label: t('backoffice.pos.orderTypes.roomService'), icon: '🛎️' },
])

const filteredItems = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return items.value.filter(item => {
    if (!item.is_available) return false
    if (selectedCategoryId.value !== 'all' && item.category_id !== Number(selectedCategoryId.value)) return false
    if (!query) return true
    return item.name.toLowerCase().includes(query) || (item.name_ar ?? '').toLowerCase().includes(query)
  })
})

const cartContextLabel = computed(() => {
  if (orderType.value === 'dine_in' && selectedTableId.value) {
    const table = tables.value.find(item => item.id === selectedTableId.value)
    return table
      ? t('backoffice.pos.tableLabel', { number: table.table_number })
      : t('backoffice.pos.orderTypes.dineIn')
  }
  const option = orderTypeOptions.value.find(item => item.value === orderType.value)
  return option ? `${option.icon} ${option.label}` : ''
})

const noteLabel = computed(() => {
  if (orderType.value === 'delivery') return t('backoffice.pos.deliveryAddress')
  if (orderType.value === 'room_service') return t('backoffice.pos.roomNumber')
  return t('backoffice.pos.note')
})

function localizedName(value: { name: string; name_ar: string | null }): string {
  return locale.value === 'ar' ? (value.name_ar || value.name) : value.name
}

function categoryName(category: DiningCategory): string {
  return localizedName(category)
}

function itemName(item: DiningItemRow): string {
  return localizedName(item)
}

function itemPrice(item: DiningItemRow): number {
  const variants = (item.variants ?? []).filter(variant => variant.is_available)
  if (variants.length) return Math.min(...variants.map(variant => Number(variant.price)))
  return Number(item.price)
}

async function loadOutlets() {
  try {
    const { data } = await api.get(ENDPOINTS.dining.outlets, {
      params: { branch_id: branchId, active_only: true },
    })
    outlets.value = data
    if (data.length && selectedOutletId.value === null) selectedOutletId.value = data[0].id
  } catch {
    toast.error(t('backoffice.pos.errors.loadOutlets'))
  }
}

async function loadMenu() {
  if (!selectedOutletId.value) return
  menuLoading.value = true
  try {
    const [categoryResponse, itemResponse] = await Promise.all([
      api.get(ENDPOINTS.dining.categories(selectedOutletId.value)),
      api.get(ENDPOINTS.dining.items(selectedOutletId.value), { params: { available_only: false } }),
    ])
    categories.value = categoryResponse.data
    items.value = itemResponse.data
    selectedCategoryId.value = 'all'
  } catch {
    toast.error(t('backoffice.pos.errors.loadOutletData'))
  } finally {
    menuLoading.value = false
  }
}

async function loadTables() {
  try {
    const { data } = await api.get(ENDPOINTS.dining.tables(branchId))
    tables.value = data
  } catch {
    toast.error(t('backoffice.pos.errors.loadTables'))
  }
}

async function loadActiveOrders() {
  activeOrdersLoading.value = true
  try {
    const fetchStatus = async (status: string): Promise<ActiveOrder[]> => {
      const result: ActiveOrder[] = []
      let page = 1
      const pageSize = 100
      while (true) {
        const { data } = await api.get(ENDPOINTS.dining.orders, {
          params: { branch_id: branchId, status, page, size: pageSize },
        })
        const pageItems: ActiveOrder[] = data?.items ?? []
        result.push(...pageItems)
        if (pageItems.length < pageSize) break
        page += 1
      }
      return result
    }
    const [open, kitchen, served] = await Promise.all([
      fetchStatus('open'),
      fetchStatus('in_kitchen'),
      fetchStatus('served'),
    ])
    activeOrders.value = [...open, ...kitchen, ...served]
  } catch {
    toast.error(t('backoffice.pos.errors.loadActiveOrders'))
  } finally {
    activeOrdersLoading.value = false
  }
}

function cartKey(itemId: number, variantId: number | null, extraIds: number[]): string {
  return `${itemId}:${variantId ?? ''}:${[...extraIds].sort().join(',')}`
}

function onItemClick(item: DiningItemRow) {
  if (cartLocked.value) return
  const hasVariants = (item.variants ?? []).some(variant => variant.is_available)
  const hasExtras = (item.extra_groups ?? []).length > 0
  if (hasVariants || hasExtras) {
    extrasModalItem.value = item
    return
  }
  addLineToCart(item, { variantId: null, extraIds: [], extraTexts: {}, notes: '' })
}

function addLineToCart(
  item: DiningItemRow,
  choice: { variantId: number | null; extraIds: number[]; extraTexts: Record<number, string>; notes: string },
) {
  const baseKey = cartKey(item.id, choice.variantId, choice.extraIds)
  const normalizedExtraIds = [...choice.extraIds].sort((a, b) => a - b).join(',')
  const existing = cart.value.find(line => (
    line.itemId === item.id &&
    line.variantId === choice.variantId &&
    [...line.extraIds].sort((a, b) => a - b).join(',') === normalizedExtraIds &&
    Object.keys(line.extraTexts).length === 0 &&
    Object.keys(choice.extraTexts).length === 0 &&
    !line.notes &&
    !choice.notes
  ))
  if (existing) {
    existing.quantity += 1
    return
  }
  const variant = (item.variants ?? []).find(value => value.id === choice.variantId)
  const extras = (item.extra_groups ?? [])
    .flatMap(group => group.options)
    .filter(option => choice.extraIds.includes(option.id))
  const textAnswers = Object.entries(choice.extraTexts).map(([groupId, answer]) => {
    const group = (item.extra_groups ?? []).find(value => value.id === Number(groupId))
    return `${group ? localizedName(group) : ''}: ${answer}`
  })
  const extraPrice = extras.reduce((sum, option) => sum + Number(option.price_addition), 0)
  cart.value.push({
    key: `${baseKey}:${Date.now()}:${cart.value.length}`,
    itemId: item.id,
    variantId: choice.variantId,
    variantLabel: variant ? localizedName(variant) : null,
    name: item.name,
    nameAr: item.name_ar,
    unitPrice: Number(variant ? variant.price : item.price) + extraPrice,
    quantity: 1,
    notes: choice.notes,
    extraIds: choice.extraIds,
    extraTexts: choice.extraTexts,
    extrasLabel: [
      ...extras.map(option => localizedName(option)),
      ...textAnswers,
    ].join(listSeparator.value),
  })
}

function onExtrasConfirm(choice: {
  variantId: number | null
  extraIds: number[]
  extraTexts: Record<number, string>
  notes: string
}) {
  if (!extrasModalItem.value) return
  addLineToCart(extrasModalItem.value, choice)
  extrasModalItem.value = null
}

function adjustQuantity(key: string, delta: number) {
  if (cartLocked.value) return
  const line = cart.value.find(item => item.key === key)
  if (!line) return
  line.quantity += delta
  if (line.quantity <= 0) removeLine(key)
}

function removeLine(key: string) {
  if (cartLocked.value) return
  cart.value = cart.value.filter(line => line.key !== key)
}

function buildOrderPayload() {
  return {
    outlet_id: selectedOutletId.value,
    table_id: orderType.value === 'dine_in' ? selectedTableId.value : null,
    order_type: orderType.value,
    guests_count: covers.value,
    notes: extraNote.value.trim() || undefined,
    customer_id: selectedCustomer.value?.id,
    items: cart.value.map(line => ({
      item_id: line.itemId,
      variant_id: line.variantId ?? undefined,
      quantity: line.quantity,
      notes: line.notes || undefined,
      extra_ids: line.extraIds,
      extra_texts: line.extraTexts,
    })),
  }
}

function resetDraft() {
  cart.value = []
  covers.value = 1
  extraNote.value = ''
  selectedTableId.value = null
  selectedCustomer.value = null
  pendingOrderId.value = null
  pendingOrderNumber.value = ''
  pendingOrderStatus.value = null
  pendingOrderSummary.value = null
  mobileCartOpen.value = false
}

async function cancelAndResetDraft(): Promise<boolean> {
  if (pendingOrderId.value !== null) {
    try {
      await api.patch(ENDPOINTS.dining.orderStatus(pendingOrderId.value), { status: 'cancelled' })
    } catch {
      toast.error(t('backoffice.pos.errors.cancelHeldOrder'))
      return false
    }
  }
  resetDraft()
  await Promise.all([loadTables(), loadActiveOrders()])
  return true
}

async function requestClearDraft() {
  if (!hasItems.value && pendingOrderId.value === null) return
  const accepted = await confirm({
    title: t('backoffice.pos.cart.clearTitle'),
    message: t('backoffice.pos.cart.clearMessage'),
    confirmText: t('backoffice.pos.cart.clearConfirm'),
    cancelText: t('backoffice.pos.cart.keepOrder'),
    danger: true,
  })
  if (accepted) await cancelAndResetDraft()
}

function validateDraft(): boolean {
  if (!hasItems.value || !selectedOutletId.value) return false
  if (orderType.value === 'dine_in' && !selectedTableId.value) {
    toast.error(t('backoffice.pos.errors.selectTableRequired'))
    workspace.value = 'tables'
    return false
  }
  return true
}

function stageServerOrder(order: DiningOrderDetail, status: 'held' | 'open') {
  pendingOrderId.value = order.id
  pendingOrderNumber.value = order.order_number
  pendingOrderStatus.value = status
  pendingOrderSummary.value = {
    discount_amount: order.discount_amount,
    total: order.total,
  }
}

async function applyDiscountToCart() {
  if (!validateDraft() || applyingDiscount.value || !selectedOutletId.value) return
  if (pendingOrderId.value === null) {
    try {
      const { data } = await api.post(
        ENDPOINTS.dining.outletOrdersHold(selectedOutletId.value),
        buildOrderPayload(),
      )
      stageServerOrder(data, 'held')
    } catch {
      toast.error(t('backoffice.pos.errors.holdOrderForDiscount'))
      return
    }
  }
  showDiscountPinGuard.value = true
}

function onDiscountPinApproved(approval: { approverUserId: number | null; approverPin: string | null }) {
  showDiscountPinGuard.value = false
  performDiscount(approval)
}

async function performDiscount(approval: { approverUserId: number | null; approverPin: string | null }) {
  if (pendingOrderId.value === null) return
  try {
    const data = await applyDiscountRule(pendingOrderId.value, approval)
    pendingOrderSummary.value = { discount_amount: data.discount_amount, total: data.total }
    toast.success(Number(data.discount_amount) > 0
      ? t('backoffice.pos.discountApplied', { amount: formatMoney(data.discount_amount, currency) })
      : t('backoffice.pos.noActiveDiscountRule'))
  } catch {
    // useOrderDiscount exposes the localized/renderable message inline.
  }
}

async function printReceipt(orderId: number) {
  try {
    const response = await api.get(ENDPOINTS.dining.receipt(orderId), { responseType: 'blob' })
    const outcome = printBlob(response.data, `dining-receipt-${orderId}.pdf`)
    if (outcome.downloadedInstead) toast.warning(t('backoffice.pos.receiptDownloadedInstead'))
  } catch {
    // Printing is a convenience after a confirmed server transition; failure
    // must never roll back or misreport the order itself.
  }
}

async function sendOrderToKitchen() {
  if (!validateDraft() || submitting.value || !selectedOutletId.value) return
  submitting.value = true
  let orderId: number | null = pendingOrderId.value
  try {
    if (pendingOrderId.value !== null) {
      if (pendingOrderStatus.value === 'held') {
        const { data } = await api.patch(ENDPOINTS.dining.orderStatus(pendingOrderId.value), { status: 'open' })
        stageServerOrder(data, 'open')
      }
    } else {
      const data = await submitOrderOnlineOrQueue(branchId, buildOrderPayload(), selectedOutletId.value)
      if (data === null) {
        resetDraft()
        workspace.value = orderType.value === 'dine_in' ? 'tables' : 'order'
        toast.success(t('backoffice.pos.offlineSaved'))
        return
      }
      orderId = data.id
      stageServerOrder(data, 'open')
    }

    orderId = pendingOrderId.value
    if (!orderId) return
    await api.patch(ENDPOINTS.dining.orderStatus(orderId), { status: 'in_kitchen' })
    await printReceipt(orderId)
    resetDraft()
    toast.success(t('backoffice.pos.kitchenSentSuccess'))
    selectedOrderId.value = orderId
    await Promise.all([loadTables(), loadActiveOrders()])
  } catch {
    toast.error(t('backoffice.pos.errors.sendToKitchen'))
    if (orderId) selectedOrderId.value = orderId
  } finally {
    submitting.value = false
  }
}

async function openDirectPayment() {
  if (!validateDraft() || submitting.value || !selectedOutletId.value) return
  if (!isOnline.value) {
    toast.error(t('backoffice.pos.cart.paymentOffline'))
    return
  }
  submitting.value = true
  try {
    let order: DiningOrderDetail
    if (pendingOrderId.value !== null) {
      if (pendingOrderStatus.value === 'held') {
        const { data } = await api.patch(ENDPOINTS.dining.orderStatus(pendingOrderId.value), { status: 'open' })
        order = data
        stageServerOrder(order, 'open')
      } else {
        const { data } = await api.get(ENDPOINTS.dining.order(pendingOrderId.value))
        order = data
      }
    } else {
      const { data } = await api.post(ENDPOINTS.dining.outletOrders(selectedOutletId.value), buildOrderPayload())
      order = data
      stageServerOrder(order, 'open')
    }
    directPaymentOrder.value = order
    pendingOrderSummary.value = { discount_amount: order.discount_amount, total: order.total }
    paymentOpen.value = true
    mobileCartOpen.value = false
  } catch {
    toast.error(t('backoffice.pos.errors.createForPayment'))
  } finally {
    submitting.value = false
  }
}

async function onDirectPaymentCompleted(order: DiningOrderDetail) {
  paymentOpen.value = false
  directPaymentOrder.value = null
  resetDraft()
  toast.success(t('backoffice.pos.payment.success', { number: order.order_number }))
  workspace.value = order.order_type === 'dine_in' ? 'tables' : 'order'
  await Promise.all([loadTables(), loadActiveOrders()])
}

async function selectOutlet(value: string | number) {
  const nextId = Number(value)
  if (nextId === selectedOutletId.value) return
  if (hasItems.value || pendingOrderId.value !== null) {
    const accepted = await confirm({
      title: t('backoffice.pos.switchOutlet.title'),
      message: t('backoffice.pos.switchOutlet.message'),
      confirmText: t('backoffice.pos.switchOutlet.confirm'),
      cancelText: t('backoffice.pos.cart.keepOrder'),
      danger: true,
    })
    if (!accepted || !(await cancelAndResetDraft())) return
  }
  selectedOutletId.value = nextId
  await loadMenu()
}

async function changeOrderType(nextType: OrderType) {
  if (nextType === orderType.value) return
  if (hasItems.value || pendingOrderId.value !== null) {
    const accepted = await confirm({
      title: t('backoffice.pos.switchOrderType.title'),
      message: t('backoffice.pos.switchOrderType.message'),
      confirmText: t('backoffice.pos.switchOrderType.confirm'),
      cancelText: t('backoffice.pos.cart.keepOrder'),
      danger: true,
    })
    if (!accepted || !(await cancelAndResetDraft())) return
  }
  orderType.value = nextType
  selectedTableId.value = null
  workspace.value = nextType === 'dine_in' ? 'tables' : 'order'
}

async function startTableOrder(table: VenueTable) {
  if ((hasItems.value || pendingOrderId.value !== null) && selectedTableId.value !== table.id) {
    const accepted = await confirm({
      title: t('backoffice.pos.tablesWorkspace.changeTableTitle'),
      message: t('backoffice.pos.tablesWorkspace.changeTableMessage'),
      confirmText: t('backoffice.pos.tablesWorkspace.changeTableConfirm'),
      cancelText: t('backoffice.pos.cart.keepOrder'),
      danger: true,
    })
    if (!accepted || !(await cancelAndResetDraft())) return
  }
  orderType.value = 'dine_in'
  selectedTableId.value = table.id
  covers.value = Math.max(1, table.capacity > 0 ? Math.min(2, table.capacity) : 1)
  workspace.value = 'order'
}

function openOrder(orderId: number) {
  selectedOrderId.value = orderId
}

async function onOrderDetailClosed() {
  selectedOrderId.value = null
  await Promise.all([loadTables(), loadActiveOrders()])
}

function openWorkspace(next: POSWorkspace) {
  workspace.value = next
  if (next === 'active') loadActiveOrders()
}

function beginNewOrder() {
  if (orderType.value === 'dine_in' && !selectedTableId.value) workspace.value = 'tables'
  else workspace.value = 'order'
}

function selectCustomer(customer: POSCustomer) {
  selectedCustomer.value = customer
  customerModalOpen.value = false
}

function clearCustomer() {
  selectedCustomer.value = null
  customerModalOpen.value = false
}

function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null
  return !!element && (
    ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName) || element.isContentEditable
  )
}

function focusSearch() {
  const root = (searchInputEl.value as any)?.$el as HTMLElement | undefined
  root?.querySelector<HTMLInputElement>('input')?.focus()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    if (mobileCartOpen.value) { mobileCartOpen.value = false; return }
    if (extrasModalItem.value) { extrasModalItem.value = null; return }
    if (customerModalOpen.value) { customerModalOpen.value = false; return }
    return
  }
  if (isTypingTarget(event.target)) return
  if (event.key === '/') {
    event.preventDefault()
    workspace.value = 'order'
    focusSearch()
    return
  }
  if (event.key === 'F4' && hasItems.value) {
    event.preventDefault()
    openDirectPayment()
    return
  }
  if (event.key === 'Enter' && event.ctrlKey && hasItems.value) {
    event.preventDefault()
    sendOrderToKitchen()
  }
}

onMounted(async () => {
  await loadOutlets()
  await Promise.all([loadMenu(), loadTables(), loadActiveOrders()])
  window.addEventListener('keydown', handleKeydown)
})
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div class="h-full min-h-0 flex flex-col bg-stone-50 dark:bg-background">
    <div
      v-if="!isOnline"
      class="bg-amber-500 text-white text-sm font-bold px-4 py-2 flex items-center justify-center gap-2 flex-shrink-0"
    >
      <AppIcon name="offline" class="w-5 h-5" />
      <span>{{ t('backoffice.pos.offlineBanner') }}</span>
      <AppBadge v-if="pendingCount > 0" variant="warning">{{ t('backoffice.pos.pendingCount', { count: pendingCount }) }}</AppBadge>
    </div>
    <div
      v-else-if="pendingCount > 0"
      class="bg-primary-700 text-white text-sm font-bold px-4 py-2 text-center flex-shrink-0"
    >
      {{ t('backoffice.pos.syncingBanner', { count: pendingCount }) }}
    </div>
    <div
      v-if="lastPartialRejection?.length"
      class="bg-red-100 text-red-900 dark:bg-red-950/40 dark:text-red-200 text-sm font-semibold px-4 py-2 flex-shrink-0 border-b border-red-200"
    >
      {{ t('backoffice.pos.partialRejectionBanner') }}
      {{ lastPartialRejection.map(item => `${item.name} (×${item.requested_qty})`).join(listSeparator) }}
    </div>

    <header class="bg-white dark:bg-surface border-b border-stone-200 dark:border-border px-3 lg:px-4 py-2.5 flex items-center gap-3 flex-shrink-0 shadow-sm">
      <div class="w-44 lg:w-56 flex-shrink-0">
        <AppSelect
          :model-value="selectedOutletId ?? ''"
          :options="outletOptions"
          :placeholder="t('backoffice.pos.selectOutlet')"
          @update:model-value="selectOutlet"
        />
      </div>

      <nav class="flex items-center gap-1.5 min-w-0 overflow-x-auto" :aria-label="t('backoffice.pos.workspaceNav.label')">
        <button
          type="button"
          :aria-current="workspace === 'tables' ? 'page' : undefined"
          :class="[
            'min-h-[46px] px-3 rounded-xl font-bold text-sm whitespace-nowrap flex items-center gap-2 transition-colors',
            workspace === 'tables' ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-stone-100 dark:hover:bg-gray-800',
          ]"
          @click="openWorkspace('tables')"
        >
          <AppIcon name="table" size="sm" />
          <span>{{ t('backoffice.pos.workspaceNav.tables') }}</span>
        </button>
        <button
          type="button"
          :aria-current="workspace === 'order' ? 'page' : undefined"
          :class="[
            'min-h-[46px] px-3 rounded-xl font-bold text-sm whitespace-nowrap flex items-center gap-2 transition-colors',
            workspace === 'order' ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-stone-100 dark:hover:bg-gray-800',
          ]"
          @click="beginNewOrder"
        >
          <AppIcon name="cart" size="sm" />
          <span>{{ t('backoffice.pos.workspaceNav.order') }}</span>
          <AppBadge v-if="cart.length" variant="warning" size="sm">{{ cart.length }}</AppBadge>
        </button>
        <button
          type="button"
          :aria-current="workspace === 'active' ? 'page' : undefined"
          :class="[
            'min-h-[46px] px-3 rounded-xl font-bold text-sm whitespace-nowrap flex items-center gap-2 transition-colors',
            workspace === 'active' ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-stone-100 dark:hover:bg-gray-800',
          ]"
          @click="openWorkspace('active')"
        >
          <AppIcon name="clipboard" size="sm" />
          <span>{{ t('backoffice.pos.workspaceNav.active') }}</span>
          <AppBadge v-if="activeOrders.length" variant="info" size="sm">{{ activeOrders.length }}</AppBadge>
        </button>
      </nav>

      <div class="ms-auto flex items-center gap-2 flex-shrink-0">
        <span
          :class="[
            'hidden sm:inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold',
            wsStatus === 'connected' ? 'bg-success/10 text-success' : wsStatus === 'connecting' ? 'bg-warning/10 text-warning' : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
          ]"
          :title="wsStatus === 'connected' ? t('backoffice.pos.wsStatus.connected') : wsStatus === 'connecting' ? t('backoffice.pos.wsStatus.connecting') : t('backoffice.pos.wsStatus.disconnected')"
        >
          <span :class="['w-2 h-2 rounded-full', wsStatus === 'connected' ? 'bg-success' : wsStatus === 'connecting' ? 'bg-warning animate-pulse' : 'bg-gray-400']" />
          {{ t('backoffice.pos.workspaceNav.live') }}
        </span>
      </div>
    </header>

    <main class="flex-1 min-h-0">
      <POSTablesWorkspace
        v-if="workspace === 'tables'"
        :tables="tables"
        :outlets="outlets"
        :selected-outlet-id="selectedOutletId"
        @start="startTableOrder"
        @open="openOrder"
      />

      <POSActiveOrdersWorkspace
        v-else-if="workspace === 'active'"
        :orders="activeOrders"
        :outlets="outlets"
        :tables="tables"
        :loading="activeOrdersLoading"
        :initial-outlet-id="selectedOutletId"
        @open="openOrder"
        @refresh="loadActiveOrders"
      />

      <div v-else class="pos-order-grid h-full min-h-0">
        <nav class="pos-category-rail bg-white dark:bg-surface border-e border-stone-200 dark:border-border p-2 overflow-y-auto" :aria-label="t('backoffice.pos.categoriesLabel')">
          <button
            type="button"
            :aria-pressed="selectedCategoryId === 'all'"
            :class="[
              'pos-category-button w-full min-h-[52px] rounded-xl px-3 py-2 text-sm font-bold transition-colors text-start',
              selectedCategoryId === 'all' ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-stone-100 dark:hover:bg-gray-800',
            ]"
            @click="selectedCategoryId = 'all'"
          >
            {{ t('backoffice.pos.categoryAll') }}
          </button>
          <button
            v-for="category in categories"
            :key="category.id"
            type="button"
            :aria-pressed="selectedCategoryId === String(category.id)"
            :class="[
              'pos-category-button w-full min-h-[52px] rounded-xl px-3 py-2 text-sm font-bold transition-colors text-start mt-1',
              selectedCategoryId === String(category.id) ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-stone-100 dark:hover:bg-gray-800',
            ]"
            @click="selectedCategoryId = String(category.id)"
          >
            {{ categoryName(category) }}
          </button>
        </nav>

        <section class="pos-menu min-h-0 flex flex-col bg-stone-50/80 dark:bg-background">
          <div class="bg-white dark:bg-surface border-b border-stone-200 dark:border-border p-3 flex flex-col xl:flex-row xl:items-center gap-3 flex-shrink-0">
            <div class="flex gap-1.5 overflow-x-auto pb-0.5" :aria-label="t('backoffice.pos.orderTypeLabel')">
              <button
                v-for="type in orderTypeOptions"
                :key="type.value"
                type="button"
                :aria-pressed="orderType === type.value"
                :class="[
                  'min-h-[44px] whitespace-nowrap rounded-xl px-3 font-bold text-sm border-2 transition-colors',
                  orderType === type.value
                    ? 'border-primary-700 bg-primary-50 text-primary-800'
                    : 'border-stone-200 dark:border-border text-gray-600 dark:text-gray-300',
                ]"
                @click="changeOrderType(type.value)"
              >
                {{ type.icon }} {{ type.label }}
              </button>
            </div>
            <div class="xl:ms-auto xl:w-72">
              <SearchInput
                ref="searchInputEl"
                v-model="searchQuery"
                :placeholder="t('backoffice.pos.searchPlaceholder')"
                :clear-label="t('backoffice.pos.clearSearch')"
                :debounce-ms="0"
              />
            </div>
          </div>

          <div class="flex-1 min-h-0 overflow-y-auto p-3 lg:p-4">
            <LoadingState v-if="menuLoading" :label="t('backoffice.pos.loadingMenu')" />
            <EmptyState
              v-else-if="filteredItems.length === 0"
              icon="🍽️"
              :title="t('backoffice.pos.noItems')"
              :subtitle="searchQuery ? t('backoffice.pos.noResultsFor', { query: searchQuery }) : undefined"
            />
            <div v-else class="pos-products-grid">
              <button
                v-for="item in filteredItems"
                :key="item.id"
                type="button"
                :disabled="cartLocked"
                class="relative min-h-[138px] rounded-2xl border-2 border-stone-200 dark:border-border bg-white dark:bg-surface p-3 text-start shadow-sm hover:border-primary-400 hover:shadow-md active:scale-[0.99] transition-all flex flex-col justify-between gap-3 disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
                @click="onItemClick(item)"
              >
                <div class="w-full">
                  <div class="flex items-start justify-between gap-2">
                    <span class="text-xs font-semibold text-gray-400 uppercase">{{ item.station }}</span>
                    <AppBadge v-if="(item.extra_groups ?? []).length" variant="info" size="sm">{{ t('backoffice.pos.extrasBadge') }}</AppBadge>
                  </div>
                  <h3 class="font-black text-gray-950 dark:text-gray-100 leading-snug mt-3 line-clamp-2">{{ itemName(item) }}</h3>
                </div>
                <div class="flex items-end justify-between gap-2 w-full">
                  <span v-if="(item.variants ?? []).some(variant => variant.is_available)" class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.pos.fromPrice') }}</span>
                  <span class="text-lg font-black text-primary-800 dark:text-primary-300 tabular-nums">{{ formatMoney(itemPrice(item), currency) }}</span>
                </div>
              </button>
            </div>
          </div>
        </section>

        <POSCartPanel
          class="pos-cart"
          :cart="cart"
          :order-type="orderType"
          :context-label="cartContextLabel"
          :covers="covers"
          :note="extraNote"
          :note-label="noteLabel"
          :cart-locked="cartLocked"
          :pending-order-number="pendingOrderNumber"
          :item-subtotal="cartSubtotal"
          :server-summary="pendingOrderSummary"
          :customer="selectedCustomer"
          :submitting="submitting"
          :applying-discount="applyingDiscount"
          :discount-error="discountError"
          :online="isOnline"
          @update:covers="covers = $event"
          @update:note="extraNote = $event"
          @quantity="adjustQuantity"
          @remove="removeLine"
          @clear="requestClearDraft"
          @discount="applyDiscountToCart"
          @customer="customerModalOpen = true"
          @send="sendOrderToKitchen"
          @pay="openDirectPayment"
        />

        <button
          v-if="!mobileCartOpen"
          type="button"
          class="pos-mobile-cart md:hidden fixed z-30 bottom-4 inset-x-4 min-h-[56px] rounded-2xl bg-primary-800 text-white px-4 shadow-xl flex items-center justify-between gap-3 font-black"
          @click="mobileCartOpen = true"
        >
          <span>🛒 {{ t('backoffice.pos.cart.mobileCart', { count: cart.length }) }}</span>
          <span class="tabular-nums">{{ formatMoney(pendingOrderSummary?.total ?? cartSubtotal, currency) }}</span>
        </button>

        <Teleport to="body">
          <div v-if="mobileCartOpen" class="md:hidden fixed inset-0 z-40">
            <div class="absolute inset-0 bg-black/50" @click="mobileCartOpen = false" />
            <div class="absolute inset-x-0 bottom-0 h-[88vh] rounded-t-3xl overflow-hidden bg-white dark:bg-surface shadow-2xl">
              <button
                type="button"
                class="absolute top-2 end-2 z-10 w-11 h-11 rounded-full bg-stone-100 dark:bg-gray-800 flex items-center justify-center"
                :aria-label="t('backoffice.pos.close')"
                @click="mobileCartOpen = false"
              >
                <AppIcon name="close" />
              </button>
              <POSCartPanel
                :cart="cart"
                :order-type="orderType"
                :context-label="cartContextLabel"
                :covers="covers"
                :note="extraNote"
                :note-label="noteLabel"
                :cart-locked="cartLocked"
                :pending-order-number="pendingOrderNumber"
                :item-subtotal="cartSubtotal"
                :server-summary="pendingOrderSummary"
                :customer="selectedCustomer"
                :submitting="submitting"
                :applying-discount="applyingDiscount"
                :discount-error="discountError"
                :online="isOnline"
                @update:covers="covers = $event"
                @update:note="extraNote = $event"
                @quantity="adjustQuantity"
                @remove="removeLine"
                @clear="requestClearDraft"
                @discount="applyDiscountToCart"
                @customer="customerModalOpen = true"
                @send="sendOrderToKitchen"
                @pay="openDirectPayment"
              />
            </div>
          </div>
        </Teleport>
      </div>
    </main>

    <DiningExtrasModal
      :item="(extrasModalItem as DiningExtrasItem | null)"
      @confirm="onExtrasConfirm"
      @close="extrasModalItem = null"
    />
    <DiningOrderDetailModal
      :order-id="selectedOrderId"
      :tables="tables"
      :branch-id="branchId"
      @close="onOrderDetailClosed"
      @changed="loadActiveOrders(); loadTables()"
    />
    <POSCustomerModal
      :open="customerModalOpen"
      :branch-id="branchId"
      :selected-customer-id="selectedCustomer?.id ?? null"
      @close="customerModalOpen = false"
      @select="selectCustomer"
      @clear="clearCustomer"
    />
    <POSPaymentModal
      :open="paymentOpen"
      :order="directPaymentOrder"
      :branch-id="branchId"
      @close="paymentOpen = false"
      @paid="onDirectPaymentCompleted"
    />
    <PinGuardModal
      v-if="showDiscountPinGuard"
      :min-level="60"
      :title="t('backoffice.pos.discountPinGuard.title')"
      :message="t('backoffice.pos.discountPinGuard.message')"
      :loading="applyingDiscount"
      :error-message="discountError"
      @approved="onDiscountPinApproved"
      @cancel="showDiscountPinGuard = false"
    />
  </div>
</template>

<style scoped>
.pos-order-grid {
  display: grid;
  grid-template-columns: 8.75rem minmax(0, 1fr) 24rem;
  grid-template-areas: "categories menu cart";
}
.pos-category-rail { grid-area: categories; }
.pos-menu { grid-area: menu; }
.pos-cart { grid-area: cart; }
.pos-products-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(155px, 1fr));
  gap: 0.75rem;
}

@media (max-width: 1279px) {
  .pos-order-grid {
    grid-template-columns: minmax(0, 1fr) 22rem;
    grid-template-rows: auto minmax(0, 1fr);
    grid-template-areas:
      "categories cart"
      "menu cart";
  }
  .pos-category-rail {
    display: flex;
    gap: 0.375rem;
    overflow-x: auto;
    overflow-y: hidden;
    border-inline-end: 0;
    border-bottom: 1px solid rgb(231 229 228);
  }
  .pos-category-button {
    width: auto;
    min-width: max-content;
    margin-top: 0;
  }
}

@media (max-width: 767px) {
  .pos-order-grid {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    grid-template-areas:
      "categories"
      "menu";
  }
  .pos-cart { display: none; }
  .pos-products-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
