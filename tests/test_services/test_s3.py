from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
from app.services.s3 import S3Service


class TestS3Service:
    @patch("app.services.s3.settings")
    @patch("boto3.client")
    def test_init(self, mock_boto_client, mock_settings):
        """Test S3Service initialization"""
        mock_settings.aws_access_key_id = "test-key"
        mock_settings.aws_secret_access_key = "test-secret"
        mock_settings.aws_region = "us-east-1"
        mock_settings.s3_bucket_name = "test-bucket"

        service = S3Service()

        mock_boto_client.assert_called_once_with(
            "s3",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
            region_name="us-east-1",
        )
        assert service.bucket_name == "test-bucket"

    @patch("boto3.client")
    def test_generate_presigned_upload_url(self, mock_boto_client):
        """Test presigned upload URL generation"""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.generate_presigned_post.return_value = {
            "url": "https://s3.amazonaws.com/test-bucket",
            "fields": {"key": "test-key", "Content-Type": "text/plain"},
        }

        service = S3Service()
        result = service.generate_presigned_upload_url("test-file.txt", "text/plain")

        assert result["url"] == "https://s3.amazonaws.com/test-bucket"
        assert result["fields"]["key"] == "test-key"
        assert result["file_key"] == "test-file.txt"

        mock_s3.generate_presigned_post.assert_called_once()

    @patch("boto3.client")
    def test_generate_presigned_download_url(self, mock_boto_client):
        """Test presigned download URL generation"""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = (
            "https://s3.amazonaws.com/test-bucket/test-file.txt?signature=xyz"
        )

        service = S3Service()
        url = service.generate_presigned_download_url("test-file.txt")

        assert "https://s3.amazonaws.com" in url
        assert "test-file.txt" in url

        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": service.bucket_name, "Key": "test-file.txt"},
            ExpiresIn=3600,
        )

    @patch("boto3.client")
    def test_delete_file_success(self, mock_boto_client):
        """Test successful file deletion"""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        service = S3Service()
        result = service.delete_file("test-file.txt")

        assert result is True
        mock_s3.delete_object.assert_called_once_with(
            Bucket=service.bucket_name, Key="test-file.txt"
        )

    @patch("boto3.client")
    def test_delete_file_failure(self, mock_boto_client):
        """Test file deletion failure"""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.delete_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "delete_object"
        )

        service = S3Service()
        result = service.delete_file("test-file.txt")

        assert result is False

    @patch("boto3.client")
    def test_file_exists_true(self, mock_boto_client):
        """Test file existence check - file exists"""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {"ContentLength": 1234}

        service = S3Service()
        exists = service.file_exists("test-file.txt")

        assert exists is True
        mock_s3.head_object.assert_called_once_with(
            Bucket=service.bucket_name, Key="test-file.txt"
        )

    @patch("boto3.client")
    def test_file_exists_false(self, mock_boto_client):
        """Test file existence check - file doesn't exist"""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404"}}, "head_object"
        )

        service = S3Service()
        exists = service.file_exists("test-file.txt")

        assert exists is False

    @patch("boto3.client")
    def test_get_file_metadata_success(self, mock_boto_client):
        """Test getting file metadata"""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {
            "ContentType": "text/plain",
            "ContentLength": 1234,
            "LastModified": "2024-01-01",
            "ETag": "abc123",
            "Metadata": {"custom": "value"},
        }

        service = S3Service()
        metadata = service.get_file_metadata("test-file.txt")

        assert metadata["content_type"] == "text/plain"
        assert metadata["content_length"] == 1234
        assert metadata["metadata"]["custom"] == "value"

    @patch("boto3.client")
    def test_get_file_metadata_not_found(self, mock_boto_client):
        """Test getting metadata for non-existent file"""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404"}}, "head_object"
        )

        service = S3Service()
        metadata = service.get_file_metadata("test-file.txt")

        assert metadata is None
