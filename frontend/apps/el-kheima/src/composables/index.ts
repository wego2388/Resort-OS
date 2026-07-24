/**
 * composables/index.ts — نقطة تصدير مركزية لكل composables الخاصة بـ el-kheima
 *
 * أي composable يُضاف تحت هذا المجلد لازم يُصدَّر من هنا عشان باقي الـ views
 * تقدر تستوردها بشكل موحّد بدل direct imports متفرقة.
 */

export { useSmartBack } from './useSmartBack'
export { useStaffLocaleSync } from './useStaffLocaleSync'
