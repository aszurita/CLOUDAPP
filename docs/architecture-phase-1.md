# Phase 1 Architecture

Enterprise CloudOps & DataOps Autopilot starts as a small cloud platform:

```text
React + Vite frontend
        ↓
FastAPI backend in Azure Container Apps
        ↓
Azure Database for PostgreSQL Flexible Server
```

Supporting services:

- Azure Static Web Apps hosts the frontend.
- Azure Container Registry stores backend images.
- Azure Key Vault stores database and future integration secrets.
- Azure Monitor and Log Analytics receive backend logs.
- GitHub Actions runs CI/CD for frontend and backend.

Phase 1 intentionally leaves Databricks, DataHub/Purview, and Gemini as placeholders so phase 2 can focus on Query Governance without platform churn.
