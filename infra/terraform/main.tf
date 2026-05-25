locals {
  name_prefix     = "${var.project_name}-${var.environment}"
  postgres_suffix = var.postgres_server_name_suffix != "" ? var.postgres_server_name_suffix : random_string.suffix.result
  tags = {
    project     = var.project_name
    environment = var.environment
    phase       = "1-platform-base"
  }
}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "random_password" "postgres_password" {
  length           = 24
  special          = true
  override_special = "!#$%*()-_=+[]{}:?"
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name_prefix}-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_container_registry" "main" {
  name                = replace("acr${var.project_name}${var.environment}${random_string.suffix.result}", "-", "")
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = local.tags
}

resource "azurerm_key_vault" "main" {
  name                       = "kv-${local.name_prefix}-${random_string.suffix.result}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  tags                       = local.tags
}

data "azurerm_client_config" "current" {}

resource "azurerm_key_vault_access_policy" "deployer" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = ["Get", "List", "Set", "Delete", "Purge", "Recover"]
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                   = "psql-${local.name_prefix}-${local.postgres_suffix}"
  resource_group_name    = azurerm_resource_group.main.name
  location               = var.postgres_location
  version                = "16"
  administrator_login    = var.postgres_admin_user
  administrator_password = random_password.postgres_password.result
  zone                   = "1"
  storage_mb             = 32768
  sku_name               = "B_Standard_B1ms"
  tags                   = local.tags
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = var.postgres_database_name
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "client" {
  count            = var.allowed_client_ip == "" ? 0 : 1
  name             = "allow-client-admin-ip"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = var.allowed_client_ip
  end_ip_address   = var.allowed_client_ip
}

locals {
  database_url = "postgresql+psycopg://${var.postgres_admin_user}:${urlencode(random_password.postgres_password.result)}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/${var.postgres_database_name}?sslmode=require"
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "DATABASE-URL"
  value        = local.database_url
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "openai_placeholder" {
  name         = "OPENAI-API-KEY"
  value        = "phase-2-placeholder"
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "databricks_placeholder" {
  name         = "DATABRICKS-HOST"
  value        = "phase-3-placeholder"
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "datahub_placeholder" {
  name         = "DATAHUB-SERVER"
  value        = var.datahub_server != "" ? var.datahub_server : "phase-4-placeholder"
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "datahub_token_placeholder" {
  name         = "DATAHUB-TOKEN"
  value        = "phase-4-placeholder"
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "purview_client_secret_placeholder" {
  name         = "PURVIEW-CLIENT-SECRET"
  value        = "phase-4-placeholder"
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.name_prefix}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

resource "azurerm_container_app" "backend" {
  name                         = "ca-${local.name_prefix}-api"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  secret {
    name  = "database-url"
    value = local.database_url
  }

  secret {
    name  = "openai-api-key"
    value = azurerm_key_vault_secret.openai_placeholder.value
  }

  secret {
    name  = "datahub-token"
    value = azurerm_key_vault_secret.datahub_token_placeholder.value
  }

  secret {
    name  = "purview-client-secret"
    value = azurerm_key_vault_secret.purview_client_secret_placeholder.value
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 0
    max_replicas = 1

    container {
      name   = "backend"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name  = "FRONTEND_ORIGINS"
        value = var.frontend_origin
      }

      env {
        name  = "AI_PROVIDER"
        value = "openai"
      }

      env {
        name  = "OPENAI_MODEL"
        value = "chat-latest"
      }

      env {
        name  = "OPENAI_MAX_OUTPUT_TOKENS"
        value = "800"
      }

      env {
        name  = "OPENAI_TEMPERATURE"
        value = "0.2"
      }

      env {
        name        = "OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }

      env {
        name  = "CATALOG_PROVIDER"
        value = var.catalog_provider
      }

      env {
        name  = "DATAHUB_SERVER"
        value = var.datahub_server
      }

      env {
        name  = "DATAHUB_ENABLED"
        value = tostring(var.datahub_enabled)
      }

      env {
        name        = "DATAHUB_TOKEN"
        secret_name = "datahub-token"
      }

      env {
        name  = "PURVIEW_ENDPOINT"
        value = var.purview_endpoint
      }

      env {
        name  = "PURVIEW_ENABLED"
        value = tostring(var.purview_enabled)
      }

      env {
        name        = "PURVIEW_CLIENT_SECRET"
        secret_name = "purview-client-secret"
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].container[0].image
    ]
  }
}

resource "azurerm_static_web_app" "frontend" {
  name                = "swa-${local.name_prefix}-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.static_web_app_location
  sku_tier            = "Free"
  sku_size            = "Free"
  tags                = local.tags
}

resource "azurerm_consumption_budget_resource_group" "main" {
  count             = length(var.budget_contact_emails) > 0 ? 1 : 0
  name              = "budget-${local.name_prefix}"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.budget_amount_usd
  time_grain        = "Monthly"

  time_period {
    start_date = "2026-06-01T00:00:00Z"
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    contact_emails = var.budget_contact_emails
  }
}
