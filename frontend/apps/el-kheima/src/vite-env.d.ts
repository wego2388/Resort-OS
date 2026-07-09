/// <reference types="vite/client" />

// window.QRCode — مكتبة qrcode@1.5.3 بتتحمّل lazy من CDN في QRGeneratorView
// (script injection)، مش موجودة كـ npm package — بنعرّفها هنا عشان vue-tsc
// ما يطلعش error على window.QRCode.toCanvas(...)
interface Window {
  QRCode?: {
    toCanvas(
      canvas: HTMLCanvasElement,
      text: string,
      options?: { width?: number; margin?: number },
    ): Promise<void>
    toDataURL(text: string, options?: object): Promise<string>
  }
}
