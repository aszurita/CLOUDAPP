import {
  Activity,
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Cloud,
  Database,
  Gauge,
  History,
  Info,
  KeyRound,
  Layers3,
  Lock,
  Network,
  RefreshCw,
  Search,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Table2,
  TerminalSquare,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";

import {
  getControlTowerDatabases,
  getControlTowerIntegrations,
  getControlTowerOverview,
  getControlTowerRecommendations,
  getControlTowerTables,
  mapSource,
  mapTable,
} from "./api";
import {
  databaseSources,
  formatPort,
  formatSize,
  integrations as integrationTemplates,
  recommendations,
  sourceIcon,
  tableInventory,
} from "./data";
import type { DatabaseSource, SourceStatus, TableInventoryItem, TowerIntegration, TowerRecommendation, TowerView } from "./types";
import "./databaseControlTower.css";

type Props = {
  onBack: () => void;
};

const views: { id: TowerView; label: string; Icon: typeof Database }[] = [
  { id: "overview", label: "Overview", Icon: Gauge },
  { id: "detail", label: "Database Detail", Icon: Database },
  { id: "tables", label: "Tables Inventory", Icon: Table2 },
  { id: "integrations", label: "Cloud Integrations", Icon: Cloud },
  { id: "recommendations", label: "Recommendations", Icon: Sparkles },
  { id: "history", label: "History", Icon: History },
];

const hiddenSourceIds = new Set(["azure_postgres_cloudapp"]);
const visibleFallbackSources = databaseSources.filter((source) => !hiddenSourceIds.has(source.id));
const visibleFallbackTables = tableInventory.filter((table) => !hiddenSourceIds.has(table.sourceId));
const visibleFallbackRecommendations = recommendations.filter((item) => !hiddenSourceIds.has(item.sourceId));
const healthScoreRules = [
  { label: "Latency", value: "-25 / -10", detail: "> 250 ms resta 25; > 100 ms resta 10." },
  { label: "Total connections", value: "-15 / -8", detail: "> 100 resta 15; > 50 resta 8." },
  { label: "Active connections", value: "-10", detail: "> 50 conexiones activas resta 10." },
  { label: "Locks", value: "-18 / -5", detail: "> 50 locks resta 18; cualquier lock resta 5." },
  { label: "Deadlocks", value: "-5", detail: "Cualquier deadlock registrado resta 5." },
  { label: "Azure resource ID", value: "-3", detail: "Azure PostgreSQL resta 3 si falta AZURE_POSTGRES_RESOURCE_ID." },
];

export function DatabaseControlTowerApp({ onBack }: Props) {
  const [activeView, setActiveView] = useState<TowerView>("overview");
  const [selectedSourceId, setSelectedSourceId] = useState(visibleFallbackSources[0].id);
  const [tableFilter, setTableFilter] = useState("all");
  const [sources, setSources] = useState<DatabaseSource[]>(visibleFallbackSources);
  const [tables, setTables] = useState<TableInventoryItem[]>(visibleFallbackTables);
  const [towerIntegrations, setTowerIntegrations] = useState<TowerIntegration[]>(integrationTemplates);
  const [towerRecommendations, setTowerRecommendations] = useState<TowerRecommendation[]>(visibleFallbackRecommendations);
  const [apiStatus, setApiStatus] = useState<"loading" | "live" | "fallback">("loading");

  useEffect(() => {
    let cancelled = false;
    async function loadControlTower() {
      try {
        const overview = await getControlTowerOverview();
        const mappedSources = overview.sources.map(mapSource).filter((source) => !hiddenSourceIds.has(source.id));
        const [tableResults, databaseResults] = await Promise.all([
          Promise.allSettled(mappedSources.map((source) => getControlTowerTables(source.id))),
          Promise.allSettled(
            mappedSources.map((source) => (source.engine === "postgresql" ? getControlTowerDatabases(source.id) : Promise.resolve(source.databases ?? []))),
          ),
        ]);
        const liveTables = tableResults.flatMap((result) => (result.status === "fulfilled" ? result.value.map(mapTable) : []))
          .filter((table) => !hiddenSourceIds.has(table.sourceId));
        const databasesBySource = new Map(
          mappedSources.map((source, index) => [
            source.id,
            databaseResults[index]?.status === "fulfilled" ? databaseResults[index].value : source.databases ?? [],
          ]),
        );
        const sourcesWithSchemas = mappedSources.map((source) => {
          const sourceTables = liveTables.filter((table) => table.sourceId === source.id);
          const liveSchemas = schemasForSource(source.id, liveTables);
          const liveDatabases = databasesBySource.get(source.id) ?? source.databases ?? [];
          return {
            ...source,
            databases: source.engine === "postgresql" ? liveDatabases : source.databases,
            databasesCount: source.engine === "postgresql" ? liveDatabases.length || source.databasesCount : source.databasesCount,
            schemas: liveSchemas.length ? liveSchemas : source.schemas,
            tablesCount: sourceTables.length || source.tablesCount,
          };
        });
        const [liveRecommendationsResult, liveIntegrationsResult] = await Promise.allSettled([
          getControlTowerRecommendations(),
          getControlTowerIntegrations(),
        ]);
        if (cancelled) return;
        setSources(sourcesWithSchemas);
        setTables(liveTables.length ? liveTables : visibleFallbackTables);
        const liveRecommendations = liveRecommendationsResult.status === "fulfilled" ? liveRecommendationsResult.value : [];
        const liveIntegrations = liveIntegrationsResult.status === "fulfilled" ? liveIntegrationsResult.value : [];
        setTowerRecommendations(
          (liveRecommendations.length ? liveRecommendations : visibleFallbackRecommendations).filter((item) => !hiddenSourceIds.has(item.sourceId)),
        );
        setTowerIntegrations(liveIntegrations.length ? mergeIntegrationIcons(liveIntegrations) : integrationTemplates);
        setSelectedSourceId((current) => (sourcesWithSchemas.some((source) => source.id === current) ? current : sourcesWithSchemas[0]?.id ?? current));
        setApiStatus("live");
      } catch {
        if (!cancelled) setApiStatus("fallback");
      }
    }
    void loadControlTower();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedSource = sources.find((source) => source.id === selectedSourceId) ?? sources[0];
  const onlineSources = sources.filter((source) => source.status !== "offline" && source.status !== "pending").length;
  const localDbs = sources
    .filter((source) => source.sourceType === "docker_database" || source.sourceType === "system_database")
    .reduce((sum, source) => sum + databaseCount(source), 0);
  const cloudDbs = sources
    .filter((source) => source.sourceType === "cloud_database")
    .reduce((sum, source) => sum + databaseCount(source), 0);
  const lakehouses = sources.filter((source) => source.sourceType === "lakehouse").length;
  const healthSources = sources.filter((source) => source.healthScore > 0);
  const globalHealth = healthSources.length
    ? Math.round(healthSources.reduce((sum, source) => sum + source.healthScore, 0) / healthSources.length)
    : 0;
  const activeAlerts = towerRecommendations.filter((item) => item.severity === "high" || item.severity === "critical").length;

  function openSource(sourceId: string) {
    setSelectedSourceId(sourceId);
    setActiveView("detail");
  }

  const filteredTables = useMemo(() => {
    if (tableFilter === "all") return tables;
    return tables.filter((table) => table.sourceId === tableFilter);
  }, [tableFilter, tables]);

  return (
    <main className="tower-app-shell">
      <header className="tower-app-topbar">
        <div className="tower-title-block">
          <p className="tower-eyebrow">OGA Database Control Tower</p>
          <h1>Database Control Tower AI</h1>
          <p>Consola local-first para PostgreSQL Docker, Azure PostgreSQL y Databricks Lakehouse.</p>
        </div>
        <div className="tower-topbar-actions">
          <span className="tower-live-pill">
            <Activity size={15} aria-hidden="true" />
            {apiStatus === "live" ? "Live API" : apiStatus === "loading" ? "Loading API" : "Fallback data"}
          </span>
          <button className="tower-ghost-button" onClick={onBack}>
            <ArrowLeft size={16} aria-hidden="true" />
            Suites
          </button>
        </div>
      </header>

      <section className="tower-command-strip">
        <MetricCard label="Health global" value={`${globalHealth}/100`} Icon={ShieldCheck} tone="green" />
        <MetricCard label="Sources online" value={`${onlineSources}/${sources.length}`} Icon={CheckCircle2} tone="green" />
        <MetricCard label="Local Docker DBs" value={localDbs} Icon={Server} tone="blue" />
        <MetricCard label="Cloud DBs" value={cloudDbs} Icon={Cloud} tone="purple" />
        <MetricCard label="Lakehouse" value={lakehouses} Icon={Layers3} tone="amber" />
        <MetricCard label="Alertas" value={activeAlerts} Icon={ShieldAlert} tone="red" />
      </section>

      <nav className="tower-nav" aria-label="Database Control Tower views">
        {views.map(({ id, label, Icon }) => (
          <button key={id} className={activeView === id ? "active" : ""} onClick={() => setActiveView(id)}>
            <Icon size={16} aria-hidden="true" />
            {label}
          </button>
        ))}
      </nav>

      {activeView === "overview" && (
        <OverviewView
          sources={sources}
          integrations={towerIntegrations}
          recommendations={towerRecommendations}
          onOpenSource={openSource}
        />
      )}
      {activeView === "detail" && (
        <DetailView
          source={selectedSource}
          sources={sources}
          tables={tables}
          recommendations={towerRecommendations}
          onSelectSource={setSelectedSourceId}
        />
      )}
      {activeView === "tables" && (
        <TablesView sources={sources} tableFilter={tableFilter} setTableFilter={setTableFilter} tables={filteredTables} />
      )}
      {activeView === "integrations" && <IntegrationsView integrations={towerIntegrations} />}
      {activeView === "recommendations" && <RecommendationsView sources={sources} recommendations={towerRecommendations} onOpenSource={openSource} />}
      {activeView === "history" && <HistoryView sources={sources} selectedSource={selectedSource} onSelectSource={setSelectedSourceId} />}
    </main>
  );
}

function MetricCard({
  label,
  value,
  Icon,
  tone,
}: {
  label: string;
  value: string | number;
  Icon: typeof Database;
  tone: "green" | "blue" | "purple" | "amber" | "red";
}) {
  return (
    <div className={`tower-metric tower-tone-${tone}`}>
      <span>
        <Icon size={18} aria-hidden="true" />
      </span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function OverviewView({
  sources,
  integrations,
  recommendations,
  onOpenSource,
}: {
  sources: DatabaseSource[];
  integrations: TowerIntegration[];
  recommendations: TowerRecommendation[];
  onOpenSource: (sourceId: string) => void;
}) {
  return (
    <section className="tower-overview">
      <div className="tower-cloud-badges">
        {integrations.map((integration) => (
          <span key={integration.id} className={`tower-cloud-badge ${integration.status}`}>
            <integration.Icon size={15} aria-hidden="true" />
            {integration.name}
          </span>
        ))}
      </div>

      <div className="tower-source-grid">
        {sources.map((source) => (
          <SourceCard key={source.id} source={source} onOpen={() => onOpenSource(source.id)} />
        ))}
      </div>

      <section className="tower-panel">
        <PanelHeader title="DBA Copilot signals" count={recommendations.length} />
        <div className="tower-reco-mini-list">
          {recommendations.slice(0, 4).map((item) => (
            <RecommendationMini key={item.id} item={item} />
          ))}
        </div>
      </section>
    </section>
  );
}

function SourceCard({ source, onOpen }: { source: DatabaseSource; onOpen: () => void }) {
  const Icon = sourceIcon(source);
  return (
    <article className={`tower-source-card status-${source.status}`}>
      <div className="tower-source-head">
        <span className="tower-source-icon">
          <Icon size={22} aria-hidden="true" />
        </span>
        <StatusBadge status={source.status} />
      </div>
      <div className="tower-source-title">
        <span>{source.location}</span>
        <h2>{source.name}</h2>
        <p>{source.host}:{formatPort(source.port)}</p>
      </div>
      <div className="tower-badge-row">
        {source.badges.map((badge) => (
          <span key={badge}>{badge}</span>
        ))}
      </div>
      <div className="tower-card-metrics">
        <MiniMetric label={source.engine === "databricks" ? "Catalog" : "Base activa"} value={source.databaseName} />
        <MiniMetric label={source.engine === "databricks" ? "Esquemas" : "Bases visibles"} value={source.engine === "databricks" ? source.schemas.length : databaseCount(source)} />
        <MiniMetric label="Latency" value={source.latencyMs === null ? "managed" : `${source.latencyMs} ms`} />
        <MiniMetric label="Connections" value={source.totalConnections ?? "n/a"} />
      </div>
      {source.status === "offline" && source.message && (
        <p className="tower-source-error" title={source.message}>
          {friendlySourceError(source.message)}
        </p>
      )}
      <div className="tower-health-row">
        <div>
          <span style={{ width: `${source.healthScore}%` }} />
        </div>
        <strong>{source.healthScore}/100</strong>
      </div>
      <button className="tower-open-button" onClick={onOpen}>
        Detail
        <ChevronRight size={16} aria-hidden="true" />
      </button>
    </article>
  );
}

function DetailView({
  source,
  sources,
  tables,
  recommendations,
  onSelectSource,
}: {
  source: DatabaseSource;
  sources: DatabaseSource[];
  tables: TableInventoryItem[];
  recommendations: TowerRecommendation[];
  onSelectSource: (sourceId: string) => void;
}) {
  const sourceTables = tables.filter((table) => table.sourceId === source.id);
  const sourceRecommendations = recommendations.filter((recommendation) => recommendation.sourceId === source.id);

  return (
    <section className="tower-detail-layout">
      <aside className="tower-panel tower-source-sidebar">
        <PanelHeader title="Sources" count={sources.length} />
        <div className="tower-source-picker">
          {sources.map((item) => (
            <button
              key={item.id}
              className={item.id === source.id ? "active" : ""}
              onClick={() => onSelectSource(item.id)}
            >
              <span>{item.name}</span>
              <StatusBadge status={item.status} />
            </button>
          ))}
        </div>
      </aside>

      <div className="tower-detail-main">
        <div className="tower-panel tower-detail-hero">
          <div>
            <p className="tower-eyebrow">{source.engine} · {source.environment}</p>
            <h2>{source.displayName}</h2>
            <p>{source.host}:{formatPort(source.port)} · {source.databaseName}</p>
            {source.status === "offline" && source.message && (
              <p className="tower-detail-error">{friendlySourceError(source.message)}</p>
            )}
          </div>
          <HealthScoreRing source={source} />
        </div>

        <div className="tower-detail-metrics">
          <MetricCard label="Latency" value={source.latencyMs === null ? "managed" : `${source.latencyMs} ms`} Icon={Gauge} tone="blue" />
          <MetricCard label="Active connections" value={source.activeConnections ?? "n/a"} Icon={Activity} tone="green" />
          <MetricCard label="Locks" value={source.locksCount ?? "n/a"} Icon={Lock} tone={source.locksCount ? "amber" : "green"} />
          <MetricCard label="Tables" value={source.tablesCount} Icon={Table2} tone="purple" />
        </div>

        <section className="tower-two-column">
          <div className="tower-panel">
            <PanelHeader title="Connection profile" count={source.badges.length} />
            <div className="tower-profile-grid">
              <ProfileItem label="Host" value={source.host} />
              <ProfileItem label="Port" value={formatPort(source.port)} />
              <ProfileItem label={source.engine === "databricks" ? "Catalog" : "Base activa"} value={source.databaseName} />
              <ProfileItem label={source.engine === "databricks" ? "Esquemas" : "Bases visibles"} value={`${databaseCount(source)}`} />
              <ProfileItem label="Username" value={source.username} />
              <ProfileItem label="Secret ref" value={source.secretRef} />
              <ProfileItem label="Telemetry" value={source.telemetryProvider} />
            </div>
          </div>

          <div className="tower-panel">
            <PanelHeader title={source.engine === "databricks" ? "Esquemas del catalogo" : "Bases del servidor"} count={databaseCount(source)} />
            <DatabaseList source={source} />
          </div>
        </section>

        <div className="tower-panel">
          <PanelHeader title={source.engine === "databricks" ? `Tablas por catalogo: ${source.databaseName}` : `Tablas por base: ${source.databaseName}`} count={sourceTables.length} />
          <GroupedTableList source={source} tables={sourceTables} limit={12} />
        </div>

        <div className="tower-panel">
          <PanelHeader title="Source recommendations" count={sourceRecommendations.length} />
          {sourceRecommendations.length ? (
            <div className="tower-recommendation-list">
              {sourceRecommendations.map((item) => (
                <RecommendationCard key={item.id} item={item} />
              ))}
            </div>
          ) : (
            <div className="tower-empty-state">
              <ShieldCheck size={22} aria-hidden="true" />
              <span>Sin recomendaciones criticas para esta fuente.</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function TablesView({
  sources,
  tableFilter,
  setTableFilter,
  tables,
}: {
  sources: DatabaseSource[];
  tableFilter: string;
  setTableFilter: (value: string) => void;
  tables: TableInventoryItem[];
}) {
  const knownRows = tables.filter((table) => table.estimatedRows !== null);
  const knownSize = tables.filter((table) => table.sizeMb !== null);
  const totalRows = knownRows.reduce((sum, table) => sum + (table.estimatedRows ?? 0), 0);
  const totalSize = knownSize.reduce((sum, table) => sum + (table.sizeMb ?? 0), 0);

  return (
    <section className="tower-section-stack">
      <div className="tower-panel tower-table-toolbar">
        <div>
          <p className="tower-eyebrow">Tables Inventory</p>
          <h2>
            {tables.length} tablas · {knownRows.length ? `${totalRows.toLocaleString()} filas estimadas` : "filas n/d"} ·{" "}
            {knownSize.length ? formatSize(totalSize) : "tamano n/d"}
          </h2>
        </div>
        <label>
          Fuente
          <select value={tableFilter} onChange={(event) => setTableFilter(event.target.value)}>
            <option value="all">Todas las fuentes</option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>{source.name}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="tower-panel tower-inventory-panel">
        <div className="tower-inventory-table">
          <div className="tower-inventory-row header">
            <span>Source</span>
            <span>Schema</span>
            <span>Table</span>
            <span>Rows</span>
            <span>Size</span>
            <span>Type</span>
            <span>Last seen</span>
          </div>
          {tables.map((table) => {
            const source = sources.find((item) => item.id === table.sourceId) ?? tableSourceFallback(table.sourceId);
            return (
              <div className="tower-inventory-row" key={`${table.sourceId}-${table.schemaName}-${table.tableName}`}>
                <span>{source.name}</span>
                <span>{table.schemaName}</span>
                <strong>{table.tableName}</strong>
                <span>{formatRows(table.estimatedRows)}</span>
                <span>{formatTableSize(table.sizeMb)}</span>
                <span className="tower-type-pill">{table.tableType}</span>
                <span>{table.lastSeenAt}</span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function DatabaseList({ source }: { source: DatabaseSource }) {
  if (source.engine === "databricks") {
    return (
      <div className="tower-database-list">
        {source.schemas.map((schema) => (
          <div key={schema}>
            <Database size={16} aria-hidden="true" />
            <div>
              <strong>{schema}</strong>
              <span>schema lakehouse</span>
            </div>
            <small>catalog</small>
          </div>
        ))}
      </div>
    );
  }

  const databases = source.databases ?? [];
  if (!databases.length) {
    return (
      <div className="tower-empty-state">
        <Database size={22} aria-hidden="true" />
        <span>La API aun no devolvio el listado de bases; la base activa es {source.databaseName}.</span>
      </div>
    );
  }

  return (
    <div className="tower-database-list">
      {databases.map((database) => (
        <div key={`${database.sourceId}-${database.databaseName}`} className={database.isCurrent ? "current" : ""}>
          <Database size={16} aria-hidden="true" />
          <div>
            <strong>{database.databaseName}</strong>
            <span>
              {database.owner ?? "owner n/a"} · {database.totalConnections} conexiones · {database.sizeMb === null ? "size n/a" : formatSize(database.sizeMb)}
            </span>
          </div>
          <small>{database.isCurrent ? "activa" : database.isSystem ? "sistema" : "visible"}</small>
        </div>
      ))}
    </div>
  );
}

function GroupedTableList({ source, tables, limit }: { source: DatabaseSource; tables: TableInventoryItem[]; limit: number }) {
  if (!tables.length) {
    return (
      <div className="tower-empty-state">
        <Table2 size={22} aria-hidden="true" />
        <span>No hay tablas reportadas para esta fuente.</span>
      </div>
    );
  }

  const groups = groupTablesBySchema(tables.slice(0, limit));
  return (
    <div className="tower-table-groups">
      {groups.map((group) => (
        <section key={group.schemaName} className="tower-table-group">
          <div className="tower-table-group-head">
            <span>{source.engine === "databricks" ? "Catalogo" : "Base"}: {source.databaseName}</span>
            <strong>Esquema: {group.schemaName}</strong>
          </div>
          <div className="tower-table-mini">
            {group.tables.map((table) => (
              <div key={`${table.schemaName}-${table.tableName}`}>
                <span>{table.tableType}</span>
                <strong>{table.tableName}</strong>
                <small>{formatRows(table.estimatedRows)} · {formatTableSize(table.sizeMb)}</small>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function IntegrationsView({ integrations }: { integrations: TowerIntegration[] }) {
  return (
    <section className="tower-section-stack">
      <div className="tower-integration-grid">
        {integrations.map((integration) => (
          <article className="tower-integration-card" key={integration.id}>
            <span className="tower-integration-icon">
              <integration.Icon size={22} aria-hidden="true" />
            </span>
            <div>
              <span className="tower-provider">{integration.provider}</span>
              <h2>{integration.name}</h2>
              <p>{integration.description}</p>
            </div>
            <div className="tower-integration-foot">
              <span>{integration.signal}</span>
              <span className={`tower-integration-status ${integration.status}`}>{integrationStatusLabel(integration.status)}</span>
            </div>
          </article>
        ))}
      </div>

      <div className="tower-panel tower-architecture">
        <PanelHeader title="Local-first architecture" count={5} />
        <div className="tower-architecture-flow">
          <FlowNode Icon={Network} label="React Dashboard" value="localhost:5173" />
          <FlowNode Icon={TerminalSquare} label="FastAPI Backend" value="localhost:8000" />
          <FlowNode Icon={Database} label="PostgreSQL Docker" value="5432 · 5433 · 5440" />
          <FlowNode Icon={Cloud} label="Azure Services" value="Key Vault · Monitor · Logs" />
          <FlowNode Icon={Sparkles} label="Databricks" value="SQL Warehouse" />
        </div>
      </div>
    </section>
  );
}

function RecommendationsView({
  sources,
  recommendations,
  onOpenSource,
}: {
  sources: DatabaseSource[];
  recommendations: TowerRecommendation[];
  onOpenSource: (sourceId: string) => void;
}) {
  return (
    <section className="tower-section-stack">
      <div className="tower-recommendations-layout">
        <div className="tower-panel tower-recommendation-list">
          <PanelHeader title="DBA Copilot recommendations" count={recommendations.length} />
          {recommendations.map((item) => (
            <RecommendationCard key={item.id} item={item} sources={sources} onOpenSource={() => onOpenSource(item.sourceId)} />
          ))}
        </div>

        <aside className="tower-panel tower-rules-panel">
          <PanelHeader title="Health score rules" count={healthScoreRules.length} />
          {healthScoreRules.map((rule) => (
            <RuleRow key={rule.label} label={rule.label} value={rule.value} detail={rule.detail} />
          ))}
        </aside>
      </div>
    </section>
  );
}

function HistoryView({
  sources,
  selectedSource,
  onSelectSource,
}: {
  sources: DatabaseSource[];
  selectedSource: DatabaseSource;
  onSelectSource: (sourceId: string) => void;
}) {
  return (
    <section className="tower-section-stack">
      <div className="tower-panel tower-table-toolbar">
        <div>
          <p className="tower-eyebrow">Metric snapshots</p>
          <h2>{selectedSource.name} · health evolution</h2>
        </div>
        <label>
          Fuente
          <select value={selectedSource.id} onChange={(event) => onSelectSource(event.target.value)}>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>{source.name}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="tower-panel tower-history-panel">
        <div className="tower-history-chart">
          {selectedSource.trend.map((value, index) => (
            <div key={`${value}-${index}`} className="tower-history-bar">
              <span style={{ height: `${value}%` }} />
              <small>{value}</small>
            </div>
          ))}
        </div>
        <div className="tower-history-summary">
          <ProfileItem label="Last snapshot" value={selectedSource.lastSnapshot} />
          <ProfileItem label="Metric provider" value={selectedSource.telemetryProvider} />
          <ProfileItem label="Health score" value={`${selectedSource.healthScore}/100`} />
          <ProfileItem label="Tables tracked" value={`${selectedSource.tablesCount}`} />
        </div>
      </div>
    </section>
  );
}

function PanelHeader({ title, count }: { title: string; count: number }) {
  return (
    <div className="tower-panel-header">
      <h2>{title}</h2>
      <span>{count}</span>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusBadge({ status }: { status: SourceStatus }) {
  return <span className={`tower-status ${status}`}>{status}</span>;
}

function ProfileItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="tower-profile-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RecommendationMini({ item }: { item: TowerRecommendation }) {
  const source = tableSourceFallback(item.sourceId);
  return (
    <div className="tower-reco-mini">
      <span className={`tower-severity-dot ${item.severity}`} />
      <div>
        <strong>{item.title}</strong>
        <p>{source.name} · {item.category}</p>
      </div>
    </div>
  );
}

function RecommendationCard({
  item,
  sources,
  onOpenSource,
}: {
  item: TowerRecommendation;
  sources?: DatabaseSource[];
  onOpenSource?: () => void;
}) {
  const source = sources?.find((candidate) => candidate.id === item.sourceId) ?? tableSourceFallback(item.sourceId);
  return (
    <article className={`tower-recommendation-card severity-${item.severity}`}>
      <div className="tower-recommendation-head">
        <div>
          <span>{source.name} · {item.category}</span>
          <h3>{item.title}</h3>
        </div>
        <span className={`tower-reco-severity ${item.severity}`}>{item.severity}</span>
      </div>
      <p>{item.recommendation}</p>
      <div className="tower-recommendation-evidence">
        <span>Evidence</span>
        <strong>{item.evidence}</strong>
      </div>
      <div className="tower-impact-row">
        <span>{item.impact}</span>
        {onOpenSource && (
          <button onClick={onOpenSource}>
            Source
            <ChevronRight size={15} aria-hidden="true" />
          </button>
        )}
      </div>
    </article>
  );
}

function tableSourceFallback(sourceId: string) {
  return visibleFallbackSources.find((source) => source.id === sourceId) ?? visibleFallbackSources[0];
}

function schemasForSource(sourceId: string, tables: TableInventoryItem[]) {
  return [...new Set(tables.filter((table) => table.sourceId === sourceId).map((table) => table.schemaName))].sort();
}

function groupTablesBySchema(tables: TableInventoryItem[]) {
  const groups = new Map<string, TableInventoryItem[]>();
  for (const table of tables) {
    groups.set(table.schemaName, [...(groups.get(table.schemaName) ?? []), table]);
  }
  return [...groups.entries()]
    .sort(([schemaA], [schemaB]) => schemaA.localeCompare(schemaB))
    .map(([schemaName, groupTables]) => ({
      schemaName,
      tables: groupTables.sort((tableA, tableB) => tableA.tableName.localeCompare(tableB.tableName)),
    }));
}

function formatRows(value: number | null) {
  return value === null ? "filas n/d" : `${value.toLocaleString()} filas`;
}

function formatTableSize(value: number | null) {
  return value === null ? "tamano n/d" : `${value} MB`;
}

function databaseCount(source: DatabaseSource) {
  if (source.engine === "databricks") return source.schemas.length || 1;
  return source.databasesCount ?? source.databases?.length ?? 1;
}

function mergeIntegrationIcons(items: Omit<TowerIntegration, "Icon">[]): TowerIntegration[] {
  return items.map((item) => {
    const template = integrationTemplates.find((candidate) => candidate.id === item.id);
    return { ...item, Icon: template?.Icon ?? Database };
  });
}

function integrationStatusLabel(status: TowerIntegration["status"]) {
  if (status === "pending") return "Opcional";
  if (status === "configured") return "Configurado";
  if (status === "connected") return "Conectado";
  return status;
}

function HealthScoreRing({ source }: { source: DatabaseSource }) {
  const appliedPenalties = healthScoreAppliedPenalties(source);

  return (
    <div className="tower-health-score-shell">
      <div className="tower-detail-score" style={{ "--score": `${source.healthScore}%` } as CSSProperties}>
        <span>{source.healthScore}</span>
        <small>health score</small>
      </div>
      <button className="tower-score-info-button" type="button" aria-label={`Formula health score para ${source.displayName}`}>
        <Info size={16} aria-hidden="true" />
      </button>
      <div className="tower-score-tooltip" role="tooltip">
        <strong>Formula health score</strong>
        <p>Empieza en 100 y descuenta riesgo operacional segun las metricas del snapshot.</p>
        <div className="tower-score-breakdown">
          <div>
            <span>Base</span>
            <b>100</b>
          </div>
          {appliedPenalties.length ? (
            appliedPenalties.map((item) => (
              <div key={item.label}>
                <span>{item.label}</span>
                <b>{item.value}</b>
                <small>{item.detail}</small>
              </div>
            ))
          ) : (
            <div>
              <span>Sin descuentos</span>
              <b>0</b>
              <small>Metricas dentro de los umbrales.</small>
            </div>
          )}
          <div className="total">
            <span>Score reportado</span>
            <b>{source.healthScore}</b>
          </div>
        </div>
        <div className="tower-score-rules">
          {healthScoreRules.map((rule) => (
            <span key={rule.label}>{rule.label}: {rule.value}</span>
          ))}
        </div>
        <p className="tower-score-advice">Si baja de 90, revisar latencia, pooling, sesiones activas, locks y deadlocks.</p>
      </div>
    </div>
  );
}

function healthScoreAppliedPenalties(source: DatabaseSource) {
  if (source.engine === "databricks") {
    return source.status === "online"
      ? [{ label: "Databricks online", value: "-10", detail: "Lakehouse configurado usa snapshot administrado de 90." }]
      : [{ label: "Databricks pendiente", value: "-100", detail: "Host o token no configurado." }];
  }

  const penalties: { label: string; value: string; detail: string }[] = [];
  const latency = source.latencyMs;
  if (latency !== null && latency > 250) {
    penalties.push({ label: "Latency", value: "-25", detail: `${latency} ms > 250 ms.` });
  } else if (latency !== null && latency > 100) {
    penalties.push({ label: "Latency", value: "-10", detail: `${latency} ms > 100 ms.` });
  }

  const totalConnections = source.totalConnections ?? 0;
  if (totalConnections > 100) {
    penalties.push({ label: "Total connections", value: "-15", detail: `${totalConnections} conexiones > 100.` });
  } else if (totalConnections > 50) {
    penalties.push({ label: "Total connections", value: "-8", detail: `${totalConnections} conexiones > 50.` });
  }

  const activeConnections = source.activeConnections ?? 0;
  if (activeConnections > 50) {
    penalties.push({ label: "Active connections", value: "-10", detail: `${activeConnections} activas > 50.` });
  }

  const locks = source.locksCount ?? 0;
  if (locks > 50) {
    penalties.push({ label: "Locks", value: "-18", detail: `${locks} locks > 50.` });
  } else if (locks > 0) {
    penalties.push({ label: "Locks", value: "-5", detail: `${locks} locks activos.` });
  }

  const deadlocks = source.deadlocks ?? 0;
  if (deadlocks > 0) {
    penalties.push({ label: "Deadlocks", value: "-5", detail: `${deadlocks} deadlocks registrados.` });
  }

  if (source.sourceType === "cloud_database") {
    penalties.push({ label: "Azure resource ID", value: "ver config", detail: "Resta -3 solo si falta AZURE_POSTGRES_RESOURCE_ID." });
  }

  return penalties;
}

function friendlySourceError(message: string) {
  if (/password authentication failed/i.test(message)) {
    return "Auth failed: revisa usuario o password de Azure PostgreSQL.";
  }
  if (/timeout|timed out/i.test(message)) {
    return "Timeout al conectar: revisa firewall o red.";
  }
  if (/could not translate host|Name or service not known|getaddrinfo/i.test(message)) {
    return "Host no resuelve: revisa AZURE_POSTGRES_HOST.";
  }
  return message.replace(/\s*\(Background on this error:.*$/s, "");
}

function FlowNode({ Icon, label, value }: { Icon: typeof Database; label: string; value: string }) {
  return (
    <div className="tower-flow-node">
      <Icon size={20} aria-hidden="true" />
      <strong>{label}</strong>
      <span>{value}</span>
    </div>
  );
}

function RuleRow({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="tower-rule-row">
      <div>
        <strong>{label}</strong>
        <p>{detail}</p>
      </div>
      <span>{value}</span>
    </div>
  );
}
