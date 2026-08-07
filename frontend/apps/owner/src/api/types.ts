/**
 * owner API types — mirrors backend owner/schemas.py (Phase 3).
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
}

export interface OwnerPerformanceResponse {
  today_vs_yesterday: PeriodComparison
  week_vs_prior_week: PeriodComparison
  month_vs_prior_month: PeriodComparison
  computed_at: string
}
