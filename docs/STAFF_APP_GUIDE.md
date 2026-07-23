# El Kheima Resort OS — Staff App Guide

> Find your role below. Read only your section.
> Arabic version: `docs/STAFF_APP_GUIDE_AR.md`
> App URL: `https://[your-resort-domain]/login`

---

## Quick Role Finder

| Your Job Title | Your Role | Jump To |
|---|---|---|
| Resort Manager / Owner | `admin` / `manager` | [→ Manager](#manager--admin) |
| Finance / Accounting | `accountant` | [→ Accountant](#accountant) |
| HR Manager | `hr_manager` | [→ HR Manager](#hr_manager) |
| Front Desk / Supervisor | `supervisor` | [→ Supervisor](#supervisor) |
| Front Desk / Receptionist | `receptionist` | [→ Receptionist](#receptionist) |
| Beach Cashier / POS | `cashier` | [→ Cashier](#cashier) |
| Waiter / Floor Service | `waiter` | [→ Waiter](#waiter) |
| Chef / Kitchen Staff | `chef` / `kitchen` | [→ Kitchen](#chef--kitchen) |
| Inventory / Purchasing | `supervisor` | [→ Inventory](#inventory--purchasing-supervisor) |
| Timeshare Agent | `timeshare_agent` | [→ Timeshare Agent](#timeshare_agent) |
| Employee (self-service) | `employee` | [→ Employee](#employee) |

---

## First Day — All Roles

1. Open the app link and enter your email + temporary password.
2. You will be forced to change your password. Choose something you will
   remember — minimum 8 characters.
3. **Accountant, hr\_manager, admin, super\_admin:** after changing your
   password you will be taken to the 2FA setup screen. Scan the QR code with
   Google Authenticator or Authy. Write down the recovery codes and keep them
   safe. You will need a 6-digit code from the app every time you log in.
4. After setup you land on your home screen automatically.

---

## manager / admin

**Home screen:** `/admin/dashboard`

### Daily tasks

- **Morning:** review Dashboard → today's revenue, occupancy, alerts.
- **During the day:** approve pending purchase requests (Inventory → Purchase
  Requests), review open maintenance work orders.
- **End of day:** check shift reports (Finance → Shifts), review audit log for
  any anomalies.

### Your screens

| Screen | Path | What you do there |
|---|---|---|
| Dashboard | Admin → Dashboard | Live revenue, occupancy, KPIs |
| Analytics | Admin → Analytics | Trends, occupancy charts, energy |
| Finance | Admin → Finance | Accounts, journal entries, cost centers |
| Shifts | Admin → Finance → Shifts | Open/close cashier shifts, view reports |
| HR | Admin → HR | Employee list, payroll, attendance |
| Dining Menu | Admin → Dining Menu | Outlets, categories, items, tables |
| Recipes | Admin → Recipes | Item recipes + food cost |
| Food Cost | Admin → Food Cost | Cost report by outlet/period |
| Inventory | Admin → Inventory | Stock, products, suppliers |
| Beach Admin | Admin → Beach Admin | Beach locations, B2B contracts |
| CRM | Admin → CRM | Customers, leads, campaigns |
| Timeshare | Admin → Timeshare | Contracts, installments, visits |
| Maintenance | Admin → Maintenance | Assets, work orders, schedules |
| Leasing | Admin → Leasing | Lease contracts, payments |
| Settings | Admin → Settings | Branch settings |
| Permissions | Admin → Permissions | Grant/deny specific permissions |
| Audit Log | Admin → Super Admin → Audit | All sensitive events |
| QR Codes | Admin → QR Codes | Generate table/location QR codes |

### Things that need manager approval

These actions require your PIN approval or step-up confirmation when a
lower-level staff member requests them:

- Voiding a posted payment (Finance)
- Applying a discount above the outlet's configured threshold
- Cancelling a booking after check-in
- Approving a purchase request
- Approving leave requests
- Approving payroll runs

### Tips

- Shift reports auto-generate when a cashier closes their shift — you only
  need to review, not create them.
- Global settings (system-wide) are managed in **Super Admin Panel → Settings**
  and require step-up authentication.

---

## accountant

**Home screen:** `/admin/dashboard`

### Daily tasks

- Review Finance → Shifts for completed shift settlements.
- Post journal entries for daily revenue allocation.
- Check Finance → Folios for any outstanding guest balances.
- Monitor ETA e-invoice queue (Finance → E-Invoice).

### Your screens

| Screen | Path | What you do there |
|---|---|---|
| Finance | Admin → Finance | Accounts, journal entries, exchange rates |
| Folios | Admin → Finance → Folios | Guest billing folios |
| Cost Centers | Admin → Finance → Cost Centers | Cost center allocations |
| Shift Reports | Admin → Finance → Shifts | Shift settlement reports |
| Trial Balance | Admin → Finance → Reports | Trial balance, income statement |
| E-Invoice (ETA) | Admin → E-Invoice | Egyptian Tax Authority invoices |
| Depreciation | Admin → Finance → Depreciation | Fixed asset depreciation runs |
| Bank Accounts | Admin → Finance → Bank Accounts | Reconciliation |
| Discounts | Admin → Finance → Discounts | Discount rules configuration |

### Requires manager approval

- Closing an accounting period (Finance → Periods)
- Voiding a posted payment

### Important

- You must have 2FA enabled. If you skip 2FA setup, every API call will fail
  with 403 and screens will appear empty — this is expected, not a bug.
- ETA invoices: the system queues them automatically after payment. Your job is
  to monitor status and handle rejections.

---

## hr\_manager

**Home screen:** `/admin/hr`

### Daily tasks

- Review today's attendance (HR → Attendance).
- Process any pending leave requests (HR → Leave Requests).
- Check salary advances expiring this month.

### Your screens

| Screen | Path | What you do there |
|---|---|---|
| Employees | Admin → HR → Employees | Add/edit employee records |
| Attendance | Admin → HR → Attendance | Daily attendance, punch records |
| Import Attendance | Admin → HR → Attendance → Import | Upload Excel from biometric device |
| Leave Requests | Admin → HR → Leave Requests | Approve or reject leaves |
| Leave Types | Admin → HR → Leave Types | Configure leave categories |
| Payroll | Admin → HR → Payroll | Monthly payroll runs |
| Payslips | Admin → HR → Employees → Payslip | Per-employee payslip |
| Salary Advances | Admin → HR → Salary Advances | Advances and deductions |
| Penalties | Admin → HR → Penalties | Penalty records |
| Rota | Admin → HR → Rota | Shift scheduling and templates |
| Tax Config | Admin → HR → Config | Tax brackets, social insurance |
| Leaderboard | Admin → HR → Leaderboard | Staff performance ranking |

### Requires manager (admin) approval

- Running a payroll (generates payslips — requires admin approval before
  locking the run)
- Linking an employee to a system user account

### Tips

- Importing attendance: export from the biometric device as Excel, then
  HR → Attendance → Import Excel. The system maps by employee code.
- Leave balance is calculated automatically per leave type configuration.

---

## supervisor

**Home screen:** `/ops/rooms`

### Daily tasks

- Check rooms status (Ops → Rooms) — which rooms are clean, occupied, dirty.
- Review open maintenance work orders.
- Approve or escalate housekeeping tasks.

### Your screens

| Screen | Path | What you do there |
|---|---|---|
| Rooms | Ops → Rooms | Room status grid |
| Reception | Ops → Reception | Front desk overview |
| Bookings | Ops → Bookings | Reservation list |
| Housekeeping | Ops → Housekeeping | Task assignment and status |
| Maintenance | Admin → Maintenance | Work orders, assets |
| Inventory | Admin → Inventory | Stock counts, purchase requests |
| Leasing | Admin → Leasing | Lease contracts |

### Requires manager approval

- Approving a purchase order (manager final approval)
- Cancelling a confirmed booking

---

## receptionist

**Home screen:** `/ops/reception`

### Daily tasks

1. Check today's arrivals — Ops → Bookings → filter by today's check-in date.
2. Check-in arriving guests — find booking → click Check-In → confirm.
3. Check-out departing guests — find booking → click Check-Out → settle folio
   if outstanding balance exists.
4. Handle room assignments and early/late check-in requests.
5. End of day: report any no-shows to the manager.

### Your screens

| Screen | Path | What you do there |
|---|---|---|
| Reception | Ops → Reception | Check-in / check-out dashboard |
| Bookings | Ops → Bookings | All reservations, create new booking |
| Rooms | Ops → Rooms | Room availability and status |
| Housekeeping | Ops → Housekeeping | Report room issues |
| Guest Folio | via Booking → Folio | Charges and payments for a guest |

### Requires manager approval

- Applying a complimentary room (zero-rate folio charge)
- Cancelling a booking with a penalty waiver
- Checking in a walk-in without a booking (non-standard)

### Common situations

| Situation | What to do |
|---|---|
| Guest already checked in, wrong room | Ops → Rooms → move room — call manager first |
| Guest requests early check-in | Ops → Bookings → booking → Early/Late flag |
| Outstanding balance at checkout | Finance → Folios → settle before completing checkout |
| System shows room occupied but guest checked out | Ops → Rooms → manually mark clean — report to supervisor |

---

## cashier

**Home screen:** `/pos/beach`

### Daily tasks

1. **Start of shift:** POS → Shift → Open Shift. Enter opening cash amount.
2. **During shift:** process beach transactions (Beach POS), issue receipts.
3. **End of shift:** POS → Shift → Close Shift. Count cash, enter closing
   amounts per currency, submit report.

### Your screens

| Screen | Path | What you do there |
|---|---|---|
| Beach POS | POS → Beach | Sell beach services, umbrellas, tickets |
| Beach Map | POS → Beach Map | Live map of locations |
| Dining POS | POS → Dining | Table orders (if assigned) |
| Shift Dashboard | POS → Shift | Open/close shift, cash movements |

### Requires manager/supervisor approval

- **Voiding a transaction** after it is posted — scan QR or call manager for
  PIN approval
- Applying a discount not on the standard price list
- Cash movements (adding/removing cash from the drawer mid-shift) — enter
  reason, manager notified automatically

### Tips

- B2B (company) customers: select B2B Checkin. The system checks the contract
  quota automatically.
- Offline mode: if the connection drops, transactions queue locally and sync
  when reconnected. You will see an orange sync indicator.
- **Never close the shift tab without completing the cash count.** An
  incomplete shift cannot be closed remotely.

---

## waiter

**Home screen:** `/pos/dining`

### Daily tasks

1. Open the Dining POS.
2. Select a table or create a takeaway order.
3. Add items → send to kitchen (the KDS screen in the kitchen updates
   automatically).
4. When the guest is ready to pay, hand off to the cashier or process payment
   directly if you have cashier permissions.

### Your screens

| Screen | Path | What you do there |
|---|---|---|
| Dining POS | POS → Dining | Tables, orders, send to kitchen |
| KDS (view) | KDS → Dining | Monitor kitchen ticket status |

### Requires manager approval

- **Voiding an order item** that has already been sent to the kitchen —
  requires manager PIN
- Applying a discount above the outlet limit
- Splitting a bill after payment is already posted

### Tips

- Extras and modifiers: when adding an item, a modal appears for extras
  (e.g. no onions, extra sauce). Select before sending.
- Held orders: you can hold an order (save without sending) if the guest is
  not ready.
- Transfer table: Dining POS → order → Transfer — moves all items to another
  table.
- Guest alerts: guests at QR-enabled tables can ring a bell or request the
  bill — a notification appears on your screen.

---

## chef / kitchen

**Home screen:** `/kds/dining`

### Daily tasks

1. KDS screen loads automatically — shows all open kitchen tickets.
2. When you start preparing a ticket: tap → **In Progress**.
3. When ready: tap → **Done**.
4. Items marked Done disappear from the active queue.

### Your screens

| Screen | Path | What you do there |
|---|---|---|
| Kitchen Display (KDS) | KDS → Dining | All active kitchen tickets |

### Filter by station

The KDS shows tickets for all stations by default. To see only your station
(Hot, Bar, Cold, Grill, Dessert), use the station filter tabs at the top.

### Requires manager approval

- You do not initiate any approvals. If an item is cancelled after being sent,
  the waiter or manager handles it.

### Tips

- Colour coding: new tickets appear in white, tickets waiting > X minutes turn
  yellow, then red. The threshold is set by your manager.
- If the screen freezes: refresh the browser (F5). Tickets are server-side —
  nothing is lost.

---

## inventory / purchasing (supervisor)

**Home screen:** `/ops/rooms` (then navigate to Admin → Inventory)

### Daily tasks

- Check low-stock alerts (Inventory → Low Stock).
- Receive delivered goods against open purchase orders.
- Create purchase requests for items that need ordering.

### Your screens

| Screen | Path | What you do there |
|---|---|---|
| Products | Admin → Inventory → Products | Product catalogue, stock levels |
| Stock Movements | Admin → Inventory → Movements | In/out stock transactions |
| Purchase Requests | Admin → Inventory → Purchase Requests | Request items for approval |
| Purchase Orders | Admin → Inventory → Purchase Orders | Confirmed orders to suppliers |
| Stock Counts | Admin → Inventory → Stock Counts | Physical count reconciliation |
| Suppliers | Admin → Inventory → Suppliers | Supplier list and contacts |
| Categories | Admin → Inventory → Categories | Product categories |
| Warehouses | Admin → Inventory → Warehouses | Storage locations |
| Food Cost | Admin → Food Cost | Cost report linked to recipes |
| Recipes | Admin → Recipes | Item ingredient lists + costs |

### Requires manager approval

- **Approving a purchase request** → manager converts it to a purchase order
- **Submitting a stock count** → manager approves the variance before stock
  is adjusted
- Writing off damaged goods → notify manager, who posts the journal entry

### Workflow: ordering new stock

1. Inventory → Purchase Requests → New Request.
2. Add items + quantities + preferred supplier.
3. Submit — the manager receives a notification to approve.
4. Once approved, a Purchase Order is created automatically.
5. When goods arrive, open the PO → mark items received → stock updates.

### Recipes and food cost

- Admin → Recipes: link ingredients (inventory products) to menu items.
- Each ingredient quantity + cost is saved. The system calculates theoretical
  food cost automatically.
- Admin → Food Cost: compare theoretical vs actual cost per outlet/period.

---

## timeshare\_agent

**Home screen:** `/admin/timeshare`

### Daily tasks

- Review upcoming visits (Timeshare → Upcoming Visits).
- Process installment payments for today's due amounts.
- Update visit status after guest check-in.

### Your screens

| Screen | Path | What you do there |
|---|---|---|
| Contracts | Admin → Timeshare → Contracts | All timeshare contracts |
| Installments | Admin → Timeshare → Installments | Payment schedule, collect payment |
| Visits | Admin → Timeshare → Visits | Book and manage unit visits |
| Units | Admin → Timeshare → Units | Available unit types and weeks |
| Waitlist | Admin → Timeshare → Waitlist | Guests waiting for specific weeks |
| Sales Dashboard | Admin → Timeshare → Sales Dashboard | Pipeline and performance |
| Calendar | Admin → Timeshare → Calendar | Visual week availability |
| CRM | Admin → CRM | Customer profiles, leads, interactions |

### Requires manager approval

- Cancelling a contract
- Waiving a late payment penalty
- Transferring a unit between contracts

### Tips

- Installment payments: Timeshare → Installments → find due item → Pay.
  Choose payment method (cash / card / transfer).
- After collecting payment, the folio updates automatically.
- Survey: after a visit completes, a WhatsApp survey can be sent automatically
  if configured. You can also trigger it manually from Visits → Send Survey.

---

## employee

**Home screen:** `/portal/attendance`

### Your screens

| Screen | Path | What you do there |
|---|---|---|
| Attendance | Portal → Attendance | View your punch records, punch in/out |
| Leave Requests | Portal → Leaves | Submit a leave request |
| Payslips | Portal → Payroll | View your monthly payslips |
| Profile | Portal → Profile | Update your personal info and language |

### How to request a leave

1. Portal → Leaves → New Request.
2. Select leave type, start date, end date, notes.
3. Submit. Your HR manager will approve or reject it.
4. You receive a notification when the status changes.

### Requires approval

Everything in your portal that affects payroll or schedule requires HR manager
or manager approval:
- Leave requests
- Salary advance requests (if available)

### Tips

- Language: Portal → Profile → change your preferred language. The app
  switches immediately.
- Payslips are available after payroll is run each month. If you don't see
  your payslip, HR has not yet processed this month's run.

---

## Common Issues (All Roles)

| Problem | Solution |
|---|---|
| Screen shows empty / all zeros | Your session may have expired. Log out and log in again. If you have 2FA required and haven't set it up, go to `/2fa-setup` |
| "403 Forbidden" on an action | You don't have permission for this action. Contact your manager |
| TOTP code rejected | Make sure your phone time is correct (Settings → Auto time). TOTP codes are time-based |
| Transaction not showing after posting | Refresh the page. If still missing after 1 minute, report to your supervisor |
| App offline / can't connect | Check your internet. Beach POS has offline mode — orange sync icon means transactions are queued and will sync automatically |
| Forgot password | Go to `/forgot-password`. An email will be sent with a reset link |
| Lost TOTP device | Contact your manager or super-admin — they will deactivate your account and create a new one for you |

---

*App version: Resort OS 2026-07 | For technical issues contact your system administrator.*
