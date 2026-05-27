export type AppFactoryCapability = {
  name: string;
  available: boolean;
  detail: string;
};

export type AppFactoryStatus = {
  title: string;
  mode: "local-generator" | "cloud-ready";
  generated_root: string;
  supported_frontends: string[];
  supported_backends: string[];
  supported_databases: string[];
  supported_clouds: string[];
  capabilities: AppFactoryCapability[];
};

export type AppFactoryField = {
  name: string;
  label: string;
  type: "text" | "email" | "number" | "currency" | "date" | "status";
  required: boolean;
};

export type AppFactoryEntity = {
  name: string;
  route: string;
  display_name: string;
  fields: AppFactoryField[];
};

export type AppFactoryResource = {
  name: string;
  type: string;
  purpose: string;
  provisioner: string;
};

export type AppFactoryStep = {
  name: string;
  status: "pending" | "running" | "success" | "blocked" | "skipped";
  detail: string;
};

export type AppFactoryPlanRequest = {
  prompt: string;
  project_name?: string;
  frontend?: "React + Vite";
  backend?: "FastAPI";
  database?: "PostgreSQL";
  auth?: "JWT demo" | "Sin auth";
  cloud?: "Azure Container Apps";
};

export type AppFactoryPlan = {
  project_name: string;
  slug: string;
  summary: string;
  frontend: string;
  backend: string;
  database: string;
  auth: string;
  cloud: string;
  entities: AppFactoryEntity[];
  resources: AppFactoryResource[];
  steps: AppFactoryStep[];
  files_preview: string[];
  estimated_cost_tier: string;
  guardrails: string[];
};

export type AppFactoryGenerateRequest = AppFactoryPlanRequest & {
  initialize_git?: boolean;
  publish_github?: boolean;
  deploy_azure?: boolean;
  github_private?: boolean;
  github_token?: string;
};

export type AppFactoryLink = {
  label: string;
  url: string;
  kind: "local" | "file" | "command" | "cloud-template" | "github-template" | "github" | "azure";
};

export type AppFactoryArtifact = {
  label: string;
  path: string;
  kind: "project" | "backend" | "frontend" | "terraform" | "workflow" | "documentation";
};

export type AppFactoryGenerateResponse = {
  job_id: string;
  status: "success" | "partial" | "blocked";
  message: string;
  project_name: string;
  slug: string;
  project_path: string;
  generated_at: string;
  links: AppFactoryLink[];
  artifacts: AppFactoryArtifact[];
  steps: AppFactoryStep[];
  commands: string[];
  plan: AppFactoryPlan;
};
