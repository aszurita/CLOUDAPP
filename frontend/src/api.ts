const DEFAULT_API_BASE_URL = import.meta.env.DEV
  ? "http://localhost:8000"
  : "";

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

export type DatabaseColumnMetadata = {
  name: string;
  type: string;
  nullable: boolean;
  sensitive: boolean;
};

export type DatabaseTableMetadata = {
  name: string;
  schema_name: string;
  qualified_name: string;
  column_count: number;
  columns: DatabaseColumnMetadata[];
  allowed_query: boolean;
  internal: boolean;
  source_role: string;
};

export type DatabaseSchemaMetadata = {
  name: string;
  tables: DatabaseTableMetadata[];
};

export type DatabaseSourceMetadata = {
  key: string;
  label: string;
  role: string;
  engine: string;
  host: string | null;
  database_name: string;
  lab_mode: string;
  status: string;
  error: string | null;
  table_count: number;
  queryable_table_count: number;
  schemas: DatabaseSchemaMetadata[];
};

export type DatabaseInventory = {
  environment: string;
  sources: DatabaseSourceMetadata[];
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

export type DataOpsPipeline = {
  id: number;
  name: string;
  pipeline_key: string | null;
  pipeline_type: string | null;
  description: string | null;
  databricks_job_id: string | null;
  config_json: Record<string, unknown>;
  status: string;
  updated_at: string;
};

export type DataOpsMetric = {
  key: string;
  label: string;
  value: string | number | boolean | null;
  unit?: string;
  formatted?: string;
  tone?: string;
  order?: number;
};

export type DataOpsRunEvent = {
  event_type?: string;
  severity?: string;
  rule_code?: string;
  record_ref?: string;
  reason?: string;
  preview?: Record<string, string | number | boolean | null>;
  preview_json?: Record<string, string | number | boolean | null>;
};

export type DataOpsPipelineRun = {
  id: number;
  pipeline_id: number;
  run_id: string;
  databricks_run_id: string | null;
  business_run_id: string | null;
  status: string;
  bronze_rows: number;
  silver_rows: number;
  gold_rows: number;
  quality_score: number;
  quarantine_rows: number;
  duration_ms: number;
  failed_rules_json: { rule_code: string; layer: string; failed_rows: number; description: string }[];
  generated_tables_json: string[];
  metrics_json: DataOpsMetric[];
  events_json: DataOpsRunEvent[];
  databricks_run_url: string | null;
  ai_summary: string | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
};

export type DataOpsCurrent = {
  pipeline: DataOpsPipeline;
  latest_run: DataOpsPipelineRun | null;
};

export type DataOpsQualityCheck = {
  id: number;
  run_id: string;
  rule_code: string;
  layer: string;
  status: string;
  failed_rows: number;
  description: string;
  created_at: string;
};

export type DataOpsGeneratedAsset = {
  id: number;
  run_id: string;
  layer: string;
  asset_name: string;
  row_count: number;
  storage_path: string | null;
  created_at: string;
};

export type DataOpsQuarantineEvent = {
  id: number;
  run_id: string;
  rule_code: string;
  reason: string;
  source_file: string | null;
  record_ref: string | null;
  preview_json: Record<string, string | number | boolean | null>;
  created_at: string;
};

export type AutopilotTask = {
  id: number;
  report_id: number;
  title: string;
  priority: string;
  category: string;
  status: string;
  owner: string;
  source: string;
  due_hint: string | null;
  action_json: {
    description?: string;
    actions?: string[];
    evidence?: unknown[];
  };
  created_at: string;
  updated_at: string;
};

export type AutopilotReport = {
  id: number;
  run_id: string;
  status: string;
  overall_score: number;
  risk_level: string;
  summary: string;
  metrics_json: Record<string, string | number | boolean | null>;
  findings_json: {
    category: string;
    severity: string;
    title: string;
    description: string;
    evidence?: unknown[];
    actions?: string[];
    source?: string;
  }[];
  remediation_plan_json: {
    step: number;
    priority: string;
    category: string;
    title: string;
    recommended_actions: string[];
    expected_outcome: string;
  }[];
  infra_suggestions_json: {
    area: string;
    title: string;
    suggestion: string;
    impact: string;
  }[];
  ai_summary: string | null;
  raw_context_json: Record<string, unknown>;
  created_at: string;
  tasks: AutopilotTask[];
};

export type AutopilotCurrent = {
  latest_report: AutopilotReport | null;
};

export type CatalogStatus = {
  provider: string;
  external_catalog: string;
  datahub_configured: boolean;
  purview_configured: boolean;
  assets_total: number;
  documented_assets: number;
  sensitive_columns: number;
  lineage_edges: number;
  latest_sync_status: string | null;
};

export type CatalogAsset = {
  id: number;
  asset_urn: string;
  asset_name: string;
  display_name: string;
  source_system: string;
  platform: string;
  database_name: string | null;
  schema_name: string | null;
  table_name: string;
  layer: string;
  domain: string;
  owner: string;
  description: string | null;
  documentation_status: string;
  quality_score: number | null;
  sensitivity_level: string;
  external_url: string | null;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CatalogColumn = {
  id: number;
  asset_id: number;
  column_name: string;
  data_type: string;
  nullable: boolean;
  description: string | null;
  classification: string;
  is_sensitive: boolean;
  sample_safe_value: string | null;
  created_at: string;
};

export type CatalogClassification = {
  id: number;
  code: string;
  label: string;
  rank: number;
  description: string;
  created_at: string;
};

export type CatalogLineageEdge = {
  id: number;
  source_asset_urn: string;
  target_asset_urn: string;
  lineage_type: string;
  transformation_name: string | null;
  confidence: number;
  created_at: string;
};

export type CatalogSyncRun = {
  id: number;
  source: string;
  status: string;
  assets_seen: number;
  assets_created: number;
  assets_updated: number;
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
};

export type CatalogDocumentResponse = {
  asset: CatalogAsset;
  documentation: string;
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

export function getQueryMetadata() {
  return request<DatabaseInventory>("/api/query-governance/metadata");
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

export function getDbaSources() {
  return request<DatabaseInventory>("/api/dba/sources");
}

export function getDatabaseInventory() {
  return request<DatabaseInventory>("/api/database/inventory");
}

function encodeDataOpsKey(pipelineKey: string) {
  return encodeURIComponent(pipelineKey);
}

export function getDataOpsPipelines() {
  return request<DataOpsPipeline[]>("/api/dataops/pipelines");
}

export function runDataOpsPipeline(pipelineKey?: string) {
  const path = pipelineKey
    ? `/api/dataops/pipelines/${encodeDataOpsKey(pipelineKey)}/run`
    : "/api/dataops/pipelines/run";
  return request<DataOpsPipelineRun>(path, {
    method: "POST",
    body: JSON.stringify({ actor: "demo-user" }),
  });
}

export function getDataOpsCurrent(pipelineKey?: string) {
  const path = pipelineKey
    ? `/api/dataops/pipelines/${encodeDataOpsKey(pipelineKey)}/current`
    : "/api/dataops/pipelines/current";
  return request<DataOpsCurrent>(path);
}

export function getDataOpsHistory(pipelineKey?: string) {
  const path = pipelineKey
    ? `/api/dataops/pipelines/${encodeDataOpsKey(pipelineKey)}/history`
    : "/api/dataops/pipelines/history";
  return request<DataOpsPipelineRun[]>(path);
}

export function getDataOpsQuality(pipelineKey?: string) {
  const path = pipelineKey
    ? `/api/dataops/pipelines/${encodeDataOpsKey(pipelineKey)}/quality/latest`
    : "/api/dataops/quality/latest";
  return request<DataOpsQualityCheck[]>(path);
}

export function getDataOpsAssets(pipelineKey?: string) {
  const path = pipelineKey
    ? `/api/dataops/pipelines/${encodeDataOpsKey(pipelineKey)}/assets`
    : "/api/dataops/assets";
  return request<DataOpsGeneratedAsset[]>(path);
}

export function getDataOpsQuarantine(pipelineKey?: string) {
  const path = pipelineKey
    ? `/api/dataops/pipelines/${encodeDataOpsKey(pipelineKey)}/quarantine`
    : "/api/dataops/quarantine";
  return request<DataOpsQuarantineEvent[]>(path);
}

export function runAutopilotAnalysis() {
  return request<AutopilotReport>("/api/autopilot/analyze", {
    method: "POST",
    body: JSON.stringify({ actor: "demo-user" }),
  });
}

export function getAutopilotLatest() {
  return request<AutopilotCurrent>("/api/autopilot/latest");
}

export function getAutopilotHistory() {
  return request<AutopilotReport[]>("/api/autopilot/history");
}

export function updateAutopilotTaskStatus(taskId: number, status: string) {
  return request<AutopilotTask>(`/api/autopilot/tasks/${taskId}/status`, {
    method: "POST",
    body: JSON.stringify({ status, actor: "demo-user" }),
  });
}

export function syncCatalog() {
  return request<CatalogSyncRun>("/api/catalog/sync", {
    method: "POST",
    body: JSON.stringify({ actor: "demo-user" }),
  });
}

export function getCatalogStatus() {
  return request<CatalogStatus>("/api/catalog/status");
}

export function getCatalogAssets() {
  return request<CatalogAsset[]>("/api/catalog/assets");
}

export function getCatalogColumns(assetId: number) {
  return request<CatalogColumn[]>(`/api/catalog/assets/${assetId}/columns`);
}

export function getCatalogLineage() {
  return request<CatalogLineageEdge[]>("/api/catalog/lineage");
}

export function getCatalogClassifications() {
  return request<CatalogClassification[]>("/api/catalog/classifications");
}

export function getCatalogSyncRuns() {
  return request<CatalogSyncRun[]>("/api/catalog/sync-runs");
}

export function generateCatalogDocumentation(assetId: number) {
  return request<CatalogDocumentResponse>(`/api/catalog/assets/${assetId}/document`, {
    method: "POST",
    body: JSON.stringify({ actor: "demo-user" }),
  });
}

export function updateCatalogOwner(assetId: number, owner: string) {
  return request<CatalogAsset>(`/api/catalog/assets/${assetId}/owner`, {
    method: "POST",
    body: JSON.stringify({ owner, actor: "demo-user" }),
  });
}

export function updateCatalogClassification(assetId: number, classification: string) {
  return request<CatalogAsset>(`/api/catalog/assets/${assetId}/classification`, {
    method: "POST",
    body: JSON.stringify({ classification, actor: "demo-user" }),
  });
}

export function updateCatalogColumnDescription(columnId: number, description: string) {
  return request<CatalogColumn>(`/api/catalog/columns/${columnId}/description`, {
    method: "POST",
    body: JSON.stringify({ description, actor: "demo-user" }),
  });
}
