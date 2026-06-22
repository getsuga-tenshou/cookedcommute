# These outputs feed the Snowflake storage-integration placeholders in
# snowflake/02_azure_stage_and_load.sql:
#   storage_account  -> <ADLS_ACCOUNT>
#   adls_container   -> <ADLS_CONTAINER>
#   azure_tenant_id  -> <AZURE_TENANT_ID>

output "resource_group" {
  value = azurerm_resource_group.rg.name
}

output "storage_account" {
  value       = azurerm_storage_account.lake.name
  description = "ADLS_ACCOUNT for .env and the Snowflake storage integration."
}

output "adls_container" {
  value = azurerm_storage_data_lake_gen2_filesystem.raw.name
}

output "adls_url" {
  value = "azure://${azurerm_storage_account.lake.name}.blob.core.windows.net/${azurerm_storage_data_lake_gen2_filesystem.raw.name}/"
}

output "function_app" {
  value = azurerm_linux_function_app.ingest.name
}

output "azure_tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}
