import { useCallback, useEffect, useRef, useState } from 'react'
import { wsUrl } from './api.js'

// One WebSocket per investigation run. Events accumulate in order; the
// timeline renders them directly. approve() answers the pending SQL gate.
export function useInvestigation(role = 'analyst') {
  const [events, setEvents] = useState([])
  const [running, setRunning] = useState(false)
  const [connection, setConnection] = useState('idle')
  const wsRef = useRef(null)
  const pendingApprovalRef = useRef(null)

  useEffect(() => () => wsRef.current?.close(), [])

  const start = useCallback((engine, caseId) => {
    wsRef.current?.close()
    setEvents([])
    setRunning(true)
    setConnection('connecting')
    const ws = new WebSocket(wsUrl('/ws/investigate', { engine, case: caseId, role }))
    wsRef.current = ws
    ws.onopen = () => setConnection('connected')
    ws.onmessage = (msg) => {
      const e = JSON.parse(msg.data)
      if (e.type === 'approval_request') pendingApprovalRef.current = e
      if (e.type === 'approval_result') pendingApprovalRef.current = null
      setEvents((prev) => [...prev, e])
      if (e.type === 'done' || e.type === 'error') {
        setRunning(false)
        setConnection(e.type === 'error' ? 'error' : 'complete')
      }
    }
    ws.onerror = () => setConnection('error')
    ws.onclose = () => {
      setRunning(false)
      setConnection((current) => current === 'complete' || current === 'error' ? current : 'disconnected')
    }
  }, [role])

  const approve = useCallback((ok) => {
    const pending = pendingApprovalRef.current
    wsRef.current?.send(JSON.stringify({
      approve: ok,
      call_id: pending?.call_id ?? pending?.id,
      id: pending?.id ?? pending?.call_id,
      run_id: pending?.run_id,
    }))
  }, [])

  const reset = useCallback(() => {
    wsRef.current?.close()
    setEvents([])
    setRunning(false)
    setConnection('idle')
    pendingApprovalRef.current = null
  }, [])

  const hydrate = useCallback((history) => {
    if (!running) setEvents(Array.isArray(history) ? history : [])
  }, [running])

  return { events, running, connection, start, approve, reset, hydrate }
}
