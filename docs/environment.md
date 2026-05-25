# Environment Variables

## Backend

| Variable | Required | Description |
| --- | --- | --- |
| `ENVIRONMENT` | yes | Runtime environment, for example `local`, `dev`, `prod`. |
| `DATABASE_URL` | yes | SQLAlchemy database URL. Use `sqlite:///./cloudapp.db` locally and PostgreSQL in Azure. |
| `FRONTEND_ORIGINS` | yes | Comma-separated CORS origins, for example `http://localhost:5173` locally or `https://kind-dune-06cb3ca0f.7.azurestaticapps.net` in Azure. |
| `AI_PROVIDER` | yes | AI provider name. Use `openai` for phase 2. |
| `OPENAI_API_KEY` | yes for phase 2 | OpenAI API key. Keep it only in `.env`, GitHub Secrets, Key Vault, or Container App secrets. |
| `OPENAI_MODEL` | yes for phase 2 | OpenAI model name, default `chat-latest`. |
| `OPENAI_MAX_OUTPUT_TOKENS` | no | Maximum output tokens for OpenAI explanations, default `800`. |
| `OPENAI_TEMPERATURE` | no | Temperature for deterministic DBA/query explanations, default `0.2`. |
| `DATABRICKS_HOST` | no | Azure Databricks workspace URL for DataOps phase. |
| `DATABRICKS_TOKEN` | no | Databricks PAT stored only in `.env`, GitHub Secrets, Key Vault, or Container App secrets. |
| `DATABRICKS_JOB_ID` | no | Databricks Workflow job ID launched by the DataOps Monitor. |
| `DATABRICKS_CATALOG` | no | Databricks catalog name, default `databricks_proyectobg`. |
| `DATABRICKS_SCHEMA_BRONZE` | no | Bronze schema name, default `tpcds_bronze`. |
| `DATABRICKS_SCHEMA_SILVER` | no | Silver schema name, default `tpcds_silver`. |
| `DATABRICKS_SCHEMA_GOLD` | no | Gold schema name, default `tpcds_gold`. |
| `CATALOG_PROVIDER` | no | Catalog mode for phase 4: `internal`, `datahub`, or `purview`. Default `internal`. |
| `DATAHUB_ENABLED` | no | Set to `true` to publish catalog metadata to DataHub. |
| `DATAHUB_SERVER` | no | DataHub server URL. If empty, the portal uses the internal PostgreSQL catalog fallback. |
| `DATAHUB_TOKEN` | no | DataHub token stored only in local `.env`, GitHub Secrets, Key Vault, or Container App secrets. |
| `PURVIEW_ENABLED` | no | Set to `true` for Purview enterprise mode placeholders. |
| `PURVIEW_ENDPOINT` | no | Microsoft Purview endpoint. |
| `PURVIEW_ACCOUNT_NAME` | no | Microsoft Purview account name. |
| `PURVIEW_TENANT_ID` | no | Entra tenant for Purview service principal. |
| `PURVIEW_CLIENT_ID` | no | Service principal client ID for Purview. |
| `PURVIEW_CLIENT_SECRET` | no | Purview client secret stored only in secret stores. |

## Frontend

| Variable | Required | Description |
| --- | --- | --- |
| `VITE_API_BASE_URL` | yes | Public backend base URL, for example `https://ca-cloudapp-dev-api.delightfulsea-04be8a68.eastus.azurecontainerapps.io`. Do not include `/docs`. |
