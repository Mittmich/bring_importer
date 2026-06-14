// Vitest setup file. jsdom provides most of what we need, but a few
// browser APIs that the helpers may reach for are missing in jsdom
// 25. Stub them here so the helpers don't throw on first use.
//
// Tests that don't need these can ignore the stubs.

import { vi } from 'vitest';

// matchMedia — jsdom doesn't ship it; Bootstrap collapse uses it.
if (typeof window !== 'undefined' && typeof window.matchMedia === 'undefined') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

// crypto.subtle — jsdom may not include the WebCrypto subtle API in
// some Node versions; stub as no-op.
if (typeof globalThis.crypto === 'undefined') {
  Object.defineProperty(globalThis, 'crypto', {
    value: { subtle: { digest: () => Promise.resolve(new ArrayBuffer(0)) } },
  });
}
