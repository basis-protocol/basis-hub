//! Basis Provenance — TLSNotary proof pipeline
//!
//! Generates MPC-TLS proofs for all data sources feeding Basis Protocol indices.
//! V7.8 constitution: 4 operational sources + static component sources.
//!
//! Architecture:
//!   source registry (YAML) → per-category prover → R2 storage → DB registration
//!
//! Static source categories:
//!   A: GitHub API (audit reports, security docs) — JSON, small payload
//!   B: Protocol APIs (operator stats, etc.) — JSON, moderate payload
//!   C: HTML documentation sites — Range header, first 16KB
//!   D: PDF documents (audit reports) — Range header or HEAD-only

pub mod attestation;
pub mod config;
pub mod prover;
pub mod source;
pub mod storage;
pub mod strategy;
