import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

const testStorage = new Map()
Object.defineProperty(window, 'localStorage', {
  configurable: true,
  value: {
    getItem: (key) => testStorage.has(key) ? testStorage.get(key) : null,
    setItem: (key, value) => testStorage.set(key, String(value)),
    removeItem: (key) => testStorage.delete(key),
    clear: () => testStorage.clear(),
  },
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.localStorage.clear()
  window.history.replaceState({}, '', '/overview')
})
