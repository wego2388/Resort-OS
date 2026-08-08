import { api } from '@resort-os/core'
import type {
  OwnerNowResponse,
  OwnerPerformanceResponse,
  NowHistoryResponse,
  SalesPerformanceResponse,
  BeachPerformanceResponse,
  ChannelAnalyticsResponse,
  ExpenseAnalyticsResponse,
  ProcurementAnalyticsResponse,
  ShiftMonitorResponse,
  ExceptionsResponse,
  ShiftHistoryResponse,
  HRSummaryResponse,
  DiscountAnalyticsResponse,
  CreditReceivablesResponse,
} from './types'

/**
 * owner API client — wraps Phase 3 + 6 + 7 + 7a endpoints.
 * Cache-Control: no-store set server-side — we never cache here either.
 */
export async function fetchOwnerNow(): Promise<OwnerNowResponse> {
  const res = await api.get<OwnerNowResponse>('/api/v1/owner/now')
  return res.data
}

export async function fetchCreditReceivables(): Promise<CreditReceivablesResponse> {
  const res = await api.get<CreditReceivablesResponse>('/api/v1/owner/credit-receivables')
  return res.data
}

export async function fetchOwnerNowHistory(days = 7): Promise<NowHistoryResponse> {
  const res = await api.get<NowHistoryResponse>('/api/v1/owner/now/history', { params: { days } })
  return res.data
}

export async function fetchOwnerPerformance(): Promise<OwnerPerformanceResponse> {
  const res = await api.get<OwnerPerformanceResponse>('/api/v1/owner/performance')
  return res.data
}

export async function fetchSalesPerformance(params?: {
  date_from?: string
  date_to?: string
  outlet?: 'dining' | 'beach' | 'all'
  limit?: number
}): Promise<SalesPerformanceResponse> {
  const res = await api.get<SalesPerformanceResponse>('/api/v1/owner/sales', { params })
  return res.data
}

export async function fetchBeachPerformance(params?: {
  date_from?: string
  date_to?: string
}): Promise<BeachPerformanceResponse> {
  const res = await api.get<BeachPerformanceResponse>('/api/v1/owner/beach-performance', { params })
  return res.data
}

export async function fetchChannelAnalytics(params?: {
  date_from?: string
  date_to?: string
}): Promise<ChannelAnalyticsResponse> {
  const res = await api.get<ChannelAnalyticsResponse>('/api/v1/owner/channel-analytics', { params })
  return res.data
}

export async function fetchExpenseAnalytics(params?: {
  date_from?: string
  date_to?: string
}): Promise<ExpenseAnalyticsResponse> {
  const res = await api.get<ExpenseAnalyticsResponse>('/api/v1/owner/expense-analytics', { params })
  return res.data
}

export async function fetchProcurementAnalytics(params?: {
  date_from?: string
  date_to?: string
}): Promise<ProcurementAnalyticsResponse> {
  const res = await api.get<ProcurementAnalyticsResponse>('/api/v1/owner/procurement-analytics', { params })
  return res.data
}

export async function fetchShiftMonitor(): Promise<ShiftMonitorResponse> {
  const res = await api.get<ShiftMonitorResponse>('/api/v1/owner/shifts')
  return res.data
}

export async function fetchExceptions(): Promise<ExceptionsResponse> {
  const res = await api.get<ExceptionsResponse>('/api/v1/owner/exceptions')
  return res.data
}

export async function fetchShiftHistory(days = 7): Promise<ShiftHistoryResponse> {
  const res = await api.get<ShiftHistoryResponse>('/api/v1/owner/shifts/history', { params: { days } })
  return res.data
}

export async function fetchHRSummary(): Promise<HRSummaryResponse> {
  const res = await api.get<HRSummaryResponse>('/api/v1/owner/hr-summary')
  return res.data
}

export async function fetchDiscountAnalytics(params?: {
  date_from?: string
  date_to?: string
}): Promise<DiscountAnalyticsResponse> {
  const res = await api.get<DiscountAnalyticsResponse>('/api/v1/owner/discount-analytics', { params })
  return res.data
}
