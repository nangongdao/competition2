import React, { useEffect, useRef, useState } from 'react'

import {
  BookOpen,
  Check,
  FileUp,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react'

import type { UiText } from '../i18n'
import {
  addGlossaryEntry,
  clearGlossary,
  deleteGlossaryEntry,
  fetchGlossary,
  importGlossary,
  type GlossarySnapshot,
} from '../glossary/glossary-api'


export interface GlossaryPanelProps {
  isOpen: boolean
  uiText: UiText
  onClose: () => void
}


type SaveState = 'idle' | 'saving' | 'saved' | 'failed'


export const GlossaryPanel: React.FC<GlossaryPanelProps> = ({
  isOpen,
  uiText,
  onClose,
}) => {
  const text = uiText.glossary
  const [snapshot, setSnapshot] = useState<GlossarySnapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [source, setSource] = useState('')
  const [target, setTarget] = useState('')
  const [keepOriginal, setKeepOriginal] = useState(false)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)

  useEffect(() => {
    if (!isOpen) {
      return
    }
    setError(null)
    setConfirmClear(false)
    void loadGlossary()
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

  const loadGlossary = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchGlossary()
      setSnapshot(result)
    } catch {
      setError(text.loadFailed)
    } finally {
      setLoading(false)
    }
  }

  const handleAdd = async (): Promise<void> => {
    const trimmedSource = source.trim()
    if (!trimmedSource) {
      setError(text.sourceRequired)
      return
    }
    setSaveState('saving')
    setError(null)
    try {
      const entry = await addGlossaryEntry({
        source: trimmedSource,
        target: target.trim(),
        keep_original: keepOriginal,
      })
      if (!entry) {
        setSaveState('failed')
        setError(text.addFailed)
        return
      }
      setSource('')
      setTarget('')
      setKeepOriginal(false)
      setSaveState('saved')
      await loadGlossary()
      window.setTimeout(() => setSaveState('idle'), 1600)
    } catch {
      setSaveState('failed')
      setError(text.addFailed)
    }
  }

  const handleDelete = async (entryId: string): Promise<void> => {
    setError(null)
    const ok = await deleteGlossaryEntry(entryId)
    if (!ok) {
      setError(text.deleteFailed)
    }
    await loadGlossary()
  }

  const handleClear = async (): Promise<void> => {
    setError(null)
    if (!confirmClear) {
      setConfirmClear(true)
      window.setTimeout(() => setConfirmClear(false), 3000)
      return
    }
    await clearGlossary()
    setConfirmClear(false)
    await loadGlossary()
  }

  const handleImportFile = async (file: File): Promise<void> => {
    setImporting(true)
    setError(null)
    try {
      const content = await file.text()
      const imported = await importGlossary(file.name, content)
      if (imported === 0) {
        setError(text.importEmpty)
      }
      await loadGlossary()
    } catch {
      setError(text.importFailed)
    } finally {
      setImporting(false)
    }
  }

  const normalizedQuery = query.trim().toLowerCase()
  const filteredEntries = snapshot?.entries.filter((entry) => {
    if (!normalizedQuery) {
      return true
    }
    return (
      entry.source.toLowerCase().includes(normalizedQuery) ||
      entry.target.toLowerCase().includes(normalizedQuery)
    )
  }) ?? []

  return (
    <section
      aria-label={text.ariaLabel}
      role="dialog"
      aria-modal="false"
      className="glossary-panel"
    >
      <div className="glossary-header">
        <div className="glossary-title">
          <BookOpen size={18} />
          <h3>{text.title}</h3>
          <span className="glossary-count">{snapshot?.size ?? 0}</span>
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

      <div className="glossary-body">
        <div className="glossary-actions">
          <label className="glossary-search">
            <Search size={14} />
            <input
              type="search"
              placeholder={text.searchPlaceholder}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,.csv"
            style={{ display: 'none' }}
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) {
                void handleImportFile(file)
              }
              event.target.value = ''
            }}
          />
          <button
            type="button"
            className="btn-secondary"
            disabled={importing}
            onClick={() => fileInputRef.current?.click()}
          >
            {importing ? <LoaderCircle size={15} className="spin" /> : <FileUp size={15} />}
            {text.importButton}
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={!snapshot || snapshot.size === 0}
            style={confirmClear ? { color: '#ff6b5e', borderColor: 'rgba(255,107,94,0.45)' } : undefined}
            onClick={() => {
              void handleClear()
            }}
          >
            <Trash2 size={15} />
            {confirmClear ? text.confirmClear : text.clearAll}
          </button>
        </div>

        <div className="glossary-add">
          <div className="glossary-add-row">
            <input
              className="glossary-source-input"
              placeholder={text.sourcePlaceholder}
              value={source}
              onChange={(event) => setSource(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  void handleAdd()
                }
              }}
            />
            <input
              className="glossary-target-input"
              placeholder={text.targetPlaceholder}
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  void handleAdd()
                }
              }}
            />
          </div>
          <div className="glossary-add-footer">
            <label className="glossary-keep-original">
              <input
                type="checkbox"
                checked={keepOriginal}
                onChange={(event) => setKeepOriginal(event.target.checked)}
              />
              <span>{text.keepOriginal}</span>
            </label>
            <button
              type="button"
              className="btn-primary"
              disabled={saveState === 'saving'}
              onClick={() => {
                void handleAdd()
              }}
            >
              {saveState === 'saved' ? <Check size={15} /> : saveState === 'saving' ? <LoaderCircle size={15} className="spin" /> : <Plus size={15} />}
              {saveState === 'saved' ? text.added : saveState === 'failed' ? text.addFailed : text.addButton}
            </button>
          </div>
        </div>

        {error ? (
          <div className="glossary-error">{error}</div>
        ) : null}

        <div className="glossary-list">
          {loading ? (
            <div className="glossary-loading">
              <LoaderCircle size={18} className="spin" />
              {text.loading}
            </div>
          ) : filteredEntries.length === 0 ? (
            <div className="glossary-empty">{text.empty}</div>
          ) : (
            filteredEntries.map((entry) => (
              <article key={entry.id} className="glossary-entry">
                <div className="glossary-entry-text">
                  <div className="glossary-entry-source">{entry.source}</div>
                  <div className="glossary-entry-target">
                    {entry.keep_original ? (
                      <span className="glossary-badge-keep">{text.keepOriginalBadge}</span>
                    ) : (
                      entry.target || '—'
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn-icon-danger"
                  aria-label={text.deleteEntry(entry.source)}
                  onClick={() => {
                    void handleDelete(entry.id)
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </article>
            ))
          )}
        </div>

        <div className="glossary-footer">
          <button
            type="button"
            className="btn-secondary"
            style={{ gridColumn: '1 / -1' }}
            disabled={loading}
            onClick={() => {
              void loadGlossary()
            }}
          >
            <RefreshCw size={15} />
            {text.refresh}
          </button>
        </div>
      </div>
    </section>
  )
}
