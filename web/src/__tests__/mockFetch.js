import { vi } from 'vitest'

function requestUrl(input) {
  return typeof input === 'string' ? input : input.url
}

export function mockJsonFetch(routes) {
  const fetchMock = vi.fn(async (input, init = {}) => {
    const url = requestUrl(input)
    const method = (init.method ?? 'GET').toUpperCase()
    const route = routes.find((candidate) => (
      candidate.url === url && (candidate.method ?? 'GET').toUpperCase() === method
    ))

    if (!route) {
      throw new Error(`Unhandled fetch request: ${method} ${url}`)
    }

    const payload = typeof route.response === 'function'
      ? await route.response({ input, init, method, url })
      : route.response
    const status = route.status ?? 200

    return {
      ok: status >= 200 && status < 300,
      status,
      headers: {
        get: (name) => name.toLowerCase() === 'content-type' ? 'application/json' : null,
      },
      json: async () => payload,
      text: async () => typeof payload === 'string' ? payload : JSON.stringify(payload),
    }
  })

  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
