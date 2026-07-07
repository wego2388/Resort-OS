// All API endpoints — mirrors backend routes
export const ENDPOINTS = {
  auth: {
    login: '/api/v1/auth/login',
    refresh: '/api/v1/auth/refresh',
    me: '/api/v1/auth/me',
    setup2fa: '/api/v1/auth/2fa/setup',
    enable2fa: '/api/v1/auth/2fa/enable',
    disable2fa: '/api/v1/auth/2fa/disable',
  },
  core: {
    branches: '/api/v1/branches',
    notifications: '/api/v1/notifications',
    // Guest alerts (نادِ الجرسون / هات الفاتورة) — راجع
    // backend/app/modules/core/models.py::GuestAlert
    alerts: '/api/v1/alerts',
    alertStatus: (alertId: number) => `/api/v1/alerts/${alertId}/status`,
    // PIN تشغيلي — راجع backend/app/modules/core/models.py::PinCredential
    pinApprovers: '/api/v1/pins/approvers',
  },
  beach: {
    inventory: '/api/v1/beach/inventory',
    summary: '/api/v1/beach/summary',
    sell: '/api/v1/beach/sell',
    transactions: '/api/v1/beach/transactions',
    ticket: (txId: number) => `/api/v1/beach/transactions/${txId}/ticket`,
    b2bContracts: '/api/v1/beach/b2b-contracts',
    b2bCheckin: '/api/v1/beach/b2b-checkin',
    reservations: '/api/v1/beach/reservations',
    reservationPublic: (id: number) => `/api/v1/beach/reservations/${id}/public`,
    reservationCheckin: (id: number) => `/api/v1/beach/reservations/${id}/checkin`,
    b2bQuotaStatus: '/api/v1/beach/b2b-contracts/status',
    liveDashboard: '/api/v1/beach/live-dashboard',
    eodReport: '/api/v1/beach/eod-report',
    eodReportPdf: '/api/v1/beach/eod-report/pdf',
    // خريطة الشاطئ الحية (شمسية/برجولة فعلية) — راجع
    // backend/app/modules/beach/models.py::BeachLocation
    locations: '/api/v1/beach/locations',
    locationsBulk: '/api/v1/beach/locations/bulk',
    locationsReduce: '/api/v1/beach/locations/reduce',
    locationUpdate: (id: number) => `/api/v1/beach/locations/${id}`,
    locationCheckin: (id: number) => `/api/v1/beach/locations/${id}/checkin`,
    locationCheckout: (id: number) => `/api/v1/beach/locations/${id}/checkout`,
  },
  restaurant: {
    tables: '/api/v1/restaurant/tables',
    menu: '/api/v1/restaurant/menu/items',
    categories: '/api/v1/restaurant/menu/categories',
    orders: '/api/v1/restaurant/orders',
    orderSync: '/api/v1/restaurant/orders/sync',
    receipt: (orderId: number) => `/api/v1/restaurant/orders/${orderId}/receipt`,
  },
  cafe: {
    menu: '/api/v1/cafe/items',
    categories: '/api/v1/cafe/categories',
    orders: '/api/v1/cafe/orders',
  },
  pms: {
    rooms: '/api/v1/pms/rooms',
    bookings: '/api/v1/pms/bookings',
    housekeeping: '/api/v1/pms/housekeeping/tasks',
    checkout: (bookingId: number) => `/api/v1/pms/bookings/${bookingId}/checkout`,
  },
  finance: {
    accounts: '/api/v1/finance/accounts',
    checks: '/api/v1/finance/checks',
    periods: '/api/v1/finance/periods',
    folios: '/api/v1/finance/folios',
    shiftsOpen: '/api/v1/finance/shifts/open',
    shiftsCurrent: '/api/v1/finance/shifts/current',
    shifts: '/api/v1/finance/shifts',
    shiftReport: (id: number) => `/api/v1/finance/shifts/${id}/report`,
    shiftClose: (id: number) => `/api/v1/finance/shifts/${id}/close`,
    costCenterReport: '/api/v1/finance/cost-centers/report',
    etaInvoices: '/api/v1/finance/eta/invoices',
    etaInvoice: (id: number) => `/api/v1/finance/eta/invoices/${id}`,
  },
  hr: {
    employees: '/api/v1/hr/employees',
    payroll: '/api/v1/hr/payroll/runs',
    attendance: '/api/v1/hr/attendance',
    leaves: '/api/v1/hr/leaves',
  },
  inventory: {
    products: '/api/v1/inventory/products',
    movements: '/api/v1/inventory/movements',
    purchaseOrders: '/api/v1/inventory/purchase-orders',
    lowStock: '/api/v1/inventory/low-stock',
  },
  analytics: {
    // Note: there is no per-branch-id-in-path `/analytics/dashboard/{id}` route
    // on the backend (it's `GET /analytics/dashboard?branch_id=`, a 30-day
    // aggregate, not a "today" snapshot) — DashboardView.vue used to call a URL
    // shape that never matched any real route (always 404, silently swallowed).
    // `dailyStats` below is the real "today's numbers" endpoint and is what the
    // dashboard actually uses now.
    dailyStats: '/api/v1/analytics/daily-stats',
    // DailyStats is a nightly-computed snapshot (Celery beat, crontab hour=1,
    // always computes *yesterday*) — there is structurally no row for *today*
    // until 1am tomorrow. `revenue` computes restaurant/cafe/pms/beach totals
    // live from the source tables for any date range, so the dashboard falls
    // back to it for same-day figures instead of always showing 0.
    revenue: '/api/v1/analytics/revenue',
  },
}
