import type {
  AppFactoryGenerateRequest,
  AppFactoryGenerateResponse,
  AppFactoryPlan,
  AppFactoryPlanRequest,
  AppFactoryStatus,
} from "./types";

const BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://localhost:8000" : "")
).replace(/\/+$/, "");

const PREFIX = `${BASE}/api/app-factory`;

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${PREFIX}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new Error("No se pudo conectar con el backend de AI Cloud App Factory.");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    const detail = (body as { detail?: unknown }).detail;
    throw new Error(typeof detail === "string" ? detail : `Error ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export const getAppFactoryStatus = (): Promise<AppFactoryStatus> =>
  apiFetch<AppFactoryStatus>("");

export const planCloudApp = (body: AppFactoryPlanRequest): Promise<AppFactoryPlan> =>
  apiFetch<AppFactoryPlan>("/plan", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const generateCloudApp = (body: AppFactoryGenerateRequest): Promise<AppFactoryGenerateResponse> =>
  apiFetch<AppFactoryGenerateResponse>("/generate", {
    method: "POST",
    body: JSON.stringify(body),
  });

