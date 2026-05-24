import {
  Activity,
  Boxes,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cog,
  Database,
  GitBranch,
  Play,
  SearchCheck,
  Server,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
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
  getDbaRecommendations,
  getDbaTables,
  getDemoQueries,
  getDeployments,
  getEnvironments,
  getPlatformStatus,
  getQueryHistory,
  getQueryPolicies,
  getServices,
  runDbaAnalysis,
} from "./api";

type LoadState = "loading" | "ready" | "error";
type View = "overview" | "query" | "dba";

function statusTone(status: string) {
  if (["healthy", "success", "connected", "approved", "low", "configured"].includes(status)) {
    return "text-emerald-700 bg-emerald-50 border-emerald-200";
  }
  if (["attention", "degraded", "medium", "warning"].includes(status)) return "text-amber-700 bg-amber-50 border-amber-200";
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
  return <span className={`status-badge ${statusTone(value)}`}>{value}</span>;
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

export default function App() {
  const [activeView, setActiveView] = useState<View>("overview");
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [status, setStatus] = useState<PlatformStatus | null>(null);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);

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
          <p className="eyebrow">Phase 2 Query Governance</p>
          <h1>Enterprise CloudOps & DataOps Autopilot</h1>
        </div>
        <div className="topbar-actions">
          <StatusBadge value={status.database} />
          <StatusBadge value={status.ai_configured ? "configured" : "blocked"} />
        </div>
      </header>

      <nav className="view-tabs" aria-label="Platform views">
        <button className={activeView === "overview" ? "active" : ""} onClick={() => setActiveView("overview")}>
          Platform Overview
        </button>
        <button className={activeView === "query" ? "active" : ""} onClick={() => setActiveView("query")}>
          Query Governance
        </button>
        <button className={activeView === "dba" ? "active" : ""} onClick={() => setActiveView("dba")}>
          DBA Copilot
        </button>
      </nav>

      {activeView === "overview" && (
        <Overview status={status} environments={environments} services={services} deployments={deployments} />
      )}
      {activeView === "query" && <QueryGovernance />}
      {activeView === "dba" && <DbaCopilot />}
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

function QueryGovernance() {
  const [sql, setSql] = useState("");
  const [policies, setPolicies] = useState<QueryPolicy[]>([]);
  const [history, setHistory] = useState<QueryReview[]>([]);
  const [analysis, setAnalysis] = useState<QueryAnalyzeResponse | null>(null);
  const [execution, setExecution] = useState<QueryExecuteResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getDemoQueries(), getQueryPolicies(), getQueryHistory()])
      .then(([demoQueries, policyList, queryHistory]) => {
        setSql(demoQueries.dangerous);
        setPolicies(policyList);
        setHistory(queryHistory);
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

function parseFindingRec(raw: string): { description: string; actions: string[] } {
  try {
    const data = JSON.parse(raw);
    if (data && typeof data === "object" && "description" in data) {
      return { description: String(data.description ?? ""), actions: Array.isArray(data.actions) ? data.actions : [] };
    }
  } catch { /* plain text fallback */ }
  return { description: raw, actions: [] };
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<Date | null>(null);

  useEffect(() => {
    Promise.all([getDbaTables(), getDbaRecommendations()])
      .then(([tableProfiles, recommendationList]) => {
        setTables(tableProfiles);
        setRecommendations(recommendationList);
        if (recommendationList.length > 0) setLastRun(new Date());
      })
      .catch((requestError) => setError(getErrorMessage(requestError)));
  }, []);

  async function analyze() {
    setBusy(true);
    setError(null);
    try {
      await runDbaAnalysis();
      const [tableProfiles, recommendationList] = await Promise.all([getDbaTables(), getDbaRecommendations()]);
      setTables(tableProfiles);
      setRecommendations(recommendationList);
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
            Analizadas {tables.length} tablas · {recommendations.length} acciones sugeridas · {updatedText}
          </p>
        </div>
        <button className="primary" onClick={() => void analyze()} disabled={busy}>
          <Sparkles size={16} aria-hidden="true" />
          Ejecutar Nuevo Análisis
        </button>
      </div>

      <ErrorNotice error={error} />

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
