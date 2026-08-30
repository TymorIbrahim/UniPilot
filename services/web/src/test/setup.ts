import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jsdom implements no layout, so it ships no scrollIntoView. Any component that
// scrolls a ref into view on mount (AdvisorPage's message list) throws without it.
Element.prototype.scrollIntoView = () => {}

afterEach(() => {
  cleanup()
  localStorage.clear()
})

// JSDOM implements no layout, so it ships no ResizeObserver. Components that
// measure themselves — the course rows watch for overflow to decide whether to
// show their scroll arrows — need a stub to render at all under test.
if (!('ResizeObserver' in globalThis)) {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
}
