/**
 * owner API types — mirrors backend owner/schemas.py (Phase 3 + 6 + 7).
 * Decision 0004: لا بيانات ضيف شخصية، كل رقم يحمل is_provisional.
 */

export interface PeriodMeta {
  date_from: string
  date_to: string
  is_provisional: boolean
  computed_at: string
}

export interface OccupancyNow {
  occupied_rooms: number
  total_rooms: number
  occupancy_pct: string
  computed_at: string
}

export interface BeachCapacityToday {
  capacity_used: number
  capacity_max: number
  utilisation_pct: string
  inventory_date: string
  note: string
}

export interface B2BReceivableItem {
  contract_id: number
  hotel_name: string
  outstanding: string
  is_overdue: boolean
  credit_limit: string | null
  last_settled_at: string | null
}

export interface TimeshareReceivableItem {
  contract_id: number
  total_overdue: string
  installment_count: number
}

export interface OwnerNowResponse {
  revenue_today: string
  cash_in_drawers: string
  expense_today: string
  b2b_receivables: B2BReceivableItem[]
  b2b_total_outstanding: string
  timeshare_receivables: TimeshareReceivableItem[]
  timeshare_total_overdue: string
  occupancy: OccupancyNow
  beach_capacity: BeachCapacityToday
  period: PeriodMeta
  open_shift_count: number
  credit_account_outstanding: string
  credit_account_count: number
}

export interface CreditReceivableItem {
  account_id: number
  holder_type: 'customer' | 'employee'
  holder_name: string
  current_balance: string
  credit_limit: string
  status: 'active' | 'suspended' | 'closed'
  last_charge_at: string | null
  days_since_last_charge: number | null
  is_overdue: boolean
}

export interface CreditReceivablesResponse {
  branch_id: number
  accounts: CreditReceivableItem[]
  total_outstanding: string
  overdue_count: number
  computed_at: string
}

export interface PeriodSnapshot {
  date_from: string
  date_to: string
  label: string
  total_revenue: string
  total_expense: string
  net_income: string
  is_provisional: boolean
  computed_at: string
}

export interface PeriodComparison {
  current: PeriodSnapshot
  prior: PeriodSnapshot
  revenue_delta: string
  revenue_pct: string | null
  expense_delta: string
  expense_pct: string | null
  net_income_delta: string
  net_income_pct: string | null
  breakdown?: PerformanceBreakdown | null
}

export interface OwnerPerformanceResponse {
  today_vs_yesterday: PeriodComparison
  week_vs_prior_week: PeriodComparison
  month_vs_prior_month: PeriodComparison
  computed_at: string
}

// ─── Phase 6: Sales ──────────────────────────────────────────────────

export interface ItemMetricResponse {
  item_id: number
  name: string
  quantity_sold: number
  revenue: string
  recipe_cost: string | null
  margin_pct: string | null
  margin_amount: string | null
  abc_class: 'A' | 'B' | 'C' | null
  cumulative_pct: string | null
}

export interface SalesPerformanceResponse {
  period_from: string
  period_to: string
  outlet: string
  items: ItemMetricResponse[]
  total_revenue: string
  is_provisional: boolean
  computed_at: string
}

export interface BeachTicketTypeRow {
  tx_type: string
  count: number
  total_amount: string
  avg_unit_price: string
}

export interface BeachPerformanceResponse {
  period_from: string
  period_to: string
  ticket_types: BeachTicketTypeRow[]
  total_revenue: string
  total_count: number
  computed_at: string
}

// ─── Phase 6: Channel Analytics ──────────────────────────────────────

export interface ChannelContractRow {
  contract_id: number
  hotel_name: string
  period_checkins: number
  period_revenue: string
  outstanding: string
  is_overdue: boolean
  credit_limit: string | null
  fnb_attach: string
  fnb_avg_per_checkin: string
}

export interface ChannelAnalyticsResponse {
  period_from: string
  period_to: string
  contracts: ChannelContractRow[]
  total_checkins: number
  total_beach_revenue: string
  total_fnb_attach: string
  computed_at: string
}

// ─── Phase 6: Expense Analytics ──────────────────────────────────────

export interface ExpenseLineResponse {
  account_code: string
  account_name: string
  current_amount: string
  prior_amount: string
  current_pct: string | null
  prior_pct: string | null
  variance_flag: boolean
  variance_delta: string | null
}

export interface PayrollSummary {
  period_year: number
  period_month: number
  total_net: string
  revenue: string
  payroll_pct: string | null
  status: string
}

export interface ExpenseAnalyticsResponse {
  period_from: string
  period_to: string
  prior_from: string
  prior_to: string
  current_revenue: string
  prior_revenue: string
  expense_lines: ExpenseLineResponse[]
  payroll: PayrollSummary | null
  is_provisional: boolean
  computed_at: string
}

// ─── Phase 6: Procurement ────────────────────────────────────────────

export interface SupplierSpendRow {
  supplier_id: number
  supplier_name: string
  total_spend: string
  spend_pct: string
  order_count: number
  concentration_flag: boolean
}

export interface PRPOVarianceRow {
  product_id: number
  product_name: string
  estimated_cost: string
  actual_cost: string
  variance_amount: string
  variance_pct: string | null
}

export interface ProcurementAnalyticsResponse {
  period_from: string
  period_to: string
  total_spend: string
  suppliers: SupplierSpendRow[]
  pr_po_variance: PRPOVarianceRow[]
  computed_at: string
}

// ─── Phase 7: Shift Monitoring ───────────────────────────────────────

export interface CashMovementItem {
  id: number
  movement_type: string
  amount: string
  direction: string | null
  reason: string
  performed_by_name: string
  created_at: string
}

export interface ShiftMonitorItem {
  shift_id: number
  cashier_id: number
  cashier_name: string
  opened_at: string
  opening_float: string
  total_sales: string
  total_cash: string
  expected_cash: string
  invoice_count: number
  variance: string | null
  is_closed: boolean
  cash_movements: CashMovementItem[]
  variance_tier: 'critical' | 'attention' | 'normal'
}

export interface ShiftMonitorResponse {
  branch_id: number
  open_count: number
  shifts: ShiftMonitorItem[]
  computed_at: string
}

// ─── Phase 7: Exceptions ─────────────────────────────────────────────

export interface OwnerExceptionItem {
  exception_id: string
  tier: 'critical' | 'attention' | 'watch'
  category: string
  title: string
  detail: string
  entity_id: number | null
  entity_name: string | null
  impact: string
  confidence: string
  status: 'realized' | 'projected' | 'potential'
  source: string
  score: string
}

export interface ExceptionsResponse {
  critical_count: number
  attention_count: number
  watch_count: number
  exceptions: OwnerExceptionItem[]
  computed_at: string
}

// ─── Phase 7a: Now History (Sparklines) ──────────────────────────────

export interface DaySnapshot {
  day: string
  revenue: string
  expense: string
  cash_in_drawers: string
  occupancy_pct: string
  beach_utilisation_pct: string
  is_provisional: boolean
}

export interface NowHistoryResponse {
  days: DaySnapshot[]
  computed_at: string
}

// ─── Phase 7b: Shift History ─────────────────────────────────────────

export interface ShiftHistoryItem {
  shift_id: number
  cashier_id: number
  cashier_name: string
  opened_at: string
  closed_at: string
  opening_float: string
  total_sales: string
  total_cash: string
  expected_cash: string
  invoice_count: number
  variance: string | null
  cash_movements: CashMovementItem[]
  variance_tier: 'critical' | 'attention' | 'normal'
}

export interface ShiftHistoryResponse {
  branch_id: number
  days: number
  shifts: ShiftHistoryItem[]
  computed_at: string
}

// ─── Phase 7c: HR Summary ────────────────────────────────────────────

export interface EmployeePayrollSummary {
  payroll_run_id: number
  period_year: number
  period_month: number
  gross_salary: string
  net_salary: string
  penalty_deduction: string
  advance_deduction: string
}

export interface EmployeeAttendanceSummary {
  present_days: number
  absent_days: number
  late_days: number
  leave_days: number
  total_working_days: number
}

export interface HREmployeeRow {
  employee_id: number
  full_name: string
  position: string
  department: string | null
  hire_date: string
  status: string
  payroll: EmployeePayrollSummary | null
  attendance_this_month: EmployeeAttendanceSummary | null
}

export interface HRSummaryResponse {
  branch_id: number
  employees: HREmployeeRow[]
  active_count: number
  on_leave_count: number
  total_net_payroll: string
  period_year: number
  period_month: number
  computed_at: string
}

// ─── Phase 7d: Discount Analytics ───────────────────────────────────

export interface DiscountTypeRow {
  type: string
  type_label: string
  order_count: number
  total_amount: string
  pct_of_revenue: string
}

export interface ManualDiscountPerCashier {
  cashier_id: number
  cashier_name: string
  order_count: number
  total_manual_discount: string
}

export interface CustomerGroupMember {
  customer_id: number
  full_name: string
  invoice_count: number
  total_sales: string
}

export interface CustomerGroupDiscountRow {
  group_id: number
  group_name: string
  discount_pct: string
  member_count: number
  total_invoices: number
  total_sales_after_discount: string
  members: CustomerGroupMember[]
}

export interface DiscountAnalyticsResponse {
  period_from: string
  period_to: string
  total_revenue: string
  total_discount: string
  discount_pct_of_revenue: string
  discount_types: DiscountTypeRow[]
  manual_per_cashier: ManualDiscountPerCashier[]
  customer_groups: CustomerGroupDiscountRow[]
  computed_at: string
}

// ─── Phase 7e: Performance Breakdown ────────────────────────────────

export interface PerformanceBreakdown {
  dining_revenue: string | null
  beach_revenue: string | null
  rooms_revenue: string | null
  other_revenue: string | null
}

// ─── Phase 8: تفاصيل التفاصيل (Universal Drill-Down) + بحث عام ─────────

export interface DiningItemTransaction {
  order_id: number
  order_number: string
  outlet_name: string
  order_type: string
  quantity: number
  unit_price: string
  line_total: string
  status: string
  ordered_at: string
}

export interface DiningItemDetailResponse {
  item_id: number
  item_name: string
  period_from: string
  period_to: string
  transactions: DiningItemTransaction[]
  total_quantity: number
  total_revenue: string
  computed_at: string
}

export interface BeachTypeTransaction {
  transaction_id: number
  tx_date: string
  guest_name: string | null
  unit_price: string
  total_amount: string
  cashier_name: string | null
}

export interface BeachTypeDetailResponse {
  tx_type: string
  period_from: string
  period_to: string
  transactions: BeachTypeTransaction[]
  total_count: number
  total_revenue: string
  computed_at: string
}

export interface ExpenseJournalLine {
  entry_id: number
  entry_date: string
  reference: string
  description: string
  amount: string
  source: string | null
  cost_center: string | null
}

export interface ExpenseDetailResponse {
  account_code: string
  account_name: string
  period_from: string
  period_to: string
  lines: ExpenseJournalLine[]
  total_amount: string
  computed_at: string
}

export interface SupplierPurchaseOrder {
  po_id: number
  po_number: string
  status: string
  ordered_at: string
  received_at: string | null
  item_count: number
  total_amount: string
}

export interface SupplierDetailResponse {
  supplier_id: number
  supplier_name: string
  period_from: string
  period_to: string
  orders: SupplierPurchaseOrder[]
  total_amount: string
  computed_at: string
}

// ─── Phase 2/8: المفضلة (Watchlist) ─────────────────────────────────

export interface OwnerWatchlistRead {
  id: number
  owner_user_id: number
  metric_key: string
  display_order: number
  label_override: string | null
  branch_id: number
  created_at: string
  updated_at: string
}

export interface ProductMovement {
  movement_id: number
  movement_type: string
  quantity: string
  unit_cost: string
  warehouse_name: string
  moved_at: string
  notes: string | null
}

export interface ProductDetailResponse {
  product_id: number
  product_name: string
  unit: string
  current_stock: string
  cost_price: string
  period_from: string
  period_to: string
  movements: ProductMovement[]
  total_in: string
  total_out: string
  computed_at: string
}

export interface SearchResultItem {
  entity_type: string
  entity_id: number
  title: string
  subtitle: string | null
  value: string | null
  value_label: string | null
}

export interface OwnerSearchResponse {
  query: string
  results: SearchResultItem[]
  computed_at: string
}
