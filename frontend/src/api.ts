const DEFAULT_API_BASE_URL = import.meta.env.DEV
  ? "http://localhost:8000"
  : "https://ca-cloudapp-dev-api.delightfulsea-04be8a68.eastus.azurecontainerapps.io";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `API request failed: ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export type PlatformStatus = {
  app_name: string;
  environment: string;
  database: string;
  services_total: number;
  services_healthy: number;
  environments_total: number;
  latest_deployment_status: string | null;
  audit_events_total: number;
  ai_provider: string;
  ai_configured: boolean;
  ai_model: string;
};

export type QueryAnalyzeResponse = {
  id: number;
  decision: string;
  risk_level: string;
  reasons: string[];
  recommendations: string[];
  suggested_sql: string | null;
  ai_explanation: string;
  created_at: string;
};

export type QueryExecuteResponse = QueryAnalyzeResponse & {
  columns: string[];
  rows: Record<string, string | number | boolean | null>[];
  row_count: number;
  execution_ms: number;
};

export type QueryReview = {
  id: number;
  sql_text: string;
  action: string;
  decision: string;
  risk_level: string;
  reasons_json: string[];
  recommendations_json: string[];
  ai_explanation: string | null;
  suggested_sql: string | null;
  row_count: number | null;
  execution_ms: number | null;
  actor: string;
  created_at: string;
};

export type QueryPolicy = {
  id: number;
  code: string;
  description: string;
  severity: string;
  enabled: boolean;
};

export type DemoQueries = {
  dangerous: string;
  safe: string;
};

export type DbaAnalyzeResponse = {
  profiles_count: number;
  recommendations_count: number;
  ai_summary: string;
};

export type DbaTableProfile = {
  id: number;
  schema_name: string;
  table_name: string;
  estimated_rows: number;
  total_size_bytes: number;
  columns_json: { name: string; type: string; nullable: boolean }[];
  sensitive_columns_json: string[];
  risk_level: string;
  created_at: string;
};

export type DbaRecommendation = {
  id: number;
  profile_id: number | null;
  title: string;
  severity: string;
  recommendation: string;
  category: string;
  affected_tables_json: string[];
  source: string;
  created_at: string;
};

export type Environment = {
  id: number;
  code: string;
  name: string;
  status: string;
  region: string;
  is_active: boolean;
};

export type Service = {
  id: number;
  environment_id: number;
  name: string;
  service_type: string;
  status: string;
  version: string;
  health_url: string | null;
  cost_estimate_usd: number;
};

export type Deployment = {
  id: number;
  service_id: number;
  commit_sha: string;
  status: string;
  deployed_by: string;
  pipeline_url: string | null;
  deployed_at: string;
};

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

export function getPlatformStatus() {
  return request<PlatformStatus>("/api/platform/status");
}

export function getEnvironments() {
  return request<Environment[]>("/api/environments");
}

export function getServices() {
  return request<Service[]>("/api/services");
}

export function getDeployments() {
  return request<Deployment[]>("/api/deployments");
}

export function getDemoQueries() {
  return request<DemoQueries>("/api/query-governance/demo-queries");
}

export function getQueryPolicies() {
  return request<QueryPolicy[]>("/api/query-governance/policies");
}

export function getQueryHistory() {
  return request<QueryReview[]>("/api/query-governance/history");
}

export function analyzeQuery(sql: string) {
  return request<QueryAnalyzeResponse>("/api/query-governance/analyze", {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}

export function executeQuery(sql: string) {
  return request<QueryExecuteResponse>("/api/query-governance/execute", {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}

export function runDbaAnalysis() {
  return request<DbaAnalyzeResponse>("/api/dba/analyze", { method: "POST" });
}

export function getDbaTables() {
  return request<DbaTableProfile[]>("/api/dba/tables");
}

export function getDbaRecommendations() {
  return request<DbaRecommendation[]>("/api/dba/recommendations");
}
