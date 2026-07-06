import React, { useEffect, useState } from 'react'

const clean = (path) => {
  const value = (path || '/').replace(/\/+$/, '')
  return value || '/overview'
}

export function navigate(path, { replace = false } = {}) {
  const target = clean(path)
  window.history[replace ? 'replaceState' : 'pushState']({}, '', target)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function useRoute() {
  const [path, setPath] = useState(() => clean(window.location.pathname))
  useEffect(() => {
    if (window.location.pathname === '/') navigate('/overview', { replace: true })
    const onChange = () => setPath(clean(window.location.pathname))
    window.addEventListener('popstate', onChange)
    return () => window.removeEventListener('popstate', onChange)
  }, [])
  return path
}

export function Link({ to, children, onClick, ...props }) {
  return (
    <a
      href={to}
      onClick={(event) => {
        onClick?.(event)
        if (!event.defaultPrevented && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey) {
          event.preventDefault()
          navigate(to)
        }
      }}
      {...props}
    >
      {children}
    </a>
  )
}

