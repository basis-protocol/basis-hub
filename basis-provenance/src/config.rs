//! Source registry configuration — loads static sources from YAML.

use std::path::Path;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

use crate::source::StaticSource;

/// Top-level configuration for the provenance pipeline.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProvenanceConfig {
    /// secp256k1 private key hex (loaded from env, never serialized).
    #[serde(skip)]
    pub attestor_private_key: String,

    /// R2/S3 storage configuration.
    pub storage: StorageConfig,

    /// API registration endpoint (basis-hub).
    pub registration_endpoint: String,

    /// Admin key for registering proofs via the API.
    #[serde(skip)]
    pub admin_key: String,

    /// Static component sources to notarize.
    pub static_sources: Vec<StaticSource>,
}

/// R2/S3-compatible storage configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StorageConfig {
    /// S3-compatible endpoint URL (Cloudflare R2).
    pub endpoint_url: String,
    /// Bucket name.
    pub bucket: String,
    /// Public URL prefix for constructing proof URLs.
    pub public_url_prefix: String,
    /// Region (default: auto for R2).
    #[serde(default = "default_region")]
    pub region: String,
}

fn default_region() -> String {
    "auto".into()
}

impl ProvenanceConfig {
    /// Load configuration from a YAML file, with secrets from environment.
    pub fn load(config_path: &Path) -> Result<Self> {
        let contents = std::fs::read_to_string(config_path)
            .with_context(|| format!("Failed to read config: {}", config_path.display()))?;
        let mut config: ProvenanceConfig = serde_yaml::from_str(&contents)
            .with_context(|| "Failed to parse provenance config YAML")?;

        // Load secrets from environment
        config.attestor_private_key = std::env::var("ATTESTOR_PRIVATE_KEY")
            .unwrap_or_default();
        config.admin_key = std::env::var("ADMIN_KEY")
            .unwrap_or_default();

        // Resolve API key env vars for sources that need them
        for source in &mut config.static_sources {
            if let Some(env_var) = &source.api_key_env {
                if std::env::var(env_var).is_err() {
                    tracing::warn!(
                        url = %source.url,
                        env_var = %env_var,
                        "API key env var not set for source"
                    );
                }
            }
        }

        Ok(config)
    }

    /// Get sources filtered by category.
    pub fn sources_by_category(&self, category: crate::source::SourceCategory) -> Vec<&StaticSource> {
        self.static_sources
            .iter()
            .filter(|s| s.category == category)
            .collect()
    }

    /// Total count of unique source URLs.
    pub fn unique_source_count(&self) -> usize {
        let mut urls: Vec<&str> = self.static_sources.iter().map(|s| s.url.as_str()).collect();
        urls.sort();
        urls.dedup();
        urls.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_minimal_config() {
        let yaml = r#"
storage:
  endpoint_url: "https://account.r2.cloudflarestorage.com"
  bucket: "basis-provenance"
  public_url_prefix: "https://provenance.basis.io"
registration_endpoint: "https://api.basis.io/api/provenance/register"
static_sources:
  - url: "https://api.github.com/repos/wormhole-foundation/wormhole/contents/SECURITY.md"
    category: github_api
    index_id: bri
    entity: wormhole
    components: ["bridge_audit_count", "bug_bounty_size"]
    max_bytes: 32768
"#;
        let config: ProvenanceConfig = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(config.static_sources.len(), 1);
        assert_eq!(config.static_sources[0].entity, "wormhole");
        assert_eq!(config.unique_source_count(), 1);
    }
}
