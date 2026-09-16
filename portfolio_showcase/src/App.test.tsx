import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { demoEvents, navItems } from './content'

afterEach(() => {
  vi.useRealTimers()
})

describe('CoursePilot portfolio showcase', () => {
  it('renders the core narrative and all navigation anchors', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { name: /面向教师备课场景的智能 Agent 平台/ }),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Port 稳定后拆成两个核心/ })).toBeInTheDocument()

    navItems.forEach((item) => {
      const link = screen.getByRole('link', { name: item.label })
      expect(link).toHaveAttribute('href', `#${item.id}`)
    })
  })

  it('renders verified material without placeholder labels', () => {
    render(<App />)
    expect(screen.queryByText('示例内容')).not.toBeInTheDocument()
    expect(screen.getByText('Hybrid Recall@10')).toBeInTheDocument()
    expect(screen.getByText(/P18 正式内容质量 Gate 未通过/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /CourseRAG 仓库/ })).toHaveAttribute(
      'href',
      'https://github.com/meo0306/course-rag',
    )
  })

  it('switches between workflow scenarios with accessible tabs', async () => {
    const user = userEvent.setup()
    render(<App />)

    const slidesTab = screen.getByRole('tab', { name: 'PPT' })
    await user.click(slidesTab)

    expect(slidesTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('从 Slide Architecture 到可编辑 PPTX')).toBeInTheDocument()
    expect(screen.getByText('Editable Slides · PPTX')).toBeInTheDocument()
  })

  it('plays and resets the deterministic demo in the expected order', async () => {
    vi.useFakeTimers()
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: /开始演示/ }))
    await act(async () => {
      vi.advanceTimersByTime(demoEvents.reduce((total, event) => total + event.delay, 0))
    })

    const demoTimeline = within(screen.getByTestId('demo-events'))
    const labels = demoEvents.map((event) => demoTimeline.getByText(event.label))
    labels.forEach((label) => expect(label).toBeInTheDocument())
    expect(screen.getByText('Replay completed')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /重新演示/ }))
    expect(screen.getByText('Replay running')).toBeInTheDocument()
  })

  it('exposes the reduced-motion state to the page and skips motion setup', () => {
    render(<App />)
    expect(document.querySelector('[data-reduced-motion="true"]')).toBeInTheDocument()
  })
})
