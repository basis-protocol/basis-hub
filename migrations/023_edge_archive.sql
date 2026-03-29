BEGIN;

CREATE TABLE IF NOT EXISTS wallet_graph.wallet_edges_archive (
    LIKE wallet_graph.wallet_edges INCLUDING ALL
);

CREATE INDEX IF NOT EXISTS idx_edges_archive_from ON wallet_graph.wallet_edges_archive(from_address);
CREATE INDEX IF NOT EXISTS idx_edges_archive_to ON wallet_graph.wallet_edges_archive(to_address);

INSERT INTO migrations (name) VALUES ('023_edge_archive') ON CONFLICT DO NOTHING;

COMMIT;
