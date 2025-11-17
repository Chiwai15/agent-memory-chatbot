"""
Script to inspect the actual database schema created by LangGraph
"""
import asyncio
import asyncpg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

async def inspect_schema():
    """Inspect the actual database tables and schema"""

    db_uri = "postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable"

    # Setup database structures
    async with (
        AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer,
        AsyncPostgresStore.from_conn_string(db_uri) as store
    ):
        await checkpointer.setup()
        await store.setup()
        print("✓ Database setup complete\n")

    # Connect directly to inspect schema
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='postgres',
        database='postgres'
    )

    try:
        print("=" * 80)
        print("DATABASE SCHEMA INSPECTION")
        print("=" * 80)

        # List all tables
        tables = await conn.fetch("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """)

        print("\n📋 TABLES:")
        for table in tables:
            print(f"  - {table['tablename']}")

        # Inspect each table
        for table in tables:
            table_name = table['tablename']
            print(f"\n{'='*80}")
            print(f"TABLE: {table_name}")
            print('='*80)

            # Get columns
            columns = await conn.fetch("""
                SELECT
                    column_name,
                    data_type,
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = $1
                ORDER BY ordinal_position;
            """, table_name)

            print("\nCOLUMNS:")
            for col in columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                max_len = f"({col['character_maximum_length']})" if col['character_maximum_length'] else ""
                default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
                print(f"  {col['column_name']:30} {col['data_type']}{max_len:15} {nullable:10}{default}")

            # Get primary key
            pk = await conn.fetch("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = $1::regclass
                AND i.indisprimary;
            """, table_name)

            if pk:
                pk_cols = [p['attname'] for p in pk]
                print(f"\nPRIMARY KEY: {', '.join(pk_cols)}")

            # Get indexes
            indexes = await conn.fetch("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = $1;
            """, table_name)

            if indexes:
                print("\nINDEXES:")
                for idx in indexes:
                    print(f"  {idx['indexname']}")
                    print(f"    {idx['indexdef']}")

            # Get row count
            count = await conn.fetchval(f'SELECT COUNT(*) FROM "{table_name}"')
            print(f"\nROW COUNT: {count}")

        # Get database size
        print(f"\n{'='*80}")
        print("DATABASE STATISTICS")
        print('='*80)

        db_size = await conn.fetchval("""
            SELECT pg_size_pretty(pg_database_size('postgres'));
        """)
        print(f"Database Size: {db_size}")

        for table in tables:
            table_name = table['tablename']
            size = await conn.fetchval(f"""
                SELECT pg_size_pretty(pg_total_relation_size('"{table_name}"'));
            """)
            print(f"Table '{table_name}': {size}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(inspect_schema())
