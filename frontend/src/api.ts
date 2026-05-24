const DEFAULT_API_BASE_URL = import.meta.env.DEV
  ? "http://localhost:8000"
  : "https://ca-cloudapp-dev-api.delightfulsea-04be8a68.eastus.azurecontainerapps.io";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, "");

export type PlatformStatus = {
  app_name: string;
  environment: string;
  database: string;
  services_total: number;
  services_healthy: number;
  environments_total: number;
  latest_deployment_status: string | null;
  audit_events_total: number;
  ai_provider: string;
  ai_configured: boolean;
  ai_model: string;
};

export type Environment = {
  id: number;
  code: string;
  name: string;
  status: string;
  region: string;
  is_active: boolean;
};

export type Service = {
  id: number;
  environment_id: number;
  name: string;
  service_type: string;
  status: string;
  version: string;
  health_url: string | null;
  cost_estimate_usd: number;
};

export type Deployment = {
  id: number;
  service_id: number;
  commit_sha: string;
  status: string;
  deployed_by: string;
  pipeline_url: string | null;
  deployed_at: string;
};

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getPlatformStatus() {
  return request<PlatformStatus>("/api/platform/status");
}

export function getEnvironments() {
  return request<Environment[]>("/api/environments");
}

export function getServices() {
  return request<Service[]>("/api/services");
}

export function getDeployments() {
  return request<Deployment[]>("/api/deployments");
}
