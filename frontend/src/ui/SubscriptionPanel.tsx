import React, { useEffect, useState } from 'react'

import {
  Check,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react'

import type { UiText } from '../i18n'
import {
  fetchSubscription,
  resetSubscriptionUsage,
  updateSubscriptionPlan,
  type SubscriptionPlan,
  type SubscriptionSnapshot,
} from '../subscription/subscription-api'


export interface SubscriptionPanelProps {
  isOpen: boolean
  uiText: UiText
  onClose: () => void
}


export const SubscriptionPanel: React.FC<SubscriptionPanelProps> = ({
  isOpen,
  uiText,
  onClose,
}) => {
  const text = uiText.subscription
  const [subscription, setSubscription] = useState<SubscriptionSnapshot | null>(null)
  const [plans, setPlans] = useState<SubscriptionPlan[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) {
      return
    }
    setError(null)
    void loadSubscription()
  }, [isOpen])

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

  if (!isOpen) {
    return null
  }

  const loadSubscription = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchSubscription()
      setSubscription(result?.subscription ?? null)
      setPlans(result?.plans ?? [])
    } catch {
      setError(text.loadFailed)
    } finally {
      setLoading(false)
    }
  }

  const handleSwitchPlan = async (plan: string): Promise<void> => {
    setError(null)
    const updated = await updateSubscriptionPlan(plan)
    if (!updated) {
      setError(text.switchFailed)
      return
    }
    setSubscription(updated)
  }

  const handleReset = async (): Promise<void> => {
    setError(null)
    const updated = await resetSubscriptionUsage()
    if (!updated) {
      setError(text.resetFailed)
      return
    }
    setSubscription(updated)
  }

  const usagePercent = subscription && subscription.daily_limit
    ? Math.min(100, Math.round((subscription.daily_used / subscription.daily_limit) * 100))
    : 0

  return (
    <section
      aria-label={text.ariaLabel}
      role="dialog"
      aria-modal="false"
      className="sub-panel"
    >
      <div className="sub-header">
        <div className="sub-title">
          <Sparkles size={18} />
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

      <div className="sub-body">
        {error ? (
          <div className="glossary-error">{error}</div>
        ) : null}

        {loading ? (
          <div className="sub-loading">
            <LoaderCircle size={18} className="spin" />
            {text.loading}
          </div>
        ) : !subscription ? (
          <div className="sub-empty">{text.noData}</div>
        ) : (
          <div className="sub-current">
            <div className="sub-current-plan">
              <Sparkles size={16} />
              <span>{subscription.plan_name}</span>
              <span className="sub-price">{subscription.price}</span>
            </div>

            <div className="sub-usage">
              <div className="sub-usage-label">
                <span>{text.dailyUsage}</span>
                <span>
                  {subscription.daily_limit === null
                    ? `${subscription.daily_used} / -`
                    : `${subscription.daily_used} / ${subscription.daily_limit}`}
                </span>
              </div>
              <div className="sub-usage-bar">
                <div
                  className={`sub-usage-fill${subscription.daily_remaining === 0 ? ' sub-usage-full' : ''}`}
                  style={{ width: `${usagePercent}%` }}
                />
              </div>
              <div className="sub-usage-hint">
                {subscription.daily_limit === null
                  ? text.unlimited
                  : subscription.daily_remaining === 0
                    ? text.limitReached
                    : `${text.remaining} ${subscription.daily_remaining}`}
              </div>
            </div>

            <div className="sub-section-label">{text.plans}</div>
            <div className="sub-plan-list">
              {plans.map((plan) => (
                <div
                  key={plan.key}
                  className={`sub-plan-card${plan.key === subscription.plan ? ' sub-plan-active' : ''}`}
                >
                  <div className="sub-plan-card-header">
                    <span className="sub-plan-name">{plan.name}</span>
                    <span className="sub-plan-price">{plan.price}</span>
                  </div>
                  <div className="sub-plan-features">
                    {plan.features.map((feature) => (
                      <div key={feature} className="sub-plan-feature">
                        <Check size={13} />
                        {feature}
                      </div>
                    ))}
                  </div>
                  {plan.key === subscription.plan ? (
                    <div className="sub-plan-current-badge">{text.currentPlan}</div>
                  ) : (
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ width: '100%', minHeight: '34px', marginTop: '8px' }}
                      onClick={() => {
                        void handleSwitchPlan(plan.key)
                      }}
                    >
                      {text.switchPlan}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="sub-footer">
        <button
          type="button"
          className="btn-secondary"
          disabled={loading}
          onClick={() => {
            void loadSubscription()
          }}
        >
          <RefreshCw size={15} />
          {text.refresh}
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={loading}
          onClick={() => {
            void handleReset()
          }}
        >
          {text.resetUsage}
        </button>
      </div>
    </section>
  )
}
