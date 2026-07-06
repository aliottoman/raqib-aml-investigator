import React, { useEffect, useState } from 'react'
import { api, ROLES } from './api.js'
import Shell from './components/Shell.jsx'
import { EmptyState } from './components/States.jsx'
import ArchitecturePage from './pages/ArchitecturePage.jsx'
import AlertsPage from './pages/AlertsPage.jsx'
import CasePage from './pages/CasePage.jsx'
import CasesPage from './pages/CasesPage.jsx'
import IntelligencePage from './pages/IntelligencePage.jsx'
import OverviewPage from './pages/OverviewPage.jsx'
import { Link, useRoute } from './router.jsx'

function getInitialRole() {
  const saved = window.localStorage.getItem('raqib-role')
  return saved && ROLES[saved] ? saved : 'analyst'
}

export default function App() {
  const path = useRoute()
  const [role, setRoleState] = useState(getInitialRole)
  const [health, setHealth] = useState(null)
  const setRole = (next) => {
    if (!ROLES[next]) return
    window.localStorage.setItem('raqib-role', next)
    setRoleState(next)
  }
  useEffect(() => {
    Promise.all([
      api('/api/health', { role }),
      api('/api/session', { role }).catch(() => null),
    ]).then(([status]) => setHealth(status)).catch(() => setHealth({ live_available: false }))
  }, [role])

  let page
  if (path === '/overview') page = <OverviewPage role={role} />
  else if (path === '/alerts') page = <AlertsPage role={role} />
  else if (path === '/cases') page = <CasesPage role={role} />
  else if (path.startsWith('/cases/')) page = <CasePage caseId={decodeURIComponent(path.slice('/cases/'.length))} role={role} health={health} />
  else if (path === '/intelligence') page = <IntelligencePage role={role} />
  else if (path === '/architecture') page = <ArchitecturePage role={role} health={health} />
  else page = <EmptyState eyebrow="404" title="This workspace does not exist" body="Return to the operations overview to continue." action={<Link className="btn primary" to="/overview">Back to overview</Link>} />

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <Shell path={path} role={role} setRole={setRole} health={health}>{page}</Shell>
    </>
  )
}
