// All API endpoints — mirrors backend routes
export const ENDPOINTS = {
  auth: {
    login: '/api/v1/auth/login',
    refresh: '/api/v1/auth/refresh',
    me: '/api/v1/auth/me',
    setup2fa: '/api/v1/auth/2fa/setup',
    enable2fa: '/api/v1/auth/2fa/enable',
    disable2fa: '/api/v1/auth/2fa/disable',
    passwordResetRequest: '/api/v1/auth/password-reset/request',
    passwordResetConfirm: '/api/v1/auth/password-reset/confirm',
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
    pinSwitch: '/api/v1/pins/switch',
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
  // Unified dining module — replaced the old separate restaurant:/cafe:
  // blocks entirely (DINING_CUTOVER_PLAN.md Batch 6, 2026-07-13). outlet_id-
  // scoped paths mirror app/modules/dining/api/router.py exactly.
  dining: {
    outlets: '/api/v1/dining/outlets',
    outlet: (outletId: number) => `/api/v1/dining/outlets/${outletId}`,
    categories: (outletId: number) => `/api/v1/dining/outlets/${outletId}/categories`,
    category: (categoryId: number) => `/api/v1/dining/categories/${categoryId}`,
    items: (outletId: number) => `/api/v1/dining/outlets/${outletId}/items`,
    item: (itemId: number) => `/api/v1/dining/items/${itemId}`,
    extraGroups: (itemId: number) => `/api/v1/dining/items/${itemId}/extra-groups`,
    extraGroup: (groupId: number) => `/api/v1/dining/extra-groups/${groupId}`,
    variants: (itemId: number) => `/api/v1/dining/items/${itemId}/variants`,
    variant: (variantId: number) => `/api/v1/dining/variants/${variantId}`,
    tables: (outletId: number) => `/api/v1/dining/outlets/${outletId}/tables`,
    table: (tableId: number) => `/api/v1/dining/tables/${tableId}`,
    tableGrid: (tableId: number) => `/api/v1/dining/tables/${tableId}/grid`,
    orders: '/api/v1/dining/orders',
    order: (orderId: number) => `/api/v1/dining/orders/${orderId}`,
    outletOrders: (outletId: number) => `/api/v1/dining/outlets/${outletId}/orders`,
    outletOrdersHold: (outletId: number) => `/api/v1/dining/outlets/${outletId}/orders/hold`,
    outletOrdersHeld: (outletId: number) => `/api/v1/dining/outlets/${outletId}/orders/held`,
    orderItems: (orderId: number) => `/api/v1/dining/orders/${orderId}/items`,
    orderItemVoid: (orderId: number, itemId: number) => `/api/v1/dining/orders/${orderId}/items/${itemId}/void`,
    orderItemRefund: (orderId: number, itemId: number) => `/api/v1/dining/orders/${orderId}/items/${itemId}/refund`,
    orderItemStatus: (orderId: number, itemId: number) => `/api/v1/dining/orders/${orderId}/items/${itemId}/status`,
    orderStatus: (orderId: number) => `/api/v1/dining/orders/${orderId}/status`,
    orderTransfer: (orderId: number) => `/api/v1/dining/orders/${orderId}/transfer`,
    orderDiscount: (orderId: number) => `/api/v1/dining/orders/${orderId}/discount`,
    receipt: (orderId: number) => `/api/v1/dining/orders/${orderId}/receipt`,
    kitchenTickets: '/api/v1/dining/kitchen/tickets',
    ticketStatus: (ticketId: number) => `/api/v1/dining/kitchen/tickets/${ticketId}/status`,
    kdsWs: (branchId: number) => `/api/v1/dining/ws/kds/${branchId}`,
    tablesWs: (branchId: number) => `/api/v1/dining/ws/tables/${branchId}`,
    salesReport: (outletId: number) => `/api/v1/dining/outlets/${outletId}/reports/sales`,
    foodCostReport: (outletId: number) => `/api/v1/dining/outlets/${outletId}/reports/food-cost`,
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
    shiftReportPdf: (id: number) => `/api/v1/finance/shifts/${id}/report/pdf`,
    shiftInvoices: (id: number) => `/api/v1/finance/shifts/${id}/invoices`,
    shiftClose: (id: number) => `/api/v1/finance/shifts/${id}/close`,
    shiftHandoverNote: '/api/v1/finance/shifts/handover-note',
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
    // Full dashboard aggregate (revenue_30d + hr + maintenance + crm + inventory + reviews)
    dashboard: '/api/v1/analytics/dashboard',
    // Occupancy by month — ?branch_id=&month=&year=
    occupancy: '/api/v1/analytics/occupancy',
    // HR summary (active employees + last payroll) — ?branch_id=
    hr: '/api/v1/analytics/hr',
    // Maintenance KPIs (open/critical work orders) — ?branch_id=
    maintenance: '/api/v1/analytics/maintenance',
    // CRM pipeline (customers + opportunities by stage) — ?branch_id=
    crm: '/api/v1/analytics/crm',
    // Inventory alerts (low-stock + out-of-stock counts) — ?branch_id=
    inventory: '/api/v1/analytics/inventory',
    // Utility readings (energy/water/gas) — GET list, POST create
    utilities: '/api/v1/analytics/utilities',
    // Energy KPIs (cost per kWh/guest) — ?branch_id=&period=YYYY-MM
    energy: '/api/v1/analytics/energy',
    // Guest reviews list — ?branch_id= (published only, unless booking_id/timeshare_visit_id provided)
    reviews: '/api/v1/analytics/reviews',
    // Per-category review insights (GSS score breakdown) — ?branch_id=
    reviewInsights: '/api/v1/analytics/reviews/insights',
    // Submit a guest review via survey JWT token — ?token=
    reviewSubmit: '/api/v1/analytics/reviews/submit',
    // Generate survey token for a PMS booking — GET /analytics/reviews/survey-token/{booking_id}
    reviewSurveyToken: (bookingId: number) => `/api/v1/analytics/reviews/survey-token/${bookingId}`,
    // Generate survey token for a timeshare visit
    reviewTimeshareSurveyToken: (visitId: number) => `/api/v1/analytics/reviews/survey-token/timeshare/${visitId}`,
    // Queue WhatsApp survey delivery for a timeshare visit
    reviewTimeshareSurveySend: (visitId: number) => `/api/v1/analytics/reviews/survey-token/timeshare/${visitId}/send`,
  },
}
