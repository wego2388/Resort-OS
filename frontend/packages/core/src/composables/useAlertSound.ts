/**
 * useAlertSound — shared Web Audio beep for real-time staff alerts (new KDS
 * ticket, guest call-waiter/request-bill). No external audio file needed.
 * Extracted from DiningKDSView.vue so GuestAlertsBell.vue doesn't silently
 * miss a busy floor — a toast alone is easy to miss when nobody is looking
 * at the screen.
 */
let audioCtx: AudioContext | null = null

export function useAlertSound() {
  function playAlertSound() {
    try {
      if (!audioCtx) audioCtx = new AudioContext()
      const osc = audioCtx.createOscillator()
      const gain = audioCtx.createGain()
      osc.connect(gain)
      gain.connect(audioCtx.destination)
      osc.type = 'sine'
      osc.frequency.setValueAtTime(880, audioCtx.currentTime)
      osc.frequency.setValueAtTime(660, audioCtx.currentTime + 0.1)
      gain.gain.setValueAtTime(0.3, audioCtx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.4)
      osc.start(audioCtx.currentTime)
      osc.stop(audioCtx.currentTime + 0.4)
    } catch {
      // صامت لو المتصفح مش بيدعم AudioContext
    }
  }

  return { playAlertSound }
}
