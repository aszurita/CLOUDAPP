import type { LucideIcon } from "lucide-react";

export type TowerView = "overview" | "detail" | "tables" | "integrations" | "recommendations" | "history";

export type SourceStatus = "online" | "degraded" | "offline" | "pending";

export type SourceKind = "docker_database" | "cloud_database" | "lakehouse" | "system_database";

export type MetricProvider = "SQL directo" | "Azure Monitor" | "Application Insights" | "Log Analytics" | "Databricks";

export type MonitoredDatabase = {
  sourceId: string;
  databaseName: string;
  owner: string | null;
  encoding: string | null;
  isTemplate: boolean;
  allowConnections: boolean;
  sizeMb: number | null;
  activeConnections: number;
  totalConnections: number;
  isCurrent: boolean;
  isSystem: boolean;
};

export type DatabaseSource = {
  id: string;
  name: string;
  displayName: string;
  sourceType: SourceKind;
  engine: "postgresql" | "databricks";
  environment: string;
  location: string;
  host: string;
  port: number | null;
  databaseName: string;
  username: string;
  secretRef: string;
  containerName?: string;
  cloudProvider: "none" | "azure";
  telemetryProvider: MetricProvider;
  status: SourceStatus;
  healthScore: number;
  latencyMs: number | null;
  activeConnections: number | null;
  totalConnections: number | null;
  idleConnections: number | null;
  databaseSizeMb: number | null;
  tablesCount: number;
  locksCount: number | null;
  deadlocks?: number | null;
  databasesCount?: number;
  databases?: MonitoredDatabase[];
  schemas: string[];
  badges: string[];
  actions: string[];
  lastSnapshot: string;
  message?: string | null;
  trend: number[];
};

export type TableInventoryItem = {
  sourceId: string;
  schemaName: string;
  tableName: string;
  estimatedRows: number | null;
  sizeMb: number | null;
  tableType: "table" | "delta" | "view" | "system";
  lastSeenAt: string;
};

export type TowerIntegration = {
  id: string;
  name: string;
  provider: "Azure" | "Databricks" | "Local";
  status: "connected" | "configured" | "pending";
  signal: string;
  description: string;
  Icon: LucideIcon;
};

export type TowerRecommendation = {
  id: string;
  sourceId: string;
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  title: string;
  recommendation: string;
  evidence: string;
  impact: string;
  actionType: "read_only" | "approval_required" | "configuration";
};

export type ImplementationPhase = {
  phase: string;
  title: string;
  status: "ready" | "next" | "planned";
  outcome: string;
};
