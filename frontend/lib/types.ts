export type Provenance = 'declared' | 'code' | 'observed' | 'inferred'
export type Basis = Provenance | 'connectivity_fallback' | 'n/a'
export type NodeLabel = 'Service' | 'Resource' | 'Engineer' | 'Team' | 'File' | 'Incident' | 'Runbook'

export interface GraphNode {
  id: string
  label: NodeLabel
  name: string
  properties: Record<string, string | number | boolean | null>
  risk_score?: number
}
export interface GraphEdge {
  id: string
  source_id: string
  target_id: string
  type: 'DEPENDS_ON' | 'USES' | 'CO_CHANGES_WITH' | 'OWNS' | 'COMMITTED_TO'
  provenance: Provenance
  confidence: number
  valid_from: string | null
  valid_to: string | null
  evidence?: string
}
export interface Evidence {
  cypher: string[]
  params: Record<string, unknown>
  returned_ids: string[]
  note?: string
}
export interface ImpactItem {
  service: GraphNode
  hops: number
  path: string[]
  path_confidence: number
  basis: Basis
}
export interface Envelope<T> {
  data: T
  meta: { basis: Basis; took_ms: number; cypher: string[] }
}
export interface HiddenDependency {
  id: string
  kind: 'shared_resource' | 'co_change'
  a: GraphNode
  b: GraphNode
  via?: GraphNode
  confidence: number
  support?: number
  jaccard?: number
  evidence: string
}
export interface Responder {
  engineer: GraphNode
  score: number
  reason: string
}
export interface Incident {
  id: string
  title: string
  symptom: string
  severity: 'sev1' | 'sev2' | 'sev3'
  status: 'open' | 'resolved'
  started_at: string
  resolved_at: string | null
  affected: string[]
  root_cause?: string
  fix?: string
  resolved_by?: string
  source?: 'github_issue' | 'fix_commit' | 'manual'
  url?: string
}
export type AgentEvent =
  | { type: 'tool_call'; data: { id: string; name: string; args: unknown } }
  | { type: 'tool_result'; data: { id: string; duration_ms: number; summary: string; evidence: Evidence } }
  | { type: 'graph_path'; data: { node_ids: string[]; edge_ids: string[]; paths: string[][] } }
  | { type: 'insufficient_data'; data: { reason: string } }
  | { type: 'answer_token'; data: { text: string } }
  | { type: 'error'; data: { message: string } }
  | { type: 'done'; data: { basis: Basis; took_ms: number } }

export interface Health {
  status: 'ok'
  falkordb: 'up' | 'down'
  graph_counts: { services: number; edges: number; incidents: number }
}
export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}
export interface GraphQuery {
  center?: string
  depth?: number
  min_confidence?: number
  provenance?: Provenance[]
  as_of?: string
}
export interface ServiceDetail {
  node: GraphNode
  owners: GraphNode[]
  upstream: ImpactItem[]
  blast_radius_count: number
  responders: Responder[]
  resources: GraphNode[]
}
export interface BlastRadius {
  service: string
  items: ImpactItem[]
  risk_score: number
}
export interface Suspect {
  service: GraphNode
  hops: number
  recent_commits: number
  score: number
}
export interface UpstreamSuspects {
  service: string
  suspects: Suspect[]
}
export interface WhatIf {
  failed: string[]
  items: ImpactItem[]
  risk_score: number
}
export interface SimilarIncident {
  incident: Incident
  similarity: number
}
export interface ChangeCheck {
  services: GraphNode[]
  impacted: ImpactItem[]
  risk_score: number
  coupled_files: { path: string; count: number }[]
  reviewers: Responder[]
  similar_incidents: SimilarIncident[]
}
export type RankingMetric = 'pagerank' | 'centrality' | 'community'
export interface Rankings {
  metric: RankingMetric
  algorithm: 'falkordb' | 'degree_fallback'
  items: { service: GraphNode; score: number; community?: number }[]
}
export interface SuggestedEdge {
  from: string
  to: string
  type: string
  reason: string
}
export interface IncidentDetail {
  incident: Incident
  similar: SimilarIncident[]
  suggested_edges: SuggestedEdge[]
}
export interface NewIncident {
  title: string
  symptom: string
  severity: Incident['severity']
  affected: string[]
  started_at?: string
}
export interface ResolveIncident {
  root_cause: string
  fix: string
  resolved_by?: string
  confirmed_edges: { from: string; to: string }[]
  refuted_edges?: { from: string; to: string }[]
}
export interface ResolveResult {
  incident: Incident
  graph_updates: { created: number; strengthened: number; weakened: number }
}
export type RepoStatus = 'queued' | 'cloning' | 'detecting' | 'ingesting' | 'ready' | 'failed'
export interface Repo {
  id: string
  owner: string
  name: string
  full_name: string
  url: string
  status: RepoStatus
  progress: number
  message: string | null
  error: string | null
  last_synced_at: string | null
  created_at: string
  is_demo: boolean
}
export interface SystemScore {
  name: string
  predicted: number
  hits: number
  precision: number | null
  recall: number | null
}
export interface Evaluation {
  status: 'ok' | 'insufficient_history'
  reason: string | null
  commits_total: number
  commits_eligible: number
  train_commits: number
  test_commits: number
  split_at: string | null
  truth_pairs: number
  systems: SystemScore[]
  hidden_hits: { a: string; b: string }[]
  created_at: string
}
