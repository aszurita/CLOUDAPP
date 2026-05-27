// ── Dashboard Schema types (mirror of backend) ────────────────────────────────

export type WidgetType = "kpi" | "bar_chart" | "line_chart" | "pie_chart" | "table";

export type QueryDef = {
  id: string;
  purpose: string;
  sql: string;
};

export type WidgetDef = {
  id: string;
  type: WidgetType;
  title: string;
  query_id: string;
  value_field?: string;
  x_field?: string;
  y_field?: string;
  col_span: number;
};

export type FilterDef = {
  id: string;
  label: string;
  type: "date" | "select" | "text";
  default_value?: string;
};

export type DashboardSchema = {
  title: string;
  description: string;
  catalog: string;
  schema_name: string;
  queries: QueryDef[];
  widgets: WidgetDef[];
  filters: FilterDef[];
};

// ── API request / response ────────────────────────────────────────────────────

export type PlanDashboardRequest = {
  prompt: string;
  catalog: string;
  schema_name: string;
  table?: string;
};

export type PlanDashboardResponse = {
  dashboard_schema: DashboardSchema;
  analysis_type: string;
  detected_tables: string[];
};

export type GenerateDashboardRequest = {
  prompt: string;
  catalog: string;
  schema_name: string;
  dashboard_schema: DashboardSchema;
};

export type GenerateDashboardResponse = {
  id: number;
  name: string;
  status: string;
  message: string;
};

export type WidgetData = {
  widget_id: string;
  query_id: string;
  columns: string[];
  rows: unknown[][];
  error: string | null;
};

export type ExecuteDashboardResponse = {
  dashboard_id: number;
  results: WidgetData[];
  execution_time_ms: number;
  demo_mode: boolean;
};

export type DashboardRecord = {
  id: number;
  name: string;
  description: string | null;
  prompt_original: string;
  catalog_name: string;
  schema_name: string;
  dashboard_schema: DashboardSchema;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type DashboardListResponse = {
  total: number;
  dashboards: DashboardRecord[];
};

// ── Catalog discovery ─────────────────────────────────────────────────────────

export type CatalogItem = { name: string };
export type SchemaItem = { name: string; catalog_name: string };
export type TableItem = {
  name: string;
  schema_name: string;
  catalog_name: string;
  table_type: string;
};

// ── Status ────────────────────────────────────────────────────────────────────

export type FactoryStatus = {
  title: string;
  databricks_configured: boolean;
  warehouse_id: string | null;
  catalog: string;
  total_dashboards: number;
};

// ── Gold Factory ─────────────────────────────────────────────────────────────

export type GoldObjectType = "TABLE" | "VIEW";
export type GoldWriteMode = "OR_REPLACE" | "IF_NOT_EXISTS";

export type GoldFactoryRequest = {
  prompt: string;
  target_catalog: string;
  target_schema: string;
  object_type: GoldObjectType;
  write_mode?: GoldWriteMode;
  created_by?: string;
};

export type GoldTablePlan = {
  decision: string;
  object_type: GoldObjectType;
  target_catalog: string;
  target_schema: string;
  target_name: string;
  source_tables: string[];
  source_sql: string;
  generated_sql: string;
  explanation: string;
  validation_status: string;
  validation_messages: string[];
  dry_run_ok: boolean;
  confidence: number;
};

export type GoldFactorySubmitRequest = {
  prompt: string;
  plan: GoldTablePlan;
  write_mode: GoldWriteMode;
  created_by?: string;
};

export type GoldFactorySubmitResponse = {
  request_id: number;
  status: string;
  databricks_job_id: string | null;
  databricks_run_id: string | null;
  databricks_run_url: string | null;
  target_table: string;
  message: string;
};

export type GoldFactoryRequestStatus = {
  request_id: number;
  status: string;
  target_table: string;
  object_type: string;
  write_mode: string;
  prompt: string | null;
  created_by: string | null;
  source_tables: string[];
  validation_status: string | null;
  validation_messages: string[];
  databricks_job_id: string | null;
  databricks_run_id: string | null;
  databricks_run_url: string | null;
  row_count: number | null;
  error_message: string | null;
  sync_error: string | null;
  generated_sql: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
};

// ── View ──────────────────────────────────────────────────────────────────────

export type FactoryView = "generator" | "history" | "viewer";
