/**
 * useOrderDiscount — shared "apply best active discount rule" action for
 * dining orders.
 *
 * `POST /dining/orders/{id}/discount` — no request body, the server evaluates
 * every active `ConditionalDiscount` (finance module — flat/percentage/
 * combo_fixed_price, optionally scoped to outlet/category/item and/or a
 * time-of-day "Happy Hour" window) and applies the best-matching one to the
 * order, returning the updated order with `discount_amount`/`total`
 * recalculated. There is no manual amount entry — the cashier does not pick a
 * rule, the engine does.
 *
 * DINING_CUTOVER_PLAN.md Batch 6 (2026-07-13): used to take a `module`
 * param ('restaurant' | 'cafe' | 'dining') since restaurant/cafe had their
 * own parallel `.../orders/{id}/discount` endpoints with the identical
 * contract — both deleted, dining is the only caller left, so this is now
 * hardcoded to the one endpoint that still exists.
 */
import { ref } from 'vue'
import { api } from '../api/client'

export function useOrderDiscount() {
  const applyingDiscount = ref(false)
  const discountError = ref('')

  /** Applies the best active discount rule to `orderId` and returns the
   * server's updated order representation. Throws on failure — callers
   * decide how to surface `discountError` (toast, inline message, ...). */
  async function applyDiscount(orderId: number): Promise<any> {
    discountError.value = ''
    applyingDiscount.value = true
    try {
      const { data } = await api.post(`/api/v1/dining/orders/${orderId}/discount`, {})
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
