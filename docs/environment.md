# Environment Variables

## Backend

| Variable | Required | Description |
| --- | --- | --- |
| `ENVIRONMENT` | yes | Runtime environment, for example `local`, `dev`, `prod`. |
| `DATABASE_URL` | yes | SQLAlchemy database URL. Use `sqlite:///./cloudapp.db` locally and PostgreSQL in Azure. |
| `FRONTEND_ORIGINS` | yes | Comma-separated CORS origins, for example `http://localhost:5173` locally or `https://kind-dune-06cb3ca0f.7.azurestaticapps.net` in Azure. |
| `AI_PROVIDER` | no | AI provider name. Use `gemini` for this project. |
| `GEMINI_API_KEY` | no | Gemini API key for later AI phases. Keep it only in `.env`, GitHub Secrets, or Key Vault. |
| `GEMINI_MODEL` | no | Gemini model name, default `gemini-2.5-flash`. |
| `DATABRICKS_HOST` | no | Placeholder for DataOps phase. |
| `DATAHUB_SERVER` | no | Placeholder for catalog phase. |

## Frontend

| Variable | Required | Description |
| --- | --- | --- |
| `VITE_API_BASE_URL` | yes | Public backend base URL, for example `https://ca-cloudapp-dev-api.delightfulsea-04be8a68.eastus.azurecontainerapps.io`. Do not include `/docs`. |
