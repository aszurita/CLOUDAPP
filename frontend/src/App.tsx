import {
  Activity,
  BookOpen,
  Boxes,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cog,
  Database,
  ExternalLink,
  GitBranch,
  LayoutDashboard,
  Mail,
  Network,
  PackagePlus,
  Play,
  RefreshCw,
  SearchCheck,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Tags,
  TriangleAlert,
  UserRound,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { DashboardFactoryApp } from "./apps/dashboard-factory/DashboardFactoryApp";
import { AppFactoryApp } from "./apps/app-factory/AppFactoryApp";
import { CloudOpsAutopilotApp } from "./apps/cloudops-autopilot/CloudOpsAutopilotApp";
import { DatabaseControlTowerApp } from "./apps/database-control-tower/DatabaseControlTowerApp";
import { CoreBankingDashboard } from "./pages/core-banking/CoreBankingDashboard";
import { SentinelDashboard } from "./pages/sentinel/SentinelDashboard";
import {
  ApiError,
  AutopilotReport,
  AutopilotTask,
  CatalogAsset,
  CatalogClassification,
  CatalogColumn,
  CatalogLineageEdge,
  CatalogStatus,
  CatalogSyncRun,
  DataOpsGeneratedAsset,
  DataOpsMetric,
  DataOpsPipeline,
  DataOpsPipelineRun,
  DataOpsQualityCheck,
  DataOpsQuarantineEvent,
  DataOpsRunEvent,
  DatabaseInventory,
  DatabaseSourceMetadata,
  DbaAnalyzeResponse,
  DbaRecommendation,
  DbaTableProfile,
  Deployment,
  Environment,
  PlatformStatus,
  QueryAnalyzeResponse,
  QueryExecuteResponse,
  QueryPolicy,
  QueryReview,
  Service,
  analyzeQuery,
  executeQuery,
  generateCatalogDocumentation,
  getAutopilotHistory,
  getAutopilotLatest,
  getCatalogAssets,
  getCatalogClassifications,
  getCatalogColumns,
  getCatalogLineage,
  getCatalogStatus,
  getCatalogSyncRuns,
  getDbaRecommendations,
  getDbaSources,
  getDbaTables,
  getDataOpsAssets,
  getDataOpsCurrent,
  getDataOpsHistory,
  getDataOpsPipelines,
  getDataOpsQuality,
  getDataOpsQuarantine,
  getDemoQueries,
  getDeployments,
  getEnvironments,
  getPlatformStatus,
  getQueryHistory,
  getQueryMetadata,
  getQueryPolicies,
  getServices,
  runAutopilotAnalysis,
  runDataOpsPipeline,
  runDbaAnalysis,
  syncCatalog,
  updateAutopilotTaskStatus,
  updateCatalogColumnDescription,
  updateCatalogClassification,
  updateCatalogOwner,
} from "./api";

type LoadState = "loading" | "ready" | "error";
type View = "overview" | "banking" | "query" | "dba" | "dataops" | "catalog" | "autopilot" | "sentinel";
type Suite = "cloudops" | "database-control" | "dashboard-factory" | "app-factory" | "cloudops-autopilot";

function statusTone(status: string) {
  if (status === "bronze") return "layer-bronze";
  if (status === "silver") return "layer-silver";
  if (status === "gold") return "layer-gold";
  if (status === "source") return "layer-source";
  if (status === "audit") return "layer-audit";
  if (status === "alert") return "layer-alert";
  if (status === "lab") return "layer-lab";
  if (status === "operational") return "layer-operational";
  if (["healthy", "success", "connected", "approved", "low", "configured", "passed", "available"].includes(status)) {
    return "text-emerald-700 bg-emerald-50 border-emerald-200";
  }
  if (["attention", "degraded", "medium", "warning", "running", "high"].includes(status)) return "text-amber-700 bg-amber-50 border-amber-200";
  return "text-rose-700 bg-rose-50 border-rose-200";
}

function Stat({ label, value, icon: Icon }: { label: string; value: string | number; icon: typeof Activity }) {
  return (
    <div className="metric">
      <div className="metric-icon">
        <Icon size={20} aria-hidden="true" />
      </div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function StatusBadge({ value }: { value: string }) {
  const label = value === "success" ? "Correcto" : value;
  return <span className={`status-badge ${statusTone(value)}`}>{label}</span>;
}

function ErrorNotice({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="notice error">
      <TriangleAlert size={18} aria-hidden="true" />
      <span>{error}</span>
    </div>
  );
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (typeof error.detail === "string") return error.detail;
    if (typeof error.detail === "object" && error.detail && "ai_explanation" in error.detail) {
      return "Query execution was blocked by governance policy.";
    }
  }
  return "Platform request failed.";
}

function formatQualityScore(value: number) {
  return Number.isInteger(value) ? `${value}` : `${value}`;
}

export default function App() {
  const [activeSuite, setActiveSuite] = useState<Suite | null>(null);

  if (activeSuite === "cloudops") {
    return <PlatformApp onBack={() => setActiveSuite(null)} />;
  }

  if (activeSuite === "database-control") {
    return <DatabaseControlTowerApp onBack={() => setActiveSuite(null)} />;
  }

  if (activeSuite === "dashboard-factory") {
    return <DashboardFactoryApp onBack={() => setActiveSuite(null)} />;
  }

  if (activeSuite === "app-factory") {
    return <AppFactoryApp onBack={() => setActiveSuite(null)} />;
  }

  if (activeSuite === "cloudops-autopilot") {
    return <CloudOpsAutopilotApp onBack={() => setActiveSuite(null)} />;
  }

  return <SuiteLauncher onSelect={setActiveSuite} />;
}

function SuiteLauncher({ onSelect }: { onSelect: (suite: Suite) => void }) {
  return (
    <main className="launcher-shell">
      <section className="launcher-hero" aria-labelledby="launcher-title">
        <div className="launcher-brand">
          <span className="launcher-brand-mark">
            <Sparkles size={24} aria-hidden="true" />
          </span>
          <span>Enterprise AI Operations Hub</span>
        </div>
        <p className="eyebrow">CloudOps · DataOps · Governance · Database Intelligence</p>
        <h1 id="launcher-title">Selecciona el centro de operación</h1>
        <p className="launcher-copy">
          Cinco centros dentro de una sola plataforma: operaciones empresariales, control de bases, dashboards Databricks, generación de apps y operación Azure.
        </p>
        <div className="launcher-status-row">
          <span>Local demo</span>
          <span>Azure ready</span>
          <span>AI enabled</span>
        </div>
      </section>

      <section className="suite-grid" aria-label="Application suites">
        <button className="suite-card suite-card-cloudops" onClick={() => onSelect("cloudops")}>
          <span className="suite-card-head">
            <span className="suite-icon">
              <Network size={24} aria-hidden="true" />
            </span>
            <span className="suite-state">Disponible</span>
          </span>
          <span className="suite-kicker">Application 01</span>
          <strong>CloudOps · DataOps · Governance</strong>
          <span className="suite-copy">
            Autopilot, gobierno de consultas, DBA Copilot, DataOps, catálogo y DB Sentinel AI.
          </span>
          <span className="suite-chip-row">
            <span>Operations</span>
            <span>Governance</span>
            <span>Sentinel</span>
          </span>
          <span className="suite-open">
            Entrar
            <ChevronRight size={18} aria-hidden="true" />
          </span>
        </button>

        <button className="suite-card suite-card-database" onClick={() => onSelect("database-control")}>
          <span className="suite-card-head">
            <span className="suite-icon">
              <Database size={24} aria-hidden="true" />
            </span>
            <span className="suite-state">Disponible</span>
          </span>
          <span className="suite-kicker">Application 02</span>
          <strong>Database Control Tower AI</strong>
          <span className="suite-copy">
            Control Tower para PostgreSQL Docker, Azure PostgreSQL, Databricks, secretos, métricas y recomendaciones DBA.
          </span>
          <span className="suite-chip-row">
            <span>PostgreSQL</span>
            <span>Azure</span>
            <span>Databricks</span>
          </span>
          <span className="suite-open">
            Abrir Control Tower
            <ChevronRight size={18} aria-hidden="true" />
          </span>
        </button>

        <button className="suite-card suite-card-factory" onClick={() => onSelect("dashboard-factory")}>
          <span className="suite-card-head">
            <span className="suite-icon">
              <LayoutDashboard size={24} aria-hidden="true" />
            </span>
            <span className="suite-state">Disponible</span>
          </span>
          <span className="suite-kicker">Application 03</span>
          <strong>Databricks Dashboard Factory</strong>
          <span className="suite-copy">
            Genera dashboards completos en Databricks desde un prompt. El sistema interpreta tu solicitud, construye el SQL, crea los widgets y publica el dashboard con un solo clic.
          </span>
          <span className="suite-chip-row">
            <span>Prompt → SQL</span>
            <span>Lakeview API</span>
            <span>Auto-publish</span>
          </span>
          <span className="suite-open">
            Abrir Factory
            <ChevronRight size={18} aria-hidden="true" />
          </span>
        </button>

        <button className="suite-card suite-card-appfactory" onClick={() => onSelect("app-factory")}>
          <span className="suite-card-head">
            <span className="suite-icon">
              <PackagePlus size={24} aria-hidden="true" />
            </span>
            <span className="suite-state">Disponible</span>
          </span>
          <span className="suite-kicker">Application 04</span>
          <strong>AI Cloud App Factory</strong>
          <span className="suite-copy">
            Crea aplicaciones React + FastAPI + PostgreSQL desde un prompt, con Docker, Terraform, GitHub Actions y links finales.
          </span>
          <span className="suite-chip-row">
            <span>Prompt → App</span>
            <span>Terraform</span>
            <span>Azure Ready</span>
          </span>
          <span className="suite-open">
            Abrir App Factory
            <ChevronRight size={18} aria-hidden="true" />
          </span>
        </button>

        <button className="suite-card suite-card-cloudautopilot" onClick={() => onSelect("cloudops-autopilot")}>
          <span className="suite-card-head">
            <span className="suite-icon">
              <Server size={24} aria-hidden="true" />
            </span>
            <span className="suite-state">Disponible</span>
          </span>
          <span className="suite-kicker">Application 05</span>
          <strong>CloudOps Autopilot Azure</strong>
          <span className="suite-copy">
            Opera apps generadas: readiness, recursos Azure, timeline de despliegue, secretos, monitoreo y costos.
          </span>
          <span className="suite-chip-row">
            <span>Deploy Center</span>
            <span>Azure Ops</span>
            <span>Observability</span>
          </span>
          <span className="suite-open">
            Abrir CloudOps
            <ChevronRight size={18} aria-hidden="true" />
          </span>
        </button>
      </section>
    </main>
  );
}

function PlatformApp({ onBack }: { onBack: () => void }) {
  const [activeView, setActiveView] = useState<View>("overview");
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [status, setStatus] = useState<PlatformStatus | null>(null);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [dataOpsRunningRun, setDataOpsRunningRun] = useState<DataOpsPipelineRun | null>(null);

  useEffect(() => {
    Promise.all([getPlatformStatus(), getEnvironments(), getServices(), getDeployments()])
      .then(([platformStatus, envs, serviceList, deploymentList]) => {
        setStatus(platformStatus);
        setEnvironments(envs);
        setServices(serviceList);
        setDeployments(deploymentList);
        setLoadState("ready");
      })
      .catch(() => setLoadState("error"));
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function refreshDataOpsState() {
      try {
        const current = await getDataOpsCurrent();
        if (!cancelled) {
          setDataOpsRunningRun(current.latest_run?.status === "running" ? current.latest_run : null);
        }
      } catch {
        if (!cancelled) setDataOpsRunningRun(null);
      }
    }
    void refreshDataOpsState();
    const id = window.setInterval(() => void refreshDataOpsState(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  if (loadState === "loading") {
    return (
      <main className="app-shell centered">
        <Activity className="spin" size={28} aria-hidden="true" />
        <p>Loading platform telemetry...</p>
      </main>
    );
  }

  if (loadState === "error" || !status) {
    return (
      <main className="app-shell centered">
        <TriangleAlert size={32} aria-hidden="true" />
        <h1>Platform API unavailable</h1>
        <p>Check `VITE_API_BASE_URL`, start the FastAPI backend, and verify CORS origins.</p>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">CloudOps · DataOps · Governance</p>
          <h1>Enterprise CloudOps & DataOps Autopilot</h1>
        </div>
        <div className="topbar-actions">
          <button className="suite-switch" onClick={onBack}>
            <ChevronRight size={16} aria-hidden="true" />
            Cambiar suite
          </button>
          <StatusBadge value={status.database} />
          <StatusBadge value={status.ai_configured ? "configured" : "blocked"} />
        </div>
      </header>

      <nav className="view-tabs" aria-label="Platform views">
        <button className={activeView === "overview" ? "active" : ""} onClick={() => setActiveView("overview")}>
          Platform Overview
        </button>
        <button className={activeView === "banking" ? "active" : ""} onClick={() => setActiveView("banking")}>
          <LayoutDashboard size={15} aria-hidden="true" />
          Core Banking Dashboard
        </button>
        <button className={activeView === "query" ? "active" : ""} onClick={() => setActiveView("query")}>
          Query Governance
        </button>
        <button className={activeView === "dba" ? "active" : ""} onClick={() => setActiveView("dba")}>
          DBA Copilot
        </button>
        <button className={activeView === "dataops" ? "active" : ""} onClick={() => setActiveView("dataops")}>
          {dataOpsRunningRun && <Activity className="tab-spin" size={15} aria-hidden="true" />}
          DataOps Monitor
        </button>
        <button className={activeView === "catalog" ? "active" : ""} onClick={() => setActiveView("catalog")}>
          Catalog Governance
        </button>
        <button className={activeView === "autopilot" ? "active" : ""} onClick={() => setActiveView("autopilot")}>
          <Zap size={15} aria-hidden="true" />
          Autopilot Analysis
        </button>
        <button className={activeView === "sentinel" ? "active" : ""} onClick={() => setActiveView("sentinel")}>
          <ShieldAlert size={15} aria-hidden="true" />
          DB Sentinel AI
        </button>
      </nav>

      {activeView === "overview" && (
        <Overview status={status} environments={environments} services={services} deployments={deployments} />
      )}
      {activeView === "banking" && <CoreBankingDashboard />}
      {activeView === "query" && <QueryGovernance />}
      {activeView === "dba" && <DbaCopilot />}
      {activeView === "dataops" && <DataOpsMonitor onRunStatusChange={setDataOpsRunningRun} />}
      {activeView === "catalog" && <CatalogGovernance />}
      {activeView === "autopilot" && <AutopilotCenter />}
      {activeView === "sentinel" && <SentinelDashboard />}
    </main>
  );
}

function Overview({
  status,
  environments,
  services,
  deployments,
}: {
  status: PlatformStatus;
  environments: Environment[];
  services: Service[];
  deployments: Deployment[];
}) {
  const monthlyCost = useMemo(() => services.reduce((total, service) => total + service.cost_estimate_usd, 0), [services]);

  return (
    <>
      <section className="metrics-grid" aria-label="Platform metrics">
        <Stat label="Services" value={status.services_total} icon={Server} />
        <Stat label="Healthy" value={status.services_healthy} icon={CheckCircle2} />
        <Stat label="Environments" value={status.environments_total} icon={Boxes} />
        <Stat label="Audit events" value={status.audit_events_total} icon={ShieldCheck} />
        <Stat label="Monthly estimate" value={`$${monthlyCost}`} icon={Database} />
      </section>

      <section className="content-grid">
        <div className="panel wide integration-strip">
          <div>
            <p className="eyebrow">AI Provider</p>
            <h2>{status.ai_provider.toUpperCase()} · {status.ai_model}</h2>
          </div>
          <StatusBadge value={status.ai_configured ? "configured" : "blocked"} />
        </div>

        <div className="panel">
          <div className="panel-heading">
            <h2>Environments</h2>
            <span>{status.environment}</span>
          </div>
          <div className="row-list">
            {environments.map((environment) => (
              <div className="data-row" key={environment.id}>
                <div>
                  <strong>{environment.code}</strong>
                  <p>{environment.name} · {environment.region}</p>
                </div>
                <StatusBadge value={environment.status} />
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <h2>Services</h2>
            <span>Azure ready</span>
          </div>
          <div className="row-list">
            {services.map((service) => (
              <div className="data-row" key={service.id}>
                <div>
                  <strong>{service.name}</strong>
                  <p>{service.service_type} · v{service.version}</p>
                </div>
                <StatusBadge value={service.status} />
              </div>
            ))}
          </div>
        </div>

        <div className="panel wide">
          <div className="panel-heading">
            <h2>Latest Deployments</h2>
            <GitBranch size={18} aria-hidden="true" />
          </div>
          <div className="table">
            <div className="table-header">
              <span>Service</span>
              <span>Status</span>
              <span>Commit</span>
              <span>Actor</span>
            </div>
            {deployments.map((deployment) => {
              const service = services.find((item) => item.id === deployment.service_id);
              return (
                <div className="table-row" key={deployment.id}>
                  <span>{service?.name ?? `service-${deployment.service_id}`}</span>
                  <StatusBadge value={deployment.status} />
                  <span>{deployment.commit_sha}</span>
                  <span>{deployment.deployed_by}</span>
                </div>
              );
            })}
          </div>
        </div>
      </section>
    </>
  );
}

function reportMetric(report: AutopilotReport | null, key: string, fallback: string | number = 0) {
  const value = report?.metrics_json?.[key];
  if (typeof value === "number" || typeof value === "string") return value;
  return fallback;
}

function priorityTone(priority: string) {
  if (priority === "p0" || priority === "p1") return "high";
  if (priority === "p2") return "medium";
  return "low";
}

function AutopilotCenter() {
  const [report, setReport] = useState<AutopilotReport | null>(null);
  const [history, setHistory] = useState<AutopilotReport[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refreshAutopilot() {
    const [latest, reportHistory] = await Promise.all([getAutopilotLatest(), getAutopilotHistory()]);
    setReport(latest.latest_report);
    setHistory(reportHistory);
  }

  useEffect(() => {
    refreshAutopilot().catch((requestError) => setError(getErrorMessage(requestError)));
  }, []);

  async function runAnalysis() {
    setBusy(true);
    setError(null);
    try {
      const nextReport = await runAutopilotAnalysis();
      setReport(nextReport);
      setHistory(await getAutopilotHistory());
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function setTaskStatus(task: AutopilotTask, status: string) {
    setError(null);
    try {
      await updateAutopilotTaskStatus(task.id, status);
      await refreshAutopilot();
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    }
  }

  const openTasks = report?.tasks.filter((task) => task.status !== "done" && task.status !== "dismissed") ?? [];
  const highFindings = report?.findings_json.filter((finding) => ["critical", "high"].includes(finding.severity)) ?? [];

  return (
    <div className="autopilot-center">
      <div className="panel autopilot-hero">
        <div>
          <p className="eyebrow">Fase 5 · Intelligent Autopilot</p>
          <h2 className="autopilot-title">
            <Zap size={22} aria-hidden="true" />
            Run Autopilot Analysis
          </h2>
          <p>
            Analiza plataforma, consultas, DBA, DataOps y catálogo para producir riesgos, tareas y plan de remediación.
          </p>
        </div>
        <div className="button-row autopilot-actions">
          <button onClick={() => void refreshAutopilot()} disabled={busy}>
            <RefreshCw size={16} aria-hidden="true" />
            Refresh
          </button>
          <button className="primary" onClick={() => void runAnalysis()} disabled={busy}>
            <Play size={16} aria-hidden="true" />
            Run Analysis
          </button>
        </div>
      </div>

      <ErrorNotice error={error} />

      <section className="metrics-grid autopilot-metrics">
        <Stat label="Autopilot score" value={report ? `${report.overall_score}/100` : "0/100"} icon={ShieldCheck} />
        <Stat label="Risk level" value={report?.risk_level ?? "pending"} icon={TriangleAlert} />
        <Stat label="Findings" value={reportMetric(report, "findings_total")} icon={SearchCheck} />
        <Stat label="Open tasks" value={openTasks.length} icon={CheckCircle2} />
        <Stat label="Sensitive columns" value={reportMetric(report, "sensitive_columns")} icon={Tags} />
      </section>

      {!report && !busy && (
        <div className="panel dba-empty">
          <Zap size={34} aria-hidden="true" />
          <p>Ejecuta Autopilot para generar el primer reporte ejecutivo.</p>
        </div>
      )}

      {report && (
        <section className="content-grid autopilot-grid">
          <div className="panel wide autopilot-summary">
            <div>
              <p className="eyebrow">Latest Report</p>
              <h2>{report.summary}</h2>
              <p>{new Date(report.created_at).toLocaleString()} · {report.run_id}</p>
            </div>
            <StatusBadge value={report.risk_level} />
          </div>

          {report.ai_summary && (
            <div className="panel wide">
              <div className="panel-heading">
                <h2>Executive AI Brief</h2>
                <Sparkles size={18} aria-hidden="true" />
              </div>
              <AiMarkdown text={report.ai_summary} />
            </div>
          )}

          <div className="panel">
            <div className="panel-heading">
              <h2>Priority Findings</h2>
              <span>{highFindings.length} high</span>
            </div>
            <div className="row-list compact">
              {report.findings_json.map((finding) => (
                <div className="data-row autopilot-finding" key={`${finding.category}-${finding.title}`}>
                  <div>
                    <strong>{finding.title}</strong>
                    <p>{finding.category} · {finding.description}</p>
                    {finding.actions && finding.actions.length > 0 && (
                      <small>{finding.actions.slice(0, 2).join(" · ")}</small>
                    )}
                  </div>
                  <StatusBadge value={finding.severity} />
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-heading">
              <h2>Remediation Tasks</h2>
              <span>{openTasks.length} open</span>
            </div>
            <div className="row-list compact">
              {report.tasks.map((task) => (
                <div className="data-row autopilot-task" key={task.id}>
                  <div>
                    <strong>{task.title}</strong>
                    <p>{task.owner} · {task.category} · {task.due_hint ?? "backlog"}</p>
                    <small>{task.action_json.actions?.slice(0, 2).join(" · ")}</small>
                    <div className="button-row task-actions">
                      {task.status === "open" && (
                        <button onClick={() => void setTaskStatus(task, "in_progress")}>Start</button>
                      )}
                      {task.status !== "done" && (
                        <button onClick={() => void setTaskStatus(task, "done")}>Done</button>
                      )}
                    </div>
                  </div>
                  <div className="task-badges">
                    <StatusBadge value={priorityTone(task.priority)} />
                    <StatusBadge value={task.status} />
                  </div>
                </div>
              ))}
              {report.tasks.length === 0 && <p className="catalog-muted">Sin tareas pendientes.</p>}
            </div>
          </div>

          <div className="panel">
            <div className="panel-heading">
              <h2>Infrastructure Suggestions</h2>
              <Cog size={18} aria-hidden="true" />
            </div>
            <div className="row-list compact">
              {report.infra_suggestions_json.map((item) => (
                <div className="data-row" key={`${item.area}-${item.title}`}>
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.area} · {item.suggestion}</p>
                    <small>{item.impact}</small>
                  </div>
                  <StatusBadge value="medium" />
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-heading">
              <h2>History</h2>
              <span>{history.length}</span>
            </div>
            <div className="row-list compact">
              {history.map((item) => (
                <div className="data-row" key={item.id}>
                  <div>
                    <strong>{item.overall_score}/100 · {item.risk_level}</strong>
                    <p>{item.findings_json.length} findings · {new Date(item.created_at).toLocaleString()}</p>
                  </div>
                  <StatusBadge value={item.risk_level} />
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function QueryGovernance() {
  const [sql, setSql] = useState("");
  const [policies, setPolicies] = useState<QueryPolicy[]>([]);
  const [history, setHistory] = useState<QueryReview[]>([]);
  const [metadata, setMetadata] = useState<DatabaseInventory | null>(null);
  const [analysis, setAnalysis] = useState<QueryAnalyzeResponse | null>(null);
  const [execution, setExecution] = useState<QueryExecuteResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getDemoQueries(), getQueryPolicies(), getQueryHistory(), getQueryMetadata()])
      .then(([demoQueries, policyList, queryHistory, inventory]) => {
        setSql(demoQueries.dangerous);
        setPolicies(policyList);
        setHistory(queryHistory);
        setMetadata(inventory);
      })
      .catch((requestError) => setError(getErrorMessage(requestError)));
  }, []);

  async function loadDemo(kind: "dangerous" | "safe") {
    const demoQueries = await getDemoQueries();
    setSql(demoQueries[kind]);
    setAnalysis(null);
    setExecution(null);
    setError(null);
  }

  async function analyze() {
    setBusy(true);
    setError(null);
    setExecution(null);
    try {
      const result = await analyzeQuery(sql);
      setAnalysis(result);
      setHistory(await getQueryHistory());
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function execute() {
    setBusy(true);
    setError(null);
    try {
      const result = await executeQuery(sql);
      setExecution(result);
      setAnalysis(result);
      setHistory(await getQueryHistory());
    } catch (requestError) {
      setError(getErrorMessage(requestError));
      setHistory(await getQueryHistory());
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="workspace-grid">
      <div className="panel workspace-main">
        <div className="panel-heading">
          <h2>Query Governance</h2>
          {analysis && <StatusBadge value={analysis.decision} />}
        </div>
        <textarea className="sql-editor" value={sql} onChange={(event) => setSql(event.target.value)} spellCheck={false} />
        <div className="button-row">
          <button onClick={() => void loadDemo("dangerous")}>Dangerous</button>
          <button onClick={() => void loadDemo("safe")}>Safe</button>
          <button className="primary" onClick={() => void analyze()} disabled={busy}>
            <SearchCheck size={16} aria-hidden="true" />
            Analyze
          </button>
          <button className="primary" onClick={() => void execute()} disabled={busy || analysis?.decision !== "approved"}>
            <Play size={16} aria-hidden="true" />
            Execute
          </button>
        </div>
        <ErrorNotice error={error} />
        {analysis && (
          <div className="result-panel">
            <div className="panel-heading">
              <h2>Análisis de IA</h2>
              <StatusBadge value={analysis.risk_level} />
            </div>
            <AiMarkdown text={analysis.ai_explanation} />
            {analysis.reasons.length > 0 && (
              <div className="result-columns">
                <ListBlock title="Motivos" items={analysis.reasons} />
                <ListBlock title="Recomendaciones" items={analysis.recommendations} />
              </div>
            )}
          </div>
        )}
        {execution && (
          <div className="result-panel">
            <div className="panel-heading">
              <h2>Resultado</h2>
            </div>
            <PaginatedResultTable
              columns={execution.columns}
              rows={execution.rows}
              rowCount={execution.row_count}
              executionMs={execution.execution_ms}
            />
          </div>
        )}
      </div>

      <aside className="side-stack">
        <div className="panel">
          <div className="panel-heading">
            <h2>Policies</h2>
            <ShieldCheck size={18} aria-hidden="true" />
          </div>
          <div className="row-list compact">
            {policies.map((policy) => (
              <div className="data-row" key={policy.id}>
                <div>
                  <strong>{policy.code}</strong>
                  <p>{policy.description}</p>
                </div>
                <StatusBadge value={policy.severity} />
              </div>
            ))}
          </div>
        </div>
        <DatabaseInventoryPanel inventory={metadata} title="Bases y tablas" />
        <div className="panel">
          <div className="panel-heading">
            <h2>History</h2>
            <span>{history.length}</span>
          </div>
          <div className="row-list compact">
            {history.map((item) => (
              <div className="data-row history-row" key={item.id}>
                <div>
                  <strong>{item.action}</strong>
                  <p>{item.sql_text}</p>
                </div>
                <StatusBadge value={item.decision} />
              </div>
            ))}
          </div>
        </div>
      </aside>
    </section>
  );
}

function DatabaseInventoryPanel({ inventory, title }: { inventory: DatabaseInventory | null; title: string }) {
  const sources = inventory?.sources ?? [];
  return (
    <div className="panel database-inventory-panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        <span>{sources.length}</span>
      </div>
      <div className="database-source-list">
        {sources.length === 0 && <p className="catalog-muted">Inventario no disponible.</p>}
        {sources.map((source) => (
          <DatabaseSourceCard key={source.key} source={source} compact />
        ))}
      </div>
    </div>
  );
}

function DatabaseSourceCard({ source, compact = false }: { source: DatabaseSourceMetadata; compact?: boolean }) {
  const tables = source.schemas.flatMap((schema) => schema.tables.map((table) => ({ ...table, schema: schema.name })));
  return (
    <article className="database-source-card">
      <div className="database-source-head">
        <div>
          <strong>{source.database_name}</strong>
          <small>{source.engine} · {source.role} · {source.lab_mode}</small>
        </div>
        <StatusBadge value={source.status} />
      </div>
      {source.error && <p className="catalog-muted">{source.error}</p>}
      <div className="database-source-stats">
        <span>{source.table_count} tablas</span>
        <span>{source.queryable_table_count} queryables</span>
        {source.host && <span>{source.host}</span>}
      </div>
      <div className="database-table-chips">
        {tables.slice(0, compact ? 8 : 18).map((table) => (
          <span className={table.allowed_query ? "queryable" : table.internal ? "internal" : ""} key={table.qualified_name}>
            {table.schema}.{table.name}
          </span>
        ))}
        {tables.length > (compact ? 8 : 18) && <span>+{tables.length - (compact ? 8 : 18)}</span>}
      </div>
    </article>
  );
}

function parseFindingRec(raw: string): { description: string; actions: string[] } {
  try {
    const data = JSON.parse(raw);
    if (data && typeof data === "object" && "description" in data) {
      return { description: String(data.description ?? ""), actions: Array.isArray(data.actions) ? data.actions : [] };
    }
  } catch { /* plain text fallback */ }
  return { description: raw, actions: [] };
}

type DbaAiFinding = {
  category?: string;
  title?: string;
  description?: string;
  severity?: string;
  affected_tables?: string[];
  actions?: string[];
};

function parseDbaAiSummary(raw: string | null): DbaAiFinding[] {
  if (!raw) return [];
  const candidates = [raw.trim()];
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start >= 0 && end > start) candidates.push(raw.slice(start, end + 1));

  function findingsFrom(value: unknown): DbaAiFinding[] {
    if (typeof value === "string") {
      try {
        return findingsFrom(JSON.parse(value));
      } catch {
        return [];
      }
    }
    if (value && typeof value === "object" && Array.isArray((value as { findings?: unknown }).findings)) {
      return (value as { findings: DbaAiFinding[] }).findings;
    }
    return [];
  }

  for (const candidate of candidates) {
    try {
      const findings = findingsFrom(JSON.parse(candidate));
      if (findings.length > 0) return findings;
    } catch {
      // Try the next candidate.
    }
  }
  return [];
}

function looksLikeJsonSummary(raw: string | null): boolean {
  if (!raw) return false;
  try {
    const parsed = JSON.parse(raw);
    return Boolean(parsed && typeof parsed === "object" && "findings" in parsed);
  } catch {
    return raw.includes('"findings"') || raw.includes("{'findings'");
  }
}

const DBA_CATEGORIES = [
  { key: "security", label: "Seguridad y Accesos", Icon: ShieldCheck, cardClass: "dba-cat-security" },
  { key: "performance", label: "Rendimiento e Índices", Icon: Zap, cardClass: "dba-cat-performance" },
  { key: "architecture", label: "Arquitectura y Esquema", Icon: Database, cardClass: "dba-cat-architecture" },
  { key: "operations", label: "Operaciones y Gobernanza", Icon: Cog, cardClass: "dba-cat-operations" },
] as const;

const SEVERITY_LABEL: Record<string, string> = {
  critical: "Crítico",
  high: "Alto",
  medium: "Medio",
  low: "Bajo",
  info: "Info",
};

const SEVERITY_CLASS: Record<string, string> = {
  critical: "sev-critical",
  high: "sev-high",
  medium: "sev-medium",
  low: "sev-low",
  info: "sev-info",
};

function timeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return `${seconds} segundos`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minuto${minutes !== 1 ? "s" : ""}`;
  const hours = Math.floor(minutes / 60);
  return `${hours} hora${hours !== 1 ? "s" : ""}`;
}

function DbaCopilot() {
  const [tables, setTables] = useState<DbaTableProfile[]>([]);
  const [recommendations, setRecommendations] = useState<DbaRecommendation[]>([]);
  const [sources, setSources] = useState<DatabaseInventory | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<Date | null>(null);
  const [aiSummary, setAiSummary] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getDbaTables(), getDbaRecommendations(), getDbaSources()])
      .then(([tableProfiles, recommendationList, inventory]) => {
        setTables(tableProfiles);
        setRecommendations(recommendationList);
        setSources(inventory);
        if (recommendationList.length > 0) setLastRun(new Date());
      })
      .catch((requestError) => setError(getErrorMessage(requestError)));
  }, []);

  async function analyze() {
    setBusy(true);
    setError(null);
    try {
      const summary: DbaAnalyzeResponse = await runDbaAnalysis();
      const [tableProfiles, recommendationList, inventory] = await Promise.all([
        getDbaTables(),
        getDbaRecommendations(),
        getDbaSources(),
      ]);
      setTables(tableProfiles);
      setRecommendations(recommendationList);
      setSources(inventory);
      setAiSummary(summary.ai_summary);
      setLastRun(new Date());
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  function toggleExpand(id: number) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const grouped = useMemo(() => {
    const result: Record<string, DbaRecommendation[]> = {};
    for (const cat of DBA_CATEGORIES) {
      result[cat.key] = recommendations.filter((r) => r.category === cat.key);
    }
    return result;
  }, [recommendations]);
  const summaryFindings = useMemo(() => parseDbaAiSummary(aiSummary), [aiSummary]);
  const sourceSummary = useMemo(() => {
    const sourceList = sources?.sources ?? [];
    if (sourceList.length === 0) return "sin fuentes registradas";
    return sourceList.map((source) => `${source.database_name} (${source.role})`).join(" · ");
  }, [sources]);

  const updatedText = lastRun ? `Actualizado hace ${timeAgo(lastRun)}` : "Sin análisis previo";

  return (
    <div className="dba-copilot">
      <div className="panel dba-header-panel">
        <div>
          <h2 className="dba-title">
            <Sparkles size={20} aria-hidden="true" />
            Análisis DBA con IA
          </h2>
          <p className="dba-subtitle">
            Analizadas {tables.length} tablas · {recommendations.length} acciones sugeridas · {sourceSummary} · {updatedText}
          </p>
        </div>
        <button className="primary" onClick={() => void analyze()} disabled={busy}>
          <Sparkles size={16} aria-hidden="true" />
          Ejecutar Nuevo Análisis
        </button>
      </div>

      <ErrorNotice error={error} />

      <DatabaseInventoryPanel inventory={sources} title="Fuentes DBA" />

      {aiSummary && (
        <div className="panel dba-summary-panel">
          <div className="panel-heading">
            <h2>Resumen IA</h2>
            <Sparkles size={18} aria-hidden="true" />
          </div>
          {summaryFindings.length > 0 ? (
            <DbaSummaryFindings findings={summaryFindings} />
          ) : looksLikeJsonSummary(aiSummary) ? (
            <p className="ai-para">Resumen estructurado recibido. Ejecuta de nuevo el análisis si deseas regenerar la vista.</p>
          ) : (
            <AiMarkdown text={aiSummary} />
          )}
        </div>
      )}

      {recommendations.length > 0 && (
        <>
          <div className="dba-category-grid">
            {DBA_CATEGORIES.map((cat) => {
              const count = grouped[cat.key]?.length ?? 0;
              return (
                <div key={cat.key} className={`panel dba-category-card ${cat.cardClass}`}>
                  <cat.Icon size={28} aria-hidden="true" />
                  <span className="cat-count">{count}</span>
                  <span className="cat-label">{cat.label}</span>
                </div>
              );
            })}
          </div>

          {DBA_CATEGORIES.map((cat) => {
            const catRecs = grouped[cat.key] ?? [];
            if (!catRecs.length) return null;
            return (
              <section key={cat.key} className="dba-section">
                <div className="dba-section-head">
                  <cat.Icon size={18} aria-hidden="true" />
                  <h3>{cat.label}</h3>
                  <span className="findings-badge">{catRecs.length} hallazgos</span>
                </div>
                <div className="dba-findings-list">
                  {catRecs.map((rec) => {
                    const { description, actions } = parseFindingRec(rec.recommendation);
                    const expanded = expandedIds.has(rec.id);
                    return (
                      <div
                        key={rec.id}
                        className={`panel dba-finding${expanded ? " dba-finding--open" : ""}`}
                        onClick={() => toggleExpand(rec.id)}
                        role="button"
                        style={{ cursor: "pointer" }}
                      >
                        <div className="dba-finding-row">
                          <div className="dba-finding-info">
                            <span className={`status-badge ${SEVERITY_CLASS[rec.severity] ?? "sev-info"}`}>
                              {SEVERITY_LABEL[rec.severity] ?? rec.severity}
                            </span>
                            <strong>{rec.title}</strong>
                          </div>
                          {expanded
                            ? <ChevronDown size={18} aria-hidden="true" className="dba-chevron" />
                            : <ChevronRight size={18} aria-hidden="true" className="dba-chevron" />}
                        </div>
                        {description && <p className="dba-finding-desc">{description}</p>}
                        {rec.affected_tables_json.length > 0 && (
                          <div className="dba-table-chips">
                            {rec.affected_tables_json.map((table) => (
                              <span key={table} className="dba-table-chip">⊞ {table}</span>
                            ))}
                          </div>
                        )}
                        {expanded && actions.length > 0 && (
                          <div className="dba-actions" onClick={(e) => e.stopPropagation()}>
                            <p className="dba-actions-title">ACCIONES RECOMENDADAS</p>
                            <ul className="dba-actions-list">
                              {actions.map((action, i) => (
                                <li key={i}>
                                  <CheckCircle2 size={16} className="action-check" aria-hidden="true" />
                                  <span>{renderInline(action)}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </>
      )}

      {recommendations.length === 0 && !busy && (
        <div className="panel dba-empty">
          <Sparkles size={32} aria-hidden="true" />
          <p>Ejecuta un análisis para ver los hallazgos DBA con IA.</p>
        </div>
      )}
    </div>
  );
}

function DbaSummaryFindings({ findings }: { findings: DbaAiFinding[] }) {
  return (
    <div className="dba-summary-grid">
      {findings.slice(0, 6).map((finding, index) => (
        <article className="dba-summary-card" key={`${finding.title ?? "finding"}-${index}`}>
          <div className="dba-summary-card-head">
            <span className={`status-badge ${SEVERITY_CLASS[finding.severity ?? "info"] ?? "sev-info"}`}>
              {SEVERITY_LABEL[finding.severity ?? "info"] ?? finding.severity ?? "Info"}
            </span>
            <span className="dba-summary-category">{finding.category ?? "operations"}</span>
          </div>
          <h3>{finding.title ?? "Hallazgo DBA"}</h3>
          {finding.description && <p>{finding.description}</p>}
          {Array.isArray(finding.affected_tables) && finding.affected_tables.length > 0 && (
            <div className="dba-table-chips">
              {finding.affected_tables.slice(0, 5).map((table) => (
                <span className="dba-table-chip" key={table}>{table}</span>
              ))}
            </div>
          )}
          {Array.isArray(finding.actions) && finding.actions.length > 0 && (
            <ul className="dba-summary-actions">
              {finding.actions.slice(0, 3).map((action) => (
                <li key={action}>
                  <CheckCircle2 size={15} aria-hidden="true" />
                  <span>{renderInline(action)}</span>
                </li>
              ))}
            </ul>
          )}
        </article>
      ))}
    </div>
  );
}

type DataOpsMetricCard = {
  key: string;
  label: string;
  value: string | number;
  icon: typeof Activity;
};

function dataOpsPipelineKey(pipeline: DataOpsPipeline | null | undefined) {
  return pipeline?.pipeline_key || pipeline?.name || "tpcds-retail-dataops";
}

function metricValue(metric: DataOpsMetric) {
  if (metric.formatted) return metric.formatted;
  if (metric.value === null || metric.value === undefined) return "0";
  const rawValue = typeof metric.value === "boolean" ? (metric.value ? "yes" : "no") : `${metric.value}`;
  return metric.unit ? `${rawValue}${metric.unit}` : rawValue;
}

function metricLabel(metric: DataOpsMetric) {
  if (metric.label === "Generated transactions") return "Source transactions";
  return metric.label.replace("Generated", "Monitored");
}

function metricIcon(metric: DataOpsMetric): typeof Activity {
  const key = metric.key.toLowerCase();
  if (key.includes("email")) return Mail;
  if (key.includes("alert") || key.includes("quarantine")) return TriangleAlert;
  if (key.includes("quality") || key.includes("rate")) return ShieldCheck;
  if (key.includes("gold")) return Sparkles;
  if (key.includes("processed") || key.includes("silver")) return CheckCircle2;
  return Database;
}

function buildDataOpsMetricCards(run: DataOpsPipelineRun | null): DataOpsMetricCard[] {
  if (run?.metrics_json?.length) {
    return [...run.metrics_json]
      .sort((a, b) => (a.order ?? 99) - (b.order ?? 99))
      .slice(0, 5)
      .map((metric) => ({
        key: metric.key,
        label: metricLabel(metric),
        value: metricValue(metric),
        icon: metricIcon(metric),
      }));
  }
  return [
    { key: "bronze_rows", label: "Bronze rows", value: run?.bronze_rows ?? 0, icon: Database },
    { key: "silver_rows", label: "Silver rows", value: run?.silver_rows ?? 0, icon: CheckCircle2 },
    { key: "gold_rows", label: "Gold rows", value: run?.gold_rows ?? 0, icon: Sparkles },
    { key: "quality_score", label: "Quality score", value: run ? `${formatQualityScore(run.quality_score)}%` : "0%", icon: ShieldCheck },
    { key: "quarantine_rows", label: "Quarantine", value: run?.quarantine_rows ?? 0, icon: TriangleAlert },
  ];
}

function findRunMetric(run: DataOpsPipelineRun, key: string) {
  return run.metrics_json?.find((metric) => metric.key === key);
}

function dataOpsRunSummary(run: DataOpsPipelineRun, pipeline: DataOpsPipeline | null) {
  if (pipeline?.pipeline_type === "banking_fraud_alerts") {
    const alerts = findRunMetric(run, "alerts_generated");
    const processed = findRunMetric(run, "transactions_processed");
    return `${alerts ? metricValue(alerts) : run.gold_rows} alertas · ${processed ? metricValue(processed) : run.silver_rows} procesadas`;
  }
  return `${formatQualityScore(run.quality_score)}% · ${run.quarantine_rows} quarantine`;
}

function isLocalDataOpsRun(run: DataOpsPipelineRun | null) {
  if (!run) return false;
  return run.databricks_run_url?.startsWith("local-demo://") || run.run_id.includes("demo-");
}

function realDatabricksUrl(run: DataOpsPipelineRun | null) {
  if (!run?.databricks_run_url || isLocalDataOpsRun(run)) return null;
  return run.databricks_run_url;
}

function dataOpsAssetDisplayName(asset: DataOpsGeneratedAsset, pipeline: DataOpsPipeline | null) {
  if (pipeline?.pipeline_type !== "banking_fraud_alerts") return asset.asset_name;
  const labels: Record<string, string> = {
    transacciones_demo: "transacciones_origen",
    alertas_movimientos_inusuales: "alertas_movimientos_inusuales",
    log_ejecucion_alertas: "log_ejecucion_alertas",
  };
  return labels[asset.asset_name] ?? asset.asset_name;
}

function DataOpsMonitor({ onRunStatusChange }: { onRunStatusChange: (run: DataOpsPipelineRun | null) => void }) {
  const [pipelines, setPipelines] = useState<DataOpsPipeline[]>([]);
  const [selectedPipelineKey, setSelectedPipelineKey] = useState("");
  const [currentRun, setCurrentRun] = useState<DataOpsPipelineRun | null>(null);
  const [history, setHistory] = useState<DataOpsPipelineRun[]>([]);
  const [quality, setQuality] = useState<DataOpsQualityCheck[]>([]);
  const [assets, setAssets] = useState<DataOpsGeneratedAsset[]>([]);
  const [quarantine, setQuarantine] = useState<DataOpsQuarantineEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh(targetPipelineKey?: string) {
    const pipelineList = await getDataOpsPipelines();
    const fallbackKey = dataOpsPipelineKey(pipelineList[0]);
    const resolvedKey = targetPipelineKey || selectedPipelineKey || fallbackKey;
    const [current, runHistory, qualityChecks, generatedAssets, quarantineEvents] = await Promise.all([
      getDataOpsCurrent(resolvedKey),
      getDataOpsHistory(resolvedKey),
      getDataOpsQuality(resolvedKey),
      getDataOpsAssets(resolvedKey),
      getDataOpsQuarantine(resolvedKey),
    ]);
    setPipelines(pipelineList);
    setSelectedPipelineKey(resolvedKey);
    setCurrentRun(current.latest_run);
    onRunStatusChange(current.latest_run?.status === "running" ? current.latest_run : null);
    setHistory(runHistory);
    setQuality(qualityChecks);
    setAssets(generatedAssets);
    setQuarantine(quarantineEvents);
  }

  useEffect(() => {
    refresh().catch((requestError) => setError(getErrorMessage(requestError)));
  }, []);

  useEffect(() => {
    if (currentRun?.status !== "running") return;
    const id = window.setInterval(() => {
      refresh(selectedPipelineKey).catch((requestError) => setError(getErrorMessage(requestError)));
    }, 5000);
    return () => window.clearInterval(id);
  }, [currentRun?.status, selectedPipelineKey]);

  async function runPipeline() {
    const pipelineKey = selectedPipelineKey || dataOpsPipelineKey(pipelines[0]);
    setBusy(true);
    setError(null);
    try {
      const run = await runDataOpsPipeline(pipelineKey);
      setCurrentRun(run);
      onRunStatusChange(run.status === "running" ? run : null);
      await refresh(pipelineKey);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function changePipeline(pipelineKey: string) {
    setSelectedPipelineKey(pipelineKey);
    setBusy(true);
    setError(null);
    try {
      await refresh(pipelineKey);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  const selectedPipeline = pipelines.find((pipeline) => dataOpsPipelineKey(pipeline) === selectedPipelineKey) ?? pipelines[0] ?? null;
  const failedChecks = quality.filter((item) => item.status !== "passed");
  const metricCards = buildDataOpsMetricCards(currentRun);
  const runEvents = currentRun?.events_json ?? [];
  const currentRunLabel = currentRun?.business_run_id || currentRun?.run_id;
  const isBankingPipeline = selectedPipeline?.pipeline_type === "banking_fraud_alerts";
  const tableCountLabel = isBankingPipeline ? "tablas monitoreadas" : "tablas generadas";
  const assetsTitle = isBankingPipeline ? "Tablas Monitoreadas" : "Tablas Generadas";
  const emptyAssetsText = isBankingPipeline ? "Sin tablas monitoreadas todavia." : "Sin tablas generadas todavia.";
  const databricksUrl = realDatabricksUrl(currentRun);
  const showDatabricksRunId = Boolean(
    currentRun?.databricks_run_id && currentRun.databricks_run_id !== currentRunLabel && !isLocalDataOpsRun(currentRun)
  );

  return (
    <div className="dataops-monitor">
      <div className="panel dataops-header-panel">
        <div className="dataops-header-copy">
          <p className="eyebrow">{isBankingPipeline ? "Alertas bancarias · Gold" : "Bronze · Silver · Gold"}</p>
          <h2 className="dataops-title">
            <Database size={20} aria-hidden="true" />
            DataOps Monitor
          </h2>
          {selectedPipeline?.description && <p className="dataops-subtitle">{selectedPipeline.description}</p>}
        </div>
        <div className="dataops-toolbar">
          <label className="dataops-selector" htmlFor="dataops-pipeline">
            <span>Pipeline</span>
            <select
              id="dataops-pipeline"
              value={selectedPipelineKey}
              onChange={(event) => void changePipeline(event.target.value)}
              disabled={busy || pipelines.length === 0}
            >
              {pipelines.map((pipeline) => (
                <option key={pipeline.id} value={dataOpsPipelineKey(pipeline)}>
                  {pipeline.name}
                </option>
              ))}
            </select>
          </label>
          <div className="button-row dataops-actions">
            <button onClick={() => void refresh(selectedPipelineKey)} disabled={busy}>
              <RefreshCw size={16} aria-hidden="true" />
              Refresh
            </button>
            <button className="primary" onClick={() => void runPipeline()} disabled={busy || !selectedPipeline}>
              <Play size={16} aria-hidden="true" />
              Run Pipeline
            </button>
          </div>
        </div>
      </div>

      <ErrorNotice error={error} />

      {currentRun?.status === "running" && (
        <div className="dataops-running-banner">
          <Activity className="spin" size={18} aria-hidden="true" />
          <div>
            <strong>Job de Databricks en ejecución</strong>
            <p>Run ID {currentRunLabel}. El monitor se actualiza automáticamente mientras termina el pipeline.</p>
          </div>
          {databricksUrl && (
            <a className="external-link" href={databricksUrl} target="_blank" rel="noreferrer">
              <ExternalLink size={16} aria-hidden="true" />
              Ver Run
            </a>
          )}
        </div>
      )}

      <section className="metrics-grid dataops-metrics">
        {metricCards.map((metric) => (
          <Stat key={metric.key} label={metric.label} value={metric.value} icon={metric.icon} />
        ))}
      </section>

      {currentRun && (
        <section className="content-grid dataops-grid">
          <div className="panel wide dataops-run-strip">
            <div>
              <p className="eyebrow">Current Run</p>
              <h2>{currentRunLabel}</h2>
              <p>
                {currentRun.duration_ms} ms · {currentRun.generated_tables_json.length} {tableCountLabel}
                {showDatabricksRunId ? ` · Databricks ${currentRun.databricks_run_id}` : ""}
              </p>
            </div>
            <div className="dataops-run-actions">
              <StatusBadge value={currentRun.status} />
              {databricksUrl && (
                <a className="external-link" href={databricksUrl} target="_blank" rel="noreferrer">
                  <ExternalLink size={16} aria-hidden="true" />
                  Databricks
                </a>
              )}
            </div>
          </div>

          {currentRun.ai_summary && (
            <div className="panel wide">
              <div className="panel-heading">
                <h2>Resumen IA</h2>
                <Sparkles size={18} aria-hidden="true" />
              </div>
              <AiMarkdown text={currentRun.ai_summary} />
            </div>
          )}

          <div className="panel">
            <div className="panel-heading">
              <h2>Quality Rules</h2>
              <span>{failedChecks.length} failed</span>
            </div>
            <div className="row-list compact">
              {quality.length === 0 && <p className="catalog-muted">Sin reglas registradas para esta corrida.</p>}
              {quality.map((item) => (
                <div className="data-row" key={item.id}>
                  <div>
                    <strong>{item.rule_code}</strong>
                    <p>{item.layer} · {item.description}</p>
                  </div>
                  <StatusBadge value={item.status} />
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-heading">
              <h2>{assetsTitle}</h2>
              <span>{assets.length}</span>
            </div>
            <div className="row-list compact">
              {assets.length === 0 && <p className="catalog-muted">{emptyAssetsText}</p>}
              {assets.map((asset) => (
                <div className="data-row" key={asset.id}>
                  <div>
                    <strong>{dataOpsAssetDisplayName(asset, selectedPipeline)}</strong>
                    <p>{asset.layer} · {asset.row_count} filas</p>
                  </div>
                  <StatusBadge value={asset.layer} />
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-heading">
              <h2>{runEvents.length ? "Detected Alerts" : "Quarantine Preview"}</h2>
              <span>{runEvents.length || quarantine.length}</span>
            </div>
            <div className="row-list compact">
              {runEvents.length === 0 && quarantine.length === 0 && (
                <p className="catalog-muted">Sin eventos para mostrar en esta corrida.</p>
              )}
              {runEvents.map((event, index) => (
                <DataOpsEventRow event={event} key={`${event.record_ref ?? event.rule_code ?? "event"}-${index}`} />
              ))}
              {runEvents.length === 0 && quarantine.map((event) => (
                <div className="data-row quarantine-row" key={event.id}>
                  <div>
                    <strong>{event.record_ref ?? event.rule_code}</strong>
                    <p>{event.reason}</p>
                    <code>{JSON.stringify(event.preview_json)}</code>
                  </div>
                  <StatusBadge value={event.rule_code} />
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-heading">
              <h2>History</h2>
              <span>{history.length}</span>
            </div>
            <div className="row-list compact">
              {history.length === 0 && <p className="catalog-muted">Sin historial para este pipeline.</p>}
              {history.map((run) => (
                <div className="data-row" key={run.id}>
                  <div>
                    <strong>{run.business_run_id || run.run_id}</strong>
                    <p>{dataOpsRunSummary(run, selectedPipeline)} · {new Date(run.created_at).toLocaleString()}</p>
                  </div>
                  <StatusBadge value={run.status} />
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {!currentRun && !busy && (
        <div className="panel dba-empty">
          <Database size={32} aria-hidden="true" />
          <p>Ejecuta el pipeline seleccionado para ver métricas DataOps.</p>
        </div>
      )}
    </div>
  );
}

function DataOpsEventRow({ event }: { event: DataOpsRunEvent }) {
  const preview = event.preview ?? event.preview_json ?? {};
  const badge = event.severity || event.rule_code || "alert";
  return (
    <div className="data-row quarantine-row">
      <div>
        <strong>{event.record_ref ?? event.rule_code ?? event.event_type ?? "alert"}</strong>
        <p>{event.reason ?? "Movimiento inusual detectado."}</p>
        <code>{JSON.stringify(preview)}</code>
      </div>
      <StatusBadge value={badge} />
    </div>
  );
}

function CatalogGovernance() {
  const [status, setStatus] = useState<CatalogStatus | null>(null);
  const [assets, setAssets] = useState<CatalogAsset[]>([]);
  const [columns, setColumns] = useState<CatalogColumn[]>([]);
  const [classifications, setClassifications] = useState<CatalogClassification[]>([]);
  const [lineage, setLineage] = useState<CatalogLineageEdge[]>([]);
  const [syncRuns, setSyncRuns] = useState<CatalogSyncRun[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<number | null>(null);
  const [layerFilter, setLayerFilter] = useState("all");
  const [classificationFilter, setClassificationFilter] = useState("all");
  const [ownerDraft, setOwnerDraft] = useState("");
  const [columnDrafts, setColumnDrafts] = useState<Record<number, string>>({});
  const [savingColumnId, setSavingColumnId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refreshCatalog(nextSelectedId?: number | null) {
    const [catalogStatus, catalogAssets, catalogClassifications, catalogLineage, catalogSyncRuns] = await Promise.all([
      getCatalogStatus(),
      getCatalogAssets(),
      getCatalogClassifications(),
      getCatalogLineage(),
      getCatalogSyncRuns(),
    ]);
    const normalizedAssets = [...catalogAssets].sort((a, b) => {
      const layerOrder: Record<string, number> = { gold: 0, silver: 1, bronze: 2, lab: 3, operational: 4 };
      return (layerOrder[a.layer] ?? 9) - (layerOrder[b.layer] ?? 9) || a.asset_name.localeCompare(b.asset_name);
    });
    setStatus(catalogStatus);
    setAssets(normalizedAssets);
    setClassifications(catalogClassifications);
    setLineage(catalogLineage);
    setSyncRuns(catalogSyncRuns);
    const fallbackId = normalizedAssets[0]?.id ?? null;
    const selectedId = nextSelectedId === undefined ? selectedAssetId ?? fallbackId : nextSelectedId;
    setSelectedAssetId(selectedId);
  }

  useEffect(() => {
    refreshCatalog().catch((requestError) => setError(getErrorMessage(requestError)));
  }, []);

  const selectedAsset = assets.find((asset) => asset.id === selectedAssetId) ?? null;

  useEffect(() => {
    if (!selectedAsset) {
      setColumns([]);
      setOwnerDraft("");
      return;
    }
    setOwnerDraft(selectedAsset.owner);
    getCatalogColumns(selectedAsset.id)
      .then((items) => {
        setColumns(items);
        setColumnDrafts(Object.fromEntries(items.map((column) => [column.id, column.description ?? ""])));
      })
      .catch((requestError) => setError(getErrorMessage(requestError)));
  }, [selectedAsset?.id]);

  async function runSync() {
    setBusy(true);
    setError(null);
    try {
      await syncCatalog();
      await refreshCatalog();
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function documentAsset() {
    if (!selectedAsset) return;
    setBusy(true);
    setError(null);
    try {
      const response = await generateCatalogDocumentation(selectedAsset.id);
      await refreshCatalog(response.asset.id);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function saveOwner() {
    if (!selectedAsset) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateCatalogOwner(selectedAsset.id, ownerDraft);
      await refreshCatalog(updated.id);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function saveClassification(classification: string) {
    if (!selectedAsset) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateCatalogClassification(selectedAsset.id, classification);
      await refreshCatalog(updated.id);
      const refreshedColumns = await getCatalogColumns(updated.id);
      setColumns(refreshedColumns);
      setColumnDrafts(Object.fromEntries(refreshedColumns.map((column) => [column.id, column.description ?? ""])));
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function saveColumnDescription(column: CatalogColumn) {
    const description = columnDrafts[column.id] ?? "";
    setSavingColumnId(column.id);
    setError(null);
    try {
      const updated = await updateCatalogColumnDescription(column.id, description);
      setColumns((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setColumnDrafts((current) => ({ ...current, [updated.id]: updated.description ?? "" }));
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setSavingColumnId(null);
    }
  }

  const layerOptions = useMemo(() => ["all", ...Array.from(new Set(assets.map((asset) => asset.layer)))], [assets]);
  const filteredAssets = useMemo(() => {
    return assets.filter((asset) => {
      const layerMatch = layerFilter === "all" || asset.layer === layerFilter;
      const classMatch = classificationFilter === "all" || asset.sensitivity_level === classificationFilter;
      return layerMatch && classMatch;
    });
  }, [assets, layerFilter, classificationFilter]);

  const sensitiveColumns = columns.filter((column) => column.is_sensitive);
  const inbound = selectedAsset ? lineage.filter((edge) => edge.target_asset_urn === selectedAsset.asset_urn) : [];
  const outbound = selectedAsset ? lineage.filter((edge) => edge.source_asset_urn === selectedAsset.asset_urn) : [];
  const sourceSystems = useMemo(() => Array.from(new Set(assets.map((asset) => asset.source_system))), [assets]);

  return (
    <div className="catalog-governance">
      <div className="panel catalog-header-panel">
        <div>
          <p className="eyebrow">DataHub · Purview · Internal Catalog</p>
          <h2 className="catalog-title">
            <BookOpen size={20} aria-hidden="true" />
            Catalog Governance
          </h2>
        </div>
        <div className="button-row catalog-actions">
          <button onClick={() => void refreshCatalog()}>Refresh</button>
          <button className="primary" onClick={() => void runSync()} disabled={busy}>
            <RefreshCw size={16} aria-hidden="true" />
            Sync Catalog
          </button>
        </div>
      </div>

      <ErrorNotice error={error} />

      <section className="metrics-grid catalog-metrics">
        <Stat label="Tablas" value={status?.assets_total ?? assets.length} icon={Database} />
        <Stat label="Documented" value={status?.documented_assets ?? 0} icon={BookOpen} />
        <Stat label="Sensitive cols" value={status?.sensitive_columns ?? 0} icon={ShieldCheck} />
        <Stat label="Lineage edges" value={status?.lineage_edges ?? lineage.length} icon={Network} />
        <Stat label="Sources" value={sourceSystems.length || status?.external_catalog || "0"} icon={Tags} />
      </section>

      <section className="catalog-ops-layout">
        <aside className="panel catalog-sidebar">
          <div className="panel-heading">
            <h2>Tablas</h2>
            <span>{filteredAssets.length}</span>
          </div>
          <div className="catalog-filters">
            <select value={layerFilter} onChange={(event) => setLayerFilter(event.target.value)}>
              {layerOptions.map((layer) => (
                <option key={layer} value={layer}>{layer === "all" ? "Todas las capas" : layer}</option>
              ))}
            </select>
            <select value={classificationFilter} onChange={(event) => setClassificationFilter(event.target.value)}>
              <option value="all">Todas las clases</option>
              {classifications.map((item) => (
                <option key={item.code} value={item.code}>{item.label}</option>
              ))}
            </select>
          </div>
          <div className="row-list compact catalog-asset-list">
            {filteredAssets.map((asset) => (
              <button
                className={`catalog-asset-button${selectedAsset?.id === asset.id ? " active" : ""}`}
                key={asset.id}
                onClick={() => setSelectedAssetId(asset.id)}
              >
                <span>
                  <strong>{asset.asset_name}</strong>
                  <small>{asset.platform} · {asset.database_name ?? "-"} · {asset.schema_name ?? "-"}</small>
                </span>
                <StatusBadge value={asset.layer} />
              </button>
            ))}
          </div>
        </aside>

        <div className="catalog-main">
          {selectedAsset ? (
            <>
              <div className="panel catalog-detail-panel">
                <div className="catalog-detail-head">
                  <div>
                    <p className="eyebrow">{selectedAsset.source_system} · {domainLabel(selectedAsset.domain)}</p>
                    <h2>{selectedAsset.display_name}</h2>
                    <p>{selectedAsset.platform} · {selectedAsset.database_name ?? "-"}.{selectedAsset.schema_name ?? "-"}.{selectedAsset.table_name}</p>
                  </div>
                  <div className="catalog-detail-actions">
                    <StatusBadge value={selectedAsset.sensitivity_level} />
                    <StatusBadge value={selectedAsset.documentation_status} />
                    {selectedAsset.external_url && (
                      <a className="external-link" href={selectedAsset.external_url} target="_blank" rel="noreferrer">
                        <ExternalLink size={16} aria-hidden="true" />
                        Source
                      </a>
                    )}
                  </div>
                </div>

                <div className="catalog-origin-grid">
                  <div className="catalog-origin-chip">
                    <span>Sistema</span>
                    <strong>{selectedAsset.source_system}</strong>
                  </div>
                  <div className="catalog-origin-chip">
                    <span>Base</span>
                    <strong>{selectedAsset.database_name ?? "-"}</strong>
                  </div>
                  <div className="catalog-origin-chip">
                    <span>Esquema</span>
                    <strong>{selectedAsset.schema_name ?? "-"}</strong>
                  </div>
                  <div className="catalog-origin-chip">
                    <span>Capa</span>
                    <strong>{selectedAsset.layer}</strong>
                  </div>
                </div>

                <div className="catalog-controls">
                  <div className="catalog-class-field">
                    <ShieldCheck size={16} aria-hidden="true" />
                    <select
                      value={selectedAsset.sensitivity_level}
                      onChange={(event) => void saveClassification(event.target.value)}
                      disabled={busy}
                    >
                      {classifications.map((item) => (
                        <option key={item.code} value={item.code}>{item.label}</option>
                      ))}
                    </select>
                  </div>
                  <button className="primary" onClick={() => void documentAsset()} disabled={busy}>
                    <Sparkles size={16} aria-hidden="true" />
                    Generate Documentation
                  </button>
                </div>

                {selectedAsset.description ? (
                  <div className="catalog-doc">
                    <AiMarkdown text={selectedAsset.description} />
                  </div>
                ) : (
                  <div className="catalog-doc empty-doc">
                    <BookOpen size={24} aria-hidden="true" />
                    <p>Documentacion pendiente.</p>
                  </div>
                )}
              </div>

            </>
          ) : (
            <div className="panel dba-empty">
              <BookOpen size={32} aria-hidden="true" />
              <p>Sincroniza el catalogo para cargar tablas gobernadas.</p>
            </div>
          )}
        </div>

        <aside className="catalog-side-stack">
          <div className="panel catalog-sync-panel">
            <div className="panel-heading">
              <h2>Sync Runs</h2>
              <span>{syncRuns.length}</span>
            </div>
            <div className="row-list compact">
              {syncRuns.map((run) => (
                <div className="data-row" key={run.id}>
                  <div>
                    <strong>{run.source}</strong>
                    <p>{run.assets_seen} tablas vistas · {run.assets_created} nuevas · {new Date(run.started_at).toLocaleString()}</p>
                  </div>
                  <StatusBadge value={run.status} />
                </div>
              ))}
            </div>
          </div>

          {selectedAsset && (
            <div className="panel catalog-lineage-panel">
              <div className="panel-heading">
                <h2>Lineage</h2>
                <Network size={18} aria-hidden="true" />
              </div>
              <div className="catalog-lineage-list">
                {[...inbound, ...outbound].map((edge) => (
                  <div className="catalog-lineage-edge" key={edge.id}>
                    <GitBranch size={16} aria-hidden="true" />
                    <div>
                      <strong>{edge.transformation_name ?? edge.lineage_type}</strong>
                      <p>{shortUrn(edge.source_asset_urn)} -&gt; {shortUrn(edge.target_asset_urn)}</p>
                    </div>
                  </div>
                ))}
                {inbound.length + outbound.length === 0 && <p className="catalog-muted">Sin linaje para esta tabla.</p>}
              </div>
            </div>
          )}
        </aside>
      </section>

      {selectedAsset && (
        <section className="catalog-metadata-section">
          <div className="panel catalog-dictionary-panel">
            <div className="panel-heading">
              <h2>Diccionario de Metadata</h2>
              <span>{columns.length} fields · {sensitiveColumns.length} sensitive</span>
            </div>
            <div className="catalog-dictionary-table">
              <div className="catalog-dictionary-row catalog-dictionary-head">
                <span>Columna</span>
                <span>Type</span>
                <span>Structure</span>
                <span>Classification</span>
                <span>Description</span>
                <span>Action</span>
              </div>
              {columns.map((column) => {
                const draft = columnDrafts[column.id] ?? "";
                const unchanged = draft.trim() === (column.description ?? "").trim();
                return (
                  <div className="catalog-dictionary-row" key={column.id}>
                    <div className="field-name">
                      <strong>{column.column_name}</strong>
                      <small>{column.is_sensitive ? "Sensitive field" : "Business field"}</small>
                    </div>
                    <span>{column.data_type}</span>
                    <span>{column.nullable ? "Nullable" : "Required"}</span>
                    <StatusBadge value={column.classification} />
                    <textarea
                      value={draft}
                      onChange={(event) => setColumnDrafts((current) => ({ ...current, [column.id]: event.target.value }))}
                      aria-label={`Description for ${column.column_name}`}
                    />
                    <button
                      className="catalog-save-btn"
                      onClick={() => void saveColumnDescription(column)}
                      disabled={savingColumnId === column.id || unchanged}
                    >
                      <CheckCircle2 size={15} aria-hidden="true" />
                      Save
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function shortUrn(urn: string) {
  const parts = urn.split(",");
  return parts.length >= 2 ? parts[1] : urn;
}

function domainLabel(domain: string) {
  return domain.replace(/-/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderInline(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i} className="ai-inline-code">{part.slice(1, -1)}</code>;
    return part;
  });
}

function AiMarkdown({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  const codeBlockRegex = /```[\w]*\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  // Extract code blocks first, process the rest as markdown paragraphs
  const segments: { type: "text" | "code"; content: string }[] = [];
  while ((match = codeBlockRegex.exec(text)) !== null) {
    if (match.index > lastIndex) segments.push({ type: "text", content: text.slice(lastIndex, match.index) });
    segments.push({ type: "code", content: match[1].trim() });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) segments.push({ type: "text", content: text.slice(lastIndex) });

  segments.forEach((seg, si) => {
    if (seg.type === "code") {
      blocks.push(<pre key={`code-${si}`} className="ai-code-block">{seg.content}</pre>);
      return;
    }
    seg.content.split(/\n\n+/).forEach((block, bi) => {
      const key = `${si}-${bi}`;
      const trimmed = block.trim();
      if (!trimmed) return;

      if (/^#{1,3}\s/.test(trimmed)) {
        blocks.push(<p key={key} className="ai-section-label">{renderInline(trimmed.replace(/^#{1,3}\s*/, ""))}</p>);
      } else if (/^\d+\.\s/.test(trimmed)) {
        const items = trimmed.split(/\n(?=\d+\.)/).map((l) => l.replace(/^\d+\.\s*/, "").trim());
        blocks.push(<ol key={key} className="ai-list">{items.map((it, ii) => <li key={ii}>{renderInline(it)}</li>)}</ol>);
      } else if (/^-\s/.test(trimmed)) {
        const items = trimmed.split(/\n-\s/).map((l) => l.replace(/^-\s*/, "").trim());
        blocks.push(<ul key={key} className="ai-list">{items.map((it, ii) => <li key={ii}>{renderInline(it)}</li>)}</ul>);
      } else {
        blocks.push(<p key={key} className="ai-para">{renderInline(trimmed)}</p>);
      }
    });
  });

  return <div className="ai-markdown">{blocks}</div>;
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h3>{title}</h3>
      <ul className="clean-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function PaginatedResultTable({
  columns,
  rows,
  rowCount,
  executionMs,
}: {
  columns: string[];
  rows: Record<string, string | number | boolean | null>[];
  rowCount: number;
  executionMs: number;
}) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const visibleRows = rows.slice((page - 1) * pageSize, page * pageSize);

  function changePage(next: number) {
    setPage(Math.min(totalPages, Math.max(1, next)));
  }

  return (
    <div className="paginated-table">
      <div className="table-toolbar">
        <span className="table-toolbar-info">{rowCount} filas · {executionMs} ms</span>
        <div className="page-size-group">
          <span>Por página</span>
          {[10, 25, 50].map((size) => (
            <button
              key={size}
              className={`page-size-btn${pageSize === size ? " active" : ""}`}
              onClick={() => { setPageSize(size); setPage(1); }}
            >
              {size}
            </button>
          ))}
        </div>
      </div>
      <ResultTable columns={columns} rows={visibleRows} />
      {totalPages > 1 && (
        <div className="pagination-bar">
          <button className="pag-btn" onClick={() => changePage(page - 1)} disabled={page === 1}>‹</button>
          <span>Página {page} de {totalPages}</span>
          <button className="pag-btn" onClick={() => changePage(page + 1)} disabled={page === totalPages}>›</button>
        </div>
      )}
    </div>
  );
}

function ResultTable({ columns, rows }: { columns: string[]; rows: Record<string, string | number | boolean | null>[] }) {
  return (
    <div className="query-result-table">
      <div className="query-result-row header" style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(140px, 1fr))` }}>
        {columns.map((column) => (
          <span key={column}>{column}</span>
        ))}
      </div>
      {rows.map((row, index) => (
        <div className="query-result-row" key={index} style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(140px, 1fr))` }}>
          {columns.map((column) => (
            <span key={column}>{String(row[column] ?? "")}</span>
          ))}
        </div>
      ))}
    </div>
  );
}
