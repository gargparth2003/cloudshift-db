variable "aws_region" {
  description = "AWS region for the optional CloudShift reference deployment."
  type        = string
  default     = "ap-south-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "database_name" {
  type    = string
  default = "parth_commerce_target"
}

variable "database_username" {
  type    = string
  default = "cloudshift_admin"
}

variable "database_password" {
  description = "RDS password supplied through TF_VAR_database_password or a secure CI secret."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = length(var.database_password) >= 16
    error_message = "database_password must contain at least 16 characters."
  }
}

variable "database_instance_class" {
  description = "Cost-sensitive default; resize only after workload evidence."
  type        = string
  default     = "db.t4g.micro"
}

variable "application_instance_type" {
  type    = string
  default = "t4g.small"
}

variable "database_allocated_storage_gb" {
  description = "Initial gp3 allocation. Review current RDS pricing before increasing it."
  type        = number
  default     = 20
  validation {
    condition     = var.database_allocated_storage_gb >= 20
    error_message = "RDS PostgreSQL gp3 storage must be at least 20 GiB."
  }
}

variable "database_max_allocated_storage_gb" {
  description = "Autoscaling ceiling; must be greater than or equal to the initial allocation."
  type        = number
  default     = 100
  validation {
    condition     = var.database_max_allocated_storage_gb >= var.database_allocated_storage_gb
    error_message = "database_max_allocated_storage_gb must not be below the initial allocation."
  }
}

variable "database_multi_az" {
  description = "Creates a standby and additional cost when true. Disabled in the cost-sensitive reference default."
  type        = bool
  default     = false
}

variable "backup_retention_days" {
  description = "Automated backup retention; RDS permits 0 through 35 days for a DB instance."
  type        = number
  default     = 7
  validation {
    condition     = var.backup_retention_days >= 1 && var.backup_retention_days <= 35
    error_message = "backup_retention_days must be between 1 and 35 for this protected reference target."
  }
}

variable "deletion_protection" {
  description = "Keep enabled for protected environments; disabling requires a reviewed lifecycle change."
  type        = bool
  default     = true
}

variable "allowed_console_cidrs" {
  description = "CIDRs allowed to reach the optional console host. Never defaults to the public internet."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for cidr in var.allowed_console_cidrs : cidr != "0.0.0.0/0" && cidr != "::/0"])
    error_message = "Public-anywhere console ingress is intentionally rejected; supply explicit operator CIDRs."
  }
}
