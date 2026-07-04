/**
 * usePrintDocument — shared POS receipt/ticket printing helper.
 *
 * Real POS/thermal-printer software auto-triggers the print dialog instead of
 * making the cashier manually hit Ctrl+P in a new tab. It also has to survive
 * the browser's popup blocker silently eating `window.open()` — before this
 * composable existed, RestaurantPOSView and CafePOSView had no fallback at
 * all: a blocked popup meant the receipt silently vanished with no error
 * shown to the cashier and no way to retrieve it. BeachPOSView already had a
 * forced-download fallback; this generalizes that behavior to all three POS
 * screens and adds the auto-print-dialog step to all of them.
 */
export interface PrintOutcome {
  /** true if a new tab/window opened and print() was invoked on it. */
  printed: boolean
  /** true if the popup was blocked and we fell back to a forced download. */
  downloadedInstead: boolean
}

const REVOKE_DELAY_MS = 60_000 // give the popup/download time to load before freeing the blob URL

export function usePrintDocument() {
  /** Opens a PDF blob for printing; falls back to a forced download if the
   * popup is blocked. Never throws — printing a receipt must never block the
   * sale itself, but callers can inspect the returned outcome to warn the
   * cashier when the popup was blocked. */
  function printBlob(blob: Blob, downloadFilename: string): PrintOutcome {
    const url = URL.createObjectURL(blob)
    const revoke = () => URL.revokeObjectURL(url)

    const win = window.open(url, '_blank')
    if (win) {
      // Auto-open the print dialog once the PDF has actually loaded — some
      // browsers render PDFs in a plugin viewer that fires `load` late, so we
      // still guard the print() call in case it's not ready/allowed yet.
      win.onload = () => {
        try {
          win.print()
        } catch {
          // some browsers restrict programmatic print() on cross-origin/blob
          // documents — the cashier still has the tab open to print manually
        }
      }
      setTimeout(revoke, REVOKE_DELAY_MS)
      return { printed: true, downloadedInstead: false }
    }

    // Popup blocked — force a download so the receipt isn't silently lost.
    const a = document.createElement('a')
    a.href = url
    a.download = downloadFilename
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(revoke, REVOKE_DELAY_MS)
    return { printed: false, downloadedInstead: true }
  }

  return { printBlob }
}
