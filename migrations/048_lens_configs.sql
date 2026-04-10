BEGIN;

CREATE TABLE IF NOT EXISTS lens_configs (
    id SERIAL PRIMARY KEY,
    lens_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    version VARCHAR(20) NOT NULL DEFAULT '1.0',
    author VARCHAR(128) NOT NULL DEFAULT 'system',
    description TEXT,
    criteria JSONB NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lens_configs_lens_id ON lens_configs(lens_id);

-- Seed built-in lenses

INSERT INTO lens_configs (lens_id, name, version, author, description, criteria, content_hash)
VALUES (
    'SCO60',
    'Basel Committee SCO60',
    '1.0',
    'basis-protocol',
    'Basel Committee on Banking Supervision — Standard on Cryptoasset Exposures (SCO60). Classifies stablecoins as Group 1 (lower risk weight) or Group 2.',
    '{
        "framework": "Basel Committee SCO60",
        "classification": {
            "group_1": {
                "criteria": [
                    {
                        "name": "Effective stabilization mechanism",
                        "sii_categories": ["peg"],
                        "threshold": 70,
                        "logic": "category_score_above"
                    },
                    {
                        "name": "Sufficient reserves",
                        "sii_categories": ["structural"],
                        "sub_categories": ["reserves"],
                        "threshold": 60,
                        "logic": "sub_score_above"
                    },
                    {
                        "name": "Full redemption rights at par",
                        "sii_categories": ["flows"],
                        "threshold": 50,
                        "logic": "category_score_above"
                    },
                    {
                        "name": "Adequate liquidity",
                        "sii_categories": ["liquidity"],
                        "threshold": 60,
                        "logic": "category_score_above"
                    }
                ],
                "all_required": true
            }
        }
    }'::jsonb,
    'bea5e8b86dc9f44a5f229d34f4b5a504c837889da8b06d1bf30cebea4cf6324d'
) ON CONFLICT (lens_id) DO NOTHING;

INSERT INTO lens_configs (lens_id, name, version, author, description, criteria, content_hash)
VALUES (
    'MiCA67',
    'EU MiCA Article 67 (EMT)',
    '1.0',
    'basis-protocol',
    'EU Markets in Crypto-Assets Regulation — Article 67 (EMT). Requires fiat-backing, peg stability, and governance standards.',
    '{
        "framework": "EU Markets in Crypto-Assets Regulation — Article 67 (EMT)",
        "classification": {
            "emt_eligible": {
                "criteria": [
                    {
                        "name": "Peg stability maintained",
                        "sii_categories": ["peg"],
                        "threshold": 65,
                        "logic": "category_score_above"
                    },
                    {
                        "name": "Reserve adequacy",
                        "sii_categories": ["structural"],
                        "sub_categories": ["reserves"],
                        "threshold": 55,
                        "logic": "sub_score_above"
                    },
                    {
                        "name": "Governance and operations",
                        "sii_categories": ["structural"],
                        "sub_categories": ["governance"],
                        "threshold": 50,
                        "logic": "sub_score_above"
                    }
                ],
                "all_required": true
            }
        }
    }'::jsonb,
    '0ec5b04994570de93b2f5f8dae08328230367c78b407acd54871e9d83a369e95'
) ON CONFLICT (lens_id) DO NOTHING;

INSERT INTO lens_configs (lens_id, name, version, author, description, criteria, content_hash)
VALUES (
    'GENIUS',
    'GENIUS Act — U.S. Stablecoin',
    '1.0',
    'basis-protocol',
    'U.S. GENIUS Act payment stablecoin classification. Requires 1:1 backing, redemption guarantees, and disclosure requirements.',
    '{
        "framework": "GENIUS Act — U.S. Stablecoin Framework",
        "classification": {
            "payment_stablecoin": {
                "criteria": [
                    {
                        "name": "1:1 fiat or equivalent backing",
                        "sii_categories": ["structural"],
                        "sub_categories": ["reserves"],
                        "threshold": 65,
                        "logic": "sub_score_above"
                    },
                    {
                        "name": "Redemption at par value",
                        "sii_categories": ["peg"],
                        "threshold": 70,
                        "logic": "category_score_above"
                    },
                    {
                        "name": "Adequate market liquidity",
                        "sii_categories": ["liquidity"],
                        "threshold": 55,
                        "logic": "category_score_above"
                    },
                    {
                        "name": "Transparent holder distribution",
                        "sii_categories": ["distribution"],
                        "threshold": 40,
                        "logic": "category_score_above"
                    }
                ],
                "all_required": true
            }
        }
    }'::jsonb,
    'da718cd0fa8ccadf80d7f338a9e095df391312709f396ddc391907203a927ed3'
) ON CONFLICT (lens_id) DO NOTHING;

INSERT INTO migrations (name) VALUES ('048_lens_configs') ON CONFLICT DO NOTHING;

COMMIT;
