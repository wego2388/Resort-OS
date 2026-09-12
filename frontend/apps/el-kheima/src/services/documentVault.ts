import { api } from '@resort-os/core'

export function formatDocumentSize(sizeBytes: number): string {
  if (sizeBytes < 1024) return `${sizeBytes} B`
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
}

export async function downloadPrivateDocument(url: string, filename: string): Promise<void> {
  const response = await api.get<Blob>(url, { responseType: 'blob' })
  const objectUrl = URL.createObjectURL(response.data)
  try {
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = filename || 'document'
    anchor.rel = 'noopener'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    // Safari can cancel a download when the object URL is revoked in the same
    // task as anchor.click(). A short delay is still prompt cleanup and lets
    // every supported browser claim the blob first.
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000)
  }
}
