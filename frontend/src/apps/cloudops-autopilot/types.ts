export type CloudOpsToolStatus = {
  name: string;
  available: boolean;
  detail: string;
};

export type CloudOpsArtifactStatus = {
  key: string;
  label: string;
  path: string;
  present: boolean;
  purpose: string;
};

export type CloudOpsGeneratedApp = {
  id: string;
  name: string;
  slug: string;
  path: string;
  created_at: string | null;
  updated_at: string | null;
  status: "ready" | "partial" | "blocked";
  readiness_score: number;
  artifacts: CloudOpsArtifactStatus[];
  azure_links: string[];
  github_url: string | null;
};

export type CloudOpsAzureResource = {
  name: string;
  resource_group: string;
  type: string;
  location: string | null;
  status: string | null;
  url: string | null;
};

export type CloudOpsAzureSnapshot = {
  authenticated: boolean;
  subscription_name: string | null;
  subscription_id: string | null;
  tenant_id: string | null;
  user: string | null;
  resource_groups: CloudOpsAzureResource[];
  container_apps: CloudOpsAzureResource[];
  registries: CloudOpsAzureResource[];
  postgres_servers: CloudOpsAzureResource[];
  errors: string[];
};

export type CloudOpsPlanStep = {
  name: string;
  stage: "validate" | "provision" | "build" | "release" | "observe" | "govern";
  status: "ready" | "manual" | "warning" | "blocked";
  detail: string;
};

export type CloudOpsDeploymentPlan = {
  app_id: string | null;
  app_slug: string | null;
  project_path: string | null;
  mode: "readiness" | "cloudops-mvp";
  summary: string;
  readiness_score: number;
  required_inputs: string[];
  steps: CloudOpsPlanStep[];
  matched_azure_resources: CloudOpsAzureResource[];
};

export type CloudOpsOverview = {
  title: string;
  mode: "operations-console";
  generated_root: string;
  tools: CloudOpsToolStatus[];
  apps: CloudOpsGeneratedApp[];
  selected_app: CloudOpsGeneratedApp | null;
  azure: CloudOpsAzureSnapshot;
  plan: CloudOpsDeploymentPlan;
};

