import React, { useEffect, useMemo, useState } from 'react'

import {
  AudioLines,
  Languages,
  RefreshCw,
  Timer,
  TrendingUp,
  X,
} from 'lucide-react'

import type { RevisionEvent } from '../types'
import type { RevisionTimelinePanelText, UiText } from '../i18n'


interface RevisionTimelinePanelProps {
  events: RevisionEvent[]
  isOpen: boolean
  uiText: UiText
  onClose: () => void
}


/**
 * 阶段 4「修正历史可观测」：展示本次会话累积的修正事件时间线。
 *
 * 每条事件展示：修正类型（识别/翻译）、触发方式、修正来源、耗时、
 * 置信度、以及「修正前 → 修正后」文本对比。事件按时间倒序排列，
 * 上限 200 条（见 AppController._recordRevisionEvent）。
 */
export const RevisionTimelinePanel: React.FC<RevisionTimelinePanelProps> = ({
  events,
  isOpen,
  uiText,
  onClose,
}) => {
  const text = uiText.revisionTimeline
  const [filter, setFilter] = useState<'all' | 'asr_correction' | 'translation_correction'>('all')

  useEffect(() => {
    if (!isOpen) {
      return
    }
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isOpen, onClose])

  const filtered = useMemo(() => {
    if (filter === 'all') {
      return events
    }
    return events.filter((event) => event.reason === filter)
  }, [events, filter])

  const stats = useMemo(() => {
    let asr = 0
    let translation = 0
    for (const event of events) {
      if (event.reason === 'asr_correction') {
        asr += 1
      } else {
        translation += 1
      }
    }
    return { total: events.length, asr, translation }
  }, [events])

  if (!isOpen) {
    return null
  }

  const sourceLabel = (event: RevisionEvent): string | null => {
    if (!event.correctionSource) {
      return null
    }
    return text.sourceLabels[event.correctionSource] ?? event.correctionSource
  }

  const triggerLabel = (event: RevisionEvent): string | null => {
    if (!event.trigger) {
      return null
    }
    return text.triggerLabels[event.trigger] ?? event.trigger
  }

  const minutesAgo = (timestamp: number): string => {
    const minutes = (Date.now() - timestamp) / 60000
    return text.ago(minutes)
  }

  return (
    <section
      aria-label={text.ariaLabel}
      role="dialog"
      aria-modal="false"
      className="revision-timeline-panel"
    >
      <div className="history-header">
        <div className="history-title">
          <TrendingUp size={18} />
          <h3>{text.title}</h3>
        </div>
        <button
          type="button"
          className="btn-secondary"
          style={{ width: 'auto', minHeight: '38px', padding: '0 14px' }}
          onClick={onClose}
        >
          <X size={14} />
          {text.close}
        </button>
      </div>

      <div className="revision-timeline-stats">
        <span>
          <RefreshCw size={13} />
          {text.statTotal}: <strong>{stats.total}</strong>
        </span>
        <span>
          <AudioLines size={13} />
          {text.statAsr}: <strong>{stats.asr}</strong>
        </span>
        <span>
          <Languages size={13} />
          {text.statTranslation}: <strong>{stats.translation}</strong>
        </span>
      </div>

      <div className="revision-timeline-filter">
        {(['all', 'asr_correction', 'translation_correction'] as const).map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={filter === value}
            className={filter === value ? 'active' : ''}
            onClick={() => setFilter(value)}
          >
            {value === 'all'
              ? text.statTotal
              : text.reasonLabels[value]}
          </button>
        ))}
      </div>

      <div className="revision-timeline-list">
        {filtered.length === 0 ? (
          <div className="revision-timeline-empty">{text.empty}</div>
        ) : (
          filtered.map((event) => {
            const source = sourceLabel(event)
            const trigger = triggerLabel(event)
            const isAsr = event.reason === 'asr_correction'
            return (
              <article
                key={event.id}
                className={`revision-timeline-item ${isAsr ? 'asr' : 'translation'}`}
              >
                <div className="revision-timeline-item-meta">
                  <span className={`revision-badge ${isAsr ? 'asr' : 'translation'}`}>
                    {isAsr ? <AudioLines size={12} /> : <Languages size={12} />}
                    {text.reasonLabels[event.reason]}
                  </span>
                  <span className="revision-timeline-time">{minutesAgo(event.timestamp)}</span>
                </div>

                <div className="revision-timeline-item-tags">
                  {event.segmentIndex !== undefined ? (
                    <span className="revision-tag">
                      {text.segmentLabel} #{event.segmentIndex}
                    </span>
                  ) : null}
                  {trigger ? <span className="revision-tag">{trigger}</span> : null}
                  {source ? <span className="revision-tag">{source}</span> : null}
                  {event.latencyMs !== undefined ? (
                    <span className="revision-tag">
                      <Timer size={11} />
                      {text.latencyLabel}: {event.latencyMs}ms
                    </span>
                  ) : null}
                  {event.confidence !== undefined ? (
                    <span className="revision-tag">
                      {text.confidenceLabel}: {event.confidence.toFixed(2)}
                    </span>
                  ) : null}
                </div>

                <div className="revision-timeline-diff">
                  {isAsr && event.sourceText ? (
                    <div className="revision-diff-row">
                      <span className="revision-diff-label">{text.sourceTextLabel}</span>
                      <span className="revision-diff-new">{event.sourceText}</span>
                    </div>
                  ) : null}
                  {!isAsr && event.oldText ? (
                    <div className="revision-diff-row">
                      <span className="revision-diff-label">{text.oldTextLabel}</span>
                      <span className="revision-diff-old">{event.oldText}</span>
                    </div>
                  ) : null}
                  <div className="revision-diff-row">
                    <span className="revision-diff-label">{text.newTextLabel}</span>
                    <span className="revision-diff-new">{event.newText}</span>
                  </div>
                </div>
              </article>
            )
          })
        )}
      </div>
    </section>
  )
}


/** 供测试与外部导入使用的文案类型导出。 */
export type { RevisionTimelinePanelText }
