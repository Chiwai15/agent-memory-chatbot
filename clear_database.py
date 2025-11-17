#!/usr/bin/env python3
"""
Quick script to clear all data from PostgreSQL database.
Useful for public testing - clears both long-term memories and conversation history.

Usage:
    python clear_database.py
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection string
DB_URI = "postgresql://postgres:postgres@localhost:5432/postgres"


async def clear_database():
    """Clear all memories and checkpoints from the database"""
    print("🧹 Clearing all data from PostgreSQL database...")
    print("=" * 60)

    try:
        # Connect to database
        conn = await asyncpg.connect(DB_URI)

        try:
            # Count before clearing
            store_count_before = await conn.fetchval("SELECT COUNT(*) FROM store;")
            checkpoint_count_before = await conn.fetchval("SELECT COUNT(*) FROM checkpoints;")

            print(f"\n📊 Current database status:")
            print(f"   Long-term memories (store): {store_count_before} entries")
            print(f"   Conversation history (checkpoints): {checkpoint_count_before} entries")

            # Confirm deletion
            print(f"\n⚠️  WARNING: This will delete ALL data!")
            confirm = input("   Type 'yes' to continue: ")

            if confirm.lower() != 'yes':
                print("\n❌ Cancelled. No data was deleted.")
                return

            # Clear all tables
            print("\n🗑️  Deleting data...")

            # Clear store table (long-term memories)
            store_result = await conn.execute("DELETE FROM store;")
            store_count = int(store_result.split()[-1]) if store_result else 0

            # Clear checkpoints table (short-term conversation history)
            checkpoint_result = await conn.execute("DELETE FROM checkpoints;")
            checkpoint_count = int(checkpoint_result.split()[-1]) if checkpoint_result else 0

            # Also clear checkpoint writes and blobs for cleanup
            await conn.execute("DELETE FROM checkpoint_writes;")
            await conn.execute("DELETE FROM checkpoint_blobs;")

            print(f"\n✅ Successfully cleared all data!")
            print(f"   Long-term memories deleted: {store_count}")
            print(f"   Conversation history deleted: {checkpoint_count}")
            print(f"\n🎉 Database is now clean for public testing!")
            print("=" * 60)

        finally:
            await conn.close()

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print(f"\nMake sure PostgreSQL is running:")
        print(f"   docker-compose up -d")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(clear_database())
    exit(exit_code or 0)
