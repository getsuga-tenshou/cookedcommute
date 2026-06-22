terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # For real use, configure a remote backend, e.g.:
  # backend "azurerm" {
  #   resource_group_name  = "tfstate-rg"
  #   storage_account_name = "tfstateparkpulse"
  #   container_name       = "tfstate"
  #   key                  = "parkpulse.tfstate"
  # }
}

provider "azurerm" {
  features {}
}
