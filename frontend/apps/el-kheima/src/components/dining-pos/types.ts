import type { DiningExtrasItem } from '../DiningExtrasModal.vue'

export type OrderType = 'dine_in' | 'takeaway' | 'delivery' | 'room_service'
export type PaymentMethod = 'cash' | 'card' | 'room' | 'wallet'
export type POSWorkspace = 'tables' | 'order' | 'active'

export interface DiningOutlet {
  id: number
  name: string
  name_ar: string | null
  outlet_type: string
  is_active: boolean
}

export interface DiningCategory {
  id: number
  name: string
  name_ar: string | null
  sort_order: number
}

export interface VenueTable {
  id: number
  table_number: string
  status: string
  capacity: number
  section: string | null
  active_order_id: number | null
  active_order_number: string | null
  active_order_total: number | string | null
  active_covers: number | null
  occupied_at: string | null
  order_status: string | null
  active_order_outlet_id: number | null
  // هوية الضيف القاعد على الطاولة دي (2026-08-03، طلب Mohamed) — من
  // DiningOrder.guest_name/guest_phone بتاعة الطلب النشط.
  active_order_guest_name: string | null
  active_order_guest_phone: string | null
}

export interface DiningItemRow extends DiningExtrasItem {
  is_available: boolean
  category_id: number | null
  station: string
}

export interface CartLine {
  key: string
  itemId: number
  outletId: number          // الـ outlet اللي الصنف ده منه — بيتحدّد وقت الإضافة، لعرض السلة مجمّعة فقط (cross-outlet)
  outletName: string        // اسم الـ outlet للعرض في السلة (grouping header)
  variantId: number | null
  variantLabel: string | null
  name: string
  nameAr: string | null
  unitPrice: number
  quantity: number
  notes: string
  extraIds: number[]
  extraTexts: Record<number, string>
  extrasLabel: string
}

export interface ActiveOrder {
  id: number
  outlet_id: number
  order_number: string
  status: string
  table_id: number | null
  order_type: OrderType
  total: number | string
  guests_count: number
  created_at: string
  // هوية الضيف (2026-08-03) — راجع VenueTable.active_order_guest_name
  guest_name: string | null
  guest_phone: string | null
}

export interface POSCustomer {
  id: number
  full_name: string
  phone: string | null
  segment: string
  visits_count: number
  blacklisted: boolean
  blacklist_reason: string | null
  group_name?: string | null
  group_discount_percentage?: number | null
}

export interface OrderItemExtra {
  id: number
  extra_id: number | null
  extra_name: string
  extra_name_ar?: string | null
  price_addition: number | string
  text_value: string | null
}

export interface OrderItem {
  id: number
  item_id: number
  name: string
  name_ar?: string | null
  unit_price: number | string
  quantity: number
  notes: string | null
  status: string
  extras: OrderItemExtra[]
  voided_reason: string | null
}

export interface DiningOrderDetail {
  id: number
  outlet_id: number
  order_number: string
  status: string
  order_type: OrderType
  table_id: number | null
  created_at: string
  guests_count: number
  payment_method: PaymentMethod | 'split' | null
  subtotal: number | string
  vat_amount: number | string
  service_charge: number | string
  delivery_fee?: number | string
  discount_amount: number | string
  refunded_amount: number | string
  total: number | string
  customer_id: number | null
  // هوية الضيف (2026-08-03) — راجع VenueTable.active_order_guest_name
  guest_name: string | null
  guest_phone: string | null
  items: OrderItem[]
}

export interface CheckedInRoom {
  id: number
  name: string
  guestName: string
  bookingNumber: string
  checkOut: string
}
