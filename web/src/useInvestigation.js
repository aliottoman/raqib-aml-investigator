import { useCallback, useEffect, useRef, useState } from 'react'
import { wsUrl } from './api.js'

// One WebSocket per attachment to an investigation run. Events accumulate in
// order; the timeline renders them directly. approve() answers the pending SQL
// gate. Because the run now lives on the server (decoupled from this socket),
// resume() reattaches to a run this socket dropped — replaying its persisted
// events, then streaming the live tail.
export function useInvestigation(role = 'analyst') {
  const [events, setEvents] = useState([])
  const [running, setRunning] = useState(false)
  const [connection, setConnection] = useState('idle')
  const [runId, setRunId] = useState(null)
  const wsRef = useRef(null)
  const pendingApprovalRef = useRef(null)

  useEffect(() => () => wsRef.current?.close(), [])

  const connect = useCallback((params) => {
    wsRef.current?.close()
    setEvents([])
    setRunning(true)
    setConnection('connecting')
    pendingApprovalRef.current = null
    const ws = new WebSocket(wsUrl('/ws/investigate', { ...params, role }))
    wsRef.current = ws
    ws.onopen = () => setConnection('connected')
    ws.onmessage = (msg) => {
      const e = JSON.parse(msg.data)
      if (e.run_id) setRunId(e.run_id)
      if (e.type === 'approval_request') pendingApprovalRef.current = e
      if (e.type === 'approval_result') pendingApprovalRef.current = null
      setEvents((prev) => [...prev, e])
      // done | error end the run; run_status arrives when reattaching to a run
      // that already finished while we were away.
      if (e.type === 'done' || e.type === 'error' || e.type === 'run_status') {
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

  const start = useCallback((engine, caseId) => connect({ engine, case: caseId }), [connect])

  // Reattach to an existing run. after=0 replays the whole run from the server,
  // so the reconnected timeline is complete without client-side dedup.
  const resume = useCallback((resumeRunId, after = 0) => {
    const target = resumeRunId ?? runId
    if (target) connect({ run: target, after })
  }, [connect, runId])

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
    setRunId(null)
    pendingApprovalRef.current = null
  }, [])

  const hydrate = useCallback((history) => {
    if (!running) setEvents(Array.isArray(history) ? history : [])
  }, [running])

  return { events, running, connection, runId, start, resume, approve, reset, hydrate }
}
