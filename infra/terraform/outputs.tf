output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "acr_admin_username" {
  value = azurerm_container_registry.main.admin_username
}

output "acr_admin_password" {
  value     = azurerm_container_registry.main.admin_password
  sensitive = true
}

output "container_app_name" {
  value = azurerm_container_app.backend.name
}

output "container_app_url" {
  value = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
}

output "static_web_app_name" {
  value = azurerm_static_web_app.frontend.name
}

output "static_web_app_default_host_name" {
  value = azurerm_static_web_app.frontend.default_host_name
}

output "static_web_app_api_key" {
  value     = azurerm_static_web_app.frontend.api_key
  sensitive = true
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "key_vault_url" {
  value = azurerm_key_vault.main.vault_uri
}

output "application_insights_name" {
  value = azurerm_application_insights.main.name
}

output "applicationinsights_connection_string" {
  value     = azurerm_application_insights.main.connection_string
  sensitive = true
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.id
}

output "postgres_server_fqdn" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}

output "postgres_server_resource_id" {
  value = azurerm_postgresql_flexible_server.main.id
}
