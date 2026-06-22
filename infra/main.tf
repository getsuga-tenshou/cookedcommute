data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "azurerm_resource_group" "rg" {
  name     = "${local.prefix}-rg"
  location = var.location
  tags     = local.tags
}

# --------------------------------------------------------------------------- #
# Data lake (ADLS Gen2) — raw landing zone that Snowflake loads from
# --------------------------------------------------------------------------- #
resource "azurerm_storage_account" "lake" {
  name                     = "${var.project}lake${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true # ADLS Gen2 hierarchical namespace
  tags                     = local.tags
}

resource "azurerm_storage_data_lake_gen2_filesystem" "raw" {
  name               = "raw"
  storage_account_id = azurerm_storage_account.lake.id
}

resource "azurerm_storage_data_lake_gen2_filesystem" "curated" {
  name               = "curated"
  storage_account_id = azurerm_storage_account.lake.id
}

# Separate plain storage account for the Function App runtime (not HNS).
resource "azurerm_storage_account" "func" {
  name                     = "${var.project}func${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = local.tags
}

# --------------------------------------------------------------------------- #
# Observability
# --------------------------------------------------------------------------- #
resource "azurerm_log_analytics_workspace" "logs" {
  name                = "${local.prefix}-logs"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_application_insights" "appi" {
  name                = "${local.prefix}-appi"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  workspace_id        = azurerm_log_analytics_workspace.logs.id
  application_type    = "other"
  tags                = local.tags
}

# --------------------------------------------------------------------------- #
# Ingestion — Linux Function App (Python, consumption) landing raw to ADLS
# --------------------------------------------------------------------------- #
resource "azurerm_service_plan" "func" {
  name                = "${local.prefix}-func-plan"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = "Y1" # consumption: 1M free executions/month
  tags                = local.tags
}

resource "azurerm_linux_function_app" "ingest" {
  name                       = "${local.prefix}-ingest-${random_string.suffix.result}"
  resource_group_name        = azurerm_resource_group.rg.name
  location                   = azurerm_resource_group.rg.location
  service_plan_id            = azurerm_service_plan.func.id
  storage_account_name       = azurerm_storage_account.func.name
  storage_account_access_key = azurerm_storage_account.func.primary_access_key

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_stack {
      python_version = "3.11"
    }
    application_insights_connection_string = azurerm_application_insights.appi.connection_string
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME = "python"
    # ADLS via the Function's managed identity (no secrets):
    ADLS_ACCOUNT             = azurerm_storage_account.lake.name
    ADLS_FILESYSTEM          = azurerm_storage_data_lake_gen2_filesystem.raw.name
    LAKE_DIR                 = "/tmp/lake"
    NDW_TRAFFICSPEED_URL     = "https://opendata.ndw.nu/trafficspeed.xml.gz"
    NDW_MEASUREMENT_URL      = "https://opendata.ndw.nu/measurement.xml.gz"
    AMS_PARKING_URL          = "https://npropendata.rdw.nl/parkingdata/v2"
    TOMTOM_API_KEY           = var.tomtom_api_key
  }

  tags = local.tags
}

# Let the Function write to the lake via its managed identity.
resource "azurerm_role_assignment" "func_blob" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_linux_function_app.ingest.identity[0].principal_id
}
