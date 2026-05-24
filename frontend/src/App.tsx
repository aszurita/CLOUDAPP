import { Activity, Boxes, CheckCircle2, Database, GitBranch, Server, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Deployment, Environment, PlatformStatus, Service, getDeployments, getEnvironments, getPlatformStatus, getServices } from "./api";

type LoadState = "loading" | "ready" | "error";

function statusTone(status: string) {
  if (["healthy", "success", "connected"].includes(status)) return "text-emerald-700 bg-emerald-50 border-emerald-200";
  if (["attention", "degraded"].includes(status)) return "text-amber-700 bg-amber-50 border-amber-200";
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

export default function App() {
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

  const monthlyCost = useMemo(() => services.reduce((total, service) => total + service.cost_estimate_usd, 0), [services]);

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
          <p className="eyebrow">Phase 1 Platform Base</p>
          <h1>Enterprise CloudOps & DataOps Autopilot</h1>
        </div>
        <StatusBadge value={status.database} />
      </header>

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
          <StatusBadge value={status.ai_configured ? "configured" : "pending"} />
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
    </main>
  );
}
