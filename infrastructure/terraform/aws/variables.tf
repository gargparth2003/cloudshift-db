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

variable "allowed_console_cidrs" {
  description = "CIDRs allowed to reach the optional console host. Never defaults to the public internet."
  type        = list(string)
  default     = []
}
