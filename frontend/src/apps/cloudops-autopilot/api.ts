import type { CloudOpsOverview } from "./types";

const BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://localhost:8000" : "")
).replace(/\/+$/, "");

const PREFIX = `${BASE}/api/cloudops-autopilot`;

async function apiFetch<T>(path = ""): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${PREFIX}${path}`, {
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    throw new Error("No se pudo conectar con CloudOps Autopilot.");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    const detail = (body as { detail?: unknown }).detail;
    throw new Error(typeof detail === "string" ? detail : `Error ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getCloudOpsOverview(appId?: string): Promise<CloudOpsOverview> {
  return apiFetch<CloudOpsOverview>(appId ? `?app_id=${encodeURIComponent(appId)}` : "");
}

