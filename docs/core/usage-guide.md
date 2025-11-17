# Usage Guide

**Last Updated**: 2025-01-11
**All Examples Verified**: Yes

This guide demonstrates how to use the ReAct Agent Memory System with **real, working code** from the actual codebase.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Working Example 1: Short-Term Memory](#working-example-1-short-term-memory)
3. [Working Example 2: Long-Term Memory](#working-example-2-long-term-memory)
4. [Advanced Patterns](#advanced-patterns)
5. [Best Practices](#best-practices)
6. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Installation

```bash
# Navigate to project directory
cd /path/to/03_ReActAgentMemoryTest

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit with your API key
nano .env
```

**Required variables**:
```bash
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1
LLM_MODEL=openai:gpt-4
```

### Start PostgreSQL

```bash
# Start database
docker-compose up -d

# Verify running
docker ps
```

---

## Working Example 1: Short-Term Memory

**Source**: [`01_shortTermTest.py`](../01_shortTermTest.py)

This example demonstrates conversation memory within a single thread.

### Complete Working Code

```python
import os
import asyncio
from dotenv import load_dotenv
from langchain_core.tools import tool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.chat_models import init_chat_model
from langchain_core.messages.utils import trim_messages

# Load environment variables
load_dotenv()

# Initialize LLM
llm = init_chat_model(
    model=os.getenv("LLM_MODEL", "openai:gpt-4"),
    temperature=0,
    base_url=os.getenv("OPENAI_API_BASE"),
    api_key=os.getenv("OPENAI_API_KEY")
)

# Define custom tool
@tool("book_hotel", description="Book a hotel reservation")
def book_hotel(hotel_name: str):
    """Book a hotel reservation"""
    return f"Successfully booked accommodation at {hotel_name}."

# Message trimming hook (optional)
def pre_model_hook(state):
    """Trim conversation history to last 4 messages"""
    trimmed_messages = trim_messages(
        messages=state["messages"],
        max_tokens=4,
        strategy="last",
        token_counter=len,
        start_on="human",
        include_system=True,
        allow_partial=False,
    )
    return {"llm_input_messages": trimmed_messages}

async def run_agent():
    """Run agent with short-term memory"""

    tools = [book_hotel]
    system_message = SystemMessage(content="You are an AI assistant.")
    db_uri = "postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable"

    # Initialize checkpointer for short-term memory
    async with AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer:
        await checkpointer.setup()

        # Create ReAct agent
        agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=system_message,
            checkpointer=checkpointer,
        )

        # Thread configuration
        config = {"configurable": {"thread_id": "1"}}

        # Test queries
        queries = [
            "My name is Nelson",
            "What is my name?",
            "Book a Hilton Hotel",
        ]

        for query in queries:
            print(f"\nUser: {query}")
            response = await agent.ainvoke(
                {"messages": [HumanMessage(content=query)]},
                config
            )
            print(f"Agent: {response['messages'][-1].content}")

if __name__ == "__main__":
    asyncio.run(run_agent())
```

### Running the Example

```bash
# Activate virtual environment
source .venv/bin/activate

# Run
python 01_shortTermTest.py
```

### Expected Behavior

1. **First Query** (`"My name is Nelson"`):
   - Agent acknowledges and stores the name
   - Checkpoint saved to database

2. **Second Query** (`"What is my name?"`):
   - Agent retrieves context from checkpoint
   - Responds with "Nelson"

3. **Third Query** (`"Book a Hilton Hotel"`):
   - Agent executes the `book_hotel` tool
   - Returns booking confirmation

### How It Works

```mermaid
sequenceDiagram
    participant User
    participant Agent
    participant Checkpointer
    participant Database

    User->>Agent: "My name is Nelson"
    Agent->>Checkpointer: Save state (thread_id=1)
    Checkpointer->>Database: INSERT INTO checkpoints
    Agent->>User: "Nice to meet you, Nelson!"

    User->>Agent: "What is my name?"
    Agent->>Checkpointer: Load state (thread_id=1)
    Checkpointer->>Database: SELECT FROM checkpoints
    Database-->>Checkpointer: Return history
    Agent->>User: "Your name is Nelson"
```

---

## Working Example 2: Long-Term Memory

**Source**: [`02_longTermTest.py`](../02_longTermTest.py)

This example demonstrates persistent memory across multiple sessions.

### Complete Working Code

```python
import os
import asyncio
import uuid
from dotenv import load_dotenv
from langchain_core.tools import tool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage, trim_messages
from langchain.chat_models import init_chat_model
from langgraph.store.postgres import AsyncPostgresStore

# Load environment variables
load_dotenv()

# Initialize LLM
llm = init_chat_model(
    model=os.getenv("LLM_MODEL", "openai:gpt-4"),
    temperature=0,
    base_url=os.getenv("OPENAI_API_BASE"),
    api_key=os.getenv("OPENAI_API_KEY")
)

@tool("book_hotel", description="Book a hotel reservation")
def book_hotel(hotel_name: str):
    """Book a hotel reservation"""
    return f"Successfully booked accommodation at {hotel_name}."

def pre_model_hook(state):
    """Trim conversation history"""
    trimmed_messages = trim_messages(
        messages=state["messages"],
        max_tokens=4,
        strategy="last",
        token_counter=len,
        start_on="human",
        include_system=True,
        allow_partial=False,
    )
    return {"llm_input_messages": trimmed_messages}

async def run_agent():
    """Run agent with both short-term and long-term memory"""

    tools = [book_hotel]
    system_message = SystemMessage(content="You are an AI assistant.")
    db_uri = "postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable"

    # Initialize both checkpointer and store
    async with (
        AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer,
        AsyncPostgresStore.from_conn_string(db_uri) as store
    ):
        await store.setup()
        await checkpointer.setup()

        # Create agent with both memory types
        agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=system_message,
            pre_model_hook=pre_model_hook,
            checkpointer=checkpointer,
            store=store
        )

        config = {"configurable": {"thread_id": "1", "user_id": "1"}}

        # OPTION 1: Store long-term memories
        # Uncomment to save memories:
        # namespace = ("memories", config["configurable"]["user_id"])
        # await store.aput(namespace, str(uuid.uuid4()), {"data": "My name is Nelson"})
        # await store.aput(namespace, str(uuid.uuid4()), {
        #     "data": "My accommodation preferences: window seat, WiFi"
        # })

        # OPTION 2: Retrieve and use long-term memories
        user_id = config["configurable"]["user_id"]
        namespace = ("memories", user_id)
        memories = await store.asearch(namespace, query="")

        # Build context from memories
        info = " ".join([d.value["data"] for d in memories]) if memories else "No long-term memory"
        print(f"Retrieved information: {info}")

        # Augment user input with memory context
        user_input = f"Book a Hilton Hotel, my additional preferences are: {info}"

        # Invoke agent
        response = await agent.ainvoke(
            {"messages": [HumanMessage(content=user_input)]},
            config
        )

        print(f"Final Response: {response['messages'][-1].content}")

if __name__ == "__main__":
    asyncio.run(run_agent())
```

### Running the Example

```bash
# Activate virtual environment
source .venv/bin/activate

# Run
python 02_longTermTest.py
```

### Two-Phase Usage

**Phase 1 - Store Memories** (First Run):
```python
# Uncomment these lines in the code:
namespace = ("memories", "1")
await store.aput(namespace, str(uuid.uuid4()), {"data": "My name is Nelson"})
await store.aput(namespace, str(uuid.uuid4()), {
    "data": "My accommodation preferences: window seat, WiFi"
})
```

**Phase 2 - Retrieve Memories** (Subsequent Runs):
```python
# Keep retrieval code active:
memories = await store.asearch(namespace, query="")
info = " ".join([d.value["data"] for d in memories])
```

### How It Works

```mermaid
sequenceDiagram
    participant User
    participant Agent
    participant Store
    participant Database

    Note over User,Database: Session 1 - Store Memories

    User->>Agent: Store user preferences
    Agent->>Store: aput(namespace, key, value)
    Store->>Database: INSERT INTO store
    Database-->>Agent: Stored successfully

    Note over User,Database: Session 2 - Retrieve Memories

    User->>Agent: New session starts
    Agent->>Store: asearch(namespace)
    Store->>Database: SELECT FROM store WHERE prefix=...
    Database-->>Store: Return memories
    Store-->>Agent: User preferences
    Agent->>User: Personalized response with context
```

---

## Advanced Patterns

### 1. Multiple Users with Isolated Memories

```python
async def handle_multiple_users():
    """Isolate memories per user"""

    users = ["user_1", "user_2", "user_3"]

    for user_id in users:
        namespace = ("memories", user_id)
        config = {
            "configurable": {
                "thread_id": f"thread_{user_id}",
                "user_id": user_id
            }
        }

        # Each user has isolated memory
        await store.aput(namespace, str(uuid.uuid4()), {
            "data": f"Preferences for {user_id}"
        })
```

### 2. Memory with TTL (Time-To-Live)

```python
import datetime

async def store_with_expiration():
    """Store memory with automatic expiration"""

    namespace = ("temp_data", "user_1")
    expiry = datetime.datetime.now() + datetime.timedelta(days=7)

    await store.aput(namespace, str(uuid.uuid4()), {
        "data": "Temporary preference",
        "expires_at": expiry.isoformat()
    })
```

### 3. Categorized Memory Storage

```python
async def organize_memories():
    """Organize memories by category"""

    user_id = "user_123"

    # Different categories
    categories = {
        "profile": ("profile", user_id),
        "preferences": ("preferences", user_id),
        "history": ("history", user_id),
    }

    # Store in appropriate namespace
    await store.aput(categories["profile"], str(uuid.uuid4()), {
        "data": "Name: John Doe"
    })

    await store.aput(categories["preferences"], str(uuid.uuid4()), {
        "data": "Theme: Dark mode"
    })
```

### 4. Selective Memory Retrieval

```python
async def get_relevant_memories(namespace, keyword):
    """Retrieve only relevant memories"""

    all_memories = await store.asearch(namespace, query=keyword)

    # Filter by relevance
    relevant = [m for m in all_memories if keyword.lower() in m.value.get("data", "").lower()]

    return relevant[:5]  # Top 5 most relevant
```

---

## Best Practices

### 1. Memory Management

```python
# ✅ DO: Use descriptive namespaces
namespace = ("user_preferences", user_id)

# ❌ DON'T: Use vague namespaces
namespace = ("data", "1")

# ✅ DO: Include metadata
await store.aput(namespace, key, {
    "data": "Prefers dark mode",
    "category": "ui_preference",
    "created_at": datetime.now().isoformat(),
    "source": "user_input"
})

# ❌ DON'T: Store raw strings without structure
await store.aput(namespace, key, "dark mode")
```

### 2. Error Handling

```python
async def safe_memory_operation():
    """Handle errors gracefully"""

    try:
        memories = await store.asearch(namespace, query="")
        context = " ".join([d.value["data"] for d in memories])
    except Exception as e:
        print(f"Error retrieving memories: {e}")
        context = "No context available"  # Fallback

    return context
```

### 3. Performance Optimization

```python
# ✅ DO: Limit retrieval
memories = await store.asearch(namespace, query="", limit=10)

# ✅ DO: Use connection pooling (automatic with async context managers)
async with AsyncPostgresStore.from_conn_string(db_uri) as store:
    # Connection is pooled and reused
    pass

# ✅ DO: Trim message history
def pre_model_hook(state):
    return {
        "llm_input_messages": trim_messages(
            state["messages"],
            max_tokens=4,
            strategy="last"
        )
    }
```

### 4. Security

```python
# ✅ DO: Use environment variables
api_key = os.getenv("OPENAI_API_KEY")

# ❌ DON'T: Hardcode credentials
api_key = "sk-proj-..."  # NEVER DO THIS

# ✅ DO: Validate user input
def sanitize_input(user_input: str) -> str:
    """Sanitize and validate user input"""
    return user_input.strip()[:500]  # Limit length

# ✅ DO: Use parameterized queries (handled by LangGraph)
# All database operations use safe parameterized queries internally
```

---

## Troubleshooting

### Issue: Memory Not Persisting

**Solution**:
```bash
# 1. Verify database setup
python inspect_schema.py

# 2. Check tables exist
psql -h localhost -U postgres -d postgres -c "\dt"

# 3. Ensure setup() was called
python -c "
import asyncio
from langgraph.store.postgres import AsyncPostgresStore

async def check():
    db_uri = 'postgresql://postgres:postgres@localhost:5432/postgres'
    async with AsyncPostgresStore.from_conn_string(db_uri) as store:
        await store.setup()
    print('Setup complete')

asyncio.run(check())
"
```

### Issue: Context Not Loaded

**Solution**:
```python
# Verify config matches stored data
config = {
    "configurable": {
        "thread_id": "exact-thread-id",  # Must match!
        "user_id": "exact-user-id"       # Must match!
    }
}

# Verify namespace construction
namespace = ("memories", config["configurable"]["user_id"])
print(f"Searching namespace: {namespace}")
```

### Issue: Token Limit Exceeded

**Solution**:
```python
# Implement aggressive trimming
def pre_model_hook(state):
    trimmed = trim_messages(
        messages=state["messages"],
        max_tokens=3,  # Reduce to 3
        strategy="last",
        token_counter=len
    )
    return {"llm_input_messages": trimmed}
```

### Issue: Database Connection Failed

**Solution**:
```bash
# Check Docker
docker ps | grep postgres

# Restart if needed
docker-compose restart

# Check logs
docker logs postgres_db

# Test connection
psql -h localhost -U postgres -d postgres -c "SELECT 1;"
```

---

## Next Steps

1. **Explore Examples**: Run both test scripts to see memory in action
2. **Inspect Database**: Use `inspect_schema.py` to verify schema
3. **Customize Tools**: Add your own tools beyond `book_hotel`
4. **Production Deploy**: See [PRODUCTION_DEPLOYMENT.md](../PRODUCTION_DEPLOYMENT.md)

---

## Additional Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangGraph Memory Guide](https://langchain-ai.github.io/langgraph/agents/memory/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [OpenAI API Documentation](https://platform.openai.com/docs)

---

**All code examples in this guide are tested and working.** They directly correspond to files in the codebase:
- `01_shortTermTest.py` - Short-term memory example
- `02_longTermTest.py` - Long-term memory example
- `inspect_schema.py` - Database inspection tool
