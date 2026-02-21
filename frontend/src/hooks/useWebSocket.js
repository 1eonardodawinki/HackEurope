import { useEffect, useRef, useCallback } from 'react'

const WS_URL = 'ws://localhost:8000/ws'

export function useWebSocket(handlers) {
  const ws = useRef(null)
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  const dispatch = useCallback((msg) => {
    const h = handlersRef.current
    switch (msg.type) {
      case 'init':         h.onInit?.(msg.data); break
      case 'ships':        h.onShips?.(msg.data); break
      case 'incident':     h.onIncident?.(msg.data); break
      case 'evaluation':   h.onEvaluation?.(msg.data); break
      case 'agent_status': h.onAgentStatus?.(msg.data); break
      case 'threshold_update': h.onThresholdUpdate?.(msg.data); break
      case 'report':       h.onReport?.(msg.data); break
      case 'mode_change':  h.onModeChange?.(msg.data); break
      case 'heartbeat':    break
      default: break
    }
  }, [])

  useEffect(() => {
    let retryTimeout = null
    let retries = 0

    function connect() {
      const socket = new WebSocket(WS_URL)
      ws.current = socket

      socket.onopen = () => {
        retries = 0
        handlersRef.current.onConnect?.()
        // Heartbeat ping
        const pingInterval = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }))
          }
        }, 25000)
        socket._pingInterval = pingInterval
      }

      socket.onmessage = (e) => {
        try { dispatch(JSON.parse(e.data)) } catch {}
      }

      socket.onclose = () => {
        clearInterval(socket._pingInterval)
        handlersRef.current.onDisconnect?.()
        // Exponential backoff reconnect
        const delay = Math.min(1000 * 2 ** retries, 15000)
        retries++
        retryTimeout = setTimeout(connect, delay)
      }

      socket.onerror = () => socket.close()
    }

    connect()
    return () => {
      clearTimeout(retryTimeout)
      if (ws.current) {
        ws.current.onclose = null
        ws.current.close()
      }
    }
  }, [dispatch])
}
