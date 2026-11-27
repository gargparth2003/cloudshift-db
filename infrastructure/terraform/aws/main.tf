data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ami" "amazon_linux_arm64" {
  most_recent = true
  owners      = ["137112412989"]
  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-arm64"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_vpc" "cloudshift" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "cloudshift-parth-vpc" }
}

resource "aws_internet_gateway" "cloudshift" {
  vpc_id = aws_vpc.cloudshift.id
  tags   = { Name = "cloudshift-parth-igw" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.cloudshift.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 10)
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags                    = { Name = "cloudshift-parth-public" }
}

resource "aws_subnet" "database" {
  count             = 2
  vpc_id            = aws_vpc.cloudshift.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 20 + count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = { Name = "cloudshift-parth-database-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.cloudshift.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.cloudshift.id
  }
  tags = { Name = "cloudshift-parth-public" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "application" {
  name        = "cloudshift-parth-application"
  description = "Optional console ingress and unrestricted egress for image/package retrieval."
  vpc_id      = aws_vpc.cloudshift.id

  dynamic "ingress" {
    for_each = toset(var.allowed_console_cidrs)
    content {
      description = "Explicitly authorized console client"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "cloudshift-parth-application" }
}

resource "aws_security_group" "database" {
  name        = "cloudshift-parth-database"
  description = "PostgreSQL reachable only from the CloudShift application security group."
  vpc_id      = aws_vpc.cloudshift.id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.application.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "cloudshift-parth-database" }
}

resource "aws_db_subnet_group" "cloudshift" {
  name       = "cloudshift-parth"
  subnet_ids = aws_subnet.database[*].id
}

resource "aws_db_instance" "target" {
  identifier                   = "cloudshift-parth-target"
  engine                       = "postgres"
  engine_version               = "16.6"
  instance_class               = var.database_instance_class
  allocated_storage            = 20
  max_allocated_storage        = 100
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_name                      = var.database_name
  username                     = var.database_username
  password                     = var.database_password
  db_subnet_group_name         = aws_db_subnet_group.cloudshift.name
  vpc_security_group_ids       = [aws_security_group.database.id]
  publicly_accessible          = false
  backup_retention_period      = 7
  deletion_protection          = true
  skip_final_snapshot          = false
  final_snapshot_identifier    = "cloudshift-parth-target-final"
  auto_minor_version_upgrade   = true
  performance_insights_enabled = false
  tags                         = { Name = "cloudshift-parth-target" }
}

resource "aws_s3_bucket" "backups" {
  bucket_prefix = "cloudshift-parth-backups-"
  force_destroy = false
  tags          = { Name = "cloudshift-parth-backups" }
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket                  = aws_s3_bucket.backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_iam_role" "application" {
  name = "cloudshift-parth-application"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "backup_access" {
  name = "cloudshift-parth-backup-access"
  role = aws_iam_role.application.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
      Resource = [aws_s3_bucket.backups.arn, "${aws_s3_bucket.backups.arn}/*"]
    }]
  })
}

resource "aws_iam_instance_profile" "application" {
  name = "cloudshift-parth-application"
  role = aws_iam_role.application.name
}

resource "aws_instance" "application" {
  ami                    = data.aws_ami.amazon_linux_arm64.id
  instance_type          = var.application_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.application.id]
  iam_instance_profile   = aws_iam_instance_profile.application.name
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  root_block_device {
    encrypted   = true
    volume_size = 16
    volume_type = "gp3"
  }
  tags = { Name = "cloudshift-parth-application" }
}

resource "aws_cloudwatch_log_group" "application" {
  name              = "/cloudshift-parth/application"
  retention_in_days = 14
}
