import React, { useEffect, useRef, useState } from 'react'

import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { CircleAlert, LoaderCircle, Maximize2, Minimize2, RotateCcw, Terminal as TerminalIcon, Wifi, X } from 'lucide-react'
import '@xterm/xterm/css/xterm.css'

import { resolveTerminalWebSocketUrl } from '../network/ws-url'


interface TerminalPanelProps {
  isOpen: boolean
  onClose: () => void
}


type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'failed'


export const TerminalPanel: React.FC<TerminalPanelProps> = ({ isOpen, onClose }) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const terminalRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const [isMaximized, setIsMaximized] = useState(false)

  // 打开/关闭时建立/销毁连接
  useEffect(() => {
    if (!isOpen) {
      return
    }

    const container = containerRef.current
    if (!container) {
      return
    }

    const terminal = new Terminal({
      cursorBlink: true,
      fontSize: 12.5,
      fontFamily: "'JetBrains Mono', 'Cascadia Code', Consolas, monospace",
      theme: {
        background: '#080b12',
        foreground: '#d5e0ee',
        cursor: '#4aa3ff',
        cursorAccent: '#080b12',
        selectionBackground: 'rgba(74, 163, 255, 0.3)',
        black: '#1b2230',
        red: '#ff6b5e',
        green: '#34d399',
        yellow: '#f4c84c',
        blue: '#4aa3ff',
        magenta: '#a78bfa',
        cyan: '#7ee0ff',
        white: '#e6edf6',
        brightBlack: '#5d6a7c',
        brightRed: '#ff8a7f',
        brightGreen: '#5ee6b4',
        brightYellow: '#f7d97a',
        brightBlue: '#7cc2ff',
        brightMagenta: '#c4a9ff',
        brightCyan: '#a5ecff',
        brightWhite: '#ffffff',
      },
      scrollback: 2000,
      convertEol: false,
    })

    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.open(container)
    fitAddon.fit()

    // 欢迎横幅：提示终端用途与连接状态
    terminal.writeln('\x1b[1;38;2;126;224;255mAI Interpreter 内置终端\x1b[0m')
    terminal.writeln('\x1b[38;2;139;152;170m输入命令可直接操作本机后端环境，例如：\x1b[0m')
    terminal.writeln('\x1b[38;2;196;210;221m  status\x1b[0m \x1b[38;2;139;152;170m— 查看后端服务状态\x1b[0m')
    terminal.writeln('\x1b[38;2;196;210;221m  help\x1b[0m  \x1b[38;2;139;152;170m— 查看可用命令\x1b[0m')
    terminal.writeln('')


    terminalRef.current = terminal
    fitAddonRef.current = fitAddon

    let socket: WebSocket | null = null
    setConnectionState('connecting')

    const connect = (): void => {
      const url = resolveTerminalWebSocketUrl()
      const ws = new WebSocket(url)
      socket = ws

      ws.binaryType = 'arraybuffer'
      ws.onopen = () => {
        socketRef.current = ws
        setConnectionState('connected')
        sendResize(ws, terminal)
      }
      ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          terminal.write(event.data)
        } else {
          terminal.write(new Uint8Array(event.data))
        }
      }
      ws.onclose = () => {
        socketRef.current = null
        if (socket === ws) {
          setConnectionState('disconnected')
        }
      }
      ws.onerror = () => {
        if (socket === ws) {
          setConnectionState('failed')
        }
      }
    }

    connect()

    const onData = terminal.onData((data) => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.send(data)
      }
    })

    const resizeObserver = new ResizeObserver(() => {
      if (fitAddonRef.current) {
        fitAddonRef.current.fit()
        sendResize(socketRef.current, terminal)
      }
    })
    resizeObserver.observe(container)

    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)

    return () => {
      window.removeEventListener('keydown', onKeyDown)
      resizeObserver.disconnect()
      onData.dispose()
      if (socket) {
        socket.onclose = null
        socket.onerror = null
        if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
          socket.close()
        }
      }
      socketRef.current = null
      terminal.dispose()
      terminalRef.current = null
      fitAddonRef.current = null
      setConnectionState('disconnected')
    }
  }, [isOpen, onClose])

  if (!isOpen) {
    return null
  }

  const handleReconnect = (): void => {
    // 简单实现：关闭后重建由 effect 依赖控制
    onClose()
  }

  const toggleMaximize = (): void => {
    setIsMaximized((value) => !value)
    window.setTimeout(() => {
      fitAddonRef.current?.fit()
      if (socketRef.current) {
        sendResize(socketRef.current, terminalRef.current)
      }
    }, 60)
  }

  return (
    <section aria-label="内置终端" className="terminal-shell" style={isMaximized ? { position: 'fixed', inset: 0, width: '100%', height: '100%', borderRadius: 0, zIndex: 100004 } : undefined}>
      <div className="terminal-header">
        <div className="terminal-title">
          <TerminalIcon size={14} />
          <span>内置终端</span>
        </div>
        <div className="terminal-actions">
          <button type="button" className="terminal-icon-btn" aria-label="重连" onClick={handleReconnect}>
            <RotateCcw />
          </button>
          <button type="button" className="terminal-icon-btn" aria-label={isMaximized ? '还原' : '最大化'} onClick={toggleMaximize}>
            {isMaximized ? <Minimize2 /> : <Maximize2 />}
          </button>
          <button type="button" className="terminal-icon-btn" aria-label="关闭终端" onClick={onClose}>
            <X />
          </button>
        </div>
      </div>
      <div ref={containerRef} className="terminal-body" />
      <div className={`terminal-status ${connectionState === 'connected' ? 'online' : 'offline'}`}>
        {connectionState === 'connected' ? (
          <>
            <Wifi size={12} /> 已连接 · 输入命令可直接操作后端环境
          </>
        ) : connectionState === 'connecting' ? (
          <>
            <LoaderCircle size={12} className="spin" /> 正在连接本地终端服务
          </>
        ) : (
          <>
            <CircleAlert size={12} /> {connectionState === 'failed' ? '连接失败，点击重连' : '连接已断开'}
          </>
        )}
      </div>
    </section>
  )
}


function sendResize(socket: WebSocket | null, terminal: Terminal | null): void {
  if (!socket || !terminal || socket.readyState !== WebSocket.OPEN) {
    return
  }
  socket.send(JSON.stringify({
    type: 'resize',
    cols: terminal.cols,
    rows: terminal.rows,
  }))
}
