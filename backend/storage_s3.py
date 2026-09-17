"""Portable S3-compatible object storage (boto3). Works with AWS S3, Cloudflare R2,
MinIO, Backblaze B2, DigitalOcean Spaces, etc. All config via environment variables:

  S3_BUCKET            (required)
  S3_ACCESS_KEY_ID     (required)
  S3_SECRET_ACCESS_KEY (required)
  S3_REGION            (optional, default us-east-1)
  S3_ENDPOINT_URL      (optional; leave empty for AWS S3, set for R2/MinIO/etc.)
"""
import os
import boto3
from botocore.client import Config

PREFIX = "shitpost-studio"
_client_cache = None


def configured() -> bool:
    return all(
        os.environ.get(k)
        for k in ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
    )


def _client():
    global _client_cache
    if _client_cache is None:
        kwargs = dict(
            aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
            region_name=os.environ.get("S3_REGION") or "us-east-1",
            config=Config(signature_version="s3v4"),
        )
        endpoint = os.environ.get("S3_ENDPOINT_URL")
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        _client_cache = boto3.client("s3", **kwargs)
    return _client_cache


def _bucket() -> str:
    return os.environ["S3_BUCKET"]


def audio_key(job_id: str, ext: str) -> str:
    return f"{PREFIX}/jobs/{job_id}/input{ext}"


def output_key(job_id: str) -> str:
    return f"{PREFIX}/jobs/{job_id}/output.mp4"


def put_bytes(key: str, data: bytes, content_type: str) -> str:
    _client().put_object(Bucket=_bucket(), Key=key, Body=data, ContentType=content_type)
    return key


def download_to(key: str, dest) -> str:
    _client().download_file(_bucket(), key, str(dest))
    return str(dest)


def upload_file(path, key: str, content_type: str) -> str:
    _client().upload_file(str(path), _bucket(), key, ExtraArgs={"ContentType": content_type})
    return key


def presigned_url(key: str, expires: int = 3600, download_name: str = None) -> str:
    params = {"Bucket": _bucket(), "Key": key}
    if download_name:
        params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
    return _client().generate_presigned_url("get_object", Params=params, ExpiresIn=expires)
