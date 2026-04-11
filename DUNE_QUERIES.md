# Dune Analytics Queries — Oracle Activity

Paste these into [dune.com](https://dune.com) to get deeper oracle analytics
that the block explorer API cannot provide.

## Query 1 — Oracle write history (Base)

```sql
SELECT block_time, tx_hash, "from" as keeper, gas_used
FROM base.transactions
WHERE "to" = 0x1651d7b2E238a952167E51A1263FFe607584DB83
ORDER BY block_time DESC
LIMIT 100
```

## Query 2 — Oracle write history (Arbitrum)

```sql
SELECT block_time, tx_hash, "from" as keeper, gas_used
FROM arbitrum.transactions
WHERE "to" = 0x1651d7b2E238a952167E51A1263FFe607584DB83
ORDER BY block_time DESC
LIMIT 100
```

## Query 3 — External interactions only (Base, exclude keeper)

```sql
SELECT block_time, tx_hash, "from" as caller, bytearray_substring(data, 1, 4) as function_selector
FROM base.transactions
WHERE "to" = 0x1651d7b2E238a952167E51A1263FFe607584DB83
  AND "from" != 0x2dF0f62D1861Aa59A4430e3B2b2E7a0D29Cb723b
ORDER BY block_time DESC
```

## Query 4 — SBT contract interactions (Base)

```sql
SELECT block_time, tx_hash, "from" as caller, bytearray_substring(data, 1, 4) as function_selector
FROM base.transactions
WHERE "to" = 0xf315411e49fC3EAbEF0D111A40e976802985E56c
ORDER BY block_time DESC
LIMIT 100
```

## Limitations

View function calls (`getScore`, etc.) do not appear as transactions. These
queries only show write-type interactions that consume gas.

To track view calls at scale, we would need to run our own RPC node with call
tracing enabled, or use a service like Tenderly or Alchemy's trace API.

For now, any non-keeper transaction to our contracts is a strong signal of
external adoption — someone wrote a transaction that interacts with Basis
on-chain state, which means they integrated our oracle or SBT into their own
contract or workflow.
