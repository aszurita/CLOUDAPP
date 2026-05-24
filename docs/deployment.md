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
AZURE_CREDENTIALS
AZURE_RESOURCE_GROUP
AZURE_CONTAINER_APP_NAME
ACR_LOGIN_SERVER
ACR_USERNAME
ACR_PASSWORD
AZURE_STATIC_WEB_APPS_API_TOKEN
GEMINI_API_KEY
```

Useful Terraform output commands:

```bash
terraform output -raw acr_login_server
terraform output -raw container_app_name
terraform output -raw resource_group_name
terraform output -raw static_web_app_api_key
terraform output -raw container_app_url
terraform output -raw static_web_app_default_host_name
```

Get ACR credentials with Azure CLI:

```bash
ACR_NAME=$(terraform output -raw acr_login_server | cut -d. -f1)
az acr credential show --name "$ACR_NAME" --query username -o tsv
az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv
```

If you want to use the Terraform ACR outputs instead, run `terraform apply` once after pulling the latest code so the state file learns the new output definitions.

Create the Azure service principal used by the backend workflow:

```bash
az ad sp create-for-rbac \
  --name cloudapp-github-actions \
  --role contributor \
  --scopes /subscriptions/$(az account show --query id -o tsv)/resourceGroups/$(terraform output -raw resource_group_name) \
  --sdk-auth
```

Copy the command output into GitHub repository secrets:

```text
AZURE_CREDENTIALS=<full JSON output>
```

The `AZURE_CREDENTIALS` JSON must include `clientId`, `clientSecret`, `tenantId`, and `subscriptionId`.

Your current subscription values:

```text
AZURE_SUBSCRIPTION_ID=c38860ad-92d1-45e2-b159-0f2496993231
AZURE_TENANT_ID=b7af8caf-83d8-4644-85ae-317c545223c1
```

For the current phase 1 Azure deployment, the non-sensitive values should look like this:

```text
AZURE_RESOURCE_GROUP=rg-cloudapp-dev
AZURE_CONTAINER_APP_NAME=ca-cloudapp-dev-api
ACR_LOGIN_SERVER=acrcloudappdevzgc5ku.azurecr.io
VITE_API_BASE_URL=https://ca-cloudapp-dev-api.delightfulsea-04be8a68.eastus.azurecontainerapps.io
```

`VITE_API_BASE_URL` is a public frontend build value. It is defined directly in `.github/workflows/frontend-ci-cd.yml` for phase 1, so it does not need to be stored as a GitHub Secret.

The deployed frontend origin should be configured in Terraform so the backend CORS policy accepts browser requests:

```hcl
frontend_origin = "https://kind-dune-06cb3ca0f.7.azurestaticapps.net"
```

Create `AZURE_STATIC_WEB_APPS_API_TOKEN` from:

```bash
terraform output -raw static_web_app_api_key
```

Do not paste Terraform state files, `.env`, or `.tfvars` into GitHub. Only paste the individual secret values into GitHub repository secrets.

Update `frontend_origin` in Terraform after Static Web Apps has a public hostname, then run `terraform apply` again so backend CORS accepts the deployed portal. Use the backend base URL for `VITE_API_BASE_URL`; do not include `/docs` or `/health`.

Terraform creates the Container App with a public placeholder image first. The backend workflow replaces it with the FastAPI image. Terraform keeps ingress on port `8000` and ignores later image changes so future `terraform apply` runs do not roll the app back to the placeholder image.

For local development, copy `backend/.env.example` to `backend/.env` and put your real Gemini key in `GEMINI_API_KEY`. Never commit `.env`.
