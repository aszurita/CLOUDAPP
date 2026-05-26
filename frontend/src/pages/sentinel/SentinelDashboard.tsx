import {
  Activity,
  AlertTriangle,
  BarChart3,
  BrainCircuit,
  Database,
  FileText,
  Gauge,
  GitBranch,
  ListChecks,
  RefreshCw,
  ShieldCheck,
  Terminal,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  CopilotResponse,
  FaultJob,
  FaultType,
  IncidentEvidence,
  ModelMetricsResponse,
  SentinelIncident,
  SentinelEngine,
  SentinelLiveMetrics,
  SentinelMetricPoint,
  SentinelPrediction,
  SentinelQuerySample,
  SentinelStatus,
  ShapResponse,
  explainSentinelCurrent,
  fetchSentinelFaults,
  fetchSentinelEngines,
  fetchSentinelFaultJob,
  fetchSentinelIncidentEvidence,
  fetchSentinelIncidents,
  fetchSentinelLiveMetrics,
  fetchSentinelMetricsHistory,
  fetchSentinelModelMetrics,
  fetchSentinelQueries,
  fetchSentinelShap,
  fetchSentinelStatus,
  predictSentinelIncident,
  resolveSentinelIncident,
  simulateSentinelFault,
  triggerSentinelCollection,
} from "../../api/sentinel";
import { FaultInjector } from "../../components/sentinel/FaultInjector";
import { IncidentCard } from "../../components/sentinel/IncidentCard";
import { MetricsTimeline } from "../../components/sentinel/MetricsTimeline";
import { RecommendationPanel } from "../../components/sentinel/RecommendationPanel";
import { RiskScoreCard } from "../../components/sentinel/RiskScoreCard";
import { RootCausePanel } from "../../components/sentinel/RootCausePanel";
import { SeverityBadge } from "../../components/sentinel/SeverityBadge";

type SentinelSection = "overview" | "incidents" | "simulate" | "evaluate";

function settledValue<T, F>(result: PromiseSettledResult<T>, fallback: F): T | F {
  return result.status === "fulfilled" ? result.value : fallback;
}

function formatNumber(value?: number | null, digits = 0) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
}

function formatPct(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${value.toFixed(2)}%`;
}

function metricFrom(group: unknown, split: string, key: string) {
  if (!group || typeof group !== "object") return "-";
  const maybeSplit = split ? (group as Record<string, unknown>)[split] : group;
  if (!maybeSplit || typeof maybeSplit !== "object") return "-";
  const value = (maybeSplit as Record<string, unknown>)[key];
  return typeof value === "number" ? value.toFixed(3) : "-";
}

function labModeLabel(value?: string | null) {
  if (value === "azure_demo") return "Azure lab";
  if (value === "local_lab") return "Local Docker";
  if (value === "not_configured") return "Sin monitor DB";
  return value ?? "-";
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function hasPredictedIncident(prediction: SentinelPrediction | null) {
  return Boolean(
    prediction &&
    (prediction.has_predicted_incident || prediction.risk_score >= 0.7) &&
    prediction.risk_score > 0
  );
}

function isRealIncident(incident: SentinelIncident) {
  return Boolean(incident.incident_type && incident.incident_type !== "none" && (incident.risk_score ?? 0) > 0);
}

export function SentinelDashboard() {
  const [section, setSection] = useState<SentinelSection>("overview");
  const [status, setStatus] = useState<SentinelStatus | null>(null);
  const [liveMetrics, setLiveMetrics] = useState<SentinelLiveMetrics | null>(null);
  const [history, setHistory] = useState<SentinelMetricPoint[]>([]);
  const [queries, setQueries] = useState<SentinelQuerySample[]>([]);
  const [prediction, setPrediction] = useState<SentinelPrediction | null>(null);
  const [incidents, setIncidents] = useState<SentinelIncident[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<SentinelIncident | null>(null);
  const [evidence, setEvidence] = useState<IncidentEvidence | null>(null);
  const [copilot, setCopilot] = useState<CopilotResponse | null>(null);
  const [modelMetrics, setModelMetrics] = useState<ModelMetricsResponse | null>(null);
  const [predictorShap, setPredictorShap] = useState<ShapResponse | null>(null);
  const [engines, setEngines] = useState<SentinelEngine[]>([]);
  const [faults, setFaults] = useState<FaultType[]>([]);
  const [faultJob, setFaultJob] = useState<FaultJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    const statusResult = await Promise.allSettled([fetchSentinelStatus()]);
    const statusValue = settledValue(statusResult[0], null);
    const databaseName = statusValue?.monitor_database_name ?? liveMetrics?.database_name ?? "core_banking_sim";
    const [
      liveResult,
      historyResult,
      queryResult,
      predictionResult,
      incidentsResult,
      modelResult,
      shapResult,
      faultsResult,
      enginesResult,
    ] = await Promise.allSettled([
      fetchSentinelLiveMetrics(),
      fetchSentinelMetricsHistory(120),
      fetchSentinelQueries(45),
      predictSentinelIncident(databaseName),
      fetchSentinelIncidents({ status: "all", limit: 12, since_hours: 24 * 30 }),
      fetchSentinelModelMetrics(),
      fetchSentinelShap("predictor", 18),
      fetchSentinelFaults(),
      fetchSentinelEngines(),
    ]);

    setStatus(statusValue);
    setLiveMetrics(settledValue(liveResult, null));
    setHistory(settledValue(historyResult, []));
    setQueries(settledValue(queryResult, []));
    const nextPrediction = settledValue(predictionResult, null);
    setPrediction(nextPrediction);
    if (!hasPredictedIncident(nextPrediction)) setCopilot(null);
    const incidentList = settledValue(incidentsResult, { incidents: [], total: 0, limit: 0, offset: 0 }).incidents
      .filter(isRealIncident);
    setIncidents(incidentList);
    setSelectedIncident((current) => {
      if (current && incidentList.some((incident) => incident.id === current.id)) return current;
      return incidentList[0] ?? null;
    });
    setModelMetrics(settledValue(modelResult, null));
    setPredictorShap(settledValue(shapResult, null));
    setFaults(settledValue(faultsResult, { faults: [] }).faults);
    setEngines(settledValue(enginesResult, { engines: [], canonical_metrics: [] }).engines);
    setLastRefresh(new Date());

    const rejected = [
      liveResult,
      historyResult,
      queryResult,
      predictionResult,
      incidentsResult,
      modelResult,
      shapResult,
      faultsResult,
      enginesResult,
      statusResult[0],
    ].find((item) => item.status === "rejected");
    if (rejected?.status === "rejected") setError("Algunos endpoints Sentinel no respondieron en este refresh.");
    setLoading(false);
  }

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!selectedIncident) {
      setEvidence(null);
      return;
    }
    fetchSentinelIncidentEvidence(selectedIncident.id)
      .then((value) => {
        if (!cancelled) setEvidence(value);
      })
      .catch(() => {
        if (!cancelled) setEvidence(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedIncident?.id]);

  async function generateCopilot() {
    if (!hasPredictedIncident(prediction)) {
      setCopilot(null);
      return;
    }
    setCopilotLoading(true);
    setError(null);
    try {
      const result = await explainSentinelCurrent({
        databaseName: status?.monitor_database_name ?? liveMetrics?.database_name ?? undefined,
        persistIncident: false,
      });
      setCopilot(result);
    } catch {
      setError("No se pudo generar el diagnóstico DBA Copilot.");
    } finally {
      setCopilotLoading(false);
    }
  }

  async function runControlledDemo(faultType: string, durationSeconds: number, intensity: string) {
    setDemoLoading(true);
    setError(null);
    try {
      const job = await simulateSentinelFault(faultType, durationSeconds, intensity, false);
      setFaultJob(job);
      let detected = false;
      for (const delay of [12_000, 15_000, 15_000, 15_000]) {
        await wait(delay);
        const latestJob = await fetchSentinelFaultJob(job.job_id).catch(() => null);
        if (latestJob) setFaultJob(latestJob);
        const collected = await triggerSentinelCollection();
        setLiveMetrics(collected.sample);
        const [nextHistory, nextQueries] = await Promise.all([
          fetchSentinelMetricsHistory(120),
          fetchSentinelQueries(45),
        ]);
        setHistory(nextHistory);
        setQueries(nextQueries);
        const databaseName = status?.monitor_database_name ?? collected.sample.database_name ?? "core_banking_sim";
        const nextPrediction = await predictSentinelIncident(databaseName);
        setPrediction(nextPrediction);
        if (hasPredictedIncident(nextPrediction)) {
          const response = await explainSentinelCurrent({ databaseName, persistIncident: true });
          setCopilot(response);
          detected = true;
          break;
        }
        setCopilot(null);
      }
      if (!detected) setError("La demo se ejecutó, pero el modelo todavía no elevó riesgo. Espera una muestra más o usa intensidad high.");
      await refresh();
    } catch {
      setError("No se pudo completar el flujo controlado del lab.");
    } finally {
      setDemoLoading(false);
    }
  }

  async function resolveSelectedIncident() {
    if (!selectedIncident) return;
    const updated = await resolveSentinelIncident(selectedIncident.id, "Validado desde dashboard Sentinel.");
    setIncidents((current) => current.map((incident) => (incident.id === updated.id ? updated : incident)));
    setSelectedIncident(updated);
  }

  const currentMetrics = prediction?.current_metrics ?? {};
  const openIncidents = incidents.filter((incident) => incident.status === "open");
  const predictionHasIncident = hasPredictedIncident(prediction);
  const healthTone = predictionHasIncident ? "critical" : "stable";
  const monitoredDatabase = status?.monitor_database_name ?? liveMetrics?.database_name ?? "core_banking_sim";

  return (
    <div className="sentinel-dashboard">
      <section className="panel sentinel-hero">
        <div>
          <p className="eyebrow">DB Sentinel AI</p>
          <h2>
            <ShieldCheck size={22} />
            PostgreSQL · {monitoredDatabase}
          </h2>
          <p className="sentinel-subtitle">
            {labModeLabel(status?.monitor_lab_mode)} · Guarda en {status?.storage_database_name ?? "cloudapp"} · Predictor {modelMetrics?.predictor.model_version ?? "1.0.0"} · RCA {modelMetrics?.rca.model_version ?? "1.0.0"}
            {lastRefresh ? ` · ${lastRefresh.toLocaleTimeString()}` : ""}
          </p>
        </div>
        <div className="sentinel-hero-actions">
          <SeverityBadge value={healthTone} />
          <button className="primary" onClick={() => void refresh()} disabled={loading}>
            <RefreshCw size={16} className={loading ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </section>

      {error && (
        <div className="notice error sentinel-notice">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      <nav className="sentinel-tabs" aria-label="Sentinel views">
        {[
          ["overview", Gauge, "Overview"],
          ["incidents", ListChecks, "Incidentes"],
          ["simulate", Terminal, "Simulation Lab"],
          ["evaluate", BarChart3, "Evaluación"],
        ].map(([key, Icon, label]) => {
          const TabIcon = Icon as typeof Gauge;
          return (
            <button key={key as string} className={section === key ? "active" : ""} onClick={() => setSection(key as SentinelSection)}>
              <TabIcon size={16} />
              {label as string}
            </button>
          );
        })}
      </nav>

      <SentinelStatusPanel status={status} />

      {section === "overview" && (
        <OverviewSection
          liveMetrics={liveMetrics}
          currentMetrics={currentMetrics}
          history={history}
          prediction={prediction}
          predictionHasIncident={predictionHasIncident}
          queries={queries}
          openIncidents={openIncidents}
          copilot={copilot}
          copilotLoading={copilotLoading}
          onGenerateCopilot={generateCopilot}
          onSelectIncident={(incident) => {
            setSelectedIncident(incident);
            setSection("incidents");
          }}
        />
      )}

      {section === "incidents" && (
        <IncidentsSection
          incidents={incidents}
          selectedIncident={selectedIncident}
          evidence={evidence}
          onSelectIncident={setSelectedIncident}
          onResolve={() => void resolveSelectedIncident()}
        />
      )}

      {section === "simulate" && (
        <SimulationSection
          faults={faults}
          job={faultJob}
          demoLoading={demoLoading}
          onJob={setFaultJob}
          onDemoRun={runControlledDemo}
        />
      )}

      {section === "evaluate" && (
        <EvaluationSection metrics={modelMetrics} shap={predictorShap} engines={engines} />
      )}
    </div>
  );
}

function SentinelStatusPanel({ status }: { status: SentinelStatus | null }) {
  const modelStatus = status?.predictor.loaded && status.rca.loaded ? "loaded" : "attention";
  const collectorStatus = status?.auto_collect_enabled ? (status.collector_running ? "running" : "configured") : "manual";
  const lastCollected = status?.last_collected_at ? new Date(status.last_collected_at).toLocaleString() : "-";

  return (
    <section className="sentinel-status-grid">
      <div className="panel sentinel-status-card">
        <div>
          <span>Base monitoreada</span>
          <strong>{status?.monitor_database_name ?? "-"}</strong>
          <small>{labModeLabel(status?.monitor_lab_mode)}</small>
        </div>
        <SeverityBadge value={status?.monitor_database_configured ? "low" : "medium"} />
      </div>
      <div className="panel sentinel-status-card">
        <div>
          <span>Recolector</span>
          <strong>{collectorStatus}</strong>
          <small>{status?.collector_interval_seconds ?? "-"}s · {lastCollected}</small>
        </div>
        <SeverityBadge value={status?.collector_running ? "stable" : "medium"} />
      </div>
      <div className="panel sentinel-status-card">
        <div>
          <span>Muestras</span>
          <strong>{formatNumber(status?.total_samples ?? 0)}</strong>
          <small>{formatNumber(status?.query_samples ?? 0)} query samples</small>
        </div>
        <SeverityBadge value={(status?.total_samples ?? 0) > 0 ? "stable" : "medium"} />
      </div>
      <div className="panel sentinel-status-card">
        <div>
          <span>Modelos ML</span>
          <strong>{modelStatus}</strong>
          <small>Predictor {status?.predictor.feature_count ?? "-"} · RCA {status?.rca.feature_count ?? "-"}</small>
        </div>
        <SeverityBadge value={modelStatus === "loaded" ? "stable" : "medium"} />
      </div>
    </section>
  );
}

function OverviewSection({
  liveMetrics,
  currentMetrics,
  history,
  prediction,
  predictionHasIncident,
  queries,
  openIncidents,
  copilot,
  copilotLoading,
  onGenerateCopilot,
  onSelectIncident,
}: {
  liveMetrics: SentinelLiveMetrics | null;
  currentMetrics: Record<string, number>;
  history: SentinelMetricPoint[];
  prediction: SentinelPrediction | null;
  predictionHasIncident: boolean;
  queries: SentinelQuerySample[];
  openIncidents: SentinelIncident[];
  copilot: CopilotResponse | null;
  copilotLoading: boolean;
  onGenerateCopilot: () => void;
  onSelectIncident: (incident: SentinelIncident) => void;
}) {
  const cards = [
    { label: "Sesiones activas", value: formatNumber(liveMetrics?.active_sessions ?? currentMetrics.active_sessions), icon: Activity },
    { label: "Lock waits", value: formatNumber(liveMetrics?.lock_waiting_sessions ?? currentMetrics.lock_waiting_sessions), icon: AlertTriangle },
    { label: "Cache hit", value: formatPct(liveMetrics?.cache_hit_ratio ?? currentMetrics.cache_hit_ratio), icon: Database },
    { label: "WAL bytes", value: formatNumber(liveMetrics?.wal_bytes_delta ?? currentMetrics.wal_bytes_delta), icon: Zap },
    { label: "Replica lag", value: `${formatNumber(liveMetrics?.replication_lag_seconds ?? currentMetrics.replication_lag_seconds, 1)}s`, icon: GitBranch },
  ];

  return (
    <>
      <section className="metrics-grid sentinel-metrics">
        {cards.map(({ label, value, icon: Icon }) => (
          <div className="metric" key={label}>
            <div className="metric-icon"><Icon size={20} /></div>
            <div>
              <p>{label}</p>
              <strong>{value}</strong>
            </div>
          </div>
        ))}
      </section>

      <section className="sentinel-overview-grid">
        <RiskScoreCard prediction={prediction} />
        <MetricsTimeline points={history} />
      </section>

      <section className="sentinel-main-grid">
        <RootCausePanel causes={prediction?.rca_top_causes ?? []} active={predictionHasIncident} />
        <RecommendationPanel copilot={copilot} loading={copilotLoading} active={predictionHasIncident} onGenerate={onGenerateCopilot} />
      </section>

      <section className="sentinel-main-grid">
        <div className="panel">
          <div className="panel-heading">
            <h2>Incidentes abiertos</h2>
            <span>{openIncidents.length}</span>
          </div>
          <div className="sentinel-card-list">
            {openIncidents.length === 0 && <p className="sentinel-muted">No hay incidentes reales abiertos.</p>}
            {openIncidents.slice(0, 5).map((incident) => (
              <IncidentCard key={incident.id} incident={incident} onSelect={onSelectIncident} />
            ))}
          </div>
        </div>

        <QueryFingerprintTable queries={queries} />
      </section>
    </>
  );
}

function QueryFingerprintTable({ queries }: { queries: SentinelQuerySample[] }) {
  return (
    <div className="panel sentinel-query-panel">
      <div className="panel-heading">
        <h2>Query fingerprints recientes</h2>
        <span>{queries.length}</span>
      </div>
      <div className="sentinel-query-table">
        <div className="sentinel-query-row header">
          <span>Query</span>
          <span>Mean ms</span>
          <span>Calls Δ</span>
          <span>WAL Δ</span>
        </div>
        {queries.slice(0, 8).map((query, index) => (
          <div className="sentinel-query-row" key={`${query.queryid ?? index}-${index}`}>
            <span>{query.query_fingerprint ?? "query unavailable"}</span>
            <span>{formatNumber(query.mean_exec_time, 2)}</span>
            <span>{formatNumber(query.calls_delta)}</span>
            <span>{formatNumber(query.wal_bytes_delta)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function IncidentsSection({
  incidents,
  selectedIncident,
  evidence,
  onSelectIncident,
  onResolve,
}: {
  incidents: SentinelIncident[];
  selectedIncident: SentinelIncident | null;
  evidence: IncidentEvidence | null;
  onSelectIncident: (incident: SentinelIncident) => void;
  onResolve: () => void;
}) {
  return (
    <section className="sentinel-incident-layout">
      <aside className="panel sentinel-incident-list-panel">
        <div className="panel-heading">
          <h2>Incidentes</h2>
          <span>{incidents.length}</span>
        </div>
        <div className="sentinel-card-list">
          {incidents.length === 0 && <p className="sentinel-muted">Sin incidentes reales registrados.</p>}
          {incidents.map((incident) => (
            <IncidentCard
              key={incident.id}
              incident={incident}
              active={selectedIncident?.id === incident.id}
              onSelect={onSelectIncident}
            />
          ))}
        </div>
      </aside>

      <div className="sentinel-incident-detail">
        {!selectedIncident && (
          <section className="panel sentinel-empty-state">
            <FileText size={26} />
            <p>Selecciona un incidente real.</p>
          </section>
        )}
        {selectedIncident && (
          <>
            <section className="panel sentinel-detail-head">
              <div>
                <p className="eyebrow">Incidente #{selectedIncident.id}</p>
                <h2>{(selectedIncident.incident_type ?? "unknown").replace(/_/g, " ")}</h2>
                <p>{selectedIncident.database_name ?? "core_banking_sim"} · {new Date(selectedIncident.detected_at).toLocaleString()}</p>
              </div>
              <div className="sentinel-detail-actions">
                <SeverityBadge value={selectedIncident.impact_level} />
                {selectedIncident.status === "open" && (
                  <button className="primary" onClick={onResolve}>
                    <ShieldCheck size={16} />
                    Resolver
                  </button>
                )}
              </div>
            </section>
            <RootCausePanel causes={selectedIncident.root_cause_top3 ?? evidence?.root_cause_top3 ?? []} active title="RCA del incidente" />
            <MetricsTimeline points={evidence?.metrics_timeline ?? []} />
            <QueryFingerprintTable queries={evidence?.slow_queries ?? []} />
          </>
        )}
      </div>
    </section>
  );
}

function SimulationSection({
  faults,
  job,
  demoLoading,
  onJob,
  onDemoRun,
}: {
  faults: FaultType[];
  job: FaultJob | null;
  demoLoading: boolean;
  onJob: (job: FaultJob) => void;
  onDemoRun: (faultType: string, durationSeconds: number, intensity: string) => Promise<void>;
}) {
  return (
    <section className="sentinel-main-grid">
      <FaultInjector faults={faults} onJob={onJob} onDemoRun={onDemoRun} />
      <div className="panel sentinel-job-panel">
        <div className="panel-heading">
          <h2>Último flujo</h2>
          {job && <SeverityBadge value={job.status} />}
        </div>
        {!job && <p className="sentinel-muted">Sin simulación preparada.</p>}
        {demoLoading && <p className="sentinel-muted">Recolectando métricas, prediciendo riesgo y preparando diagnóstico.</p>}
        {job && (
          <div className="sentinel-job-body">
            <strong>{job.fault_type.replace(/_/g, " ")}</strong>
            <ul>
              {job.plan.map((item) => <li key={item}>{item}</li>)}
            </ul>
            {job.processes && job.processes.length > 0 && (
              <div className="sentinel-process-list">
                {job.processes.map((process) => (
                  <span key={`${process.name}-${process.pid}`}>{process.name} · PID {process.pid}</span>
                ))}
              </div>
            )}
            {job.error && <p className="sentinel-muted">{job.error}</p>}
            {job.command && <pre>{job.command}</pre>}
          </div>
        )}
      </div>
    </section>
  );
}

function EvaluationSection({
  metrics,
  shap,
  engines,
}: {
  metrics: ModelMetricsResponse | null;
  shap: ShapResponse | null;
  engines: SentinelEngine[];
}) {
  const topFeatures = useMemo(() => shap?.top_features ?? [], [shap]);
  const maxImportance = Math.max(0.0001, ...topFeatures.map((feature) => feature.importance));

  return (
    <section className="sentinel-eval-grid">
      <div className="panel sentinel-model-panel">
        <div className="panel-heading">
          <h2>Predictor</h2>
          <BrainCircuit size={18} />
        </div>
        <div className="sentinel-model-stats">
          <MetricPill label="Features" value={metrics?.predictor.feature_count ?? 0} />
          <MetricPill label="Threshold" value={metrics?.predictor.threshold ?? "-"} />
          <MetricPill label="Test recall" value={metricFrom(metrics?.predictor.binary, "test", "recall")} />
          <MetricPill label="Test F1" value={metricFrom(metrics?.predictor.binary, "test", "f1")} />
        </div>
      </div>

      <div className="panel sentinel-model-panel">
        <div className="panel-heading">
          <h2>RCA</h2>
          <GitBranch size={18} />
        </div>
        <div className="sentinel-model-stats">
          <MetricPill label="Features" value={metrics?.rca.feature_count ?? 0} />
          <MetricPill label="Modelo" value={metrics?.rca.selected_model ?? "rca"} />
          <MetricPill label="Top@1" value={metricFrom(metrics?.rca.test, "", "top1")} />
          <MetricPill label="Macro F1" value={metricFrom(metrics?.rca.test, "", "macro_f1")} />
        </div>
      </div>

      <div className="panel sentinel-feature-panel">
        <div className="panel-heading">
          <h2>Feature importance</h2>
          <span>{shap?.explainability_method ?? "model"}</span>
        </div>
        <div className="sentinel-feature-bars">
          {topFeatures.map((feature) => (
            <div className="sentinel-feature-row" key={feature.feature}>
              <span>{feature.feature}</span>
              <div><i style={{ width: `${Math.max(3, (feature.importance / maxImportance) * 100)}%` }} /></div>
              <em>{feature.importance.toFixed(3)}</em>
            </div>
          ))}
        </div>
      </div>

      <div className="panel sentinel-feature-panel">
        <div className="panel-heading">
          <h2>Motores soportados</h2>
          <span>{engines.length}</span>
        </div>
        <div className="sentinel-engine-grid">
          {engines.map((engine) => (
            <article className="sentinel-engine-card" key={engine.id}>
              <div>
                <strong>{engine.id}</strong>
                <SeverityBadge value={engine.status} />
              </div>
              <p>{engine.collector}</p>
              <span>{engine.canonical_metric_count} métricas canónicas · {engine.supported_incidents.length} incidentes mapeados</span>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function MetricPill({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="sentinel-metric-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
