# Oracle Analytics — Dune Queries

Paste these into dune.com for deeper oracle analytics.

## All oracle transactions on Base

```sql
SELECT block_time, hash as tx_hash, "from" as caller, gas_used,
       substr(data, 1, 10) as function_selector
FROM base.transactions
WHERE "to" = 0x1651d7b2E238a952167E51A1263FFe607584DB83
ORDER BY block_time DESC
LIMIT 200
```

## All oracle transactions on Arbitrum

```sql
SELECT block_time, hash as tx_hash, "from" as caller, gas_used,
       substr(data, 1, 10) as function_selector
FROM arbitrum.transactions
WHERE "to" = 0x1651d7b2E238a952167E51A1263FFe607584DB83
ORDER BY block_time DESC
LIMIT 200
```

## External only (exclude keeper)

```sql
SELECT block_time, hash, "from" as caller,
       substr(data, 1, 10) as function_selector
FROM base.transactions
WHERE "to" = 0x1651d7b2E238a952167E51A1263FFe607584DB83
  AND "from" != 0x2dF0f62D1861Aa59A4430e3B2b2E7a0D29Cb723b
ORDER BY block_time DESC
```

## Limitation

View function calls (getScore, etc.) do not appear as transactions. These queries only show write-type interactions. To track view calls we would need trace-level RPC (Alchemy Trace API, Tenderly, or our own archive node). For now, any non-keeper transaction to our contracts is a strong signal of external adoption.
