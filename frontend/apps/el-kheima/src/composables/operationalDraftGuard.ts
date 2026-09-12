export type OperationalDraftExitReason = 'navigate' | 'logout' | 'operator-switch' | 'app-update'

type OperationalDraftGuard = (reason: OperationalDraftExitReason) => Promise<boolean>

let activeGuard: OperationalDraftGuard | null = null

/**
 * يربط شاشة التشغيل الحالية (POS مثلًا) بالـlayout ومودال تبديل المشغّل.
 * التسجيل singleton عمدًا: لا توجد أكثر من شاشة route نشطة في نفس اللحظة.
 */
export function registerOperationalDraftGuard(guard: OperationalDraftGuard): () => void {
  activeGuard = guard
  return () => {
    if (activeGuard === guard) activeGuard = null
  }
}

/** يطلب من الشاشة النشطة إنهاء draft بأمان قبل تغيير هوية التشغيل. */
export async function confirmOperationalDraftExit(
  reason: OperationalDraftExitReason,
): Promise<boolean> {
  return activeGuard ? activeGuard(reason) : true
}
