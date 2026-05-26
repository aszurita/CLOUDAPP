import { ApiError } from "../api";

const DEFAULT_API_BASE_URL = import.meta.env.DEV
  ? "http://localhost:8000"
  : "https://ca-cloudapp-dev-api.delightfulsea-04be8a68.eastus.azurecontainerapps.io";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, "");
const BASE = "/api/sentinel";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    ...options,
  });
  if (!response.ok) {
    let detail: unknown = `API request failed: ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail ?? body;
    } catch {
      detail = response.statusText;
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export type SentinelLiveMetrics = {
  collected_at?: string | null;
  engine?: string | null;
  database_name?: string | null;
  active_sessions?: number | null;
  waiting_sessions?: number | null;
  lock_waiting_sessions?: number | null;
  idle_in_transaction?: number | null;
  cache_hit_ratio?: number | null;
  xact_commit_delta?: number | null;
  xact_rollback_delta?: number | null;
  deadlocks_delta?: number | null;
  wal_bytes_delta?: number | null;
  replication_lag_seconds?: number | null;
  message?: string | null;
};

export type SentinelStatus = {
  environment: string;
  storage_database_name: string;
  monitor_database_configured: boolean;
  monitor_database_name: string;
  monitor_lab_mode: string;
  auto_collect_enabled: boolean;
  collector_initialized: boolean;
  collector_running: boolean;
  collector_interval_seconds: number;
  risk_threshold: number;
  total_samples: number;
  query_samples: number;
  incidents_total: number;
  last_collected_at?: string | null;
  predictor: {
    configured_path: string;
    path_exists: boolean;
    loaded: boolean;
    model_version?: string | null;
    feature_count?: number;
    error?: string | null;
  };
  rca: {
    configured_path: string;
    path_exists: boolean;
    loaded: boolean;
    model_version?: string | null;
    feature_count?: number;
    error?: string | null;
  };
};

export type SentinelCollectResponse = {
  status: string;
  sample: SentinelLiveMetrics;
};

export type SentinelMetricPoint = SentinelLiveMetrics & {
  locks_granted?: number | null;
  locks_waiting?: number | null;
  long_transactions_count?: number | null;
};

export type SentinelQuerySample = {
  collected_at?: string;
  queryid?: number | string | null;
  query_fingerprint?: string | null;
  calls_delta?: number | null;
  mean_exec_time?: number | null;
  stddev_exec_time?: number | null;
  rows_delta?: number | null;
  wal_bytes_delta?: number | null;
};

export type SentinelPrediction = {
  risk_score: number;
  has_predicted_incident: boolean;
  predicted_incident_type: string;
  impact_level: string;
  top3_predictions: Array<{ incident_type: string; probability: number; rank?: number }>;
  rca_top_causes: RootCause[];
  primary_cause: string;
  primary_evidence_summary: string;
  current_metrics: Record<string, number>;
  horizon_minutes: number;
  predicted_at: string;
  model_version: string;
};

export type RootCause = {
  rank: number;
  cause: string;
  confidence: number;
  summary?: string;
  recommended_actions?: string[];
  evidence_features?: Array<{
    feature: string;
    value: number;
    importance?: number;
    direction?: string;
    shap_contribution?: number;
  }>;
};

export type SentinelIncident = {
  id: number;
  detected_at: string;
  engine?: string | null;
  database_name?: string | null;
  incident_type?: string | null;
  risk_score?: number | null;
  impact_level?: string | null;
  root_cause_top1?: string | null;
  status: string;
  resolved_at?: string | null;
  created_at?: string | null;
  root_cause_top3?: RootCause[] | null;
  evidence?: Record<string, number> | null;
  llm_explanation?: string | null;
  llm_recommended_actions?: CopilotAction[] | null;
  dba_action_taken?: string | null;
};

export type SentinelIncidentList = {
  incidents: SentinelIncident[];
  total: number;
  limit: number;
  offset: number;
};

export type IncidentEvidence = {
  incident_id: number;
  incident_type?: string | null;
  risk_score?: number | null;
  root_cause_top1?: string | null;
  root_cause_top3?: RootCause[] | null;
  llm_explanation?: string | null;
  llm_recommended_actions?: CopilotAction[] | null;
  metrics_timeline: SentinelMetricPoint[];
  slow_queries: SentinelQuerySample[];
};

export type CopilotAction = {
  order: number;
  action: string;
  sql?: string | null;
  requires_approval: boolean;
  urgency: string;
};

export type CopilotResponse = {
  incident_summary: string;
  impact_description: string;
  severity_classification: string;
  affected_operations: string[];
  top3_causes: RootCause[];
  evidence_signals: Array<{ signal: string; importance: string }>;
  recommended_actions: CopilotAction[];
  diagnostic_sqls: Array<{ category?: string; title?: string; sql: string }>;
  escalation_needed: boolean;
  escalation_reason?: string | null;
  generated_at: string;
  model_used: string;
  tokens_used?: number | null;
  safety_mode: string;
  incident_id?: number | null;
};

export type FaultType = {
  id: string;
  title: string;
  risk: string;
  api_mode: string;
  has_lab_script: boolean;
};

export type FaultJob = {
  job_id: string;
  fault_type: string;
  status: string;
  dry_run: boolean;
  duration_seconds: number;
  intensity: string;
  started_at: string;
  finished_at?: string | null;
  plan: string[];
  command?: string | null;
  processes?: Array<{ name: string; pid: number }>;
  logs?: Array<{ name: string; stdout: string; stderr: string }>;
  error?: string | null;
};

export type ModelMetricsResponse = {
  predictor: {
    model_version: string;
    trained_at?: string | null;
    threshold?: number | null;
    feature_count: number;
    binary?: Record<string, unknown>;
    multiclass?: Record<string, unknown>;
    impact?: Record<string, unknown>;
  };
  rca: {
    model_version: string;
    trained_at?: string | null;
    selected_model?: string | null;
    classes: string[];
    feature_count: number;
    val?: Record<string, unknown>;
    test?: Record<string, unknown>;
  };
};

export type ShapResponse = {
  model: string;
  explainability_method?: string | null;
  top_features: Array<{ feature: string; importance: number; method?: string }>;
};

export type SentinelEngine = {
  id: string;
  status: string;
  collector: string;
  features: string[];
  supported_metrics: string[];
  supported_incidents: string[];
  canonical_metric_count: number;
  canonical_metrics: string[];
};

export function fetchSentinelLiveMetrics() {
  return request<SentinelLiveMetrics>(`${BASE}/metrics/live`);
}

export function fetchSentinelStatus() {
  return request<SentinelStatus>(`${BASE}/status`);
}

export function triggerSentinelCollection() {
  return request<SentinelCollectResponse>(`${BASE}/collect/trigger`, { method: "POST" });
}

export function fetchSentinelMetricsHistory(minutes = 60) {
  return request<SentinelMetricPoint[]>(`${BASE}/metrics/history?minutes=${minutes}`);
}

export function fetchSentinelQueries(minutes = 30) {
  return request<SentinelQuerySample[]>(`${BASE}/metrics/queries?minutes=${minutes}`);
}

export function predictSentinelIncident(databaseName = "core_banking_sim") {
  return request<SentinelPrediction>(`${BASE}/predict`, {
    method: "POST",
    body: JSON.stringify({
      engine: "postgresql",
      database_name: databaseName,
      window_minutes: 10,
      horizon_minutes: 10,
    }),
  });
}

export function fetchSentinelIncidents(params: { status?: string; limit?: number; offset?: number; since_hours?: number } = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) query.set(key, String(value));
  });
  return request<SentinelIncidentList>(`${BASE}/incidents?${query.toString()}`);
}

export function fetchSentinelIncident(id: number) {
  return request<SentinelIncident>(`${BASE}/incidents/${id}`);
}

export function fetchSentinelIncidentEvidence(id: number) {
  return request<IncidentEvidence>(`${BASE}/incidents/${id}/evidence`);
}

export function explainSentinelCurrent(options: { databaseName?: string; persistIncident?: boolean } = {}) {
  return request<CopilotResponse>(`${BASE}/explain`, {
    method: "POST",
    body: JSON.stringify({
      engine: "postgresql",
      database_name: options.databaseName ?? "core_banking_sim",
      window_minutes: 10,
      horizon_minutes: 10,
      use_llm: false,
      persist_incident: options.persistIncident ?? false,
    }),
  });
}

export function explainSentinelIncident(incidentId: number) {
  return request<CopilotResponse>(`${BASE}/explain`, {
    method: "POST",
    body: JSON.stringify({
      incident_id: incidentId,
      use_current_metrics: false,
      use_llm: false,
      persist_incident: false,
    }),
  });
}

export function resolveSentinelIncident(id: number, actionTaken: string) {
  return request<SentinelIncident>(`${BASE}/incidents/${id}/resolve`, {
    method: "PATCH",
    body: JSON.stringify({ resolved_by: "demo-dba", action_taken: actionTaken }),
  });
}

export function fetchSentinelFaults() {
  return request<{ faults: FaultType[] }>(`${BASE}/simulate/faults`);
}

export function simulateSentinelFault(faultType: string, durationSeconds: number, intensity: string, dryRun = true) {
  return request<FaultJob>(`${BASE}/simulate/fault/${faultType}`, {
    method: "POST",
    body: JSON.stringify({ fault_type: faultType, duration_seconds: durationSeconds, intensity, dry_run: dryRun }),
  });
}

export function fetchSentinelFaultJob(jobId: string) {
  return request<FaultJob>(`${BASE}/simulate/fault/${jobId}/status`);
}

export function fetchSentinelModelMetrics() {
  return request<ModelMetricsResponse>(`${BASE}/evaluate/model/metrics`);
}

export function fetchSentinelShap(model: "predictor" | "rca" = "predictor", limit = 20) {
  return request<ShapResponse>(`${BASE}/evaluate/model/shap?model=${model}&limit=${limit}`);
}

export function fetchSentinelEngines() {
  return request<{ engines: SentinelEngine[]; canonical_metrics: string[] }>(`${BASE}/engines`);
}
