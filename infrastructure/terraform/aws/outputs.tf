output "vpc_id" { value = aws_vpc.cloudshift.id }
output "application_public_ip" { value = aws_instance.application.public_ip }
output "database_endpoint" { value = aws_db_instance.target.address }
output "backup_bucket" { value = aws_s3_bucket.backups.id }
