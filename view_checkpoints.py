"""
View checkpoint metadata stored in PostgreSQL database
"""
import asyncio
import asyncpg
import json

async def view_checkpoints():
    """View all checkpoint metadata from PostgreSQL"""

    # Connect to database
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='postgres',
        database='postgres'
    )

    try:
        print("=" * 80)
        print("CHECKPOINTS IN DATABASE")
        print("=" * 80)

        # Query all checkpoints
        checkpoints = await conn.fetch("""
            SELECT
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                parent_checkpoint_id,
                type,
                metadata
            FROM checkpoints
            ORDER BY checkpoint_id DESC
            LIMIT 10;
        """)

        if not checkpoints:
            print("No checkpoints found in database")
        else:
            for idx, cp in enumerate(checkpoints, 1):
                print(f"\n{'─' * 80}")
                print(f"Checkpoint #{idx}")
                print(f"{'─' * 80}")
                print(f"Thread ID: {cp['thread_id']}")
                print(f"Checkpoint Namespace: {cp['checkpoint_ns']}")
                print(f"Checkpoint ID: {cp['checkpoint_id']}")
                print(f"Parent Checkpoint ID: {cp['parent_checkpoint_id']}")
                print(f"Type: {cp['type']}")

                # Parse and display metadata
                metadata = cp['metadata']
                print(f"\nMetadata (JSON):")
                if metadata:
                    print(json.dumps(metadata, indent=2))
                else:
                    print("  (empty)")

        print(f"\n{'=' * 80}")
        print(f"Total checkpoints: {len(checkpoints)}")
        print("=" * 80)

        # Query checkpoint writes
        print("\n" + "=" * 80)
        print("CHECKPOINT WRITES")
        print("=" * 80)

        writes = await conn.fetch("""
            SELECT
                thread_id,
                checkpoint_id,
                task_id,
                channel,
                type
            FROM checkpoint_writes
            ORDER BY checkpoint_id DESC
            LIMIT 5;
        """)

        if writes:
            for idx, w in enumerate(writes, 1):
                print(f"\nWrite #{idx}:")
                print(f"  Thread ID: {w['thread_id']}")
                print(f"  Checkpoint ID: {w['checkpoint_id']}")
                print(f"  Task ID: {w['task_id']}")
                print(f"  Channel: {w['channel']}")
                print(f"  Type: {w['type']}")
        else:
            print("No writes found")

        # Query store (long-term memory)
        print("\n" + "=" * 80)
        print("LONG-TERM MEMORY (STORE)")
        print("=" * 80)

        memories = await conn.fetch("""
            SELECT
                prefix,
                key,
                value,
                created_at,
                updated_at
            FROM store
            LIMIT 10;
        """)

        if memories:
            for idx, mem in enumerate(memories, 1):
                print(f"\nMemory #{idx}:")
                print(f"  Prefix (namespace): {mem['prefix']}")
                print(f"  Key: {mem['key']}")
                print(f"  Value: {json.dumps(mem['value'], indent=4)}")
                print(f"  Created: {mem['created_at']}")
                print(f"  Updated: {mem['updated_at']}")
        else:
            print("No long-term memories stored")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(view_checkpoints())
