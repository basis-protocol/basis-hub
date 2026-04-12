//! Source types and category definitions for TLSNotary proving.

use serde::{Deserialize, Serialize};

/// Category of a static component source — determines the proving strategy.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceCategory {
    /// Category A: GitHub API endpoints (JSON, small payload, <32KB)
    GithubApi,
    /// Category B: Protocol API endpoints (JSON, moderate payload)
    ProtocolApi,
    /// Category C: HTML documentation sites (Range: bytes=0-16383)
    HtmlDocs,
    /// Category D: PDF documents (Range header or HEAD-only)
    PdfDocument,
    /// Operational sources (CoinGecko, DeFiLlama, Etherscan) — existing V7.8 pipeline
    Operational,
}

impl SourceCategory {
    /// Default max bytes for this category.
    pub fn default_max_bytes(&self) -> u32 {
        match self {
            Self::GithubApi => 32_768,
            Self::ProtocolApi => 32_768,
            Self::HtmlDocs => 16_384,
            Self::PdfDocument => 16_384,
            Self::Operational => 2_048,
        }
    }

    /// Whether this category requires Range headers.
    pub fn needs_range_header(&self) -> bool {
        matches!(self, Self::HtmlDocs | Self::PdfDocument)
    }
}

/// A static component source to be notarized.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StaticSource {
    /// Full URL to notarize.
    pub url: String,
    /// Source category — determines proving strategy.
    pub category: SourceCategory,
    /// Which index this source feeds (e.g., "bri", "sii", "psi").
    pub index_id: String,
    /// Entity slug (e.g., "wormhole", "aave", "circle").
    pub entity: String,
    /// Components extracted from this source.
    pub components: Vec<String>,
    /// Maximum bytes to capture (overrides category default if set).
    pub max_bytes: Option<u32>,
    /// Whether to use Range headers (overrides category default if set).
    pub range_header: Option<bool>,
    /// Optional API key header name (for Category B sources).
    pub api_key_header: Option<String>,
    /// Optional API key env var name.
    pub api_key_env: Option<String>,
    /// HTTP method override (default: GET, Category D may use HEAD).
    pub method: Option<String>,
}

impl StaticSource {
    /// Effective max bytes (source override or category default).
    pub fn effective_max_bytes(&self) -> u32 {
        self.max_bytes.unwrap_or_else(|| self.category.default_max_bytes())
    }

    /// Whether this source needs Range headers.
    pub fn use_range_header(&self) -> bool {
        self.range_header.unwrap_or_else(|| self.category.needs_range_header())
    }

    /// The domain portion of the URL (for proof metadata).
    pub fn domain(&self) -> String {
        reqwest::Url::parse(&self.url)
            .ok()
            .and_then(|u| u.host_str().map(String::from))
            .unwrap_or_else(|| "unknown".into())
    }

    /// R2 storage prefix for this source's proofs.
    pub fn r2_prefix(&self, timestamp: &str) -> String {
        format!(
            "proofs/static/{}/{}/{}/{}",
            self.index_id, self.entity, self.components.first().unwrap_or(&"unknown".into()), timestamp
        )
    }
}

/// Result of a successful TLSNotary proof session.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProofResult {
    /// SHA-256 hash of the captured response body.
    pub response_hash: String,
    /// SHA-256 hash of the TLSNotary attestation (proof.bin).
    pub attestation_hash: String,
    /// R2 URL where proof.bin is stored.
    pub proof_url: String,
    /// secp256k1 public key of the attestor.
    pub attestor_pubkey: String,
    /// Timestamp when the proof was generated.
    pub proved_at: chrono::DateTime<chrono::Utc>,
    /// HTTP status code of the captured response.
    pub http_status: u16,
    /// Byte range captured (e.g., "0-16383") or "full".
    pub captured_range: String,
    /// Size of the proof in bytes.
    pub proof_size_bytes: u64,
    /// Size of the captured response body.
    pub response_size_bytes: u64,
    /// Source URL that was proved.
    pub source_url: String,
    /// Source category.
    pub category: SourceCategory,
}

/// Proof artifacts stored in R2.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProofArtifacts {
    /// TLSNotary attestation binary.
    pub proof_bin: Vec<u8>,
    /// Captured (possibly truncated) response body.
    pub response_body: Vec<u8>,
    /// Metadata JSON.
    pub metadata: ProofMetadata,
}

/// Metadata stored alongside proof artifacts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProofMetadata {
    pub url: String,
    pub range: Option<String>,
    pub category: SourceCategory,
    pub captured_at: chrono::DateTime<chrono::Utc>,
    pub attestor_pubkey: String,
    pub response_hash: String,
    pub attestation_hash: String,
    pub http_status: u16,
    pub response_size_bytes: u64,
    pub index_id: String,
    pub entity: String,
    pub components: Vec<String>,
}
