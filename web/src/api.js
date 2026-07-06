export const ROLES = {
  analyst: {
    label: 'AML Analyst',
    short: 'Analyst',
    initials: 'AA',
    description: 'Investigate alerts, document decisions, and prepare SAR drafts.',
  },
  reviewer: {
    label: 'MLRO Reviewer',
    short: 'Reviewer',
    initials: 'MR',
    description: 'Review investigations and approve or return SAR submissions.',
  },
  auditor: {
    label: 'Independent Auditor',
    short: 'Auditor',
    initials: 'IA',
    description: 'Inspect case evidence, decisions, and the immutable audit trail.',
  },
  rule_admin: {
    label: 'Rule Administrator',
    short: 'Rule admin',
    initials: 'RA',
    description: 'Tune, simulate, and govern deterministic detection rules.',
  },
}

export const PERMISSIONS = {
  analyst: new Set(['screen', 'investigate', 'approve_sql', 'note', 'transition', 'edit_sar', 'submit_sar']),
  reviewer: new Set(['note', 'transition', 'review_sar']),
  auditor: new Set(),
  rule_admin: new Set(['screen', 'edit_rule', 'simulate_rule']),
}

export function can(role, permission) {
  return PERMISSIONS[role]?.has(permission) ?? false
}

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

export async function api(path, { role = 'analyst', headers, body, ...options } = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'X-Raqib-Role': role,
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: body === undefined || typeof body === 'string' ? body : JSON.stringify(body),
  })

  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text()
  if (!response.ok) {
    const detail = typeof payload === 'object' ? payload.detail ?? payload.message : payload
    throw new ApiError(detail || `Request failed (${response.status})`, response.status, payload)
  }
  return payload
}

export function wsUrl(path, params = {}) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const query = new URLSearchParams(params)
  return `${protocol}://${window.location.host}${path}?${query}`
}

export function pdfUrl(caseId, lang, role) {
  return `/api/cases/${encodeURIComponent(caseId)}/sar/pdf?${new URLSearchParams({ lang, role })}`
}
