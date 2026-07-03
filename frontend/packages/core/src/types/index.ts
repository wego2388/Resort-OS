export interface User {
  id: number
  username: string
  email: string
  full_name: string
  // Mirrors backend ROLE_LEVELS (app/core/deps.py) — kept as `string` rather than
  // a fixed union because new roles are added there without a frontend release
  // (see CLAUDE.md § 14 rule 5: "role جديد → ROLE_LEVELS في deps.py").
  role: string
  branch_id: number
  // Returned by GET /auth/me (app/modules/core/schemas.py::UserRead). Mandatory
  // for super_admin/accountant server-side (app/core/deps.py::MANDATORY_2FA_ROLES)
  // — the frontend mirrors that gate in useAuthStore.needsTwoFactorSetup so the
  // router can send the user straight to /2fa-setup instead of letting every
  // other API call in the app silently 403 with no explanation.
  two_factor_enabled?: boolean
}

export interface Branch {
  id: number
  name: string
  name_ar: string
  is_active: boolean
}


export interface ApiResponse<T> {
  data: T
  message?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
}

// Beach types
export interface BeachInventory {
  branch_id: number
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

// Restaurant types
export interface MenuCategory {
  id: number
  name: string
  name_ar: string
  sort_order: number
}

export interface MenuItem {
  id: number
  category_id: number
  name: string
  name_ar: string
  price: number
  is_available: boolean
  image_url?: string
}

export interface OrderItem {
  menu_item_id: number
  name: string
  name_ar: string
  quantity: number
  unit_price: number
  notes?: string
}

export interface Order {
  id: number
  table_id?: number
  status: 'pending' | 'preparing' | 'ready' | 'paid' | 'cancelled'
  items: OrderItem[]
  total: number
  covers?: number
  outlet_type: 'restaurant' | 'cafe'
}

// PMS types
export interface Room {
  id: number
  room_number: string
  room_type: string
  status: 'available' | 'occupied' | 'checkout_pending' | 'maintenance' | 'dirty'
  floor: number
}

export interface Booking {
  id: number
  guest_name: string
  room_ids: number[]
  check_in: string
  check_out: string
  status: 'confirmed' | 'checked_in' | 'checked_out' | 'cancelled' | 'no_show'
  total_amount: number
}

// KDS types
export interface KitchenTicket {
  id: number
  order_id: number
  table_number?: string
  items: { name: string; name_ar: string; quantity: number; notes?: string }[]
  status: 'pending' | 'preparing' | 'ready'
  created_at: string
  station: string
}
