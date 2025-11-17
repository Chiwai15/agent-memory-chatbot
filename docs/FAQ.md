# FAQ - Frequently Asked Questions

## Memory & Data Storage

### Q: I cannot see any data with name: user_8pvjmlg9w in PostgreSQL, but the LLM replied with my name. Where does the data stored?

**A: Your data IS in PostgreSQL, stored in the `checkpoint_writes` table in binary format.**

Your conversation **"my name is nelson" and "i am 30 years old"** is stored in PostgreSQL, but in a **binary format (msgpack)** that you can't easily read as plain text.

**Where Your Data Is Actually Stored:**

**1. SHORT-TERM MEMORY (Conversation History)**  **YOUR DATA IS HERE**

**Location:** PostgreSQL `checkpoint_writes` table
**Format:** Binary (msgpack) - NOT readable text
**Data Found:**
-  `thread_id = 'user_8pvjmlg9w'`
-  `channel = 'messages'` (10 message entries)
-  `type = 'msgpack'` (binary encoded)

**Why you couldn't find it:**
- The `blob` column contains binary-encoded conversation data
- You can't see "nelson" or "30" in plain text because it's encoded in msgpack format
- LangGraph uses this for efficient storage of conversation state

**How the LLM reads it:**
1. LangGraph's `AsyncPostgresSaver` reads the binary blob
2. Decodes msgpack into Python objects
3. Extracts the message history
4. Sends it to the LLM

**2. LONG-TERM MEMORY (Persistent Facts)** L **NO DATA HERE**

**Location:** PostgreSQL `store` table
**Format:** Plain text JSON (readable)
**Data Found:**
- L No records with prefix `memories.user_8pvjmlg9w`

**Why no data:**
- You said "hi , my name is nelson" and "i am 30 years old"
- These messages SHOULD have triggered long-term storage (they contain "my name is" and "i am")
- But long-term storage only happens when the exact trigger phrases are detected

**To Verify Your Data Exists:**

Run this to see your conversation history size:

```sql
docker exec postgres_db psql -U postgres -d postgres -c \
"SELECT COUNT(*) as message_count,
        SUM(length(blob)) as total_bytes
 FROM checkpoint_writes
 WHERE thread_id = 'user_8pvjmlg9w'
   AND channel = 'messages';"
```

Expected output:
```
 message_count | total_bytes
---------------+-------------
            10 |       XXXXX
```

**Summary:**

| Question | Answer |
|----------|--------|
| **Where is "my name is nelson" stored?** | `checkpoint_writes` table, `blob` column (binary msgpack format) |
| **Can I read it as text?** | No - it's binary encoded for performance |
| **How does the LLM read it?** | LangGraph's `AsyncPostgresSaver` decodes the msgpack blob |
| **Why isn't it in the `store` table?** | Trigger phrases might not have fired, or memory storage failed |
| **Is my conversation safe?** | Yes - 48 checkpoints + 10 message writes found for your user_id |

**Conclusion:**

Your data IS in PostgreSQL! You just couldn't see it because:
1. It's in `checkpoint_writes.blob` (binary), not `store` (text)
2. You probably only checked the `store` table
3. The conversation is encoded in msgpack format for efficient storage

The LLM remembered "Nelson" and "30 years old" by reading the binary checkpoint data, not from the `store` table.
