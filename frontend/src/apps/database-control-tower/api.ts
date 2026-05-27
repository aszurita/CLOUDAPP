import type {
  DatabaseSource,
  MonitoredDatabase,
  SourceStatus,
  TableInventoryItem,
  TowerIntegration,
  TowerRecommendation,
} from "./types";

const DEFAULT_API_BASE_URL = import.meta.env.DEV ? "http://localhost:8000" : "";
const API_BASE_URL = (import.meta.env.VITE_CONTROLTOWER_API_BASE_URL || import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, "");

type ControlTowerSnapshot = {
  status: SourceStatus;
  latency_ms: number | null;
  active_connections: number | null;
  total_connections: number | null;
  idle_connections: number | null;
  database_size_bytes: number | null;
  tables_count: number | null;
  locks_count: number | null;
  cache_hit_ratio: number | null;
  deadlocks: number | null;
  health_score: number;
  captured_at: string;
  error: string | null;
};

type ControlTowerSourceResponse = {
  id: string;
  name: string;
  source_type: DatabaseSource["sourceType"];
  engine: DatabaseSource["engine"];
  environment: string;
  host: string | null;
  port: number | null;
  database_name: string | null;
  username: string | null;
  secret_ref: string | null;
  docker_container_name: string | null;
  cloud_provider: DatabaseSource["cloudProvider"];
  telemetry_provider: DatabaseSource["telemetryProvider"];
  badges: string[];
  status: SourceStatus;
  connection_configured: boolean;
  metric_snapshot: ControlTowerSnapshot | null;
  databases_count: number;
  databases: ControlTowerDatabaseResponse[];
  message: string | null;
};

type ControlTowerOverviewResponse = {
  health_global: number;
  sources_total: number;
  online_sources: number;
  local_docker_dbs: number;
  cloud_dbs: number;
  lakehouses: number;
  active_alerts: number;
  sources: ControlTowerSourceResponse[];
};

type ControlTowerTableResponse = {
  source_id: string;
  schema_name: string;
  table_name: string;
  estimated_rows: number | null;
  size_bytes: number | null;
  table_type: TableInventoryItem["tableType"];
  last_seen_at: string;
};

type ControlTowerDatabaseResponse = {
  source_id: string;
  database_name: string;
  owner: string | null;
  encoding: string | null;
  is_template: boolean;
  allow_connections: boolean;
  size_bytes: number | null;
  active_connections: number;
  total_connections: number;
  is_current: boolean;
  is_system: boolean;
};

type ControlTowerIntegrationResponse = Omit<TowerIntegration, "Icon"> & {
  required_settings: string[];
};

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: { "Content-Type": "application/json" } });
  if (!response.ok) throw new Error(`Control Tower API request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

export async function getControlTowerOverview() {
  return request<ControlTowerOverviewResponse>("/api/controltower/dashboard/database-overview");
}

export async function getControlTowerTables(sourceId: string) {
  return request<ControlTowerTableResponse[]>(`/api/controltower/database-sources/${encodeURIComponent(sourceId)}/tables`);
}

export async function getControlTowerDatabases(sourceId: string) {
  const databases = await request<ControlTowerDatabaseResponse[]>(`/api/controltower/database-sources/${encodeURIComponent(sourceId)}/databases`);
  return databases.map(mapDatabase);
}

export async function getControlTowerIntegrations() {
  return request<ControlTowerIntegrationResponse[]>("/api/controltower/dashboard/cloud-integrations");
}

export async function getControlTowerRecommendations() {
  return request<TowerRecommendation[]>("/api/controltower/recommendations");
}

export async function getControlTowerHistory() {
  return request<{ snapshots: { source_id: string; captured_at: string | null; health_score: number | null; status: string }[] }>(
    "/api/controltower/history",
  );
}

export function mapSource(source: ControlTowerSourceResponse): DatabaseSource {
  const snapshot = source.metric_snapshot;
  const databases = (source.databases ?? []).map(mapDatabase);
  return {
    id: source.id,
    name: source.name,
    displayName: displayName(source.name),
    sourceType: source.source_type,
    engine: source.engine,
    environment: source.environment,
    location: source.cloud_provider === "azure" ? "Azure" : source.source_type === "lakehouse" ? "Databricks" : "Local Docker",
    host: source.host ?? "not configured",
    port: source.port,
    databaseName: source.database_name ?? "not configured",
    username: source.username ?? "not configured",
    secretRef: source.secret_ref ?? "not configured",
    containerName: source.docker_container_name ?? undefined,
    cloudProvider: source.cloud_provider,
    telemetryProvider: source.telemetry_provider,
    status: source.status,
    healthScore: snapshot?.health_score ?? 0,
    latencyMs: snapshot?.latency_ms ?? null,
    activeConnections: snapshot?.active_connections ?? null,
    totalConnections: snapshot?.total_connections ?? null,
    idleConnections: snapshot?.idle_connections ?? null,
    databaseSizeMb: snapshot?.database_size_bytes ? Math.round(snapshot.database_size_bytes / 1024 / 1024) : null,
    tablesCount: snapshot?.tables_count ?? 0,
    locksCount: snapshot?.locks_count ?? null,
    deadlocks: snapshot?.deadlocks ?? null,
    databasesCount: source.databases_count ?? databases.length,
    databases,
    schemas: [],
    badges: source.badges,
    actions: source.source_type === "lakehouse" ? ["Schemas", "Tables", "History"] : ["Detail", "Tables", "Sessions", "Locks"],
    lastSnapshot: snapshot?.captured_at ? new Date(snapshot.captured_at).toLocaleString() : source.message ?? "pending",
    message: source.message ?? snapshot?.error ?? null,
    trend: [snapshot?.health_score ?? 0],
  };
}

function mapDatabase(database: ControlTowerDatabaseResponse): MonitoredDatabase {
  return {
    sourceId: database.source_id,
    databaseName: database.database_name,
    owner: database.owner,
    encoding: database.encoding,
    isTemplate: database.is_template,
    allowConnections: database.allow_connections,
    sizeMb: database.size_bytes ? Math.max(1, Math.round(database.size_bytes / 1024 / 1024)) : null,
    activeConnections: database.active_connections,
    totalConnections: database.total_connections,
    isCurrent: database.is_current,
    isSystem: database.is_system,
  };
}

export function mapTable(table: ControlTowerTableResponse): TableInventoryItem {
  return {
    sourceId: table.source_id,
    schemaName: table.schema_name,
    tableName: table.table_name,
    estimatedRows: table.estimated_rows,
    sizeMb: table.size_bytes ? Math.max(1, Math.round(table.size_bytes / 1024 / 1024)) : null,
    tableType: normalizeTableType(table.table_type),
    lastSeenAt: table.last_seen_at,
  };
}

function normalizeTableType(value: string): TableInventoryItem["tableType"] {
  const normalized = value.toLowerCase();
  if (normalized === "delta" || normalized === "view" || normalized === "system") return normalized;
  return "table";
}

function displayName(name: string) {
  return name
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
