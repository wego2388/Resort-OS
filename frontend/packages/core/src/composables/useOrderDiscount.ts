/**
 * useOrderDiscount — shared "apply best active discount rule" action for
 * dining orders.
 *
 * `POST /dining/orders/{id}/discount` — the server evaluates every active
 * `ConditionalDiscount` (finance module — flat/percentage/combo_fixed_price,
 * optionally scoped to outlet/category/item and/or a time-of-day "Happy
 * Hour" window) and applies the best-matching one to the order, returning
 * the updated order with `discount_amount`/`total` recalculated. There is no
 * manual amount entry — the cashier does not pick a rule, the engine does.
 *
 * PIN approval (Mohamed, 2026-07-13): the cashier role has zero discount
 * authority at all — `core.services.resolve_pin_approval(min_approver_level=60)`
 * gates the request server-side exactly like item void, so any acting user
 * below manager level must supply `approverUserId`/`approverPin`. This
 * mirrors `DiningOrderDetailModal.vue`'s void flow: callers should show
 * `PinGuardModal` (`min-level={60}`) before calling `applyDiscount`, which
 * self-qualifies silently (no PIN needed) for manager+ and otherwise
 * collects an approver — the same PIN-approval mechanism used everywhere
 * else, not a second one.
 *
 * DINING_CUTOVER_PLAN.md Batch 6 (2026-07-13): used to take a `module`
 * param ('restaurant' | 'cafe' | 'dining') since restaurant/cafe had their
 * own parallel `.../orders/{id}/discount` endpoints with the identical
 * contract — both deleted, dining is the only caller left, so this is now
 * hardcoded to the one endpoint that still exists.
 */
import { ref } from 'vue'
import { api } from '../api/client'

export interface DiscountApprover {
  approverUserId: number | null
  approverPin: string | null
}

export function useOrderDiscount() {
  const applyingDiscount = ref(false)
  const discountError = ref('')

  /** Applies the best active discount rule to `orderId` and returns the
   * server's updated order representation. `approver` carries the PIN-approval
   * payload from `PinGuardModal`'s `approved` event (both fields `null` when
   * the acting user self-qualifies as manager+). Throws on failure — callers
   * decide how to surface `discountError` (toast, inline message, ...). */
  async function applyDiscount(orderId: number, approver?: DiscountApprover): Promise<any> {
    discountError.value = ''
    applyingDiscount.value = true
    try {
      const body = approver?.approverUserId
        ? { approver_user_id: approver.approverUserId, approver_pin: approver.approverPin }
        : {}
      const { data } = await api.post(`/api/v1/dining/orders/${orderId}/discount`, body)
      return data
    } catch (e: any) {
      discountError.value = e?.response?.data?.detail ?? 'فشل تطبيق الخصم'
      throw e
    } finally {
      applyingDiscount.value = false
    }
  }

  return { applyingDiscount, discountError, applyDiscount }
}
