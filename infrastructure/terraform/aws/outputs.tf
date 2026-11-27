output "vpc_id" { value = aws_vpc.cloudshift.id }
output "application_public_ip" { value = aws_instance.application.public_ip }
output "database_endpoint" { value = aws_db_instance.target.address }
output "backup_bucket" { value = aws_s3_bucket.backups.id }
output "deployment_posture" {
  value = {
    database_publicly_accessible = aws_db_instance.target.publicly_accessible
    database_multi_az            = aws_db_instance.target.multi_az
    backup_retention_days        = aws_db_instance.target.backup_retention_period
    deletion_protection          = aws_db_instance.target.deletion_protection
  }
}
