//! Per-category proving strategies.
//!
//! Each source category requires a different TLSNotary session configuration:
//!   A (GitHub API): Standard session, JSON response, User-Agent required
//!   B (Protocol API): Standard session, may need API key headers
//!   C (HTML docs): Range header, truncated response, verify value in captured bytes
//!   D (PDF docs): Range header for first 16KB, or HEAD-only for existence proof

use anyhow::{Context, Result};
use reqwest::header::{HeaderMap, HeaderValue, ACCEPT, RANGE, USER_AGENT};

use crate::source::{SourceCategory, StaticSource};

/// HTTP request configuration for a TLSNotary session.
#[derive(Debug, Clone)]
pub struct SessionRequest {
    pub url: String,
    pub method: String,
    pub headers: HeaderMap,
    pub max_response_bytes: u32,
    pub expect_truncated: bool,
}

/// Build the session request for a source based on its category.
pub fn build_session_request(source: &StaticSource) -> Result<SessionRequest> {
    match source.category {
        SourceCategory::GithubApi => build_github_api_request(source),
        SourceCategory::ProtocolApi => build_protocol_api_request(source),
        SourceCategory::HtmlDocs => build_html_docs_request(source),
        SourceCategory::PdfDocument => build_pdf_document_request(source),
        SourceCategory::Operational => build_operational_request(source),
    }
}

/// Category A: GitHub API — standard GET, needs User-Agent and Accept headers.
fn build_github_api_request(source: &StaticSource) -> Result<SessionRequest> {
    let mut headers = HeaderMap::new();
    headers.insert(USER_AGENT, HeaderValue::from_static("basis-provenance/0.8"));
    headers.insert(ACCEPT, HeaderValue::from_static("application/vnd.github.v3+json"));

    // GitHub API token if available
    if let Ok(token) = std::env::var("GITHUB_TOKEN") {
        headers.insert(
            "Authorization",
            HeaderValue::from_str(&format!("Bearer {token}"))
                .context("Invalid GitHub token")?,
        );
    }

    Ok(SessionRequest {
        url: source.url.clone(),
        method: "GET".into(),
        headers,
        max_response_bytes: source.effective_max_bytes(),
        expect_truncated: false,
    })
}

/// Category B: Protocol API — standard GET, may need API key header.
fn build_protocol_api_request(source: &StaticSource) -> Result<SessionRequest> {
    let mut headers = HeaderMap::new();
    headers.insert(USER_AGENT, HeaderValue::from_static("basis-provenance/0.8"));
    headers.insert(ACCEPT, HeaderValue::from_static("application/json"));

    // Add API key if configured
    if let (Some(header_name), Some(env_var)) = (&source.api_key_header, &source.api_key_env) {
        if let Ok(api_key) = std::env::var(env_var) {
            headers.insert(
                header_name.as_str(),
                HeaderValue::from_str(&api_key)
                    .context("Invalid API key value")?,
            );
        }
    }

    Ok(SessionRequest {
        url: source.url.clone(),
        method: "GET".into(),
        headers,
        max_response_bytes: source.effective_max_bytes(),
        expect_truncated: false,
    })
}

/// Category C: HTML docs — GET with Range header to capture first 16KB.
fn build_html_docs_request(source: &StaticSource) -> Result<SessionRequest> {
    let max_bytes = source.effective_max_bytes();
    let mut headers = HeaderMap::new();
    headers.insert(USER_AGENT, HeaderValue::from_static("basis-provenance/0.8"));
    headers.insert(ACCEPT, HeaderValue::from_static("text/html"));

    if source.use_range_header() {
        headers.insert(
            RANGE,
            HeaderValue::from_str(&format!("bytes=0-{}", max_bytes - 1))
                .context("Invalid Range header")?,
        );
    }

    Ok(SessionRequest {
        url: source.url.clone(),
        method: "GET".into(),
        headers,
        max_response_bytes: max_bytes,
        expect_truncated: true,
    })
}

/// Category D: PDF documents — Range header for first 16KB, or HEAD-only.
fn build_pdf_document_request(source: &StaticSource) -> Result<SessionRequest> {
    let method = source.method.as_deref().unwrap_or("GET");
    let max_bytes = source.effective_max_bytes();
    let mut headers = HeaderMap::new();
    headers.insert(USER_AGENT, HeaderValue::from_static("basis-provenance/0.8"));

    if method == "HEAD" {
        // HEAD-only: proves existence + metadata (content-length, last-modified)
        Ok(SessionRequest {
            url: source.url.clone(),
            method: "HEAD".into(),
            headers,
            max_response_bytes: 0,
            expect_truncated: false,
        })
    } else {
        // GET with Range: captures first 16KB (header/title/summary)
        headers.insert(
            RANGE,
            HeaderValue::from_str(&format!("bytes=0-{}", max_bytes - 1))
                .context("Invalid Range header")?,
        );

        Ok(SessionRequest {
            url: source.url.clone(),
            method: "GET".into(),
            headers,
            max_response_bytes: max_bytes,
            expect_truncated: true,
        })
    }
}

/// Operational sources (existing V7.8 pipeline) — standard GET, small payload.
fn build_operational_request(source: &StaticSource) -> Result<SessionRequest> {
    let mut headers = HeaderMap::new();
    headers.insert(USER_AGENT, HeaderValue::from_static("basis-provenance/0.8"));
    headers.insert(ACCEPT, HeaderValue::from_static("application/json"));

    Ok(SessionRequest {
        url: source.url.clone(),
        method: "GET".into(),
        headers,
        max_response_bytes: source.effective_max_bytes(),
        expect_truncated: false,
    })
}

/// Validate that extracted component values appear in the captured response bytes.
/// For truncated responses (Category C/D), the value must be in the first N bytes.
/// Returns the list of components found and those missing.
pub fn validate_components_in_response(
    response_body: &[u8],
    components: &[String],
    component_values: &std::collections::HashMap<String, String>,
) -> (Vec<String>, Vec<String>) {
    let body_str = String::from_utf8_lossy(response_body);
    let mut found = Vec::new();
    let mut missing = Vec::new();

    for component in components {
        if let Some(value) = component_values.get(component) {
            if body_str.contains(value) {
                found.push(component.clone());
            } else {
                missing.push(component.clone());
            }
        } else {
            // No extracted value to validate — skip (proof still covers the source)
            found.push(component.clone());
        }
    }

    (found, missing)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn test_validate_components() {
        let body = b"guardian_count: 19, bug_bounty: $10M";
        let components = vec!["guardian_count".into(), "bug_bounty".into(), "other".into()];
        let mut values = HashMap::new();
        values.insert("guardian_count".into(), "19".into());
        values.insert("bug_bounty".into(), "$10M".into());

        let (found, missing) = validate_components_in_response(body, &components, &values);
        assert_eq!(found, vec!["guardian_count", "bug_bounty", "other"]);
        assert!(missing.is_empty());
    }

    #[test]
    fn test_missing_component_in_truncated() {
        let body = b"some content without the value";
        let components = vec!["guardian_count".into()];
        let mut values = HashMap::new();
        values.insert("guardian_count".into(), "19".into());

        let (found, missing) = validate_components_in_response(body, &components, &values);
        assert!(found.is_empty());
        assert_eq!(missing, vec!["guardian_count"]);
    }
}
