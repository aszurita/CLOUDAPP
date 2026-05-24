variable "project_name" {
  type        = string
  description = "Short lowercase project name used in Azure resource names."
  default     = "cloudapp"
}

variable "location" {
  type        = string
  description = "Default Azure region for phase 1 resources."
  default     = "eastus"
}

variable "postgres_location" {
  type        = string
  description = "Azure region for PostgreSQL Flexible Server. Some subscriptions restrict PostgreSQL by region."
  default     = "mexicocentral"
}

variable "static_web_app_location" {
  type        = string
  description = "Azure region for Static Web Apps. Supported examples: centralus, eastus2, westus2, westeurope, eastasia."
  default     = "eastus2"
}

variable "environment" {
  type        = string
  description = "Deployment environment name."
  default     = "dev"
}

variable "postgres_admin_user" {
  type        = string
  description = "PostgreSQL administrator username."
  default     = "cloudappadmin"
}

variable "postgres_database_name" {
  type        = string
  description = "Application database name."
  default     = "cloudapp"
}

variable "postgres_server_name_suffix" {
  type        = string
  description = "Optional suffix for the PostgreSQL server name. Use this if a failed Azure create operation reserved the default name."
  default     = ""
}

variable "allowed_client_ip" {
  type        = string
  description = "Optional public IP allowed to connect to PostgreSQL for administration."
  default     = ""
}

variable "budget_amount_usd" {
  type        = number
  description = "Monthly resource group budget in USD."
  default     = 20
}

variable "budget_contact_emails" {
  type        = list(string)
  description = "Emails that receive budget notifications. If empty, the budget resource is skipped."
  default     = []
}

variable "frontend_origin" {
  type        = string
  description = "Frontend origin allowed by backend CORS. Replace after Static Web Apps creates its public URL."
  default     = "http://localhost:5173"
}
