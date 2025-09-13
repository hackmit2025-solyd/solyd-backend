import boto3
from botocore.exceptions import ClientError
from typing import Dict, Optional
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        self.bucket_name = settings.s3_bucket_name

    def generate_presigned_upload_url(
        self,
        file_key: str,
        content_type: str = "application/octet-stream",
        expires_in: int = 3600,
    ) -> Dict[str, str]:
        """Generate a presigned URL for uploading a file to S3"""
        try:
            response = self.s3_client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=file_key,
                Fields={"Content-Type": content_type},
                Conditions=[
                    {"Content-Type": content_type},
                    ["content-length-range", 0, 100 * 1024 * 1024],  # Max 100MB
                ],
                ExpiresIn=expires_in,
            )

            return {
                "url": response["url"],
                "fields": response["fields"],
                "file_key": file_key,
            }
        except ClientError as e:
            logger.error(f"Error generating presigned upload URL: {e}")
            raise

    def generate_presigned_download_url(
        self, file_key: str, expires_in: int = 3600
    ) -> str:
        """Generate a presigned URL for downloading a file from S3"""
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": file_key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned download URL: {e}")
            raise

    def delete_file(self, file_key: str) -> bool:
        """Delete a file from S3"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_key)
            return True
        except ClientError as e:
            logger.error(f"Error deleting file from S3: {e}")
            return False

    def file_exists(self, file_key: str) -> bool:
        """Check if a file exists in S3"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=file_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            logger.error(f"Error checking file existence: {e}")
            raise

    def get_file_metadata(self, file_key: str) -> Optional[Dict]:
        """Get metadata for a file in S3"""
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=file_key)
            return {
                "content_type": response.get("ContentType"),
                "content_length": response.get("ContentLength"),
                "last_modified": response.get("LastModified"),
                "etag": response.get("ETag"),
                "metadata": response.get("Metadata", {}),
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            logger.error(f"Error getting file metadata: {e}")
            raise
