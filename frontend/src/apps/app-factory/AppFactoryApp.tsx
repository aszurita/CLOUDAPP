import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clipboard,
  Cloud,
  Code2,
  Database,
  ExternalLink,
  FileCode2,
  GitBranch,
  Hammer,
  Loader2,
  PackagePlus,
  RefreshCw,
  Rocket,
  Server,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { generateCloudApp, getAppFactoryStatus, planCloudApp } from "./api";
import type {
  AppFactoryArtifact,
  AppFactoryGenerateResponse,
  AppFactoryLink,
  AppFactoryPlan,
  AppFactoryStatus,
  AppFactoryStep,
} from "./types";
import "./app-factory.css";

type Props = { onBack: () => void };

const EXAMPLE_PROMPTS = [
  "Crea una app de inventario con clientes, productos y ordenes de compra",
  "Necesito una aplicacion para gestionar proveedores, productos y compras",
  "Crear una app CRUD de clientes con React, FastAPI, PostgreSQL y despliegue Azure",
];

export function AppFactoryApp({ onBack }: Props) {
  const [status, setStatus] = useState<AppFactoryStatus | null>(null);
  const [prompt, setPrompt] = useState(EXAMPLE_PROMPTS[0]);
  const [projectName, setProjectName] = useState("inventory-cloud-app");
  const [auth, setAuth] = useState<"JWT demo" | "Sin auth">("JWT demo");
  const [initializeGit, setInitializeGit] = useState(true);
  const [publishGithub, setPublishGithub] = useState(false);
  const [githubPrivate, setGithubPrivate] = useState(true);
  const [githubToken, setGithubToken] = useState("");
  const [deployAzure, setDeployAzure] = useState(false);
  const [plan, setPlan] = useState<AppFactoryPlan | null>(null);
  const [result, setResult] = useState<AppFactoryGenerateResponse | null>(null);
  const [planning, setPlanning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadStatus();
  }, []);

  async function loadStatus() {
    try {
      setStatus(await getAppFactoryStatus());
    } catch {
      setStatus(null);
    }
  }

  const requestBody = useMemo(
    () => ({
      prompt,
      project_name: projectName.trim() || undefined,
      frontend: "React + Vite" as const,
      backend: "FastAPI" as const,
      database: "PostgreSQL" as const,
      auth,
      cloud: "Azure Container Apps" as const,
    }),
    [auth, projectName, prompt],
  );

  async function analyze() {
    if (!prompt.trim()) return;
    setPlanning(true);
    setError(null);
    setResult(null);
    try {
      setPlan(await planCloudApp(requestBody));
    } catch (exc) {
      setError(errorText(exc, "No se pudo generar el plan tecnico."));
    } finally {
      setPlanning(false);
    }
  }

  async function generate() {
    if (!prompt.trim()) return;
    setGenerating(true);
    setError(null);
    try {
      const generated = await generateCloudApp({
        ...requestBody,
        initialize_git: initializeGit || publishGithub,
        publish_github: publishGithub,
        deploy_azure: deployAzure,
        github_private: githubPrivate,
        github_token: githubToken.trim() || undefined,
      });
      setPlan(generated.plan);
      setResult(generated);
    } catch (exc) {
      setError(errorText(exc, "No se pudo generar el proyecto."));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="af-shell">
      <header className="af-topbar">
        <button className="af-back-btn" onClick={onBack} aria-label="Volver al inicio">
          <ArrowLeft size={16} />
          Volver
        </button>
        <div className="af-brand">
          <span className="af-brand-icon">
            <PackagePlus size={20} />
          </span>
          <div>
            <span>Application 04</span>
            <strong>AI Cloud App Factory</strong>
          </div>
        </div>
        <div className="af-topbar-actions">
          <CapabilityPill ok={Boolean(status)} label={status ? "Backend live" : "Backend pendiente"} />
          <button className="af-icon-btn" onClick={() => void loadStatus()} aria-label="Actualizar estado">
            <RefreshCw size={15} />
          </button>
        </div>
      </header>

      <main className="af-content">
        <section className="af-generator-grid">
          <div className="af-input-panel">
            <div className="af-section-head">
              <div>
                <span className="af-eyebrow">Prompt to Cloud</span>
                <h1>Generador de aplicaciones cloud-native</h1>
              </div>
              <Sparkles size={22} />
            </div>

            <label className="af-field" htmlFor="app-prompt">
              <span>Solicitud</span>
              <textarea
                id="app-prompt"
                rows={7}
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
              />
            </label>

            <div className="af-examples">
              {EXAMPLE_PROMPTS.map((example) => (
                <button
                  key={example}
                  onClick={() => {
                    setPrompt(example);
                    if (example.includes("proveedores")) setProjectName("supplier-cloud-app");
                    if (example.includes("clientes")) setProjectName("customer-cloud-app");
                  }}
                >
                  {example}
                </button>
              ))}
            </div>

            <div className="af-config-grid">
              <label className="af-field" htmlFor="project-name">
                <span>Nombre del proyecto</span>
                <input id="project-name" value={projectName} onChange={(event) => setProjectName(event.target.value)} />
              </label>
              <label className="af-field" htmlFor="auth-mode">
                <span>Autenticacion</span>
                <select id="auth-mode" value={auth} onChange={(event) => setAuth(event.target.value as typeof auth)}>
                  <option value="JWT demo">JWT demo</option>
                  <option value="Sin auth">Sin auth</option>
                </select>
              </label>
            </div>

            <label className="af-toggle">
              <input
                type="checkbox"
                checked={initializeGit}
                onChange={(event) => setInitializeGit(event.target.checked)}
              />
              <span>Inicializar Git local</span>
            </label>

            <label className="af-toggle">
              <input
                type="checkbox"
                checked={publishGithub}
                onChange={(event) => setPublishGithub(event.target.checked)}
              />
              <span>Publicar en GitHub</span>
            </label>

            <label className="af-toggle">
              <input
                type="checkbox"
                checked={githubPrivate}
                onChange={(event) => setGithubPrivate(event.target.checked)}
                disabled={!publishGithub}
              />
              <span>Repositorio privado</span>
            </label>

            {publishGithub && (
              <label className="af-field" htmlFor="github-token">
                <span>GitHub token</span>
                <input
                  id="github-token"
                  type="password"
                  autoComplete="off"
                  value={githubToken}
                  onChange={(event) => setGithubToken(event.target.value)}
                  placeholder="PAT con permisos repo + workflow"
                />
              </label>
            )}

            <label className="af-toggle">
              <input
                type="checkbox"
                checked={deployAzure}
                onChange={(event) => setDeployAzure(event.target.checked)}
              />
              <span>Desplegar frontend y backend en Azure</span>
            </label>

            <div className="af-action-row">
              <button className="af-btn af-btn-secondary" onClick={() => void analyze()} disabled={planning || generating || !prompt.trim()}>
                {planning ? <Loader2 className="af-spin" size={16} /> : <Hammer size={16} />}
                Analizar
              </button>
              <button className="af-btn af-btn-primary" onClick={() => void generate()} disabled={planning || generating || !prompt.trim()}>
                {generating ? <Loader2 className="af-spin" size={16} /> : <Rocket size={16} />}
                {deployAzure || publishGithub ? "Generar y publicar" : "Generar proyecto"}
              </button>
            </div>

            {error && (
              <div className="af-notice af-notice-error">
                <AlertCircle size={16} />
                <span>{error}</span>
              </div>
            )}

            {status && <StatusPanel status={status} />}
          </div>

          <section className="af-output-panel">
            {!plan && !planning && !generating && (
              <div className="af-empty">
                <PackagePlus size={46} />
                <strong>El plan y los links apareceran aqui</strong>
                <p>El generador crea codigo, Docker, Terraform, GitHub Actions y documentacion en una carpeta nueva.</p>
              </div>
            )}

            {(planning || generating) && (
              <div className="af-loading">
                <Loader2 className="af-spin" size={34} />
                <strong>{generating ? "Trabajando el flujo completo..." : "Analizando arquitectura..."}</strong>
                <p>
                  {generating
                    ? deployAzure
                      ? "Generando codigo, publicando imagenes y desplegando frontend/backend en Azure. Puede tardar varios minutos."
                      : publishGithub
                        ? "Generando codigo, creando repo privado y subiendo el proyecto a GitHub."
                        : "Renderizando backend, frontend, Docker, CI/CD y Terraform."
                    : "Detectando modulos, recursos y guardrails."}
                </p>
              </div>
            )}

            {plan && !planning && !generating && (
              <div className="af-plan">
                <PlanSummary plan={plan} />
                <EntityPanel plan={plan} />
                <ResourcePanel plan={plan} />
                <StepTimeline steps={result?.steps ?? plan.steps} />
                {result && <ResultPanel result={result} />}
              </div>
            )}
          </section>
        </section>
      </main>
    </div>
  );
}

function StatusPanel({ status }: { status: AppFactoryStatus }) {
  return (
    <div className="af-status-panel">
      <div className="af-mini-head">
        <strong>Capacidades locales</strong>
        <span>{status.mode}</span>
      </div>
      <div className="af-cap-grid">
        {status.capabilities.map((capability) => (
          <div className="af-cap" key={capability.name}>
            <CapabilityPill ok={capability.available} label={capability.name} />
            <span>{capability.detail}</span>
          </div>
        ))}
      </div>
      <div className="af-root-path">
        <FileCode2 size={15} />
        <span>{status.generated_root}</span>
      </div>
    </div>
  );
}

function PlanSummary({ plan }: { plan: AppFactoryPlan }) {
  return (
    <section className="af-panel af-plan-summary">
      <div>
        <span className="af-eyebrow">Plan tecnico</span>
        <h2>{plan.project_name}</h2>
        <p>{plan.summary}</p>
      </div>
      <div className="af-stack-grid">
        <StackChip icon={<Code2 size={16} />} label="Frontend" value={plan.frontend} />
        <StackChip icon={<Server size={16} />} label="Backend" value={plan.backend} />
        <StackChip icon={<Database size={16} />} label="Database" value={plan.database} />
        <StackChip icon={<Cloud size={16} />} label="Cloud" value={plan.cloud} />
      </div>
      <div className="af-guardrails">
        {plan.guardrails.map((guardrail) => (
          <span key={guardrail}>
            <ShieldCheck size={14} />
            {guardrail}
          </span>
        ))}
      </div>
    </section>
  );
}

function EntityPanel({ plan }: { plan: AppFactoryPlan }) {
  return (
    <section className="af-panel">
      <div className="af-mini-head">
        <strong>Modulos detectados</strong>
        <span>{plan.entities.length}</span>
      </div>
      <div className="af-entity-grid">
        {plan.entities.map((entity) => (
          <div className="af-entity" key={entity.route}>
            <strong>{entity.display_name}</strong>
            <span>/api/{entity.route}</span>
            <div>
              {entity.fields.map((field) => (
                <small key={field.name}>{field.label}</small>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ResourcePanel({ plan }: { plan: AppFactoryPlan }) {
  return (
    <section className="af-panel">
      <div className="af-mini-head">
        <strong>Infraestructura Azure</strong>
        <span>{plan.estimated_cost_tier}</span>
      </div>
      <div className="af-resource-list">
        {plan.resources.map((resource) => (
          <div className="af-resource" key={`${resource.type}-${resource.name}`}>
            <div>
              <strong>{resource.name}</strong>
              <span>{resource.type}</span>
            </div>
            <p>{resource.purpose}</p>
            <small>{resource.provisioner}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function StepTimeline({ steps }: { steps: AppFactoryStep[] }) {
  return (
    <section className="af-panel">
      <div className="af-mini-head">
        <strong>Timeline</strong>
        <span>{steps.filter((step) => step.status === "success").length}/{steps.length}</span>
      </div>
      <div className="af-timeline">
        {steps.map((step) => (
          <div className={`af-step af-step-${step.status}`} key={step.name}>
            <span>{step.status === "success" ? <CheckCircle2 size={16} /> : <Loader2 size={16} />}</span>
            <div>
              <strong>{step.name}</strong>
              <p>{step.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ResultPanel({ result }: { result: AppFactoryGenerateResponse }) {
  return (
    <section className="af-panel af-result-panel">
      <div className="af-result-head">
        <CheckCircle2 size={21} />
        <div>
          <strong>Proyecto generado</strong>
          <span>{result.project_path}</span>
        </div>
      </div>
      <div className={`af-notice ${result.status === "success" ? "af-notice-ok" : "af-notice-error"}`}>
        {result.status === "success" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
        <span>{result.message}</span>
      </div>

      <div className="af-link-grid">
        {result.links.map((link) => (
          <LinkTile key={`${link.kind}-${link.label}`} link={link} />
        ))}
      </div>

      <div className="af-artifacts">
        <div className="af-mini-head">
          <strong>Artefactos</strong>
          <span>{result.artifacts.length}</span>
        </div>
        {result.artifacts.map((artifact) => (
          <ArtifactRow key={`${artifact.kind}-${artifact.path}`} artifact={artifact} />
        ))}
      </div>

      <div className="af-command-block">
        <div className="af-mini-head">
          <strong>Comandos</strong>
          <button onClick={() => void copyText(result.commands.join("\n"))}>
            <Clipboard size={14} />
            Copiar
          </button>
        </div>
        <pre>{result.commands.join("\n")}</pre>
      </div>
    </section>
  );
}

function LinkTile({ link }: { link: AppFactoryLink }) {
  const isHttp = link.url.startsWith("http");
  return (
    <div className="af-link-tile">
      <span>{link.kind}</span>
      <strong>{link.label}</strong>
      {isHttp ? (
        <a href={link.url} target="_blank" rel="noreferrer">
          {link.url}
          <ExternalLink size={13} />
        </a>
      ) : (
        <button onClick={() => void copyText(link.url)}>
          {link.url}
          <Clipboard size={13} />
        </button>
      )}
    </div>
  );
}

function ArtifactRow({ artifact }: { artifact: AppFactoryArtifact }) {
  return (
    <div className="af-artifact-row">
      <TerminalSquare size={15} />
      <div>
        <strong>{artifact.label}</strong>
        <span>{artifact.path}</span>
      </div>
    </div>
  );
}

function StackChip({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="af-stack-chip">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function CapabilityPill({ ok, label }: { ok: boolean; label: string }) {
  return <span className={`af-pill ${ok ? "af-pill-ok" : "af-pill-warn"}`}>{label}</span>;
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    /* Clipboard is best effort in local demos. */
  }
}

function errorText(exc: unknown, fallback: string) {
  return exc instanceof Error ? exc.message || fallback : fallback;
}
