# Costs And Shutdown

Recommended budget for phase 1 is USD 10 to USD 20.

Cost controls:

- Keep Container Apps at `min_replicas = 0`.
- Use Basic ACR.
- Use Free Static Web Apps.
- Use a small PostgreSQL Flexible Server SKU.
- Keep Log Analytics retention at 30 days.
- Avoid Databricks and Purview until later phases.

Shutdown options:

```bash
az containerapp update --name <container-app-name> --resource-group <resource-group> --min-replicas 0 --max-replicas 0
```

For full cleanup:

```bash
cd infra/terraform
terraform destroy
```
