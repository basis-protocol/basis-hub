//! secp256k1 self-attestation — signs proof hashes with the attestor's private key.
//!
//! V7.8 constitution: Basis self-attests all proofs with a secp256k1 key.
//! The public key is published at /api/provenance/attestor-pubkey.
//! Anyone can verify proofs independently.

use anyhow::{Context, Result};
use k256::ecdsa::{signature::Signer, Signature, SigningKey, VerifyingKey};
use sha2::{Digest, Sha256};

/// Self-attestation signer using secp256k1.
#[derive(Clone)]
pub struct Attestor {
    signing_key: SigningKey,
    public_key_hex: String,
}

impl Attestor {
    /// Create an attestor from a hex-encoded private key.
    pub fn from_hex(private_key_hex: &str) -> Result<Self> {
        let key_bytes = hex::decode(private_key_hex.trim_start_matches("0x"))
            .context("Invalid hex in attestor private key")?;
        let signing_key = SigningKey::from_slice(&key_bytes)
            .context("Invalid secp256k1 private key")?;
        let verifying_key = VerifyingKey::from(&signing_key);
        let public_key_hex = hex::encode(verifying_key.to_sec1_bytes());

        Ok(Self {
            signing_key,
            public_key_hex,
        })
    }

    /// Generate a new random attestor (for testing or initial setup).
    pub fn generate() -> Self {
        let signing_key = SigningKey::random(&mut rand::thread_rng());
        let verifying_key = VerifyingKey::from(&signing_key);
        let public_key_hex = hex::encode(verifying_key.to_sec1_bytes());

        Self {
            signing_key,
            public_key_hex,
        }
    }

    /// The attestor's public key in hex (published at the API endpoint).
    pub fn public_key_hex(&self) -> &str {
        &self.public_key_hex
    }

    /// Sign a message (typically a proof hash).
    pub fn sign(&self, message: &[u8]) -> String {
        let signature: Signature = self.signing_key.sign(message);
        hex::encode(signature.to_bytes())
    }

    /// Compute attestation hash: SHA-256(response_hash || proof_hash || timestamp).
    /// This is the canonical hash stored in the provenance_proofs table.
    pub fn compute_attestation_hash(
        &self,
        response_hash: &str,
        proof_hash: &str,
        timestamp: &str,
    ) -> String {
        let mut hasher = Sha256::new();
        hasher.update(response_hash.as_bytes());
        hasher.update(proof_hash.as_bytes());
        hasher.update(timestamp.as_bytes());
        hasher.update(self.public_key_hex.as_bytes());
        format!("0x{}", hex::encode(hasher.finalize()))
    }
}

/// Compute SHA-256 hash of arbitrary bytes, returned as 0x-prefixed hex.
pub fn sha256_hex(data: &[u8]) -> String {
    let hash = Sha256::digest(data);
    format!("0x{}", hex::encode(hash))
}

/// Compute combined evidence hash: SHA-256(proof.bin || screenshot.png || snapshot.html).
/// Used for static_evidence records where all three evidence types exist.
pub fn combined_evidence_hash(proof_bin: &[u8], screenshot: &[u8], snapshot: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(proof_bin);
    hasher.update(screenshot);
    hasher.update(snapshot);
    format!("0x{}", hex::encode(hasher.finalize()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_attestor_roundtrip() {
        let attestor = Attestor::generate();
        assert!(!attestor.public_key_hex().is_empty());

        let hash = attestor.compute_attestation_hash(
            "0xabc123",
            "0xdef456",
            "2026-04-12T00:00:00Z",
        );
        assert!(hash.starts_with("0x"));
        assert_eq!(hash.len(), 66); // 0x + 64 hex chars
    }

    #[test]
    fn test_sha256_hex() {
        let hash = sha256_hex(b"hello");
        assert!(hash.starts_with("0x"));
        assert_eq!(hash.len(), 66);
    }
}
