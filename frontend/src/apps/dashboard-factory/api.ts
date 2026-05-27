import type {
  CatalogItem,
  DashboardListResponse,
  DashboardRecord,
  ExecuteDashboardResponse,
  FactoryStatus,
  GenerateDashboardRequest,
  GenerateDashboardResponse,
  GoldFactoryRequest,
  GoldFactoryRequestStatus,
  GoldFactorySubmitRequest,
  GoldFactorySubmitResponse,
  GoldTablePlan,
  PlanDashboardRequest,
  PlanDashboardResponse,
  SchemaItem,
  TableItem,
} from "./types";

const BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://localhost:8000" : "")
).replace(/\/+$/, "");

const PREFIX = `${BASE}/api/dashboard-factory`;

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${PREFIX}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new Error("No se pudo conectar con el backend de AI Gold Factory.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error((body as { detail?: string }).detail ?? `Error ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const getFactoryStatus = (): Promise<FactoryStatus> =>
  apiFetch<FactoryStatus>("");

export const planDashboard = (body: PlanDashboardRequest): Promise<PlanDashboardResponse> =>
  apiFetch<PlanDashboardResponse>("/plan", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const generateDashboard = (
  body: GenerateDashboardRequest,
): Promise<GenerateDashboardResponse> =>
  apiFetch<GenerateDashboardResponse>("/generate", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const executeDashboard = (id: number): Promise<ExecuteDashboardResponse> =>
  apiFetch<ExecuteDashboardResponse>(`/dashboards/${id}/execute`, { method: "POST" });

export const getFactoryDashboards = (): Promise<DashboardListResponse> =>
  apiFetch<DashboardListResponse>("/dashboards");

export const getFactoryDashboard = (id: number): Promise<DashboardRecord> =>
  apiFetch<DashboardRecord>(`/dashboards/${id}`);

export const deleteDashboard = (id: number): Promise<void> =>
  apiFetch<void>(`/dashboards/${id}`, { method: "DELETE" });

export const getFactoryCatalogs = (): Promise<CatalogItem[]> =>
  apiFetch<CatalogItem[]>("/catalogs");

export const getFactorySchemas = (catalog: string): Promise<SchemaItem[]> =>
  apiFetch<SchemaItem[]>(`/catalogs/${catalog}/schemas`);

export const getFactoryTables = (catalog: string, schema: string): Promise<TableItem[]> =>
  apiFetch<TableItem[]>(`/catalogs/${catalog}/schemas/${schema}/tables`);

export const planGoldTable = (body: GoldFactoryRequest): Promise<GoldTablePlan> =>
  apiFetch<GoldTablePlan>("/gold/plan", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const submitGoldTable = (
  body: GoldFactorySubmitRequest,
): Promise<GoldFactorySubmitResponse> =>
  apiFetch<GoldFactorySubmitResponse>("/gold/submit", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getGoldRequestStatus = (
  requestId: number,
): Promise<GoldFactoryRequestStatus> =>
  apiFetch<GoldFactoryRequestStatus>(`/gold/requests/${requestId}`);

export const getGoldRequestHistory = (
  limit = 50,
): Promise<GoldFactoryRequestStatus[]> =>
  apiFetch<GoldFactoryRequestStatus[]>(`/gold/history?limit=${limit}`);
