import type {
  AgentEvent, BlastRadius, ChangeCheck, Envelope, Evaluation, GraphData, GraphNode, GraphQuery, Health,
  HiddenDependency, Incident, IncidentDetail, NewIncident, RankingMetric, Rankings,
  Repo, ResolveIncident, ResolveResult, Responder, ServiceDetail, UpstreamSuspects, WhatIf,
} from '@/lib/types'
import { type ApiToken, AuthApiError, authApi } from './auth-client'
import { currentRepoId } from './repo-store'
import { parseSSE } from './sse'

export const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message)
  }
}

const REFRESH_EARLY_MS = 30_000
let cachedToken: ApiToken | null = null
let pendingToken: Promise<ApiToken> | null = null

const NO_REDIRECT = ['/login', '/signup', '/home']

function toLogin() {
  if (typeof window === 'undefined' || NO_REDIRECT.includes(window.location.pathname)) return
  window.location.assign(`/login?next=${encodeURIComponent(location.pathname + location.search)}`)
}

async function bearer(force = false): Promise<string> {
  if (!force && cachedToken && cachedToken.expiresAt - REFRESH_EARLY_MS > Date.now()) return cachedToken.token
  pendingToken ??= authApi.token().finally(() => { pendingToken = null })
  try {
    cachedToken = await pendingToken
  } catch (e) {
    cachedToken = null
    if (e instanceof AuthApiError && e.status === 401) toLogin()
    throw new ApiError(401, 'Your session has ended. Sign in again.', 'UNAUTHENTICATED')
  }
  return cachedToken.token
}

async function authedFetch(url: string | URL, init: RequestInit = {}): Promise<Response> {
  const send = async (force: boolean) =>
    fetch(url, { ...init, headers: { ...init.headers, Authorization: `Bearer ${await bearer(force)}` } })
  const res = await send(false)
  return res.status === 401 ? send(true) : res
}

function repoHeader(): Record<string, string> {
  const id = currentRepoId()
  if (!id) throw new ApiError(400, 'Connect or pick a repository first.', 'NO_REPO')
  return { 'X-Repo-Id': id }
}

async function call<T>(
  path: string,
  init?: RequestInit & { query?: Record<string, unknown>; anonymous?: boolean; account?: boolean },
): Promise<T> {
  const url = new URL(`${BASE}/api${path}`)
  for (const [k, v] of Object.entries(init?.query ?? {})) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, String(x)))
    else url.searchParams.set(k, String(v))
  }
  let res: Response
  try {
    const scope = init?.anonymous || init?.account ? {} : repoHeader()
    const request = { ...init, headers: { 'Content-Type': 'application/json', ...scope, ...init?.headers } }
    res = await (init?.anonymous ? fetch(url, request) : authedFetch(url, request))
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError(0, `Cannot reach the Rhizo API at ${BASE}`, 'NETWORK')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.error?.message ?? res.statusText, body?.error?.code)
  }
  return ((await res.json()) as Envelope<T>).data
}
const post = <T>(path: string, body: unknown) => call<T>(path, { method: 'POST', body: JSON.stringify(body) })

export async function getHealth(): Promise<Health> {
  return call('/health', { anonymous: true })
}

export async function getGraph(q: GraphQuery = {}): Promise<GraphData> {
  return call('/graph', { query: { ...q, provenance: q.provenance?.join(',') } })
}

export async function getServices(): Promise<GraphNode[]> {
  return call('/services')
}

export async function getService(name: string): Promise<ServiceDetail> {
  return call(`/services/${encodeURIComponent(name)}`)
}

export async function getBlastRadius(body: { service: string; max_hops?: number; min_confidence?: number; as_of?: string }): Promise<BlastRadius> {
  return post('/impact/blast-radius', body)
}

export async function getUpstreamSuspects(body: { service: string; max_hops?: number }): Promise<UpstreamSuspects> {
  return post('/impact/upstream-suspects', body)
}

export async function whatIf(body: { services: string[]; max_hops?: number }): Promise<WhatIf> {
  return post('/impact/what-if', body)
}

export async function changeCheck(body: { files?: string[]; services?: string[] }): Promise<ChangeCheck> {
  return post('/impact/change-check', body)
}

export async function getHiddenDependencies(service?: string): Promise<HiddenDependency[]> {
  return call('/hidden-dependencies', { query: { service } })
}

export async function getRankings(metric: RankingMetric = 'pagerank', top_k = 10): Promise<Rankings> {
  return call('/rankings', { query: { metric, top_k } })
}

export async function getResponders(services: string[]): Promise<Responder[]> {
  return call('/responders', { query: { service: services } })
}

export async function* askAgent(question: string, ctx?: { service?: string }): AsyncGenerator<AgentEvent> {
  let res: Response
  try {
    res = await authedFetch(`${BASE}/api/agent/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...repoHeader() },
      body: JSON.stringify({ question, context: ctx }),
    })
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError(0, `Cannot reach the Rhizo API at ${BASE}`, 'NETWORK')
  }
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.error?.message ?? 'agent stream failed', body?.error?.code)
  }
  yield* parseSSE(res.body)
}

export async function getIncidents(): Promise<Incident[]> {
  return call('/incidents')
}

export async function getIncident(id: string): Promise<IncidentDetail> {
  return call(`/incidents/${encodeURIComponent(id)}`)
}

export async function createIncident(body: NewIncident): Promise<Incident> {
  return post('/incidents', body)
}

export async function resolveIncident(id: string, body: ResolveIncident): Promise<ResolveResult> {
  return post(`/incidents/${encodeURIComponent(id)}/resolve`, body)
}

export async function listRepos(): Promise<Repo[]> {
  return call('/repos', { account: true })
}

export async function getRepo(id: string): Promise<Repo> {
  return call(`/repos/${encodeURIComponent(id)}`, { account: true })
}

export async function connectRepo(url: string): Promise<Repo> {
  return call('/repos', { method: 'POST', body: JSON.stringify({ url }), account: true })
}

export async function syncRepo(id: string): Promise<Repo> {
  return call(`/repos/${encodeURIComponent(id)}/sync`, { method: 'POST', account: true })
}

export async function deleteRepo(id: string): Promise<void> {
  await call(`/repos/${encodeURIComponent(id)}`, { method: 'DELETE', account: true })
}

export async function loadDemoRepo(): Promise<Repo> {
  return call('/repos/demo', { method: 'POST', account: true })
}

export async function getBenchmark(): Promise<Evaluation> {
  return call('/benchmark/results')
}
