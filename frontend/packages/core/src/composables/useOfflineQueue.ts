/**
 * useOfflineQueue — Offline POS order queueing (IndexedDB).
 *
 * Contract matches 07-BUSINESS-RULES.md § 9: orders made while offline are
 * queued locally, sent FIFO once back online, and the server's response
 * (fulfilled | partial | rejected) is the source of truth for stock —
 * never the client's stale menu snapshot.
 */
import { ref, onMounted, onUnmounted } from 'vue'
import { openDB, type IDBPDatabase } from 'idb'
import { api } from '../api/client'

const DB_NAME = 'resort-os-offline'
const DB_VERSION = 1
const STORE_PENDING = 'pending_orders'
const STORE_SYNC_LOG = 'sync_log'

export interface PendingOrder {
  localId: string
  branchId: number
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
  status: 'partially_synced' | 'rejected'
  rejectedItems?: RejectedItem[]
  reason?: string
  timestamp: string
}

let dbPromise: Promise<IDBPDatabase> | null = null

function getDb(): Promise<IDBPDatabase> {
  dbPromise ??= openDB(DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORE_PENDING)) {
        const store = db.createObjectStore(STORE_PENDING, { keyPath: 'localId' })
        store.createIndex('by_created', 'createdAt')
      }
      if (!db.objectStoreNames.contains(STORE_SYNC_LOG)) {
        db.createObjectStore(STORE_SYNC_LOG, { keyPath: 'localId' })
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

export function useOfflineQueue() {
  const isOnline = ref(navigator.onLine)
  const pendingCount = ref(0)
  const syncing = ref(false)
  const lastPartialRejection = ref<RejectedItem[] | null>(null)

  async function refreshPendingCount() {
    const db = await getDb()
    pendingCount.value = await db.count(STORE_PENDING)
  }

  async function queueOrder(branchId: number, payload: Record<string, unknown>): Promise<string> {
    const localId = crypto.randomUUID()
    const db = await getDb()
    await db.put(STORE_PENDING, {
      localId, branchId, payload, createdAt: new Date().toISOString(),
    } satisfies PendingOrder)
    await refreshPendingCount()
    return localId
  }

  /** Submit now if online; transparently falls back to the offline queue
   * on network failure. Returns the live order on success, or null if queued. */
  async function submitOrder(branchId: number, payload: Record<string, unknown>) {
    if (!navigator.onLine) {
      await queueOrder(branchId, payload)
      return null
    }
    try {
      const { data } = await api.post(`/api/v1/restaurant/orders?branch_id=${branchId}`, payload)
      return data
    } catch (err) {
      if (isNetworkError(err)) {
        await queueOrder(branchId, payload)
        return null
      }
      throw err
    }
  }

  async function syncPendingOrders() {
    if (!navigator.onLine || syncing.value) return
    syncing.value = true
    try {
      const db = await getDb()
      const pending = (await db.getAllFromIndex(STORE_PENDING, 'by_created')) as PendingOrder[]

      for (const order of pending) {
        let response
        try {
          response = await api.post(
            `/api/v1/restaurant/orders/sync?branch_id=${order.branchId}`,
            { local_id: order.localId, created_offline_at: order.createdAt, ...order.payload },
          )
        } catch (err) {
          if (isNetworkError(err)) break // still offline / server unreachable — keep FIFO order, retry later
          // server explicitly rejected the request shape — log and drop so it doesn't block the queue forever
          await db.put(STORE_SYNC_LOG, {
            localId: order.localId, status: 'rejected',
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
            localId: order.localId, status: 'partially_synced',
            rejectedItems: rejected_items, timestamp: new Date().toISOString(),
          } satisfies SyncLogEntry)
          await db.delete(STORE_PENDING, order.localId)
          lastPartialRejection.value = rejected_items
        } else if (status === 'rejected') {
          await db.put(STORE_SYNC_LOG, {
            localId: order.localId, status: 'rejected',
            rejectedItems: rejected_items, timestamp: new Date().toISOString(),
          } satisfies SyncLogEntry)
          await db.delete(STORE_PENDING, order.localId)
          lastPartialRejection.value = rejected_items
        }
      }
    } finally {
      await refreshPendingCount()
      syncing.value = false
    }
  }

  async function getSyncLog(): Promise<SyncLogEntry[]> {
    const db = await getDb()
    return db.getAll(STORE_SYNC_LOG)
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
