import { getToken } from "@/lib/auth"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const AUTH_API_URL = process.env.NEXT_PUBLIC_AUTH_API_URL || "https://api.cogmem.ai/api/v1"

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
  })
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`)
  }
  return res.json()
}

// --- User info (from cogmem-server auth API) ---

export interface UserPublic {
  id: string
  email: string
  is_active: boolean
  is_superuser: boolean
  full_name: string | null
  tenant_id: string | null
  organization: string | null
  created_at: string | null
}

export async function fetchCurrentUser(): Promise<UserPublic> {
  const token = getToken()
  const res = await fetch(`${AUTH_API_URL}/users/me`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  if (!res.ok) throw new Error(`Auth API ${res.status}: ${res.statusText}`)
  return res.json()
}

// --- Health ---

export interface HealthResponse {
  status: string
  mode: string
  providers: Record<string, string>
  contracts: Record<string, string>
}

export function fetchHealth(): Promise<HealthResponse> {
  return apiFetch("/admin/health")
}

// --- ACP Strategies ---

export interface Strategy {
  kos_id: string
  scope_type: string
  scope_id: string
  version: number
  status: string
  created_by: string
  rationale: string
  retrieval_policy: Record<string, unknown>
  document_policy: Record<string, unknown>
  vector_policy: Record<string, unknown>
  graph_policy: Record<string, unknown>
  claim_policy: Record<string, unknown>
  created_at?: string
}

export function fetchStrategies(): Promise<Strategy[]> {
  return apiFetch("/acp/strategies")
}

export function fetchStrategy(kosId: string): Promise<Strategy> {
  return apiFetch(`/acp/strategies/${kosId}`)
}

// --- ACP Proposals ---

export interface Proposal {
  kos_id: string
  base_strategy_id: string
  proposed_strategy_id: string
  change_summary: string
  status: string
  created_at?: string
}

export function fetchProposals(status?: string): Promise<Proposal[]> {
  const params = status ? `?status=${status}` : ""
  return apiFetch(`/acp/proposals${params}`)
}

export function approveProposal(kosId: string): Promise<{ status: string }> {
  return apiFetch(`/acp/proposals/${kosId}/approve`, { method: "POST" })
}

export function rejectProposal(kosId: string): Promise<{ status: string }> {
  return apiFetch(`/acp/proposals/${kosId}/reject`, { method: "POST" })
}

// --- ACP Outcomes ---

export interface OutcomeEvent {
  kos_id: string
  tenant_id: string
  strategy_id: string
  outcome_type: string
  source: string
  metrics: Record<string, number>
  context: Record<string, unknown>
  created_at?: string
}

export function fetchOutcomes(
  strategyId?: string,
  limit = 100
): Promise<OutcomeEvent[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (strategyId) params.set("strategy_id", strategyId)
  return apiFetch(`/acp/outcomes?${params}`)
}

// --- Workbench Experiments ---

export interface Experiment {
  experiment_id: string
  name: string
  status: string
  tenant_id: string
  data_profile: Record<string, unknown> | null
  max_cycles: number
  test_queries: string[]
  cycles: CycleResult[]
  best_cycle: number | null
  best_strategy_id: string | null
  created_at: string
  updated_at: string
}

export interface CycleResult {
  cycle_number: number
  status: string
  strategy_id: string
  strategy_summary: string
  items_ingested: number
  passages_created: number
  entities_extracted: number
  ingestion_time_ms: number
  avg_precision: number
  avg_recall: number
  avg_latency_ms: number
  failure_rate: number
  conflict_density: number
  issues_detected: string[]
  proposal_generated: boolean
  proposal_summary: string | null
  started_at: string | null
  completed_at: string | null
}

export function fetchExperiments(): Promise<Experiment[]> {
  return apiFetch("/workbench/experiments")
}

export function fetchExperiment(id: string): Promise<Experiment> {
  return apiFetch(`/workbench/experiments/${id}`)
}

export function createExperiment(formData: FormData): Promise<Experiment> {
  return fetch(`${API_URL}/workbench/experiments`, {
    method: "POST",
    body: formData,
  }).then((res) => {
    if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
    return res.json()
  })
}

export function runNextCycle(
  id: string
): Promise<{ cycle: CycleResult; experiment: Experiment }> {
  return apiFetch(`/workbench/experiments/${id}/run`, { method: "POST" })
}

export function runAllCycles(id: string): Promise<Experiment> {
  return apiFetch(`/workbench/experiments/${id}/run-all`, { method: "POST" })
}

// --- Search ---

export interface SearchHit {
  kos_id: string
  item_id: string
  snippet: string
  highlights: string[]
  score: number
}

export interface SearchResponse {
  hits: SearchHit[]
  total: number
}

export function searchItems(
  query: string,
  tenantId = "workbench",
  limit = 20
): Promise<SearchResponse> {
  return apiFetch("/search", {
    method: "POST",
    body: JSON.stringify({ query, tenant_id: tenantId, limit }),
  })
}
