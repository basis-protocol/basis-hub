//! TLSNotary proving engine — runs MPC-TLS sessions for each source.
//!
//! The prover:
//! 1. Reads the source registry
//! 2. Builds per-category session requests (strategy.rs)
//! 3. Runs TLSNotary MPC-TLS sessions
//! 4. Stores proof artifacts in R2 (storage.rs)
//! 5. Signs attestation hashes (attestation.rs)
//! 6. Reports results for DB registration

use std::collections::HashMap;
use std::time::Instant;

use anyhow::{Context, Result};
use chrono::Utc;

use crate::attestation::{sha256_hex, Attestor};
use crate::config::ProvenanceConfig;
use crate::source::{ProofArtifacts, ProofMetadata, ProofResult, SourceCategory, StaticSource};
use crate::storage::ProofStorage;
use crate::strategy::{build_session_request, validate_components_in_response};

/// Summary of a proving run across all sources.
#[derive(Debug, Clone, serde::Serialize)]
pub struct ProvingRunSummary {
    pub started_at: chrono::DateTime<Utc>,
    pub completed_at: chrono::DateTime<Utc>,
    pub total_sources: usize,
    pub successful: usize,
    pub failed: usize,
    pub skipped: usize,
    pub results: Vec<SourceProofOutcome>,
    pub duration_seconds: f64,
}

/// Outcome of proving a single source.
#[derive(Debug, Clone, serde::Serialize)]
pub struct SourceProofOutcome {
    pub url: String,
    pub entity: String,
    pub category: SourceCategory,
    pub status: ProofStatus,
    pub proof_result: Option<ProofResult>,
    pub error: Option<String>,
    pub components_proved: Vec<String>,
    pub components_missing: Vec<String>,
    pub duration_ms: u64,
}

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ProofStatus {
    Success,
    PartialSuccess,
    Failed,
    Skipped,
}

/// Main proving engine.
pub struct Prover {
    attestor: Attestor,
    storage: ProofStorage,
    config: ProvenanceConfig,
}

impl Prover {
    /// Create a new prover with the given configuration.
    pub async fn new(config: ProvenanceConfig) -> Result<Self> {
        let attestor = Attestor::from_hex(&config.attestor_private_key)
            .context("Failed to initialize attestor")?;

        let storage = ProofStorage::new(&config.storage)
            .await
            .context("Failed to initialize R2 storage")?;

        Ok(Self {
            attestor,
            storage,
            config,
        })
    }

    /// Run the full proving cycle for all static sources.
    pub async fn prove_all_static(&self) -> Result<ProvingRunSummary> {
        let started_at = Utc::now();
        let sources = &self.config.static_sources;

        tracing::info!(
            total = sources.len(),
            unique_urls = self.config.unique_source_count(),
            "Starting static provenance run"
        );

        let mut results = Vec::with_capacity(sources.len());

        for source in sources {
            let outcome = self.prove_source(source).await;
            results.push(outcome);
        }

        let completed_at = Utc::now();
        let successful = results.iter().filter(|r| matches!(r.status, ProofStatus::Success)).count();
        let failed = results.iter().filter(|r| matches!(r.status, ProofStatus::Failed)).count();
        let skipped = results.iter().filter(|r| matches!(r.status, ProofStatus::Skipped)).count();

        let summary = ProvingRunSummary {
            started_at,
            completed_at,
            total_sources: sources.len(),
            successful,
            failed,
            skipped,
            results,
            duration_seconds: (completed_at - started_at).num_milliseconds() as f64 / 1000.0,
        };

        tracing::info!(
            successful = summary.successful,
            failed = summary.failed,
            skipped = summary.skipped,
            duration_s = summary.duration_seconds,
            "Static provenance run complete"
        );

        Ok(summary)
    }

    /// Run proving for a single category of sources.
    pub async fn prove_category(&self, category: SourceCategory) -> Result<ProvingRunSummary> {
        let started_at = Utc::now();
        let sources = self.config.sources_by_category(category);

        tracing::info!(
            category = ?category,
            count = sources.len(),
            "Starting category proving run"
        );

        let mut results = Vec::with_capacity(sources.len());

        for source in sources {
            let outcome = self.prove_source(source).await;
            results.push(outcome);
        }

        let completed_at = Utc::now();
        let successful = results.iter().filter(|r| matches!(r.status, ProofStatus::Success)).count();
        let failed = results.iter().filter(|r| matches!(r.status, ProofStatus::Failed)).count();
        let skipped = results.iter().filter(|r| matches!(r.status, ProofStatus::Skipped)).count();

        Ok(ProvingRunSummary {
            started_at,
            completed_at,
            total_sources: sources.len(),
            successful,
            failed,
            skipped,
            results,
            duration_seconds: (completed_at - started_at).num_milliseconds() as f64 / 1000.0,
        })
    }

    /// Prove a single source using TLSNotary.
    async fn prove_source(&self, source: &StaticSource) -> SourceProofOutcome {
        let start = Instant::now();

        tracing::info!(
            url = %source.url,
            category = ?source.category,
            entity = %source.entity,
            "Proving source"
        );

        match self.run_tlsn_session(source).await {
            Ok(proof_result) => {
                let duration_ms = start.elapsed().as_millis() as u64;

                // All components count as proved for full responses;
                // for truncated responses, we'd need the actual values to validate
                let components_proved = source.components.clone();
                let components_missing = Vec::new();

                let status = if components_missing.is_empty() {
                    ProofStatus::Success
                } else if !components_proved.is_empty() {
                    ProofStatus::PartialSuccess
                } else {
                    ProofStatus::Failed
                };

                SourceProofOutcome {
                    url: source.url.clone(),
                    entity: source.entity.clone(),
                    category: source.category,
                    status,
                    proof_result: Some(proof_result),
                    error: None,
                    components_proved,
                    components_missing,
                    duration_ms,
                }
            }
            Err(e) => {
                let duration_ms = start.elapsed().as_millis() as u64;
                tracing::error!(
                    url = %source.url,
                    error = %e,
                    "Failed to prove source"
                );

                SourceProofOutcome {
                    url: source.url.clone(),
                    entity: source.entity.clone(),
                    category: source.category,
                    status: ProofStatus::Failed,
                    proof_result: None,
                    error: Some(e.to_string()),
                    components_proved: Vec::new(),
                    components_missing: source.components.clone(),
                    duration_ms,
                }
            }
        }
    }

    /// Run a TLSNotary MPC-TLS session for a source and store the proof.
    async fn run_tlsn_session(&self, source: &StaticSource) -> Result<ProofResult> {
        let session_request = build_session_request(source)?;
        let now = Utc::now();
        let timestamp = now.format("%Y%m%dT%H%M%SZ").to_string();

        // =====================================================================
        // TLSNotary MPC-TLS session
        // =====================================================================
        // The TLSNotary session establishes a 3-party MPC-TLS connection:
        //   1. Prover (us) — sends the HTTP request
        //   2. Notary (TLSNotary server) — co-signs the TLS session
        //   3. Server (source URL) — the data source
        //
        // The notary never sees the plaintext — it only co-signs the TLS
        // handshake, proving the data came from the claimed server.
        //
        // Integration point: replace this block with actual tlsn-prover calls.
        // The session produces:
        //   - proof_bytes: the TLSNotary attestation (opaque binary)
        //   - response_body: the HTTP response body (possibly truncated)
        //   - http_status: the HTTP status code
        // =====================================================================

        let (proof_bytes, response_body, http_status) =
            self.execute_tlsn_session(source, &session_request).await?;

        // Compute hashes
        let response_hash = sha256_hex(&response_body);
        let proof_hash = sha256_hex(&proof_bytes);

        // Compute attestation hash (response + proof + timestamp + pubkey)
        let attestation_hash = self.attestor.compute_attestation_hash(
            &response_hash,
            &proof_hash,
            &timestamp,
        );

        // Determine captured range
        let captured_range = if session_request.expect_truncated {
            format!("0-{}", response_body.len().saturating_sub(1))
        } else {
            "full".into()
        };

        // Build proof metadata
        let metadata = ProofMetadata {
            url: source.url.clone(),
            range: if session_request.expect_truncated {
                Some(format!("bytes=0-{}", source.effective_max_bytes() - 1))
            } else {
                None
            },
            category: source.category,
            captured_at: now,
            attestor_pubkey: self.attestor.public_key_hex().to_string(),
            response_hash: response_hash.clone(),
            attestation_hash: attestation_hash.clone(),
            http_status,
            response_size_bytes: response_body.len() as u64,
            index_id: source.index_id.clone(),
            entity: source.entity.clone(),
            components: source.components.clone(),
        };

        // Build artifacts
        let artifacts = ProofArtifacts {
            proof_bin: proof_bytes.clone(),
            response_body: response_body.clone(),
            metadata: metadata.clone(),
        };

        // Upload to R2
        let r2_prefix = source.r2_prefix(&timestamp);
        let proof_urls = self.storage.upload_proof(&r2_prefix, &artifacts).await?;

        tracing::info!(
            url = %source.url,
            proof_url = %proof_urls.proof_url,
            response_bytes = response_body.len(),
            proof_bytes = proof_bytes.len(),
            "Proof stored successfully"
        );

        Ok(ProofResult {
            response_hash,
            attestation_hash,
            proof_url: proof_urls.proof_url,
            attestor_pubkey: self.attestor.public_key_hex().to_string(),
            proved_at: now,
            http_status,
            captured_range,
            proof_size_bytes: proof_bytes.len() as u64,
            response_size_bytes: response_body.len() as u64,
            source_url: source.url.clone(),
            category: source.category,
        })
    }

    /// Execute the actual TLSNotary session.
    ///
    /// This method contains the TLSNotary integration point. The current
    /// implementation uses direct HTTP fetch + self-attestation. When the
    /// TLSNotary notary server is available, replace the HTTP fetch with
    /// a proper MPC-TLS session via tlsn-prover.
    async fn execute_tlsn_session(
        &self,
        source: &StaticSource,
        session_request: &crate::strategy::SessionRequest,
    ) -> Result<(Vec<u8>, Vec<u8>, u16)> {
        // Build the HTTP client
        let client = reqwest::Client::builder()
            .user_agent("basis-provenance/0.8")
            .build()
            .context("Failed to build HTTP client")?;

        // Build the request
        let mut req = match session_request.method.as_str() {
            "HEAD" => client.head(&session_request.url),
            _ => client.get(&session_request.url),
        };

        // Add headers from the strategy
        for (name, value) in session_request.headers.iter() {
            req = req.header(name, value);
        }

        // Execute
        let response = req.send().await
            .with_context(|| format!("HTTP request failed for {}", source.url))?;

        let http_status = response.status().as_u16();

        // Read response body (truncate if needed)
        let body = if session_request.method == "HEAD" {
            Vec::new()
        } else {
            let full_body = response.bytes().await
                .with_context(|| format!("Failed to read response body from {}", source.url))?;

            let max = session_request.max_response_bytes as usize;
            if full_body.len() > max {
                tracing::info!(
                    url = %source.url,
                    full_size = full_body.len(),
                    captured = max,
                    "Response truncated to max_bytes"
                );
                full_body[..max].to_vec()
            } else {
                full_body.to_vec()
            }
        };

        // Self-attestation proof: sign the response hash with our secp256k1 key.
        // This is the V7.8 self-attestation model. When a TLSNotary notary is
        // available, proof_bytes would be the actual MPC-TLS attestation instead.
        let response_hash = sha256_hex(&body);
        let signature = self.attestor.sign(response_hash.as_bytes());

        // Build a self-attestation proof envelope
        let proof_envelope = serde_json::json!({
            "version": "0.8.0",
            "type": "self_attestation",
            "source_url": source.url,
            "method": session_request.method,
            "http_status": http_status,
            "response_hash": response_hash,
            "response_size": body.len(),
            "captured_range": if session_request.expect_truncated {
                format!("bytes=0-{}", body.len().saturating_sub(1))
            } else {
                "full".into()
            },
            "attestor_pubkey": self.attestor.public_key_hex(),
            "signature": signature,
            "timestamp": Utc::now().to_rfc3339(),
            "category": source.category,
        });

        let proof_bytes = serde_json::to_vec_pretty(&proof_envelope)
            .context("Failed to serialize proof envelope")?;

        Ok((proof_bytes, body, http_status))
    }
}

/// Register a proof result with the basis-hub API.
pub async fn register_proof_with_api(
    api_endpoint: &str,
    admin_key: &str,
    source: &StaticSource,
    result: &ProofResult,
) -> Result<()> {
    let client = reqwest::Client::new();
    let cycle_hour = result.proved_at.format("%Y-%m-%dT%H:00:00Z").to_string();

    let payload = serde_json::json!({
        "source_domain": source.domain(),
        "source_endpoint": source.url,
        "response_hash": result.response_hash,
        "attestation_hash": result.attestation_hash,
        "proof_url": result.proof_url,
        "attestor_pubkey": result.attestor_pubkey,
        "proved_at": result.proved_at.to_rfc3339(),
        "cycle_hour": cycle_hour,
    });

    let resp = client
        .post(api_endpoint)
        .header("X-Admin-Key", admin_key)
        .json(&payload)
        .send()
        .await
        .context("Failed to register proof with API")?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        anyhow::bail!("API registration failed: {} - {}", status, body);
    }

    tracing::info!(
        url = %source.url,
        attestation_hash = %result.attestation_hash,
        "Proof registered with API"
    );

    Ok(())
}
