import React from 'react'

const PATHS = {
  ledger: [
    'M5 5c0-1.1 3.1-2 7-2s7 .9 7 2-3.1 2-7 2-7-.9-7-2Z',
    'M5 5v6c0 1.1 3.1 2 7 2s7-.9 7-2V5M5 11v6c0 1.1 3.1 2 7 2s7-.9 7-2v-6',
  ],
  policy: ['M5 4.5A2.5 2.5 0 0 1 7.5 2H12v18H7.5A2.5 2.5 0 0 0 5 22V4.5Z', 'M19 4.5A2.5 2.5 0 0 0 16.5 2H12v18h4.5a2.5 2.5 0 0 1 2.5 2V4.5Z'],
  document: ['M6 2h8l4 4v16H6z', 'M14 2v5h5M9 12h6M9 16h6'],
  watchlist: ['M12 3 4.5 6v5c0 4.8 3 8.5 7.5 10 4.5-1.5 7.5-5.2 7.5-10V6L12 3Z', 'M9.5 11.5a2.5 2.5 0 1 0 5 0 2.5 2.5 0 0 0-5 0ZM8.5 17c.8-1.4 2-2 3.5-2s2.7.6 3.5 2'],
  search: ['M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Z', 'm16 16 4 4'],
  code: ['m9 7-5 5 5 5M15 7l5 5-5 5M13 5l-2 14'],
  chevron: ['m9 6 6 6-6 6'],
}

export function StrokeIcon({ name, className = '', title }) {
  const paths = PATHS[name] ?? PATHS.document
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden={title ? undefined : true} role={title ? 'img' : undefined}>
      {title && <title>{title}</title>}
      {paths.map((path) => <path d={path} key={path} />)}
    </svg>
  )
}
