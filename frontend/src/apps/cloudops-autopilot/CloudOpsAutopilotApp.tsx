import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clipboard,
  Cloud,
  Code2,
  Container,
  Database,
  ExternalLink,
  FileCode2,
  GitBranch,
  KeyRound,
  Loader2,
  RefreshCw,
  Rocket,
  Server,
  ShieldCheck,
  TerminalSquare,
  TriangleAlert,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

import { getCloudOpsOverview } from "./api";
import type {
  CloudOpsArtifactStatus,
  CloudOpsAzureResource,
  CloudOpsGeneratedApp,
  CloudOpsOverview,
  CloudOpsPlanStep,
  CloudOpsToolStatus,
} from "./types";
import "./cloudops-autopilot.css";

type Props = { onBack: () => void };

export function CloudOpsAutopilotApp({ onBack }: Props) {
  const [overview, setOverview] = useState<CloudOpsOverview | null>(null);
  const [selectedAppId, setSelectedAppId] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(appId = selectedAppId, quiet = false) {
    if (quiet) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const payload = await getCloudOpsOverview(appId);
      setOverview(payload);
      setSelectedAppId(payload.selected_app?.id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "CloudOps Autopilot no respondio.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void load(undefined, false);
  }, []);

  const selected = overview?.selected_app ?? null;
  const readyApps = useMemo(() => overview?.apps.filter((app) => app.status === "ready").length ?? 0, [overview]);
  const failedContainerApps = useMemo(
    () => overview?.azure.container_apps.filter((resource) => resource.status?.toLowerCase() === "failed").length ?? 0,
    [overview],
  );

  if (loading) {
    return (
      <main className="co-shell co-centered">
        <Loader2 className="co-spin" size={34} aria-hidden="true" />
        <p>Cargando consola CloudOps...</p>
      </main>
    );
  }

  if (!overview) {
    return (
      <main className="co-shell co-centered">
        <TriangleAlert size={34} aria-hidden="true" />
        <h1>CloudOps Autopilot no disponible</h1>
        <p>{error ?? "Revisa el backend FastAPI."}</p>
        <button className="co-btn co-btn-primary" onClick={() => void load(undefined, false)}>
          <RefreshCw size={16} aria-hidden="true" />
          Reintentar
        </button>
      </main>
    );
  }

  return (
    <div className="co-shell">
      <header className="co-topbar">
        <button className="co-back-btn" onClick={onBack} aria-label="Volver al inicio">
          <ArrowLeft size={16} aria-hidden="true" />
          Volver
        </button>
        <div className="co-brand">
          <span className="co-brand-icon">
            <Cloud size={20} aria-hidden="true" />
          </span>
          <div>
            <span>Application 05</span>
            <strong>CloudOps Autopilot Azure</strong>
          </div>
        </div>
        <div className="co-topbar-actions">
          <StatusPill status={overview.azure.authenticated ? "ready" : "blocked"} label={overview.azure.authenticated ? "Azure conectado" : "Azure pendiente"} />
          <button className="co-icon-btn" onClick={() => void load(selectedAppId, true)} aria-label="Actualizar">
            <RefreshCw className={refreshing ? "co-spin" : ""} size={15} aria-hidden="true" />
          </button>
        </div>
      </header>

      <main className="co-content">
        <section className="co-hero">
          <div>
            <p className="co-eyebrow">Factory to CloudOps</p>
            <h1>Operar y desplegar apps generadas en Azure</h1>
          </div>
          <div className="co-hero-actions">
            <button className="co-btn co-btn-secondary" onClick={() => void copyText(`cd "${selected?.path ?? overview.generated_root}"`)}>
              <Clipboard size={16} aria-hidden="true" />
              Copiar ruta
            </button>
            <button className="co-btn co-btn-primary" onClick={() => void copyText(deployCommand(selected))} disabled={!selected}>
              <TerminalSquare size={16} aria-hidden="true" />
              Copiar deploy
            </button>
          </div>
        </section>

        {error && (
          <div className="co-notice co-notice-error">
            <AlertCircle size={16} aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        <section className="co-metrics">
          <MetricTile icon={<Code2 size={20} />} label="Apps generadas" value={overview.apps.length} tone="blue" />
          <MetricTile icon={<CheckCircle2 size={20} />} label="Listas" value={readyApps} tone="green" />
          <MetricTile icon={<Container size={20} />} label="Container Apps" value={overview.azure.container_apps.length} tone="cyan" />
          <MetricTile icon={<TriangleAlert size={20} />} label="Fallidas" value={failedContainerApps} tone={failedContainerApps ? "amber" : "green"} />
          <MetricTile icon={<ShieldCheck size={20} />} label="Readiness" value={`${overview.plan.readiness_score}%`} tone={overview.plan.readiness_score >= 90 ? "green" : "amber"} />
        </section>

        <section className="co-layout">
          <aside className="co-panel co-app-list-panel">
            <div className="co-panel-head">
              <div>
                <span className="co-eyebrow">Application 04 output</span>
                <h2>Apps disponibles</h2>
              </div>
              <span>{overview.apps.length}</span>
            </div>
            <div className="co-app-list">
              {overview.apps.map((app) => (
                <button
                  className={`co-app-card${selected?.id === app.id ? " active" : ""}`}
                  key={app.id}
                  onClick={() => void load(app.id, true)}
                >
                  <span className="co-score" style={{ "--score": `${app.readiness_score}%` } as CSSProperties}>
                    <b>{app.readiness_score}</b>
                  </span>
                  <span className="co-app-card-body">
                    <strong>{app.name}</strong>
                    <small>{app.slug}</small>
                    <span className="co-card-meta">{formatDate(app.updated_at)} · {app.artifacts.filter((item) => item.present).length}/{app.artifacts.length} artefactos</span>
                  </span>
                  <StatusPill status={app.status === "ready" ? "ready" : app.status === "partial" ? "warning" : "blocked"} label={app.status} />
                </button>
              ))}
              {overview.apps.length === 0 && (
                <div className="co-empty-list">
                  <FileCode2 size={28} aria-hidden="true" />
                  <strong>Sin apps generadas</strong>
                  <span>{overview.generated_root}</span>
                </div>
              )}
            </div>
          </aside>

          <section className="co-main-stack">
            <div className="co-panel co-selected-panel">
              <div className="co-selected-head">
                <div>
                  <span className="co-eyebrow">Deployment candidate</span>
                  <h2>{selected?.name ?? "Selecciona una app"}</h2>
                  <p>{overview.plan.summary}</p>
                </div>
                <div className="co-selected-actions">
                  {selected?.github_url && (
                    <a href={selected.github_url} target="_blank" rel="noreferrer">
                      <GitBranch size={15} aria-hidden="true" />
                      GitHub
                    </a>
                  )}
                  {selected?.azure_links.slice(0, 2).map((link) => (
                    <a href={link} target="_blank" rel="noreferrer" key={link}>
                      <ExternalLink size={15} aria-hidden="true" />
                      Azure
                    </a>
                  ))}
                </div>
              </div>

              <div className="co-path-strip">
                <FileCode2 size={16} aria-hidden="true" />
                <span>{selected?.path ?? overview.generated_root}</span>
              </div>

              <div className="co-command">
                <div>
                  <strong>Comando operativo</strong>
                  <span>deploy-azure.ps1</span>
                </div>
                <code>{deployCommand(selected)}</code>
              </div>
            </div>

            <div className="co-panel">
              <div className="co-panel-head">
                <div>
                  <span className="co-eyebrow">Pipeline timeline</span>
                  <h2>Plan de despliegue y operacion</h2>
                </div>
                <Rocket size={20} aria-hidden="true" />
              </div>
              <div className="co-timeline">
                {overview.plan.steps.map((step) => (
                  <TimelineStep step={step} key={`${step.stage}-${step.name}`} />
                ))}
              </div>
            </div>

            <div className="co-two-col">
              <ArtifactPanel artifacts={selected?.artifacts ?? []} />
              <RequiredInputs inputs={overview.plan.required_inputs} />
            </div>
          </section>

          <aside className="co-side-stack">
            <AzureAccount overview={overview} />
            <ResourcePanel title="Recursos relacionados" resources={overview.plan.matched_azure_resources} empty="Sin recursos enlazados a esta app." />
            <ToolPanel tools={overview.tools} />
          </aside>
        </section>

        <section className="co-resource-grid">
          <ResourcePanel title="Container Apps" resources={overview.azure.container_apps} empty="No hay Container Apps visibles." />
          <ResourcePanel title="Registries" resources={overview.azure.registries} empty="No hay ACR visibles." />
          <ResourcePanel title="PostgreSQL" resources={overview.azure.postgres_servers} empty="No hay PostgreSQL Flexible Server visible." />
        </section>
      </main>
    </div>
  );
}

function MetricTile({ icon, label, value, tone }: { icon: ReactNode; label: string; value: string | number; tone: "blue" | "green" | "cyan" | "amber" }) {
  return (
    <div className={`co-metric co-tone-${tone}`}>
      <span>{icon}</span>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function TimelineStep({ step }: { step: CloudOpsPlanStep }) {
  return (
    <div className={`co-step co-step-${step.status}`}>
      <span>{step.status === "ready" ? <CheckCircle2 size={16} /> : step.status === "blocked" ? <AlertCircle size={16} /> : <RefreshCw size={16} />}</span>
      <div>
        <small>{stageLabel(step.stage)}</small>
        <strong>{step.name}</strong>
        <p>{step.detail}</p>
      </div>
      <StatusPill status={step.status} label={step.status} />
    </div>
  );
}

function ArtifactPanel({ artifacts }: { artifacts: CloudOpsArtifactStatus[] }) {
  return (
    <div className="co-panel">
      <div className="co-panel-head">
        <div>
          <span className="co-eyebrow">Readiness</span>
          <h2>Artefactos</h2>
        </div>
        <FileCode2 size={19} aria-hidden="true" />
      </div>
      <div className="co-artifact-list">
        {artifacts.map((artifact) => (
          <div className="co-artifact" key={artifact.key}>
            <span className={artifact.present ? "ok" : "missing"}>
              {artifact.present ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
            </span>
            <div>
              <strong>{artifact.label}</strong>
              <small>{artifact.path}</small>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RequiredInputs({ inputs }: { inputs: string[] }) {
  return (
    <div className="co-panel">
      <div className="co-panel-head">
        <div>
          <span className="co-eyebrow">Preflight</span>
          <h2>Configuracion pendiente</h2>
        </div>
        <KeyRound size={19} aria-hidden="true" />
      </div>
      <div className="co-input-list">
        {inputs.length ? (
          inputs.map((input) => (
            <div className="co-input-item" key={input}>
              <TriangleAlert size={15} aria-hidden="true" />
              <span>{input}</span>
            </div>
          ))
        ) : (
          <div className="co-ready-state">
            <CheckCircle2 size={18} aria-hidden="true" />
            <span>Preflight listo para despliegue controlado.</span>
          </div>
        )}
      </div>
    </div>
  );
}

function AzureAccount({ overview }: { overview: CloudOpsOverview }) {
  return (
    <div className="co-panel co-account-panel">
      <div className="co-panel-head">
        <div>
          <span className="co-eyebrow">Azure</span>
          <h2>Suscripcion</h2>
        </div>
        <Cloud size={19} aria-hidden="true" />
      </div>
      <div className="co-account-body">
        <strong>{overview.azure.subscription_name || "Sin sesion"}</strong>
        <span>{overview.azure.user || "az login pendiente"}</span>
        {overview.azure.subscription_id && <code>{overview.azure.subscription_id}</code>}
      </div>
      {overview.azure.errors.length > 0 && (
        <div className="co-azure-errors">
          {overview.azure.errors.slice(0, 2).map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function ResourcePanel({ title, resources, empty }: { title: string; resources: CloudOpsAzureResource[]; empty: string }) {
  return (
    <div className="co-panel co-resource-panel">
      <div className="co-panel-head">
        <div>
          <span className="co-eyebrow">Azure resources</span>
          <h2>{title}</h2>
        </div>
        <span>{resources.length}</span>
      </div>
      <div className="co-resource-list">
        {resources.slice(0, 8).map((resource) => (
          <div className="co-resource" key={`${title}-${resource.type}-${resource.name}-${resource.resource_group}`}>
            <span className="co-resource-icon">{resourceIcon(resource.type)}</span>
            <div>
              <strong>{resource.name}</strong>
              <small>{resource.type} · {resource.resource_group}</small>
              {resource.url && (
                <a href={resource.url} target="_blank" rel="noreferrer">
                  {resource.url}
                  <ExternalLink size={12} aria-hidden="true" />
                </a>
              )}
            </div>
            <StatusPill status={resource.status?.toLowerCase() === "failed" ? "blocked" : "ready"} label={resource.status || "found"} />
          </div>
        ))}
        {resources.length === 0 && <div className="co-empty-resource">{empty}</div>}
      </div>
    </div>
  );
}

function ToolPanel({ tools }: { tools: CloudOpsToolStatus[] }) {
  return (
    <div className="co-panel">
      <div className="co-panel-head">
        <div>
          <span className="co-eyebrow">Runtime</span>
          <h2>Herramientas</h2>
        </div>
        <Server size={19} aria-hidden="true" />
      </div>
      <div className="co-tool-list">
        {tools.map((tool) => (
          <div className="co-tool" key={tool.name}>
            <StatusPill status={tool.available ? "ready" : "blocked"} label={tool.name} />
            <span>{tool.detail}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusPill({ status, label }: { status: "ready" | "manual" | "warning" | "blocked"; label: string }) {
  return <span className={`co-pill co-pill-${status}`}>{label}</span>;
}

function stageLabel(stage: CloudOpsPlanStep["stage"]) {
  const labels: Record<CloudOpsPlanStep["stage"], string> = {
    validate: "Validar",
    provision: "Provisionar",
    build: "Build",
    release: "Release",
    observe: "Observabilidad",
    govern: "Gobierno",
  };
  return labels[stage];
}

function resourceIcon(type: string) {
  if (type.includes("PostgreSQL")) return <Database size={16} aria-hidden="true" />;
  if (type.includes("Registry")) return <Container size={16} aria-hidden="true" />;
  if (type.includes("Container App")) return <Rocket size={16} aria-hidden="true" />;
  return <Cloud size={16} aria-hidden="true" />;
}

function deployCommand(app: CloudOpsGeneratedApp | null) {
  if (!app) return "Selecciona una app generada";
  return `cd "${app.path}" && .\\scripts\\deploy-azure.ps1`;
}

function formatDate(value: string | null) {
  if (!value) return "sin fecha";
  return new Date(value).toLocaleString();
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    /* Clipboard is best effort in local demos. */
  }
}
