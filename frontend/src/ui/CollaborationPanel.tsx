import React, { useEffect, useState } from 'react'

import {
  Crown,
  LoaderCircle,
  LogIn,
  LogOut,
  Plus,
  RefreshCw,
  Send,
  Trash2,
  Users,
  X,
} from 'lucide-react'

import type { UiText } from '../i18n'
import {
  clearCollaborationRevisions,
  createCollaborationRoom,
  destroyCollaborationRoom,
  fetchCollaborationRoom,
  fetchCollaborationRooms,
  joinCollaborationRoom,
  leaveCollaborationRoom,
  submitCollaborationRevision,
  type CollaborationRoom,
  type CollaborativeRevisionItem,
} from '../collaboration/collaboration-api'


export interface CollaborationPanelProps {
  isOpen: boolean
  sessionId: string
  uiText: UiText
  onClose: () => void
}


export const CollaborationPanel: React.FC<CollaborationPanelProps> = ({
  isOpen,
  sessionId,
  uiText,
  onClose,
}) => {
  const text = uiText.collaboration
  const [rooms, setRooms] = useState<CollaborationRoom[]>([])
  const [activeRoom, setActiveRoom] = useState<CollaborationRoom | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newRoomTitle, setNewRoomTitle] = useState('')
  const [memberName, setMemberName] = useState('成员')
  const [revisionSegmentId, setRevisionSegmentId] = useState('')
  const [revisionText, setRevisionText] = useState('')
  const [confirmDestroy, setConfirmDestroy] = useState(false)

  useEffect(() => {
    if (!isOpen) {
      return
    }
    setError(null)
    setConfirmDestroy(false)
    void loadRooms()
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

  const loadRooms = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchCollaborationRooms()
      setRooms(result ?? [])
    } catch {
      setError(text.loadFailed)
    } finally {
      setLoading(false)
    }
  }

  const refreshActiveRoom = async (roomId: string): Promise<CollaborationRoom | null> => {
    try {
      const room = await fetchCollaborationRoom(roomId)
      if (room) {
        setActiveRoom(room)
      }
      return room
    } catch {
      setError(text.loadFailed)
      return null
    }
  }

  const handleCreate = async (): Promise<void> => {
    setError(null)
    const title = newRoomTitle.trim() || '协作翻译'
    const room = await createCollaborationRoom(sessionId, title)
    if (!room) {
      setError(text.createFailed)
      return
    }
    setNewRoomTitle('')
    setRooms((current) => [room, ...current])
    setActiveRoom(room)
  }

  const handleJoin = async (roomId: string): Promise<void> => {
    setError(null)
    const room = await joinCollaborationRoom(roomId, sessionId, memberName.trim() || '成员')
    if (!room) {
      setError(text.joinFailed)
      return
    }
    setActiveRoom(room)
    await loadRooms()
  }

  const handleLeave = async (): Promise<void> => {
    if (!activeRoom) {
      return
    }
    setError(null)
    await leaveCollaborationRoom(activeRoom.room_id, sessionId)
    setActiveRoom(null)
    await loadRooms()
  }

  const handleDestroy = async (): Promise<void> => {
    if (!activeRoom) {
      return
    }
    setError(null)
    if (!confirmDestroy) {
      setConfirmDestroy(true)
      window.setTimeout(() => setConfirmDestroy(false), 3000)
      return
    }
    await destroyCollaborationRoom(activeRoom.room_id, sessionId)
    setConfirmDestroy(false)
    setActiveRoom(null)
    await loadRooms()
  }

  const handleSubmitRevision = async (): Promise<void> => {
    if (!activeRoom) {
      return
    }
    setError(null)
    const segmentId = revisionSegmentId.trim()
    const newText = revisionText.trim()
    if (!segmentId || !newText) {
      setError(text.revisionEmpty)
      return
    }
    const revision = await submitCollaborationRevision(activeRoom.room_id, {
      sessionId,
      segmentId,
      newText,
    })
    if (!revision) {
      setError(text.revisionFailed)
      return
    }
    setRevisionText('')
    await refreshActiveRoom(activeRoom.room_id)
  }

  const handleClearRevisions = async (): Promise<void> => {
    if (!activeRoom) {
      return
    }
    setError(null)
    await clearCollaborationRevisions(activeRoom.room_id, sessionId)
    await refreshActiveRoom(activeRoom.room_id)
  }

  const isOwner = activeRoom?.owner_session_id === sessionId

  return (
    <section
      aria-label={text.ariaLabel}
      role="dialog"
      aria-modal="false"
      className="collab-panel"
    >
      <div className="collab-header">
        <div className="collab-title">
          <Users size={18} />
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

      <div className="collab-body">
        {error ? (
          <div className="glossary-error">{error}</div>
        ) : null}

        {!activeRoom ? (
          <div className="collab-rooms">
            <div className="collab-create-row">
              <input
                className="collab-input"
                value={newRoomTitle}
                onChange={(event) => setNewRoomTitle(event.target.value)}
                placeholder={text.createPlaceholder}
                maxLength={64}
              />
              <button
                type="button"
                className="btn-primary"
                style={{ width: 'auto', minHeight: '38px', padding: '0 14px', whiteSpace: 'nowrap' }}
                onClick={() => {
                  void handleCreate()
                }}
              >
                <Plus size={15} />
                {text.createButton}
              </button>
            </div>

            <div className="collab-join-row">
              <input
                className="collab-input"
                value={memberName}
                onChange={(event) => setMemberName(event.target.value)}
                placeholder={text.memberNamePlaceholder}
                maxLength={32}
              />
            </div>

            <div className="collab-section-label">{text.roomList}</div>

            {loading ? (
              <div className="collab-loading">
                <LoaderCircle size={18} className="spin" />
                {text.loading}
              </div>
            ) : rooms.length === 0 ? (
              <div className="collab-empty">{text.noRooms}</div>
            ) : (
              <div className="collab-room-list">
                {rooms.map((room) => (
                  <div key={room.room_id} className="collab-room-item">
                    <div className="collab-room-info">
                      <div className="collab-room-title">{room.title}</div>
                      <div className="collab-room-meta">
                        {room.member_count} {text.members}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ width: 'auto', minHeight: '34px', padding: '0 12px' }}
                      onClick={() => {
                        void handleJoin(room.room_id)
                      }}
                    >
                      <LogIn size={14} />
                      {text.joinButton}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="collab-detail">
            <div className="collab-detail-header">
              <div className="collab-detail-title">
                <Users size={16} />
                <span>{activeRoom.title}</span>
                {isOwner ? (
                  <span className="collab-owner-badge">
                    <Crown size={12} />
                    {text.ownerBadge}
                  </span>
                ) : null}
              </div>
              <div className="collab-detail-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ width: 'auto', minHeight: '34px', padding: '0 12px' }}
                  onClick={() => {
                    void refreshActiveRoom(activeRoom.room_id)
                  }}
                >
                  <RefreshCw size={14} />
                  {text.refresh}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ width: 'auto', minHeight: '34px', padding: '0 12px' }}
                  onClick={() => {
                    void handleLeave()
                  }}
                >
                  <LogOut size={14} />
                  {text.leaveButton}
                </button>
                {isOwner ? (
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{
                      width: 'auto',
                      minHeight: '34px',
                      padding: '0 12px',
                      ...(confirmDestroy ? { color: '#ff6b5e', borderColor: 'rgba(255,107,94,0.45)' } : {}),
                    }}
                    onClick={() => {
                      void handleDestroy()
                    }}
                  >
                    <Trash2 size={14} />
                    {confirmDestroy ? text.confirmDestroy : text.destroyButton}
                  </button>
                ) : null}
              </div>
            </div>

            <div className="collab-section-label">{text.members}</div>
            <div className="collab-member-list">
              {activeRoom.members.map((member) => (
                <div key={member.session_id} className="collab-member-item">
                  <span className="collab-member-name">{member.name}</span>
                  {member.is_owner ? (
                    <span className="collab-owner-badge">
                      <Crown size={11} />
                      {text.ownerBadge}
                    </span>
                  ) : null}
                  <span className="collab-member-id">{shortSessionId(member.session_id)}</span>
                </div>
              ))}
            </div>

            <div className="collab-section-label">{text.revisions}</div>
            <div className="collab-revision-form">
              <input
                className="collab-input"
                value={revisionSegmentId}
                onChange={(event) => setRevisionSegmentId(event.target.value)}
                placeholder={text.segmentIdPlaceholder}
                maxLength={120}
              />
              <div className="collab-revision-row">
                <input
                  className="collab-input"
                  value={revisionText}
                  onChange={(event) => setRevisionText(event.target.value)}
                  placeholder={text.revisionPlaceholder}
                  maxLength={2000}
                />
                <button
                  type="button"
                  className="btn-primary"
                  style={{ width: 'auto', minHeight: '38px', padding: '0 14px', whiteSpace: 'nowrap' }}
                  onClick={() => {
                    void handleSubmitRevision()
                  }}
                >
                  <Send size={15} />
                  {text.submitRevision}
                </button>
              </div>
            </div>

            {activeRoom.revisions && activeRoom.revisions.length > 0 ? (
              <div className="collab-revision-list">
                {activeRoom.revisions.map((revision) => (
                  <CollaborationRevisionRow key={revision.revision_id} revision={revision} />
                ))}
              </div>
            ) : (
              <div className="collab-empty">{text.noRevisions}</div>
            )}

            {isOwner && activeRoom.revisions && activeRoom.revisions.length > 0 ? (
              <div className="collab-detail-actions" style={{ marginTop: '10px' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ width: 'auto', minHeight: '34px', padding: '0 12px' }}
                  onClick={() => {
                    void handleClearRevisions()
                  }}
                >
                  <Trash2 size={14} />
                  {text.clearRevisions}
                </button>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </section>
  )
}


interface CollaborationRevisionRowProps {
  revision: CollaborativeRevisionItem
}


const CollaborationRevisionRow: React.FC<CollaborationRevisionRowProps> = ({ revision }) => (
  <div className="collab-revision-item">
    <div className="collab-revision-meta">
      <span className="collab-revision-author">{revision.member_name}</span>
      <span className="collab-revision-seg">{shortSessionId(revision.segment_id)}</span>
      <span className="collab-revision-time">
        {new Date(revision.created_at * 1000).toLocaleTimeString()}
      </span>
    </div>
    <div className="collab-revision-text">{revision.new_text}</div>
    {revision.source_text ? (
      <div className="collab-revision-source">{revision.source_text}</div>
    ) : null}
  </div>
)


function shortSessionId(sessionId: string): string {
  if (sessionId.length <= 12) {
    return sessionId
  }
  return `${sessionId.slice(0, 8)}...${sessionId.slice(-4)}`
}
