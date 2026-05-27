import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  Code2,
  Database,
  ExternalLink,
  History,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Table2,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  getGoldRequestHistory,
  getGoldRequestStatus,
  getFactoryCatalogs,
  getFactorySchemas,
  getFactoryStatus,
  planGoldTable,
  submitGoldTable,
} from "./api";
import type {
  CatalogItem,
  FactoryStatus,
  GoldObjectType,
  GoldFactoryRequestStatus,
  GoldTablePlan,
  GoldWriteMode,
  SchemaItem,
  GoldFactorySubmitResponse,
} from "./types";
import "./dashboard-factory.css";

type Props = { onBack: () => void };

const EXAMPLE_PROMPTS = [
  "Crear una Gold de ventas mensuales por categoría para reportes ejecutivos",
  "Necesito una tabla para monitorear alertas bancarias por canal y severidad",
  "Preparar vista Gold de calidad de datos por tabla y regla fallida",
  "Crear reporte Gold con top tiendas por ventas y cantidad de transacciones",
];

const GOLD_TERMINAL_STATUSES = new Set(["SUCCESS", "ERROR", "DEMO_SUCCESS"]);

export function DashboardFactoryApp({ onBack }: Props) {
  const [status, setStatus] = useState<FactoryStatus | null>(null);
  const [catalogs, setCatalogs] = useState<CatalogItem[]>([]);
  const [schemas, setSchemas] = useState<SchemaItem[]>([]);
  const [prompt, setPrompt] = useState(EXAMPLE_PROMPTS[0]);
  const [targetCatalog, setTargetCatalog] = useState("databricks_proyectobg");
  const [targetSchema, setTargetSchema] = useState("tpcds_gold");
  const [objectType, setObjectType] = useState<GoldObjectType>("TABLE");
  const [writeMode, setWriteMode] = useState<GoldWriteMode>("OR_REPLACE");
  const [plan, setPlan] = useState<GoldTablePlan | null>(null);
  const [submitResult, setSubmitResult] = useState<GoldFactorySubmitResponse | null>(null);
  const [requestStatus, setRequestStatus] = useState<GoldFactoryRequestStatus | null>(null);
  const [goldHistory, setGoldHistory] = useState<GoldFactoryRequestStatus[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!submitResult) return;
    const requestId: number = submitResult.request_id;

    let cancelled = false;
    let timer: number | undefined;

    async function poll() {
      try {
        const next = await getGoldRequestStatus(requestId);
        if (cancelled) return;
        setRequestStatus(next);
        void loadGoldHistory(false);
        if (!GOLD_TERMINAL_STATUSES.has(next.status)) {
          timer = window.setTimeout(() => void poll(), 4000);
        }
      } catch {
        if (!cancelled) {
          timer = window.setTimeout(() => void poll(), 6000);
        }
      }
    }

    void poll();

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [submitResult?.request_id]);

  async function bootstrap() {
    try {
      const [s, cats] = await Promise.all([getFactoryStatus(), getFactoryCatalogs()]);
      setStatus(s);
      setCatalogs(cats);
      const catalogName = cats[0]?.name ?? s.catalog;
      setTargetCatalog(catalogName);
      await loadSchemas(catalogName);
    } catch {
      /* demo fallback */
    } finally {
      void loadGoldHistory(false);
    }
  }

  async function loadGoldHistory(showSpinner = true) {
    if (showSpinner) setHistoryLoading(true);
    try {
      const items = await getGoldRequestHistory(50);
      setGoldHistory(items);
    } catch {
      /* history is auxiliary; generator must remain usable */
    } finally {
      if (showSpinner) setHistoryLoading(false);
    }
  }

  async function loadSchemas(catalog: string) {
    try {
      const nextSchemas = await getFactorySchemas(catalog);
      setSchemas(nextSchemas);
      const goldSchema = nextSchemas.find((s) => s.name.toLowerCase().includes("gold"));
      setTargetSchema(goldSchema?.name ?? nextSchemas[0]?.name ?? "tpcds_gold");
    } catch {
      setSchemas([]);
    }
  }

  async function analyze() {
    if (!prompt.trim()) return;
    setLoading(true);
    setError(null);
    setPlan(null);
    setSubmitResult(null);
    setRequestStatus(null);
    try {
      const nextPlan = await planGoldTable({
        prompt,
        target_catalog: targetCatalog,
        target_schema: targetSchema,
        object_type: objectType,
        write_mode: writeMode,
        created_by: "web-user",
      });
      setPlan(nextPlan);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "No se pudo analizar la solicitud.");
    } finally {
      setLoading(false);
    }
  }

  async function submit() {
    if (!plan) return;
    setSubmitting(true);
    setError(null);
    setRequestStatus(null);
    try {
      const result = await submitGoldTable({
        prompt,
        plan,
        write_mode: writeMode,
        created_by: "web-user",
      });
      setSubmitResult(result);
      void loadGoldHistory(false);
    } catch (exc) {
      setError(errorText(exc, "No se pudo enviar a Databricks."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="df-shell">
      <header className="df-topbar">
        <button className="df-back-btn" onClick={onBack} aria-label="Volver al inicio">
          <ArrowLeft size={16} />
          Volver
        </button>

        <div className="df-topbar-center">
          <span className="df-brand-icon" aria-hidden="true">
            <Table2 size={20} />
          </span>
          <div className="df-brand-text">
            <span className="df-brand-eyebrow">Application 03</span>
            <strong className="df-brand-title">AI Gold Factory</strong>
          </div>
        </div>

        <div className="df-topbar-right">
          {status && (
            <span className={`df-status-chip ${status.databricks_configured ? "df-chip-live" : "df-chip-warn"}`}>
              {status.databricks_configured ? "Databricks live" : "Demo mode"}
            </span>
          )}
          <button className="df-icon-btn" onClick={() => void bootstrap()} aria-label="Actualizar">
            <RefreshCw size={15} />
          </button>
        </div>
      </header>

      <main className="df-content">
        <div className="df-generator-layout">
          <section className="df-form-panel">
            <div className="df-form-group">
              <label className="df-label" htmlFor="gold-prompt">Necesidad de negocio</label>
              <textarea
                id="gold-prompt"
                className="df-textarea"
                rows={6}
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
              />
            </div>

            <div className="df-examples">
              <span className="df-examples-label">Prompts rápidos</span>
              <div className="df-examples-grid">
                {EXAMPLE_PROMPTS.map((example) => (
                  <button key={example} className="df-example-chip" onClick={() => setPrompt(example)}>
                    {example}
                  </button>
                ))}
              </div>
            </div>

            <div className="df-config-grid">
              <div className="df-form-group">
                <label className="df-label" htmlFor="target-catalog">Catálogo destino</label>
                <select
                  id="target-catalog"
                  className="df-select"
                  value={targetCatalog}
                  onChange={(event) => {
                    setTargetCatalog(event.target.value);
                    void loadSchemas(event.target.value);
                  }}
                >
                  {catalogs.length > 0
                    ? catalogs.map((catalog) => <option key={catalog.name} value={catalog.name}>{catalog.name}</option>)
                    : <option value={targetCatalog}>{targetCatalog}</option>}
                </select>
              </div>

              <div className="df-form-group">
                <label className="df-label" htmlFor="target-schema">Schema Gold</label>
                <select
                  id="target-schema"
                  className="df-select"
                  value={targetSchema}
                  onChange={(event) => setTargetSchema(event.target.value)}
                >
                  {schemas.length > 0
                    ? schemas.map((schema) => <option key={schema.name} value={schema.name}>{schema.name}</option>)
                    : <option value={targetSchema}>{targetSchema}</option>}
                </select>
              </div>

              <div className="df-action-row">
                <button
                  className={`df-btn ${objectType === "TABLE" ? "df-btn-primary" : "df-btn-secondary"}`}
                  onClick={() => setObjectType("TABLE")}
                >
                  <Database size={15} />
                  Tabla
                </button>
                <button
                  className={`df-btn ${objectType === "VIEW" ? "df-btn-primary" : "df-btn-secondary"}`}
                  onClick={() => setObjectType("VIEW")}
                >
                  <Search size={15} />
                  Vista
                </button>
              </div>

              <div className="df-form-group">
                <label className="df-label" htmlFor="write-mode">Modo escritura</label>
                <select
                  id="write-mode"
                  className="df-select"
                  value={writeMode}
                  onChange={(event) => setWriteMode(event.target.value as GoldWriteMode)}
                >
                  <option value="OR_REPLACE">CREATE OR REPLACE</option>
                  <option value="IF_NOT_EXISTS">CREATE IF NOT EXISTS</option>
                </select>
              </div>
            </div>

            <button className="df-btn df-btn-primary df-btn-full" onClick={() => void analyze()} disabled={loading || !prompt.trim()}>
              {loading ? <Loader2 size={15} className="df-spin" /> : <ClipboardCheck size={15} />}
              {loading ? "Analizando catálogo..." : "Analizar con IA"}
            </button>
          </section>

          <section className="df-output-panel">
            {error && (
              <div className="df-notice df-notice-error">
                <AlertCircle size={16} />
                <span>{error}</span>
              </div>
            )}

            {loading && (
              <div className="df-output-loading">
                <Loader2 size={28} className="df-spin" />
                <p>Revisando tablas Databricks, columnas y SQL candidato...</p>
              </div>
            )}

            {!loading && !plan && !error && (
              <div className="df-output-empty">
                <Table2 size={40} aria-hidden="true" />
                <strong>La propuesta Gold aparecerá aquí</strong>
                <p>El flujo examina el catálogo, genera solo SELECT, valida y prepara la solicitud para `dataops_requests`.</p>
              </div>
            )}

            {plan && !loading && (
              <div className="df-plan-result">
                <div className="df-plan-header">
                  {plan.validation_status === "APPROVED" ? (
                    <CheckCircle2 size={18} className="df-plan-ok-icon" />
                  ) : (
                    <AlertCircle size={18} className="df-viewer-icon" />
                  )}
                  <div>
                    <strong className="df-plan-title">
                      {plan.target_catalog}.{plan.target_schema}.{plan.target_name}
                    </strong>
                    <span className="df-plan-meta">
                      {plan.object_type} · {plan.decision} · confianza {Math.round(plan.confidence * 100)}%
                    </span>
                  </div>
                </div>

                <p className="df-plan-desc">{plan.explanation}</p>

                <div className="df-intent-grid">
                  <IntentGroup label="Fuentes" items={plan.source_tables} tone="blue" />
                  <IntentGroup label="Validación" items={plan.validation_messages} tone={plan.validation_status === "APPROVED" ? "green" : "orange"} />
                  <IntentGroup label="Dry-run" items={[plan.dry_run_ok ? "OK en Databricks" : "Pendiente o no configurado"]} tone="purple" />
                </div>

                <div className="df-plan-queries">
                  <span className="df-plan-queries-label"><Code2 size={13} /> SELECT fuente</span>
                  <pre className="df-code-block">{plan.source_sql}</pre>
                  <span className="df-plan-queries-label"><Database size={13} /> SQL materializado por Job</span>
                  <pre className="df-code-block">{plan.generated_sql}</pre>
                </div>

                <button
                  className="df-btn df-btn-primary df-btn-full"
                  onClick={() => void submit()}
                  disabled={submitting || plan.validation_status !== "APPROVED"}
                >
                  {submitting ? <Loader2 size={15} className="df-spin" /> : <Play size={15} />}
                  {submitting ? "Enviando a Databricks..." : "Registrar y ejecutar Job"}
                </button>

                {submitResult && (
                  <RequestStatusCard submitResult={submitResult} requestStatus={requestStatus} />
                )}
              </div>
            )}
          </section>
        </div>

        <GoldHistoryPanel
          history={goldHistory}
          loading={historyLoading}
          onRefresh={() => void loadGoldHistory(true)}
          onSelect={(item) => {
            setRequestStatus(item);
            setSubmitResult({
              request_id: item.request_id,
              status: item.status,
              databricks_job_id: item.databricks_job_id,
              databricks_run_id: item.databricks_run_id,
              databricks_run_url: item.databricks_run_url,
              target_table: item.target_table,
              message: item.error_message ?? "Solicitud recuperada desde historial.",
            });
          }}
        />
      </main>
    </div>
  );
}

function RequestStatusCard({
  submitResult,
  requestStatus,
}: {
  submitResult: GoldFactorySubmitResponse;
  requestStatus: GoldFactoryRequestStatus | null;
}) {
  const currentStatus = requestStatus?.status ?? submitResult.status;
  const isDemo = currentStatus === "DEMO_SUCCESS";
  const isSuccess = currentStatus === "SUCCESS" || isDemo;
  const isError = currentStatus === "ERROR";
  const cardClass = isSuccess
    ? "df-result-card df-result-success"
    : isError
      ? "df-result-card df-result-error"
      : "df-result-card df-result-pending";
  const title = isSuccess
    ? `Tabla creada: ${requestStatus?.target_table ?? submitResult.target_table}`
    : isError
      ? `Solicitud ${submitResult.request_id} falló`
      : `Solicitud ${submitResult.request_id} en ejecución`;

  return (
    <div className={cardClass}>
      <div className="df-result-head">
        {isSuccess ? <CheckCircle2 size={18} /> : isError ? <AlertCircle size={18} /> : <Loader2 size={18} className="df-spin" />}
        <strong>{title}</strong>
      </div>
      <p className="df-result-msg">
        {isSuccess
          ? isDemo
            ? "Solicitud guardada en modo demo dentro del historial persistente."
            : "Databricks materializó la tabla Gold y actualizó dataops_requests."
          : isError
            ? requestStatus?.error_message ?? "Databricks reportó un error en la solicitud."
            : submitResult.message}
      </p>
      <div className="df-result-meta">
        <span><strong>Estado:</strong> {currentStatus}</span>
        <span><strong>Destino:</strong> {requestStatus?.target_table ?? submitResult.target_table}</span>
        {(requestStatus?.databricks_job_id ?? submitResult.databricks_job_id) && (
          <span><strong>Job:</strong> {requestStatus?.databricks_job_id ?? submitResult.databricks_job_id}</span>
        )}
        {requestStatus?.row_count !== null && requestStatus?.row_count !== undefined && (
          <span><strong>Filas:</strong> {requestStatus.row_count.toLocaleString("es-EC")}</span>
        )}
        {(requestStatus?.databricks_run_id ?? submitResult.databricks_run_id) && (
          <span><strong>Run:</strong> {requestStatus?.databricks_run_id ?? submitResult.databricks_run_id}</span>
        )}
        {requestStatus?.created_at && <span><strong>Solicitud:</strong> {formatDate(requestStatus.created_at)}</span>}
        {requestStatus?.finished_at && <span><strong>Fin:</strong> {formatDate(requestStatus.finished_at)}</span>}
      </div>
      {requestStatus?.sync_error && <p className="df-result-msg">{requestStatus.sync_error}</p>}
      {(requestStatus?.databricks_run_url ?? submitResult.databricks_run_url) && (
        <a className="df-link-btn df-link-sm" href={requestStatus?.databricks_run_url ?? submitResult.databricks_run_url ?? ""} target="_blank" rel="noreferrer">
          <ExternalLink size={14} />
          Ver ejecución Databricks
        </a>
      )}
      {requestStatus?.generated_sql && (
        <pre className="df-code-block df-code-compact">{requestStatus.generated_sql}</pre>
      )}
    </div>
  );
}

function GoldHistoryPanel({
  history,
  loading,
  onRefresh,
  onSelect,
}: {
  history: GoldFactoryRequestStatus[];
  loading: boolean;
  onRefresh: () => void;
  onSelect: (item: GoldFactoryRequestStatus) => void;
}) {
  return (
    <section className="df-gold-history-panel">
      <div className="df-gold-history-head">
        <div>
          <span className="df-intent-label">Auditoría de materialización</span>
          <strong><History size={17} /> Historial Gold por Job</strong>
        </div>
        <button className="df-btn df-btn-secondary df-btn-sm" onClick={onRefresh} disabled={loading}>
          {loading ? <Loader2 size={14} className="df-spin" /> : <RefreshCw size={14} />}
          Actualizar
        </button>
      </div>

      {history.length === 0 ? (
        <div className="df-gold-history-empty">Aún no hay solicitudes Gold registradas.</div>
      ) : (
        <div className="df-gold-history-list">
          {history.map((item) => (
            <div
              className="df-gold-history-item"
              key={item.request_id}
              role="button"
              tabIndex={0}
              onClick={() => onSelect(item)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(item);
                }
              }}
            >
              <div className="df-gold-history-main">
                <span className={`df-gold-status df-gold-status-${statusTone(item.status)}`}>
                  {item.status}
                </span>
                <strong>{item.target_table}</strong>
                <p>{item.prompt || "Solicitud Gold importada sin prompt disponible."}</p>
              </div>
              <div className="df-gold-history-meta">
                <span>Request {item.request_id}</span>
                <span>Job {item.databricks_job_id || "sin job"}</span>
                <span>Run {item.databricks_run_id || "pendiente"}</span>
                <span>{item.created_at ? formatDate(item.created_at) : "sin fecha"}</span>
                {item.row_count !== null && item.row_count !== undefined && (
                  <span>{item.row_count.toLocaleString("es-EC")} filas</span>
                )}
              </div>
              {item.databricks_run_url && (
                <a className="df-gold-history-link" href={item.databricks_run_url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                  <ExternalLink size={14} />
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function IntentGroup({
  label,
  items,
  tone,
}: {
  label: string;
  items: string[];
  tone: "blue" | "green" | "purple" | "orange";
}) {
  return (
    <div className="df-intent-group">
      <span className="df-intent-label">{label}</span>
      <div className="df-intent-chips">
        {items.map((item) => (
          <span key={item} className={`df-intent-chip df-intent-${tone}`}>
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function statusTone(status: string) {
  if (status === "SUCCESS" || status === "DEMO_SUCCESS") return "success";
  if (status === "ERROR") return "error";
  return "running";
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("es-EC", { dateStyle: "medium", timeStyle: "short" });
}

function errorText(exc: unknown, fallback: string) {
  if (!(exc instanceof Error)) return fallback;
  if (exc.message === "Failed to fetch") {
    return "No se pudo conectar con el backend. Refresca el historial para reconciliar la solicitud si Databricks alcanzó a ejecutarla.";
  }
  return exc.message || fallback;
}
