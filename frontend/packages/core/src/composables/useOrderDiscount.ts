/**
 * useOrderDiscount — shared "apply best active discount rule" action for
 * restaurant/cafe orders.
 *
 * `POST /restaurant/orders/{id}/discount`, `POST /cafe/orders/{id}/discount`,
 * and `POST /dining/orders/{id}/discount` (dining — additive unified module,
 * DINING_CUTOVER_PLAN.md) all share the exact same contract: no request body,
 * the server evaluates every active `ConditionalDiscount` (finance module —
 * flat/percentage/combo_fixed_price, optionally scoped to outlet/category/item
 * and/or a time-of-day "Happy Hour" window) and applies the best-matching one
 * to the order, returning the updated order with `discount_amount`/`total`
 * recalculated. There is no manual amount entry — the cashier does not pick a
 * rule, the engine does.
 *
 * This was previously implemented only inside OrderDetailModal.vue (for an
 * order that already exists and is being reviewed). RestaurantPOSView/
 * CafePOSView need the identical action while a new order is still being
 * built — extracted here so both call sites share one implementation instead
 * of duplicating the discount contract.
 */
import { ref } from 'vue'
import { api } from '../api/client'

export function useOrderDiscount(module: 'restaurant' | 'cafe' | 'dining') {
  const applyingDiscount = ref(false)
  const discountError = ref('')

  /** Applies the best active discount rule to `orderId` and returns the
   * server's updated order representation. Throws on failure — callers
   * decide how to surface `discountError` (toast, inline message, ...). */
  async function applyDiscount(orderId: number): Promise<any> {
    discountError.value = ''
    applyingDiscount.value = true
    try {
      const { data } = await api.post(`/api/v1/${module}/orders/${orderId}/discount`, {})
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
