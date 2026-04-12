//! Basis Provenance CLI — run TLSNotary proof sessions for static component sources.
//!
//! Usage:
//!   basis-provenance --config static_sources.yaml                    # Prove all sources
//!   basis-provenance --config static_sources.yaml --category github_api   # Category A only
//!   basis-provenance --config static_sources.yaml --entity wormhole       # Single entity
//!   basis-provenance --config static_sources.yaml --dry-run               # Show plan, no proofs

use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::Parser;

use basis_provenance::config::ProvenanceConfig;
use basis_provenance::prover::{register_proof_with_api, ProofStatus, Prover};
use basis_provenance::source::SourceCategory;

#[derive(Parser, Debug)]
#[command(name = "basis-provenance", version, about = "TLSNotary provenance pipeline for static component sources")]
struct Cli {
    /// Path to the static sources YAML config file.
    #[arg(short, long, default_value = "static_sources.yaml")]
    config: PathBuf,

    /// Only prove sources in this category (github_api, protocol_api, html_docs, pdf_document).
    #[arg(long)]
    category: Option<String>,

    /// Only prove sources for this entity (e.g., wormhole, aave).
    #[arg(long)]
    entity: Option<String>,

    /// Show what would be proved without running any sessions.
    #[arg(long)]
    dry_run: bool,

    /// Register proofs with the basis-hub API after proving.
    #[arg(long, default_value = "true")]
    register: bool,

    /// JSON output (for machine consumption by the Python worker).
    #[arg(long)]
    json: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "basis_provenance=info".into()),
        )
        .init();

    let cli = Cli::parse();

    // Load configuration
    let mut config = ProvenanceConfig::load(&cli.config)
        .context("Failed to load provenance config")?;

    // Filter by category if specified
    if let Some(cat_str) = &cli.category {
        let category = parse_category(cat_str)?;
        config.static_sources.retain(|s| s.category == category);
        tracing::info!(category = %cat_str, count = config.static_sources.len(), "Filtered by category");
    }

    // Filter by entity if specified
    if let Some(entity) = &cli.entity {
        config.static_sources.retain(|s| s.entity == *entity);
        tracing::info!(entity = %entity, count = config.static_sources.len(), "Filtered by entity");
    }

    // Dry run: show plan and exit
    if cli.dry_run {
        print_plan(&config);
        return Ok(());
    }

    // Validate we have credentials
    if config.attestor_private_key.is_empty() {
        anyhow::bail!("ATTESTOR_PRIVATE_KEY environment variable is required");
    }

    // Run the prover
    let prover = Prover::new(config.clone()).await?;
    let summary = prover.prove_all_static().await?;

    // Register successful proofs with the API
    if cli.register && !config.admin_key.is_empty() {
        for outcome in &summary.results {
            if let (ProofStatus::Success | ProofStatus::PartialSuccess, Some(result)) =
                (&outcome.status, &outcome.proof_result)
            {
                let source = config
                    .static_sources
                    .iter()
                    .find(|s| s.url == outcome.url)
                    .expect("source must exist");

                if let Err(e) = register_proof_with_api(
                    &config.registration_endpoint,
                    &config.admin_key,
                    source,
                    result,
                )
                .await
                {
                    tracing::error!(url = %outcome.url, error = %e, "Failed to register proof");
                }
            }
        }
    }

    // Output summary
    if cli.json {
        println!("{}", serde_json::to_string_pretty(&summary)?);
    } else {
        print_summary(&summary);
    }

    // Exit with error code if any sources failed
    if summary.failed > 0 {
        std::process::exit(1);
    }

    Ok(())
}

fn parse_category(s: &str) -> Result<SourceCategory> {
    match s {
        "github_api" => Ok(SourceCategory::GithubApi),
        "protocol_api" => Ok(SourceCategory::ProtocolApi),
        "html_docs" => Ok(SourceCategory::HtmlDocs),
        "pdf_document" => Ok(SourceCategory::PdfDocument),
        "operational" => Ok(SourceCategory::Operational),
        _ => anyhow::bail!(
            "Unknown category: {}. Use: github_api, protocol_api, html_docs, pdf_document",
            s
        ),
    }
}

fn print_plan(config: &ProvenanceConfig) {
    println!("=== Basis Provenance — Dry Run ===");
    println!("Total sources: {}", config.static_sources.len());
    println!("Unique URLs:   {}", config.unique_source_count());
    println!();

    let categories = [
        ("Category A (GitHub API)", SourceCategory::GithubApi),
        ("Category B (Protocol API)", SourceCategory::ProtocolApi),
        ("Category C (HTML Docs)", SourceCategory::HtmlDocs),
        ("Category D (PDF Documents)", SourceCategory::PdfDocument),
    ];

    for (label, cat) in &categories {
        let sources = config.sources_by_category(*cat);
        if sources.is_empty() {
            continue;
        }
        println!("{label}: {} sources", sources.len());
        for s in &sources {
            let range_note = if s.use_range_header() {
                format!(" [Range: 0-{}]", s.effective_max_bytes() - 1)
            } else {
                String::new()
            };
            let method = s.method.as_deref().unwrap_or("GET");
            println!(
                "  {method} {}{range_note}",
                s.url,
            );
            println!(
                "    -> {}/{}: {:?}",
                s.index_id, s.entity, s.components
            );
        }
        println!();
    }

    // Estimate time
    let estimated_seconds = config.static_sources.len() as f64 * 3.0;
    println!(
        "Estimated time: {:.1} minutes ({} sources x ~3s/proof)",
        estimated_seconds / 60.0,
        config.static_sources.len()
    );
}

fn print_summary(summary: &basis_provenance::prover::ProvingRunSummary) {
    println!("=== Basis Provenance — Run Summary ===");
    println!("Duration:    {:.1}s", summary.duration_seconds);
    println!("Total:       {}", summary.total_sources);
    println!("Successful:  {}", summary.successful);
    println!("Failed:      {}", summary.failed);
    println!("Skipped:     {}", summary.skipped);
    println!();

    if summary.failed > 0 {
        println!("Failed sources:");
        for r in &summary.results {
            if matches!(r.status, ProofStatus::Failed) {
                println!(
                    "  {} ({}): {}",
                    r.url,
                    r.entity,
                    r.error.as_deref().unwrap_or("unknown error")
                );
            }
        }
    }
}
