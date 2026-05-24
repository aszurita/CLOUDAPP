# CLOUDAPP

Enterprise CloudOps & DataOps Autopilot, fase 1: plataforma base cloud-native con frontend React, backend FastAPI, PostgreSQL, contenedores, Terraform para Azure y CI/CD con GitHub Actions.

## Estructura

```text
frontend/          React + Vite + Tailwind
backend/           FastAPI + SQLAlchemy + Alembic
infra/terraform/   Azure Static Web Apps, Container Apps, ACR, PostgreSQL, Key Vault, Monitor
docs/              Arquitectura, despliegue, costos y demo
.github/workflows/ CI/CD frontend y backend
```

## Desarrollo local

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

For local development, `backend/.env.example` uses SQLite:

```env
DATABASE_URL=sqlite:///./cloudapp.db
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Verificación

```bash
cd backend
.venv/bin/pytest
```

```bash
cd frontend
npm run build
```

## INSTALAR

WINDOWS 
``bash
winget install -e --id Hashicorp.Terraform --accept-source-agreements --accept-package-agreements
winget install -e --id Microsoft.AzureCLI --accept-source-agreements --accept-package-agreements
```

MAC 
``bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform

brew update
brew install azure-cli
```
## Documentación

- [Arquitectura fase 1](docs/architecture-phase-1.md)
- [Variables de entorno](docs/environment.md)
- [Guía de despliegue](docs/deployment.md)
- [Costos y apagado](docs/costs-and-shutdown.md)
- [Demo fase 1](docs/demo-phase-1.md)
