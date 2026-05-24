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
| `DATABRICKS_HOST` | no | Placeholder for DataOps phase. |
| `DATAHUB_SERVER` | no | Placeholder for catalog phase. |

## Frontend

| Variable | Required | Description |
| --- | --- | --- |
| `VITE_API_BASE_URL` | yes | Public backend base URL, for example `https://ca-cloudapp-dev-api.delightfulsea-04be8a68.eastus.azurecontainerapps.io`. Do not include `/docs`. |
