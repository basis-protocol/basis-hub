//! R2/S3-compatible proof storage.
//!
//! Proof artifacts are stored in Cloudflare R2 (S3-compatible API):
//!   proofs/static/{index_id}/{entity}/{component}/{timestamp}/
//!     proof.bin          — TLSNotary attestation
//!     response_body.bin  — captured (possibly truncated) response
//!     metadata.json      — URL, range, category, captured_at, attestor_key

use anyhow::{Context, Result};
use aws_sdk_s3::Client as S3Client;
use aws_sdk_s3::primitives::ByteStream;

use crate::config::StorageConfig;
use crate::source::{ProofArtifacts, ProofMetadata};

/// R2 storage client for proof artifacts.
pub struct ProofStorage {
    client: S3Client,
    bucket: String,
    public_url_prefix: String,
}

impl ProofStorage {
    /// Create a new storage client from configuration.
    pub async fn new(config: &StorageConfig) -> Result<Self> {
        let sdk_config = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .endpoint_url(&config.endpoint_url)
            .region(aws_config::Region::new(config.region.clone()))
            .load()
            .await;

        let client = S3Client::new(&sdk_config);

        Ok(Self {
            client,
            bucket: config.bucket.clone(),
            public_url_prefix: config.public_url_prefix.clone(),
        })
    }

    /// Upload proof artifacts to R2 and return public URLs.
    pub async fn upload_proof(
        &self,
        prefix: &str,
        artifacts: &ProofArtifacts,
    ) -> Result<ProofUrls> {
        // Upload proof.bin
        let proof_key = format!("{prefix}/proof.bin");
        self.put_object(&proof_key, &artifacts.proof_bin, "application/octet-stream")
            .await
            .context("Failed to upload proof.bin")?;

        // Upload response_body.bin
        let response_key = format!("{prefix}/response_body.bin");
        self.put_object(&response_key, &artifacts.response_body, "application/octet-stream")
            .await
            .context("Failed to upload response_body.bin")?;

        // Upload metadata.json
        let metadata_key = format!("{prefix}/metadata.json");
        let metadata_json = serde_json::to_vec_pretty(&artifacts.metadata)
            .context("Failed to serialize metadata")?;
        self.put_object(&metadata_key, &metadata_json, "application/json")
            .await
            .context("Failed to upload metadata.json")?;

        Ok(ProofUrls {
            proof_url: self.public_url(&proof_key),
            response_url: self.public_url(&response_key),
            metadata_url: self.public_url(&metadata_key),
        })
    }

    /// Put an object into the R2 bucket.
    async fn put_object(&self, key: &str, body: &[u8], content_type: &str) -> Result<()> {
        self.client
            .put_object()
            .bucket(&self.bucket)
            .key(key)
            .body(ByteStream::from(body.to_vec()))
            .content_type(content_type)
            .send()
            .await
            .context("R2 put_object failed")?;

        tracing::debug!(key = %key, size = body.len(), "Uploaded to R2");
        Ok(())
    }

    /// Construct a public URL for an R2 key.
    fn public_url(&self, key: &str) -> String {
        format!("{}/{}", self.public_url_prefix.trim_end_matches('/'), key)
    }
}

/// URLs returned after uploading proof artifacts.
#[derive(Debug, Clone)]
pub struct ProofUrls {
    pub proof_url: String,
    pub response_url: String,
    pub metadata_url: String,
}
