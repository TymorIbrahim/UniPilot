import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n'
import { ShelfScroller } from './ShelfScroller'

/** JSDOM has no layout, so overflow has to be declared rather than measured. */
function setOverflow(el: HTMLElement, { scrollWidth = 3740, clientWidth = 1038 } = {}) {
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scrollWidth })
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: clientWidth })
}

function renderScroller(children = <div>card</div>) {
  const { container } = render(
    <I18nProvider>
      <ShelfScroller label="ML chain">{children}</ShelfScroller>
    </I18nProvider>,
  )
  return container.querySelector('div[role="group"]') as HTMLElement
}

describe('ShelfScroller', () => {
  beforeEach(() => {
    localStorage.setItem('unipilot_locale', 'en')
    document.documentElement.dir = 'ltr'
  })

  it('carries no arrows when the row fits', () => {
    renderScroller()

    expect(screen.queryByRole('button', { name: /scroll/i })).not.toBeInTheDocument()
  })

  it('exposes the row to assistive technology by its requirement name', () => {
    renderScroller()

    expect(screen.getByRole('group', { name: 'ML chain' })).toBeInTheDocument()
  })

  it('scrolls towards the end when asked to go forward', async () => {
    const user = userEvent.setup()
    const scroller = renderScroller()
    setOverflow(scroller)
    const scrollBy = vi.fn()
    scroller.scrollBy = scrollBy as unknown as typeof scroller.scrollBy
    scroller.dispatchEvent(new Event('scroll'))

    const forward = await screen.findByRole('button', { name: /scroll forward/i })
    await user.click(forward)

    expect(scrollBy).toHaveBeenCalledWith(
      expect.objectContaining({ left: expect.any(Number), behavior: 'smooth' }),
    )
    expect(scrollBy.mock.calls[0][0].left).toBeGreaterThan(0)
  })

  it('reverses the scroll direction in a right-to-left page', async () => {
    // `scrollLeft` runs negative in RTL, so a fixed positive delta would send
    // the "forward" arrow backwards.
    localStorage.setItem('unipilot_locale', 'he')
    const user = userEvent.setup()
    const scroller = renderScroller()
    setOverflow(scroller)
    const scrollBy = vi.fn()
    scroller.scrollBy = scrollBy as unknown as typeof scroller.scrollBy
    scroller.dispatchEvent(new Event('scroll'))

    const forward = await screen.findByRole('button', { name: /גלילה קדימה/ })
    await user.click(forward)

    expect(scrollBy.mock.calls[0][0].left).toBeLessThan(0)
  })

  it('disables the back arrow at the start of the row', async () => {
    const scroller = renderScroller()
    setOverflow(scroller)
    scroller.dispatchEvent(new Event('scroll'))

    expect(await screen.findByRole('button', { name: /scroll back/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /scroll forward/i })).toBeEnabled()
  })

  it('disables the forward arrow once the end is reached', async () => {
    const scroller = renderScroller()
    setOverflow(scroller)
    scroller.scrollLeft = 3740 - 1038
    scroller.dispatchEvent(new Event('scroll'))

    expect(await screen.findByRole('button', { name: /scroll forward/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /scroll back/i })).toBeEnabled()
  })
})
