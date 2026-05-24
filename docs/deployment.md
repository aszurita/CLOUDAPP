# Deployment Guide

## Local backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

## Local frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Azure infrastructure

Before applying Terraform, login and register the Azure providers used by this project:

```bash
az login
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.Web
az provider register --namespace Microsoft.DBforPostgreSQL
```

Provider registration can take a few minutes. Check the Container Apps provider with:

```bash
az provider show --namespace Microsoft.App --query registrationState -o tsv
```

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

If PostgreSQL fails with `LocationIsOfferRestricted`, edit `terraform.tfvars` and try another PostgreSQL region. Azure for Students may allow only a small set of regions. This project defaults PostgreSQL to `mexicocentral` because it is allowed by the subscription policy and PostgreSQL Flexible Server reports availability there:

```hcl
postgres_location = "mexicocentral"
```

If Azure says the PostgreSQL name already exists after a failed attempt, keep the new region and change only the PostgreSQL suffix:

```hcl
postgres_server_name_suffix = "zgc5ku2"
```

Static Web Apps does not support every Azure region. This project uses:

```hcl
static_web_app_location = "eastus2"
```

The budget resource is only created when `budget_contact_emails` has at least one email, because Azure requires a notification contact.

After Terraform finishes, set these GitHub repository secrets:

```text
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
AZURE_RESOURCE_GROUP
AZURE_CONTAINER_APP_NAME
ACR_LOGIN_SERVER
ACR_USERNAME
ACR_PASSWORD
AZURE_STATIC_WEB_APPS_API_TOKEN
VITE_API_BASE_URL
GEMINI_API_KEY
```

Useful Terraform output commands:

```bash
terraform output -raw acr_login_server
terraform output -raw acr_admin_username
terraform output -raw acr_admin_password
terraform output -raw container_app_name
terraform output -raw resource_group_name
terraform output -raw static_web_app_api_key
terraform output -raw container_app_url
terraform output -raw static_web_app_default_host_name
```

Update `frontend_origin` in Terraform after Static Web Apps has a public hostname, then run `terraform apply` again so backend CORS accepts the deployed portal.

Terraform creates the Container App with a public placeholder image first. The backend workflow replaces it with the FastAPI image and switches ingress to port `8000`.

For local development, copy `backend/.env.example` to `backend/.env` and put your real Gemini key in `GEMINI_API_KEY`. Never commit `.env`.
