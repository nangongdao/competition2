import { useEffect, useMemo, useState } from 'react'


export interface VirtualWindow {
  startIndex: number
  endIndex: number
  offsetY: number
  totalHeight: number
}


/**
 * 计算虚拟滚动窗口。
 *
 * 长会议的字幕历史可达数千条，全量渲染会让主线程卡死。
 * 只渲染视口内的条目，其余以空白填充保持滚动条比例真实。
 *
 * @param total 条目总数。
 * @param scrollTop 容器滚动位置。
 * @param viewportHeight 容器可视高度。
 * @param itemHeight 估算的条目高度。
 * @param overscan 视口外额外渲染的条目数（缓冲滚动时的空白）。
 * @returns 视口窗口参数。
 */
export function computeVirtualWindow(
  total: number,
  scrollTop: number,
  viewportHeight: number,
  itemHeight: number,
  overscan = 8,
): VirtualWindow {
  if (total <= 0 || itemHeight <= 0) {
    return { startIndex: 0, endIndex: 0, offsetY: 0, totalHeight: 0 }
  }

  const visibleCount = Math.ceil(viewportHeight / itemHeight)
  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan)
  const endIndex = Math.min(total, startIndex + visibleCount + overscan * 2)
  return {
    startIndex,
    endIndex,
    offsetY: startIndex * itemHeight,
    totalHeight: total * itemHeight,
  }
}


/**
 * React hook 封装虚拟滚动窗口。
 *
 * @param entries 全量条目（渲染前倒序排列）。
 * @param viewportHeight 容器可视高度。
 * @param itemHeight 估算的条目高度。
 * @returns 可见子集、顶部占位高度、总高度与滚动处理器。
 */
export function useVirtualizedSubtitles<T>(
  entries: readonly T[],
  viewportHeight: number,
  itemHeight: number,
): {
  visible: readonly T[]
  offsetY: number
  totalHeight: number
  onScroll: (event: { currentTarget: { scrollTop: number } }) => void
} {
  const [scrollTop, setScrollTop] = useState(0)

  useEffect(() => {
    setScrollTop(0)
  }, [entries.length])

  const window = useMemo(
    () => computeVirtualWindow(entries.length, scrollTop, viewportHeight, itemHeight),
    [entries.length, scrollTop, viewportHeight, itemHeight],
  )

  return {
    visible: entries.slice(window.startIndex, window.endIndex),
    offsetY: window.offsetY,
    totalHeight: window.totalHeight,
    onScroll: (event) => setScrollTop(event.currentTarget.scrollTop),
  }
}
