variable "project" {
  type    = string
  default = "cookedcommute"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "location" {
  type        = string
  default     = "westeurope" # closest Azure region to Amsterdam
  description = "Azure region. Match your Snowflake trial region for lowest latency."
}

variable "tomtom_api_key" {
  type        = string
  sensitive   = true
  default     = ""
  description = "TomTom Freemium key for city-road traffic (set via TF_VAR_tomtom_api_key or terraform.tfvars)."
}

locals {
  prefix = "${var.project}-${var.environment}"
  tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
  }
}
