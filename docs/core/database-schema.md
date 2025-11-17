# Database Schema Documentation

**Last Updated**: 2025-01-11
**Verified**: Yes (via `inspect_schema.py`)

This document provides the actual, verified database schema for the ReAct Agent Memory System.

---

## Database Overview

The system uses **PostgreSQL 15** with **6 tables** automatically created by LangGraph:

```mermaid
erDiagram
    CHECKPOINTS ||--o{ CHECKPOINT_WRITES : "has writes"
    CHECKPOINTS ||--o{ CHECKPOINT_BLOBS : "has blobs"
    CHECKPOINT_MIGRATIONS ||--|| CHECKPOINTS : "manages"
    STORE ||--|| STORE_MIGRATIONS : "manages"

    CHECKPOINTS {
        text thread_id PK
        text checkpoint_ns PK
        text checkpoint_id PK
        text parent_checkpoint_id
        text type
        jsonb checkpoint
        jsonb metadata
    }

    CHECKPOINT_WRITES {
        text thread_id PK
        text checkpoint_ns PK
        text checkpoint_id PK
        text task_id PK
        integer idx PK
        text channel
        text type
        bytea blob
        text task_path
    }

    CHECKPOINT_BLOBS {
        text thread_id PK
        text checkpoint_ns PK
        text channel PK
        text version PK
        text type
        bytea blob
    }

    CHECKPOINT_MIGRATIONS {
        integer v PK
    }

    STORE {
        text prefix PK
        text key PK
        jsonb value
        timestamp created_at
        timestamp updated_at
        timestamp expires_at
        integer ttl_minutes
    }

    STORE_MIGRATIONS {
        integer v PK
    }
```

---

## Table Details (Verified)

### 1. checkpoints

**Purpose**: Stores conversation thread state for short-term memory

**Columns**:
```sql
Column                  Type                    Nullable    Default
----------------------  ----------------------  ----------  ---------------
thread_id               text                    NOT NULL
checkpoint_ns           text                    NOT NULL    ''::text
checkpoint_id           text                    NOT NULL
parent_checkpoint_id    text                    NULL
type                    text                    NULL
checkpoint              jsonb                   NOT NULL
metadata                jsonb                   NOT NULL    '{}'::jsonb
```

**Primary Key**: `(thread_id, checkpoint_ns, checkpoint_id)`

**Indexes**:
- `checkpoints_pkey` - Primary key index
- `checkpoints_thread_id_idx` - Index on thread_id for fast lookups

**Usage Example**:
```python
# Data is automatically managed by AsyncPostgresSaver
async with AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer:
    await checkpointer.setup()  # Creates this table
```

---

### 2. checkpoint_writes

**Purpose**: Stores incremental checkpoint write operations

**Columns**:
```sql
Column                  Type                    Nullable    Default
----------------------  ----------------------  ----------  ---------------
thread_id               text                    NOT NULL
checkpoint_ns           text                    NOT NULL    ''::text
checkpoint_id           text                    NOT NULL
task_id                 text                    NOT NULL
idx                     integer                 NOT NULL
channel                 text                    NOT NULL
type                    text                    NULL
blob                    bytea                   NOT NULL
task_path               text                    NOT NULL    ''::text
```

**Primary Key**: `(thread_id, checkpoint_ns, checkpoint_id, task_id, idx)`

**Indexes**:
- `checkpoint_writes_pkey` - Primary key index
- `checkpoint_writes_thread_id_idx` - Index on thread_id

---

### 3. checkpoint_blobs

**Purpose**: Stores binary checkpoint data

**Columns**:
```sql
Column                  Type                    Nullable    Default
----------------------  ----------------------  ----------  ---------------
thread_id               text                    NOT NULL
checkpoint_ns           text                    NOT NULL    ''::text
channel                 text                    NOT NULL
version                 text                    NOT NULL
type                    text                    NOT NULL
blob                    bytea                   NULL
```

**Primary Key**: `(thread_id, checkpoint_ns, channel, version)`

**Indexes**:
- `checkpoint_blobs_pkey` - Primary key index
- `checkpoint_blobs_thread_id_idx` - Index on thread_id

---

### 4. checkpoint_migrations

**Purpose**: Tracks checkpoint schema migrations

**Columns**:
```sql
Column      Type        Nullable
----------  ----------  ----------
v           integer     NOT NULL
```

**Primary Key**: `v`

**Row Count**: 10 (as of schema version 10)

---

### 5. store

**Purpose**: Long-term memory storage across sessions

**Columns**:
```sql
Column          Type                        Nullable    Default
--------------  --------------------------  ----------  ------------------
prefix          text                        NOT NULL
key             text                        NOT NULL
value           jsonb                       NOT NULL
created_at      timestamp with time zone    NULL        CURRENT_TIMESTAMP
updated_at      timestamp with time zone    NULL        CURRENT_TIMESTAMP
expires_at      timestamp with time zone    NULL
ttl_minutes     integer                     NULL
```

**Primary Key**: `(prefix, key)`

**Indexes**:
- `store_pkey` - Primary key index
- `store_prefix_idx` - Index on prefix with text pattern ops
- `idx_store_expires_at` - Partial index for TTL queries (WHERE expires_at IS NOT NULL)

**Important Note**: The primary key uses `prefix`, not `namespace`. When using the LangGraph Store API with namespace tuples like `("memories", "user_1")`, this gets converted to a prefix string internally.

**Usage Example**:
```python
# Store data with namespace (converted to prefix internally)
namespace = ("memories", "user_123")
await store.aput(namespace, str(uuid.uuid4()), {
    "data": "User prefers dark mode",
    "created_at": "2025-01-11T12:00:00Z"
})

# Search by namespace
memories = await store.asearch(namespace, query="")
```

---

### 6. store_migrations

**Purpose**: Tracks store schema migrations

**Columns**:
```sql
Column      Type        Nullable
----------  ----------  ----------
v           integer     NOT NULL
```

**Primary Key**: `v`

**Row Count**: 4 (as of schema version 4)

---

## Understanding Checkpoint Metadata and Writes

### How LangGraph Stores Checkpoint Information

**IMPORTANT**: In LangGraph 3.0.0, checkpoint information is stored across **multiple normalized tables**, not in a single JSON structure.

### The Three-Table Structure

```
┌─────────────────────────────────────────────────────────────┐
│                    CHECKPOINT DATA FLOW                     │
└─────────────────────────────────────────────────────────────┘

1. checkpoints.metadata (JSON)     2. checkpoint_writes       3. checkpoint_blobs
   ┌──────────────────┐                ┌─────────────────┐       ┌──────────────┐
   │ {                │                │ checkpoint_id   │       │ thread_id    │
   │   "step": 5,     │                │ task_id         │       │ channel      │
   │   "source": loop,│                │ channel         │       │ version      │
   │   "parents": {}  │                │ type            │       │ blob (bytes) │
   │ }                │                │ blob (bytes)    │       └──────────────┘
   └──────────────────┘                └─────────────────┘
         ↓                                      ↓                      ↓
   Basic metadata           What was written to state      Actual state data
```

### Detailed Breakdown

#### 1. `checkpoints.metadata` Column (JSON)

**Contains ONLY these fields**:
```json
{
  "step": 5,          // Execution step number
  "source": "loop",   // Source: "input", "loop", or "update"
  "parents": {}       // Parent checkpoint references
}
```

**Does NOT contain**:
- ❌ `writes` field
- ❌ Actual message data
- ❌ Tool call results

**Access via**:
```python
state_snapshot = await agent.aget_state(config)
metadata = state_snapshot.metadata
print(f"Step: {metadata['step']}")
print(f"Source: {metadata['source']}")
```

#### 2. `checkpoint_writes` Table (Normalized Storage)

**Contains the "writes" information** that shows what was written to state:

```sql
checkpoint_id                           | task_id                              | channel           | type
----------------------------------------|--------------------------------------|-------------------|-------
1f0b77a0-ab60-6dae-8020-0fa176de5169   | a8e52d6b-54fc-a7c3-0465-825dff456c44 | messages          | msgpack
1f0b77a0-ab60-6dae-8020-0fa176de5169   | a8e52d6b-54fc-a7c3-0465-825dff456c44 | branch:to:agent   | null
```

**Each row represents**:
- What channel was updated (`messages`, `branch:to:agent`, `__pregel_tasks`)
- What type of data (`msgpack`, `null`)
- Which task performed the write
- Binary blob containing the actual write data

**Access via SQL**:
```python
import asyncpg

conn = await asyncpg.connect('postgresql://...')
writes = await conn.fetch(
    """
    SELECT task_id, channel, type
    FROM checkpoint_writes
    WHERE checkpoint_id = $1
    """,
    checkpoint_id
)
for write in writes:
    print(f"Channel: {write['channel']}, Type: {write['type']}")
```

**Equivalent to older format**:
```json
{
  "writes": {
    "task_a8e52d6b": {
      "messages": [...],
      "branch:to:agent": null
    }
  }
}
```

#### 3. `checkpoint_blobs` Table (State Storage)

**Contains the actual state data** (messages, tasks, etc.):

```sql
thread_id | channel      | version                                    | type    | blob
----------|--------------|--------------------------------------------|---------|---------
1         | messages     | 00000000000000000000000000000036.0.19622... | msgpack | <binary>
1         | __pregel_tasks | 00000000000000000000000000000035.0.11672... | msgpack | <binary>
```

**Contains**:
- Actual conversation messages (encoded as msgpack)
- Agent task information
- State values at different versions

### Complete Example: Querying All Checkpoint Data

```python
import asyncio
import asyncpg

async def show_complete_checkpoint(checkpoint_id: str):
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/postgres')

    # 1. Get basic metadata from checkpoints.metadata
    checkpoint = await conn.fetchrow(
        "SELECT metadata FROM checkpoints WHERE checkpoint_id = $1",
        checkpoint_id
    )
    print("Metadata:", checkpoint['metadata'])
    # Output: {"step": 5, "source": "loop", "parents": {}}

    # 2. Get writes from checkpoint_writes table
    writes = await conn.fetch(
        "SELECT task_id, channel, type FROM checkpoint_writes WHERE checkpoint_id = $1",
        checkpoint_id
    )
    print("\nWrites:")
    for write in writes:
        print(f"  - Task {write['task_id']}: channel={write['channel']}, type={write['type']}")
    # Output:
    #   - Task a8e52d6b...: channel=messages, type=msgpack
    #   - Task a8e52d6b...: channel=branch:to:agent, type=null

    # 3. Get state data from checkpoint_blobs (if needed)
    blobs = await conn.fetch(
        """
        SELECT channel, version, type
        FROM checkpoint_blobs
        WHERE thread_id = (SELECT thread_id FROM checkpoints WHERE checkpoint_id = $1)
        ORDER BY version DESC
        LIMIT 5
        """,
        checkpoint_id
    )
    print("\nBlobs (state data):")
    for blob in blobs:
        print(f"  - Channel: {blob['channel']}, Type: {blob['type']}")

    await conn.close()
```

### Why This Architecture?

**LangGraph 3.0.0 normalized the checkpoint structure for**:

1. **Performance**: Separate tables for metadata vs binary data
2. **Scalability**: Easier to query specific writes without loading full checkpoint
3. **Flexibility**: Can query writes independently from checkpoint metadata
4. **Storage efficiency**: Binary blobs stored separately from JSON metadata

### Migration from Older Versions

**If you see documentation showing**:
```json
{
  "step": 1,
  "source": "loop",
  "writes": {
    "agent": {
      "messages": [...]
    }
  }
}
```

**This format is from pre-3.0 versions**. In 3.0.0+:
- ✅ `step`, `source`, `parents` → `checkpoints.metadata`
- ✅ `writes` → `checkpoint_writes` table
- ✅ Actual data → `checkpoint_blobs` table

### Key Takeaways

1. **`checkpoints.metadata`**: Only contains `step`, `source`, `parents`
2. **`checkpoint_writes`**: Contains the "writes" information (what was written)
3. **`checkpoint_blobs`**: Contains actual binary state data
4. **`store`**: Separate system for long-term memory (not related to checkpoints)

To see this in action, run:
```bash
python 01_shortTermTest.py  # Shows metadata + writes from both tables
python view_checkpoints.py  # Shows raw database contents
```

---

## Data Access Patterns

### Short-Term Memory (Checkpoints)

```python
# Initialize checkpointer
async with AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer:
    await checkpointer.setup()

    # Create agent with checkpointer
    agent = create_react_agent(
        model=llm,
        tools=tools,
        checkpointer=checkpointer
    )

    # Use with thread_id
    config = {"configurable": {"thread_id": "session-123"}}
    response = await agent.ainvoke({"messages": [...]}, config)

    # Data is automatically stored in checkpoints table
```

### Long-Term Memory (Store)

```python
# Initialize store
async with AsyncPostgresStore.from_conn_string(db_uri) as store:
    await store.setup()

    # Store memory
    namespace = ("preferences", "user_456")
    await store.aput(namespace, str(uuid.uuid4()), {
        "data": "Prefers email notifications",
        "category": "notification_preference"
    })

    # Retrieve memories
    results = await store.asearch(namespace, query="")
    for item in results:
        print(item.value)  # Access stored data
```

---

## Database Connection

### Connection String Format

```python
# Development
db_uri = "postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable"

# Production
db_uri = "postgresql://user:password@prod-host:5432/dbname?sslmode=require"
```

### Connection Parameters

```python
# Default connection (from docker-compose.yml)
Host: localhost
Port: 5432
Database: postgres
Username: postgres
Password: postgres
```

---

## Schema Inspection

To verify the current database schema, run:

```bash
python inspect_schema.py
```

This will output:
- All table names
- Column definitions with data types
- Primary keys
- Indexes
- Row counts
- Database size statistics

**Example Output**:
```
================================================================================
TABLE: store
================================================================================

COLUMNS:
  prefix                         text                NOT NULL
  key                            text                NOT NULL
  value                          jsonb               NOT NULL
  created_at                     timestamp with time zone    NULL      DEFAULT CURRENT_TIMESTAMP
  updated_at                     timestamp with time zone    NULL      DEFAULT CURRENT_TIMESTAMP
  expires_at                     timestamp with time zone    NULL
  ttl_minutes                    integer             NULL

PRIMARY KEY: prefix, key

INDEXES:
  store_pkey
    CREATE UNIQUE INDEX store_pkey ON public.store USING btree (prefix, key)
  store_prefix_idx
    CREATE INDEX store_prefix_idx ON public.store USING btree (prefix text_pattern_ops)
  idx_store_expires_at
    CREATE INDEX idx_store_expires_at ON public.store USING btree (expires_at) WHERE (expires_at IS NOT NULL)

ROW COUNT: 0
```

---

## Performance Optimization

### Recommended Indexes (Already Created)

All necessary indexes are automatically created by LangGraph during `setup()`:

1. **Thread-based lookups**: `checkpoints_thread_id_idx`
2. **Prefix searches**: `store_prefix_idx`
3. **TTL cleanup**: `idx_store_expires_at`

### Query Performance Tips

1. **Use thread_id for filtering** - It's indexed
2. **Limit result sets** - Use `LIMIT` in custom queries
3. **Regular VACUUM** - Run `VACUUM ANALYZE` weekly
4. **Monitor slow queries** - Enable `log_min_duration_statement = 1000`

### Production Configuration

```sql
-- Recommended PostgreSQL settings for production
ALTER SYSTEM SET shared_buffers = '2GB';
ALTER SYSTEM SET effective_cache_size = '6GB';
ALTER SYSTEM SET maintenance_work_mem = '512MB';
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET work_mem = '10MB';

-- Reload configuration
SELECT pg_reload_conf();
```

---

## Monitoring Queries

### Check table sizes

```sql
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Count checkpoints per thread

```sql
SELECT
    thread_id,
    COUNT(*) as checkpoint_count
FROM checkpoints
GROUP BY thread_id
ORDER BY checkpoint_count DESC
LIMIT 10;
```

### Find expired memories

```sql
SELECT
    prefix,
    COUNT(*) as expired_count
FROM store
WHERE expires_at IS NOT NULL
  AND expires_at < CURRENT_TIMESTAMP
GROUP BY prefix;
```

### Database statistics

```sql
SELECT
    pg_size_pretty(pg_database_size('postgres')) as database_size,
    (SELECT COUNT(*) FROM checkpoints) as total_checkpoints,
    (SELECT COUNT(*) FROM store) as total_memories,
    (SELECT COUNT(DISTINCT thread_id) FROM checkpoints) as unique_threads;
```

---

## Backup & Maintenance

### Backup

```bash
# Full database backup
pg_dump -h localhost -U postgres -d postgres \
    -F custom -b -v \
    -f backup_$(date +%Y%m%d_%H%M%S).dump

# Table-specific backup
pg_dump -h localhost -U postgres -d postgres \
    -t store -t checkpoints \
    -F custom -f memory_backup.dump
```

### Restore

```bash
# Restore full backup
pg_restore -h localhost -U postgres -d postgres \
    -v backup_20250111_120000.dump

# Restore specific tables
pg_restore -h localhost -U postgres -d postgres \
    -t store -v memory_backup.dump
```

### Cleanup Old Data

```sql
-- Delete checkpoints older than 30 days
DELETE FROM checkpoints
WHERE (checkpoint->>'ts')::timestamp < NOW() - INTERVAL '30 days';

-- Delete expired store items
DELETE FROM store
WHERE expires_at IS NOT NULL
  AND expires_at < CURRENT_TIMESTAMP;

-- Vacuum to reclaim space
VACUUM ANALYZE checkpoints;
VACUUM ANALYZE store;
```

---

## Migration Notes

### Schema Versions

- **Checkpoint schema**: v10 (10 migrations applied)
- **Store schema**: v4 (4 migrations applied)

Migrations are managed automatically by LangGraph. The migration tables track which schema version is currently applied.

---

## Troubleshooting

### Tables not created

```bash
# Verify setup was called
python -c "
import asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

async def check():
    db_uri = 'postgresql://postgres:postgres@localhost:5432/postgres'
    async with AsyncPostgresSaver.from_conn_string(db_uri) as cp:
        await cp.setup()
    async with AsyncPostgresStore.from_conn_string(db_uri) as st:
        await st.setup()
    print('Setup complete')

asyncio.run(check())
"
```

### Connection issues

```bash
# Test connection
psql -h localhost -U postgres -d postgres -c "SELECT version();"

# Check if Docker is running
docker ps | grep postgres
```

### Inspect actual schema

```bash
# Run inspection script
python inspect_schema.py

# Or connect directly
psql -h localhost -U postgres -d postgres
\dt          # List tables
\d checkpoints  # Describe table
```

---

**Verification Method**: All schema information in this document was verified using `inspect_schema.py` against a live PostgreSQL database with LangGraph 1.0.2 and langgraph-checkpoint-postgres 3.0.0.

**Source Code**: See `inspect_schema.py` for the verification script.
