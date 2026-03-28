"""
Index Definition Schema
========================
Any risk index is defined as a configuration against the generic scoring engine.
SII was the first. PSI is the second. The schema is the same.

An index definition is a Python dict with:
- index_id: unique string identifier
- version: semantic version string
- name: human-readable name
- description: what this index measures
- entity_type: what kind of entity it scores (stablecoin, protocol, etc.)
- categories: dict of category_id -> {name, weight}
- components: dict of component_id -> {name, category, weight, normalization: {function, params}, data_source}

All category weights must sum to 1.0.
Component weights are relative within their category (renormalized if not all present).
"""
