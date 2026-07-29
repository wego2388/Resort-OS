/**
 * useOfflineQueue — Offline POS order queueing (IndexedDB).
 *
 * Contract matches 07-BUSINESS-RULES.md § 9: orders made while offline are
 * queued locally, sent FIFO once back online, and the server's response
 * (fulfilled | partial | rejected) is the source of truth for stock —
 * never the client's stale menu snapshot.
 *
 * #4: endpoint بقى parameter اختياري (default: restaurant).
 * CafePOSView تمرّر module: 'cafe' وكل حاجة تانية تشتغل تلقائياً.
 *
 * wagdy.md #13/#37: BeachPOSView كان عنده queue محلي منفصل (localStorage،
 * كود مكرر) بدل ما يستخدم الـ composable ده — وكان فيه باج حقيقي فيه: الـ
 * retry بعد انقطاع نت كان بيعيد إرسال نفس البيع من غير أي مفتاح idempotency،
 * فلو الرد ضاع بعد ما السيرفر خصم السعة فعلاً، الـ retry كان يعمل بيع تاني
 * حقيقي (خصم سعة مزدوج). beach مضاف هنا بنفس القفل الأساسي (IndexedDB،
 * FIFO، دعم offline)، لكن endpoint مختلف تمامًا عن restaurant/cafe:
 * - مفيش "order" بعدة أصناف — كل "بيع" مستقل (`/beach/sell` واحد لكل
 *   نوع تذكرة)، فمفيش partial/rejected على مستوى الطلب زي المطعم.
 * - نفس /beach/sell (مش endpoint /sync منفصل) بيقبل local_id اختياري
 *   للـ idempotency — لو نفس local_id اتبعت تاني بيرجع نفس المعاملة القديمة
 *   بدل ما يعمل بيع جديد (راجع beach.services.sell_ticket).
 *
 * DINING_CUTOVER_PLAN.md Batch 1: 'dining' مضاف بنفس عقد restaurant/cafe
 * بالظبط (POST مباشر + /sync بعقد OrderSyncResponse مطابق) — الفرق
 * الوحيد إن مسار dining outlet-scoped (`/dining/outlets/{outlet_id}/orders`)
 * بدل مسار مسطّح، فـ createPath/syncPath بقوا دوال بتاخد outletId اختياري
 * بدل نص ثابت (restaurant/cafe/beach بيتجاهلوه). outletId بيتخزّن مع كل
 * طلب معلّق نفسه — مش قيمة عامة واحدة للطابور كله — عشان لو الكاشير غيّر
 * المنفذ المختار وهو offline، كل طلب يتزامن على المنفذ اللي اتعمل بيه فعليًا.
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { openDB, type IDBPDatabase } from 'idb'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'

const DB_NAME = 'resort-os-offline'
// v3 adds a compound identity scope. A shared terminal may keep valid pending
// work for several employees and branches, but only the current
// user+branch+module scope may see or submit its own records.
const DB_VERSION = 3
const STORE_PENDING = 'pending_orders'
const STORE_SYNC_LOG = 'sync_log'

export type OfflineQueueModule = 'restaurant' | 'cafe' | 'beach' | 'dining'

// كل module وطريقة الـ endpoint بتاعته: restaurant/cafe/dining عندهم "order"
// حقيقي (POST مباشر + /sync منفصل بعقد OrderSyncResponse)، beach عنده بيع
// فردي بس (نفس /sell للاتنين، idempotency عبر local_id في الجسم نفسه).
// دوال بدل نصوص ثابتة عشان dining يقدر يحقن outlet_id جوه المسار.
const MODULE_CONFIG: Record<OfflineQueueModule, {
  createPath: (outletId?: number) => string
  syncPath: (outletId?: number) => string
  hasOrderSync: boolean
}> = {
  restaurant: { createPath: () => 'restaurant/orders', syncPath: () => 'restaurant/orders/sync', hasOrderSync: true },
  cafe:       { createPath: () => 'cafe/orders',       syncPath: () => 'cafe/orders/sync',       hasOrderSync: true },
  beach:      { createPath: () => 'beach/sell',        syncPath: () => 'beach/sell',             hasOrderSync: false },
  dining:     {
    createPath: (outletId) => `dining/outlets/${outletId}/orders`,
    syncPath:   (outletId) => `dining/outlets/${outletId}/orders/sync`,
    hasOrderSync: true,
  },
}

export interface PendingOrder {
  localId: string
  branchId: number
  /**
   * The authenticated employee who created the offline operation.
   *
   * Old records without an owner are deliberately quarantined: attributing
   * them to whoever next signs in would corrupt the audit trail.
   */
  ownerUserId: number | null
  module: OfflineQueueModule   // #4: تمييز وجهة الـ sync
  outletId?: number            // dining فقط — المنفذ اللي اتعمل فيه الطلب ده تحديدًا
  payload: Record<string, unknown>
  createdAt: string
}

export interface RejectedItem {
  item_id: number
  name: string
  reason: string
  available_qty: number
  requested_qty: number
}

export interface SyncLogEntry {
  localId: string
  ownerUserId: number | null
  branchId: number | null
  module: OfflineQueueModule | null
  status: 'partially_synced' | 'rejected'
  rejectedItems?: RejectedItem[]
  reason?: string
  timestamp: string
}

export function isOfflineRecordOwnedBy(
  record: Pick<PendingOrder, 'ownerUserId'>,
  activeUserId: number | null | undefined,
): boolean {
  return activeUserId != null && record.ownerUserId === activeUserId
}

export function isOfflineRecordInScope(
  record: Pick<PendingOrder, 'ownerUserId' | 'branchId' | 'module'>,
  activeUserId: number | null | undefined,
  activeBranchId: number | null | undefined,
  module: OfflineQueueModule,
): boolean {
  return activeUserId != null
    && activeBranchId != null
    && record.ownerUserId === activeUserId
    && record.branchId === activeBranchId
    && record.module === module
}

let dbPromise: Promise<IDBPDatabase> | null = null

function getDb(): Promise<IDBPDatabase> {
  dbPromise ??= openDB(DB_NAME, DB_VERSION, {
    upgrade(db, oldVersion, _newVersion, tx) {
      // ── v1 → إنشاء الـ stores من الصفر ──
      if (oldVersion < 1) {
        const store = db.createObjectStore(STORE_PENDING, { keyPath: 'localId' })
        store.createIndex('by_created', 'createdAt')
        db.createObjectStore(STORE_SYNC_LOG, { keyPath: 'localId' })
      }
      // ── v2 → إضافة حقل module للـ records القديمة (default: 'restaurant') ──
      if (oldVersion < 2) {
        const store = tx.objectStore(STORE_PENDING)
        // IDBPTransaction.objectStore().openCursor() — نعدّل كل record قديم
        void (async () => {
          let cursor = await store.openCursor()
          while (cursor) {
            if (!(cursor.value as any).module) {
              await cursor.update({ ...cursor.value, module: 'restaurant' })
            }
            cursor = await cursor.continue()
          }
        })()
      }
      // ── v3 → user + branch + module scope for safe shared terminals ──
      if (oldVersion < 3) {
        tx.objectStore(STORE_PENDING).createIndex(
          'by_scope', ['ownerUserId', 'branchId', 'module'],
        )
      }
    },
  })
  return dbPromise
}

/** true only for "never reached the server" failures — not 4xx/5xx responses */
function isNetworkError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  const axiosErr = err as { request?: unknown; response?: unknown }
  return !!axiosErr.request && !axiosErr.response
}

// #4: module parameter — default 'restaurant' للـ backward compat
export function useOfflineQueue(module: OfflineQueueModule = 'restaurant') {
  const auth = useAuthStore()
  const cfg = MODULE_CONFIG[module]
  const isOnline = ref(navigator.onLine)
  const pendingCount = ref(0)
  const syncing = ref(false)
  const lastPartialRejection = ref<RejectedItem[] | null>(null)

  async function refreshPendingCount() {
    const activeUserId = auth.user?.id
    const activeBranchId = auth.branchId
    if (activeUserId == null || activeBranchId == null) {
      pendingCount.value = 0
      return
    }

    const db = await getDb()
    const scoped = await db.getAllFromIndex(
      STORE_PENDING,
      'by_scope',
      [activeUserId, activeBranchId, module],
    ) as PendingOrder[]
    pendingCount.value = scoped.length
  }

  async function queueOrder(branchId: number, payload: Record<string, unknown>, outletId?: number): Promise<string> {
    const ownerUserId = auth.user?.id
    if (ownerUserId == null) {
      throw new Error('An authenticated employee is required to queue an offline operation')
    }
    if (auth.branchId == null || branchId !== auth.branchId) {
      throw new Error('The offline operation must match the active branch')
    }

    const localId = crypto.randomUUID()
    const db = await getDb()
    await db.put(STORE_PENDING, {
      localId,
      branchId,
      ownerUserId,
      module,
      outletId,
      payload,
      createdAt: new Date().toISOString(),
    } satisfies PendingOrder)
    await refreshPendingCount()
    return localId
  }

  /** Submit now if online; transparently falls back to the offline queue
   * on network failure. Returns the live order on success, or null if queued.
   * outletId مطلوب فعليًا لـ module: 'dining' بس (مسار outlet-scoped) —
   * الموديولات التانية بتتجاهله. */
  async function submitOrder(branchId: number, payload: Record<string, unknown>, outletId?: number) {
    if (!navigator.onLine) {
      await queueOrder(branchId, payload, outletId)
      return null
    }
    try {
      const { data } = await api.post(`/api/v1/${cfg.createPath(outletId)}?branch_id=${branchId}`, payload)
      return data
    } catch (err) {
      if (isNetworkError(err)) {
        await queueOrder(branchId, payload, outletId)
        return null
      }
      throw err
    }
  }

  async function syncPendingOrders() {
    if (!navigator.onLine || syncing.value) return
    const syncOwnerUserId = auth.user?.id
    const syncBranchId = auth.branchId
    if (syncOwnerUserId == null || syncBranchId == null) return

    syncing.value = true
    try {
      const db = await getDb()
      const pending = await db.getAllFromIndex(
        STORE_PENDING,
        'by_scope',
        [syncOwnerUserId, syncBranchId, module],
      ) as PendingOrder[]

      for (const order of pending) {
        // A PIN or branch switch can happen while a request is in flight. Stop
        // before sending the next record under a different authorization
        // context. Records remain quarantined for their original scope.
        if (
          auth.user?.id !== syncOwnerUserId
          || auth.branchId !== syncBranchId
        ) break

        // beach: بيع فردي بسيط — نفس /beach/sell (مش /sync منفصل)، idempotency
        // عبر local_id في الجسم، ومفيش partial/rejected على مستوى الطلب
        // (كل بيع إما نجح أو اترفض بالكامل، مفيش "أصناف" داخله).
        if (!cfg.hasOrderSync) {
          try {
            await api.post(
              `/api/v1/${cfg.syncPath(order.outletId)}?branch_id=${order.branchId}`,
              { ...order.payload, local_id: order.localId },
            )
            await db.delete(STORE_PENDING, order.localId)
          } catch (err) {
            if (isNetworkError(err)) break // لسه offline فعليًا — سيبه في الطابور، حاول تاني بعدين
            // السيرفر رفضه صراحة (زي تجاوز السعة بعد ما اتحفظ محليًا) — امسحه
            // عشان ميقفلش الطابور للأبد، وسجّله في sync_log عشان الكاشير يراجعه
            await db.put(STORE_SYNC_LOG, {
              localId: order.localId,
              ownerUserId: order.ownerUserId,
              branchId: order.branchId,
              module: order.module,
              status: 'rejected',
              reason: 'invalid_request', timestamp: new Date().toISOString(),
            } satisfies SyncLogEntry)
            await db.delete(STORE_PENDING, order.localId)
          }
          continue
        }

        let response
        try {
          response = await api.post(
            `/api/v1/${cfg.syncPath(order.outletId)}?branch_id=${order.branchId}`,
            { local_id: order.localId, created_offline_at: order.createdAt, ...order.payload },
          )
        } catch (err) {
          if (isNetworkError(err)) break
          await db.put(STORE_SYNC_LOG, {
            localId: order.localId,
            ownerUserId: order.ownerUserId,
            branchId: order.branchId,
            module: order.module,
            status: 'rejected',
            reason: 'invalid_request', timestamp: new Date().toISOString(),
          } satisfies SyncLogEntry)
          await db.delete(STORE_PENDING, order.localId)
          continue
        }

        const { status, rejected_items } = response.data
        if (status === 'fulfilled') {
          await db.delete(STORE_PENDING, order.localId)
        } else if (status === 'partial') {
          await db.put(STORE_SYNC_LOG, {
            localId: order.localId,
            ownerUserId: order.ownerUserId,
            branchId: order.branchId,
            module: order.module,
            status: 'partially_synced',
            rejectedItems: rejected_items, timestamp: new Date().toISOString(),
          } satisfies SyncLogEntry)
          await db.delete(STORE_PENDING, order.localId)
          lastPartialRejection.value = rejected_items
        } else if (status === 'rejected') {
          await db.put(STORE_SYNC_LOG, {
            localId: order.localId,
            ownerUserId: order.ownerUserId,
            branchId: order.branchId,
            module: order.module,
            status: 'rejected',
            rejectedItems: rejected_items, timestamp: new Date().toISOString(),
          } satisfies SyncLogEntry)
          await db.delete(STORE_PENDING, order.localId)
          lastPartialRejection.value = rejected_items
        }
      }
    } finally {
      await refreshPendingCount()
      syncing.value = false
      if (
        navigator.onLine
        && (
          auth.user?.id !== syncOwnerUserId
          || auth.branchId !== syncBranchId
        )
      ) {
        void syncPendingOrders()
      }
    }
  }

  async function getSyncLog(): Promise<SyncLogEntry[]> {
    const activeUserId = auth.user?.id
    const activeBranchId = auth.branchId
    if (activeUserId == null || activeBranchId == null) return []

    const db = await getDb()
    const entries = await db.getAll(STORE_SYNC_LOG) as SyncLogEntry[]
    return entries.filter(
      entry => entry.ownerUserId === activeUserId
        && entry.branchId === activeBranchId
        && entry.module === module,
    )
  }

  function handleOnline() {
    isOnline.value = true
    syncPendingOrders()
  }
  function handleOffline() {
    isOnline.value = false
  }

  let pollTimer: ReturnType<typeof setInterval> | null = null

  onMounted(() => {
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    refreshPendingCount()
    if (navigator.onLine) syncPendingOrders()
    // safety-net poll — covers cases where 'online' never fires reliably
    // (some browsers/OSes) but connectivity is actually back
    pollTimer = setInterval(() => {
      if (navigator.onLine && pendingCount.value > 0) syncPendingOrders()
    }, 30_000)
  })

  watch(
    () => [auth.user?.id, auth.branchId] as const,
    () => {
      lastPartialRejection.value = null
      void refreshPendingCount().then(() => {
        if (navigator.onLine) void syncPendingOrders()
      })
    },
  )

  onUnmounted(() => {
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
    if (pollTimer) clearInterval(pollTimer)
  })

  return {
    isOnline,
    pendingCount,
    syncing,
    lastPartialRejection,
    submitOrder,
    syncPendingOrders,
    getSyncLog,
  }
}
