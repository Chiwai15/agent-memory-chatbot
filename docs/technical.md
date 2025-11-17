# Memory Chat - Technical Documentation

**Last Updated:** 2025-11-16
**Version:** 1.0.0
**Tech Stack:** FastAPI + LangGraph + PostgreSQL + React

---

## Table of Contents

1. [System Architecture Overview](#system-architecture-overview)
2. [Technology Stack](#technology-stack)
3. [Core Components](#core-components)
4. [Database Architecture](#database-architecture)
5. [Memory System Implementation](#memory-system-implementation)
6. [Service Integration Architecture](#service-integration-architecture)
7. [API Specification](#api-specification)
8. [Frontend Architecture](#frontend-architecture)
9. [Deployment Architecture](#deployment-architecture)
10. [Security & Privacy](#security--privacy)
11. [Performance & Scalability](#performance--scalability)
12. [Code Structure](#code-structure)
13. [Development Guide](#development-guide)

---

## System Architecture Overview

### High-Level Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        A[React UI<br/>localhost:5173]
    end

    subgraph "API Layer"
        B[FastAPI Server<br/>localhost:8000]
        C[CORS Middleware]
        D[Request Handlers]
    end

    subgraph "Agent Layer"
        E[LangGraph ReAct Agent]
        F[Dynamic System Prompt]
        G[LLM Model<br/>OpenAI/Groq/DeepSeek]
        H[API Key Rotation]
    end

    subgraph "Memory Layer"
        I[AsyncPostgresSaver<br/>Checkpointer]
        J[AsyncPostgresStore<br/>Long-term Store]
        K[Entity Extractor]
    end

    subgraph "Data Layer"
        L[(PostgreSQL Database<br/>localhost:5432)]
        M[checkpoints table]
        N[store table]
    end

    subgraph "Service Integration"
        O[Service Capabilities<br/>Dictionary]
        P[11 Services:<br/>YouTube, Netflix,<br/>Spotify, Airbnb,<br/>Uber, etc.]
    end

    A -->|HTTP/REST| B
    B --> C --> D
    D --> E
    E --> F
    E --> G
    G --> H
    E --> I
    E --> J
    E --> K
    I --> L
    J --> L
    L --> M
    L --> N
    E --> O
    O --> P

    style A fill:#e1f5ff
    style B fill:#fff3cd
    style E fill:#d4edda
    style L fill:#f8d7da
    style O fill:#e2e3e5
```

### Request Flow Diagram

```mermaid
sequenceDiagram
    participant U as User
    participant R as React UI
    participant F as FastAPI
    participant A as Agent
    participant M as Memory System
    participant D as PostgreSQL
    participant L as LLM

    U->>R: Send message
    R->>F: POST /chat/v2

    F->>F: Extract user_id, service, mode
    F->>M: Load short-term memory
    M->>D: Query checkpoints table
    D-->>M: Last 30 messages

    F->>M: Load long-term memory
    M->>D: Query store table
    D-->>M: Stored entities

    F->>A: Create dynamic agent<br/>with system prompt
    A->>A: Build message history<br/>+ stored memories

    A->>L: Invoke LLM with context

    alt Rate Limit Hit
        L-->>A: 429 Error
        A->>A: Switch to next API key
        A->>L: Retry with new key
    end

    L-->>A: Generate response

    A->>M: Extract entities from conversation
    M->>L: LLM-based extraction
    L-->>M: Entities with metadata
    M->>M: Filter (confidence ≥ 0.5)
    M->>D: Store in store table

    A->>M: Save checkpoint
    M->>D: Update checkpoints table

    A-->>F: Return response + metadata
    F-->>R: JSON response
    R-->>U: Display message
```

---

## Technology Stack

### Backend Technologies

| Component | Version | Purpose | Why Chosen |
|-----------|---------|---------|------------|
| **Python** | 3.8+ | Runtime | Async/await support, rich AI/ML ecosystem |
| **FastAPI** | 0.115.0 | Web Framework | High performance, async, auto API docs, type validation |
| **LangGraph** | 1.0.2 | Agent Orchestration | State management, checkpointing, ReAct pattern |
| **LangChain** | 1.0.3 | LLM Framework | Multi-provider support, message abstraction |
| **asyncpg** | 0.30.0 | PostgreSQL Driver | Fastest async Postgres driver for Python |
| **PostgreSQL** | 15 | Database | ACID compliance, JSON support, reliability |
| **pydantic** | 2.x | Data Validation | Type safety, automatic validation |
| **uvicorn** | 0.24.0 | ASGI Server | High-performance async server |
| **python-dotenv** | 1.0.0 | Config Management | Environment variable loading |

### Frontend Technologies

| Component | Version | Purpose | Why Chosen |
|-----------|---------|---------|------------|
| **React** | 19.1.1 | UI Framework | Modern, component-based, large ecosystem |
| **Vite** | 7.1.7 | Build Tool | Lightning-fast HMR, modern dev experience |
| **Tailwind CSS** | 4.1.16 | Styling | Utility-first, fast development, small bundle |
| **JavaScript** | ES2022 | Language | Latest features, async/await |

### Infrastructure

| Component | Version | Purpose |
|-----------|---------|---------|
| **Docker** | 20+ | Containerization (PostgreSQL) |
| **Docker Compose** | 2.x | Multi-container orchestration |
| **npm** | 8+ | Frontend package management |
| **pip** | Latest | Python package management |

### LLM Providers Supported

| Provider | Models | Cost | Speed | Notes |
|----------|--------|------|-------|-------|
| **Groq** | Llama 3.3 70B, Mixtral 8x7B | FREE | Very Fast | Recommended for development |
| **DeepSeek** | deepseek-chat | 95% cheaper than OpenAI | Fast | Cost-effective production |
| **OpenAI** | GPT-4, GPT-3.5-turbo | Premium pricing | Fast | Highest quality |

---

## Core Components

### 1. FastAPI Server (`server.py`)

**Location:** `/Users/ny/Desktop/Nelson/Projects/AI/MemoryChat/agent-memory-chatbot/server.py`
**Lines:** 1195 total

#### Key Functions

##### `switch_to_next_api_key()` (Lines 62-100)
Handles automatic API key rotation on rate limit errors.

```python
def switch_to_next_api_key():
    """
    Switch to the next available API key and reinitialize the agent.
    Returns True if switched successfully, False if no more keys available.
    """
    global current_api_key_index, llm, global_agent

    next_index = current_api_key_index + 1
    if next_index >= len(API_KEYS):
        return False

    current_api_key_index = next_index
    # Reinitialize LLM with new key
    llm = init_chat_model(...)
    # Reinitialize agent
    global_agent = create_react_agent(...)
    return True
```

**Features:**
- Supports comma-separated API keys in `.env`
- Automatic failover on 429 rate limit errors
- Global LLM and agent reinitialization
- Logs key switches with masked keys for security

##### `extract_memories_with_llm()` (Lines 169-321)
Phase 1 implementation of LLM-based entity extraction.

```python
async def extract_memories_with_llm(
    message: str,
    conversation_history: List[Dict[str, str]],
    user_id: str
) -> Optional[MemoryExtraction]:
    """
    Use LLM to extract entities and facts from conversation.

    Features:
    - 5W1H context capture (Who, What, When, Where, Why, How)
    - 7 entity types with confidence scoring
    - Temporal awareness (past/current/future)
    - Reference sentence preservation
    """
```

**Extraction Prompt Design:**
- Analyzes last 5 messages for context
- Instructs LLM to capture complete context (5W1H)
- Defines 7 entity types: person_name, age, profession, location, preference, fact, relationship
- Requests confidence scores (0.0-1.0)
- Requests importance scores (0.0-1.0)
- Requests temporal status (past/current/future/null)
- Requests reference sentences for context

**Entity Types:**

| Type | Description | Example |
|------|-------------|---------|
| `person_name` | User's name or people mentioned | "John Smith", "Sarah from work" |
| `age` | Age information | "32 years old", "born in 1992" |
| `profession` | Jobs, careers, occupations | "software engineer at Google" |
| `location` | Cities, countries, addresses | "lives in Toronto", "from Hong Kong" |
| `preference` | Likes, dislikes, hobbies | "loves Italian food", "plays basketball" |
| `fact` | General facts about user | "vegetarian", "has two dogs" |
| `relationship` | Family, friends, colleagues | "married to Alice", "friend Mike from Boston" |

**Quality Thresholds:**
- Minimum confidence: 0.5 (only entities ≥0.5 are stored)
- High confidence (1.0): Explicit statements
- Medium confidence (0.7-0.9): Strong context
- Low confidence (0.5-0.6): Implied information

##### `create_system_prompt()` (Lines 324-657)
Generates dynamic system prompts based on mode and service.

```python
def create_system_prompt(
    mode_type: str = "ask",
    selected_service: str = None
) -> SystemMessage:
    """
    Create a dynamic system prompt.

    Args:
        mode_type: "ask" (information) or "agent" (execution)
        selected_service: Service ID like "youtube", "airbnb", etc.

    Returns:
        SystemMessage with complete prompt
    """
```

**Prompt Structure:**

```
┌─────────────────────────────────────────┐
│ Base Memory System Prompt              │
│ - Short-term: Last 30 messages         │
│ - Long-term: Persistent entities       │
│ - Critical memory rules                │
└─────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│ Mode-Specific Section                  │
│ - Ask mode: Information & Guidance     │
│ - Agent mode: Planning & Execution     │
└─────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│ Service-Specific Context (if selected) │
│ - Service name and role                │
│ - Ask/Agent capabilities               │
│ - How to respond/execute               │
│ - First message instructions           │
└─────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│ User Commands Section                  │
│ - Memory commands                      │
│ - Help commands                        │
└─────────────────────────────────────────┘
```

**Service Capabilities Dictionary** (Lines 336-502):

```python
service_capabilities = {
    "youtube": {
        "name": "YouTube",
        "ask_capabilities": [
            "Search for videos on any topic",
            "Get trending videos and popular content",
            "Find channels and creators",
            "Check video statistics and information"
        ],
        "agent_capabilities": [
            "Play specific videos or music",
            "Create and manage playlists",
            "Subscribe to channels",
            "Like and save videos"
        ]
    },
    # ... 10 more services
}
```

**All 11 Services:**
1. YouTube
2. Netflix
3. Prime Video
4. Spotify
5. Airbnb
6. Booking.com
7. Uber Eats
8. DoorDash
9. Grubhub
10. Uber
11. Lyft

##### `/chat/v2` Endpoint (Lines 705-1020)
Main chat endpoint handling all message processing.

**Request Model:**
```python
class ChatRequest(BaseModel):
    message: str                              # User's message
    user_id: str                             # Session identifier
    memory_source: Optional[str] = "both"     # "short", "long", "both"
    messages: Optional[List[Message]] = []    # Previous messages
    mode_type: Optional[str] = "ask"         # "ask" or "agent"
    selected_service: Optional[str] = None    # Service ID
```

**Response Model:**
```python
class ChatResponse(BaseModel):
    response: str                                    # AI response
    memories_used: Optional[List[Dict]] = []         # Memories referenced
    facts_extracted: Optional[List[str]] = []        # New entities extracted
    complexity_level: Optional[str] = "simple"       # Complexity indicator
    mode_transitions: Optional[List[str]] = []       # Mode changes
    thinking_process: Optional[str] = ""             # Reasoning trace
    quality_score: Optional[float] = 0.0             # Response quality
```

**Processing Flow:**

1. **Input Validation** (Lines 718-730)
   ```python
   if not request.message.strip():
       raise HTTPException(status_code=400, detail="Message cannot be empty")
   ```

2. **Configuration Setup** (Lines 732-750)
   ```python
   config = {
       "configurable": {
           "thread_id": request.user_id,
           "user_id": request.user_id
       }
   }
   ```

3. **Memory Loading** (Lines 760-817)
   - Load short-term memory (last 30 messages from checkpoints)
   - Load long-term memory (entities from store)
   - Format as augmented input with [STORED MEMORIES] section

4. **Dynamic Agent Creation** (Lines 743-750)
   ```python
   request_agent = create_react_agent(
       model=llm,
       tools=[],
       prompt=dynamic_system_message,
       pre_model_hook=pre_model_hook,
       checkpointer=global_checkpointer,
       store=global_store
   )
   ```

5. **Agent Invocation with Retry** (Lines 822-870)
   - Automatic API key rotation on rate limits
   - Max retries = number of API keys
   - Exponential backoff on failures

6. **Memory Extraction** (Lines 875-935)
   - LLM-based entity extraction
   - Confidence filtering (≥0.5)
   - Store in PostgreSQL store table

7. **Response Formation** (Lines 960-1020)
   - Extract AI response
   - Format memories_used
   - Format facts_extracted
   - Return ChatResponse

### 2. React Frontend (`ChatInterface.jsx`)

**Location:** `/Users/ny/Desktop/Nelson/Projects/AI/MemoryChat/agent-memory-chatbot/chatbot-ui/src/components/ChatInterface.jsx`

#### Component Structure

```mermaid
graph TB
    A[ChatInterface Component]

    A --> B[State Management]
    B --> B1[messages]
    B --> B2[inputMessage]
    B --> B3[isLoading]
    B --> B4[userId]
    B --> B5[memorySource]
    B --> B6[selectedService]
    B --> B7[modeType]

    A --> C[UI Sections]
    C --> C1[Header with Controls]
    C --> C2[Memory Source Selector]
    C --> C3[Mode Selector Ask/Agent]
    C --> C4[Service Dropdown 11 services]
    C --> C5[Messages Display Area]
    C --> C6[Input Box]

    A --> D[Functions]
    D --> D1[sendMessage API call]
    D --> D2[handleKeyPress Enter to send]
    D --> D3[Auto-scroll to bottom]

    style A fill:#e1f5ff
    style B fill:#d4edda
    style C fill:#fff3cd
    style D fill:#f8d7da
```

#### Key Features

1. **Multi-Session Support**
   - Each session has unique `userId`
   - Sessions maintained in localStorage
   - Session switching preserves state

2. **Memory Source Selection**
   - **Short-term**: Uses only last 30 messages
   - **Long-term**: Uses only stored entities
   - **Both**: Combines short + long-term (default)

3. **Mode Toggle**
   - **Ask Mode**: Information and guidance
   - **Agent Mode**: Task execution simulation

4. **Service Integration**
   - Dropdown with 11 services
   - Icon-based visual representation
   - Dynamically updates system prompt

5. **Real-Time Updates**
   - Loading indicator during API calls
   - Auto-scroll to latest message
   - Error handling with user feedback

---

## Database Architecture

### Entity Relationship Diagram

```mermaid
erDiagram
    CHECKPOINTS ||--o{ CHECKPOINT_BLOBS : contains
    CHECKPOINTS ||--o{ CHECKPOINT_WRITES : contains
    STORE ||--o{ STORE_ITEMS : contains

    CHECKPOINTS {
        text thread_id PK
        text checkpoint_ns PK
        bigint checkpoint_id PK
        text parent_checkpoint_id
        text type
        jsonb checkpoint
        jsonb metadata
    }

    CHECKPOINT_BLOBS {
        text thread_id FK
        text checkpoint_ns FK
        bigint checkpoint_id FK
        text channel
        text type
        bytea blob
    }

    CHECKPOINT_WRITES {
        text thread_id FK
        text checkpoint_ns FK
        bigint checkpoint_id FK
        text task_id
        bigint idx
        text channel
        text type
        bytea blob
    }

    STORE {
        text namespace PK
        text key PK
        jsonb value
        timestamp created_at
        timestamp updated_at
    }

    STORE_ITEMS {
        uuid id PK
        text namespace FK
        text key FK
        text user_id
        text entity_type
        text entity_value
        float confidence
        float importance
        text temporal_status
        text reference_sentence
        text context
        timestamp created_at
    }
```

### Table Schemas

#### 1. `checkpoints` Table
**Purpose:** Store short-term memory (last 30 conversation messages)

| Column | Type | Description |
|--------|------|-------------|
| `thread_id` | TEXT | Session/user identifier (PK) |
| `checkpoint_ns` | TEXT | Namespace for checkpoints (PK) |
| `checkpoint_id` | BIGINT | Unique checkpoint ID (PK) |
| `parent_checkpoint_id` | TEXT | Reference to parent checkpoint |
| `type` | TEXT | Checkpoint type |
| `checkpoint` | JSONB | Full checkpoint data (messages, state) |
| `metadata` | JSONB | Additional metadata |

**Indexes:**
- Primary key: `(thread_id, checkpoint_ns, checkpoint_id)`
- Index on `thread_id` for fast session lookup

**Sample Data:**
```json
{
  "thread_id": "user_12345",
  "checkpoint_id": 1,
  "checkpoint": {
    "v": 1,
    "id": "checkpoint_uuid",
    "ts": "2025-11-16T12:00:00Z",
    "channel_values": {
      "messages": [
        {"role": "user", "content": "My name is Alice"},
        {"role": "assistant", "content": "Nice to meet you, Alice!"}
      ]
    }
  }
}
```

#### 2. `store` Table
**Purpose:** Store long-term memory (entities extracted from conversations)

| Column | Type | Description |
|--------|------|-------------|
| `namespace` | TEXT | Namespace (e.g., "user_memories") (PK) |
| `key` | TEXT | Unique key (user_id + entity_id) (PK) |
| `value` | JSONB | Entity data with metadata |
| `created_at` | TIMESTAMP | Creation timestamp |
| `updated_at` | TIMESTAMP | Last update timestamp |

**Indexes:**
- Primary key: `(namespace, key)`
- Index on `namespace` for fast filtering
- GIN index on `value` for JSONB queries

**Sample Data:**
```json
{
  "namespace": "user_memories",
  "key": "user_12345_entity_001",
  "value": {
    "type": "person_name",
    "value": "Alice",
    "confidence": 1.0,
    "importance": 0.9,
    "temporal_status": "current",
    "reference_sentence": "My name is Alice",
    "context": "User introduction",
    "user_id": "user_12345",
    "created_at": "2025-11-16T12:00:00Z"
  }
}
```

### Database Connection Configuration

**Connection String:**
```python
DB_URI = "postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable"
```

**Connection Pooling:**
- Managed by `asyncpg` and LangGraph
- Async context managers for automatic cleanup
- Connection reuse across requests

**Initialization:**
```python
# On startup
global_checkpointer_cm = AsyncPostgresSaver.from_conn_string(DB_URI)
global_checkpointer = await global_checkpointer_cm.__aenter__()

global_store_cm = AsyncPostgresStore.from_conn_string(DB_URI)
global_store = await global_store_cm.__aenter__()
```

---

## Memory System Implementation

### Dual-Memory Architecture

```mermaid
graph LR
    subgraph "Input Processing"
        A[User Message]
    end

    subgraph "Short-Term Memory"
        B[Checkpoints Table]
        C[Last 30 Messages]
        D[Session-Scoped]
    end

    subgraph "Long-Term Memory"
        E[Store Table]
        F[Extracted Entities]
        G[Cross-Session]
    end

    subgraph "Memory Retrieval"
        H[Load Checkpoint]
        I[Load Entities]
        J[Merge Memories]
    end

    subgraph "Context Building"
        K[Augmented Input]
        L[STORED MEMORIES Section]
        M[Recent Messages]
    end

    subgraph "LLM Processing"
        N[Agent with Full Context]
    end

    A --> H
    A --> I
    H --> B
    B --> C
    C --> D
    I --> E
    E --> F
    F --> G
    H --> J
    I --> J
    J --> K
    K --> L
    K --> M
    K --> N

    style B fill:#ffc
    style E fill:#cff
    style N fill:#fcf
```

### Memory Loading Process

**Code Flow** (Lines 760-817 in `server.py`):

```python
# 1. Initialize memory containers
message_history = []
stored_memories = []

# 2. Load short-term memory (if enabled)
if normalized_source in ["short", "both"]:
    checkpoint_data = await global_checkpointer.aget(config)
    if checkpoint_data and "messages" in checkpoint_data["channel_values"]:
        for msg in checkpoint_data["channel_values"]["messages"]:
            if msg.role == "user":
                message_history.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                message_history.append(AIMessage(content=msg.content))

# 3. Load long-term memory (if enabled)
if normalized_source in ["long", "both"]:
    namespace = ("user_memories", request.user_id)
    stored_items = await global_store.asearch(namespace)

    for item in stored_items:
        entity_type = item.value.get("type", "unknown")
        entity_value = item.value.get("value", "")
        temporal = item.value.get("temporal_status", "current")

        memory_str = f"{entity_type}: {entity_value}"
        if temporal and temporal != "current":
            memory_str += f" ({temporal})"
        stored_memories.append(memory_str)

# 4. Build augmented input
augmented_input = request.message
if stored_memories:
    memory_context = "\n".join([f"- {mem}" for mem in stored_memories])
    augmented_input = (
        f"[STORED MEMORIES from previous conversations:\n{memory_context}]\n\n"
        f"Current user message: {request.message}"
    )

# 5. Add to message history
message_history.append(HumanMessage(content=augmented_input))
```

### Memory Extraction Process

**Entity Extraction Flow:**

```mermaid
sequenceDiagram
    participant A as Agent
    participant E as Extractor
    participant L as LLM
    participant V as Validator
    participant S as Store

    A->>E: extract_memories_with_llm()
    E->>E: Build context<br/>(last 5 messages)
    E->>E: Format extraction prompt<br/>with 5W1H instructions

    E->>L: Invoke LLM with prompt
    L-->>E: JSON response with entities

    E->>E: Parse JSON
    E->>V: Validate entities

    loop For each entity
        V->>V: Check confidence ≥ 0.5
        alt Confidence OK
            V->>S: Store entity
        else Low confidence
            V->>V: Discard entity
        end
    end

    S-->>A: Extraction complete
```

**Extraction Prompt Template** (Lines 197-278):

```python
extraction_prompt = f"""You are an expert at extracting memorable information from conversations with COMPLETE CONTEXT (5W1H: Who, What, When, Where, Why, How).

CONVERSATION CONTEXT:
{context}

TASK: Analyze the user's latest message and extract information with FULL CONTEXTUAL DETAILS in a SINGLE pass.

EXTRACT these entity types:
- person_name: User's name or names of people mentioned
- age: User's age or ages mentioned
- profession: Jobs, careers, occupations
- location: Cities, countries, addresses
- preference: Likes, dislikes, preferences (food, hobbies, etc.)
- fact: General facts about the user
- relationship: Family members, friends, colleagues WITH CONTEXT

CRITICAL: CAPTURE COMPLETE CONTEXT (5W1H)
For each entity, include ALL relevant context in the VALUE field:
- WHO: Include names, relationships, people involved
- WHAT: The specific activity, object, or information
- WHEN: Time references (past, current, future, specific times)
- WHERE: Locations if mentioned
- WHY: Reasons or motivations if stated
- HOW: Methods or manner if relevant

EXAMPLES OF COMPLETE CONTEXT:
❌ BAD (Incomplete):
  - fact: "collaborate on lesson plans"
  - preference: "basketball"
  - relationship: "friend"

✅ GOOD (Complete Context):
  - relationship: "collaborates with Sarah on lesson plans"
  - preference: "plays basketball every Saturday at Central Park"
  - relationship: "childhood friend Mike from Boston"

TEMPORAL AWARENESS:
- "past": Things that were true but are no longer (e.g., "I lived in Hong Kong")
- "current": Things that are currently true (e.g., "I live in Canada now")
- "future": Future plans or intentions (e.g., "I plan to become a doctor")
- null: Timeless facts (e.g., "My name is John")

REFERENCE SENTENCE:
Extract the exact or compacted sentence from the conversation that contains this information.

SCORING GUIDELINES:
- Confidence: 0.0-1.0 (how certain you are about this entity)
  * 1.0: Explicit statements ("My name is John")
  * 0.7-0.9: Strong context ("I'm a software engineer")
  * 0.5-0.6: Implied information ("I work in tech")
  * <0.5: Weak/uncertain information

- Importance: 0.0-1.0 (how important is this to remember)
  * 1.0: Critical identity/preference information
  * 0.7-0.9: Significant facts or relationships
  * 0.5-0.6: Moderate relevance
  * <0.5: Minor details

Respond with JSON:
{{
  "entities": [
    {{
      "type": "entity_type",
      "value": "complete contextual value",
      "confidence": 0.0-1.0,
      "importance": 0.0-1.0,
      "temporal_status": "past/current/future/null",
      "reference_sentence": "exact sentence from conversation"
    }}
  ],
  "summary": "One-sentence summary of what to remember",
  "importance": 0.0-1.0,
  "should_store": true/false
}}
"""
```

**Storage Logic** (Lines 875-935):

```python
# Extract memories
extraction_result = await extract_memories_with_llm(
    message=request.message,
    conversation_history=conversation_history,
    user_id=request.user_id
)

if extraction_result and extraction_result.should_store:
    for entity in extraction_result.entities:
        # Filter by confidence threshold
        if entity.confidence >= 0.5:
            namespace = ("user_memories", request.user_id)
            key = f"{request.user_id}_entity_{uuid.uuid4().hex[:8]}"

            value = {
                "type": entity.type,
                "value": entity.value,
                "confidence": entity.confidence,
                "importance": extraction_result.importance,
                "temporal_status": entity.temporal_status,
                "reference_sentence": entity.reference_sentence,
                "context": entity.context,
                "user_id": request.user_id,
                "created_at": datetime.utcnow().isoformat()
            }

            # Store in long-term memory
            await global_store.aput(namespace, key, value)
            facts_extracted.append(f"{entity.type}: {entity.value}")
```

### Memory Retrieval Optimization

**Checkpointing Strategy:**
- Last 30 messages per session (configurable via `SHORT_TERM_MESSAGE_LIMIT`)
- Automatic pruning of old checkpoints
- Fast lookup by `thread_id`

**Store Query Strategy:**
```python
# Search by namespace (user-scoped)
namespace = ("user_memories", user_id)
stored_items = await global_store.asearch(namespace)

# Items are already filtered by user_id in namespace
# No need for additional filtering
```

**Performance Optimizations:**
- Async I/O for database queries
- Connection pooling
- JSONB indexing for fast queries
- Batch loading of memories

---

## Service Integration Architecture

### Service Catalog Structure

```mermaid
graph TB
    subgraph "Service Capabilities Dictionary"
        A[11 Services]
    end

    subgraph "Service Categories"
        B[Streaming & Entertainment<br/>4 services]
        C[Travel & Accommodation<br/>2 services]
        D[Food Delivery<br/>3 services]
        E[Transportation<br/>2 services]
    end

    A --> B
    A --> C
    A --> D
    A --> E

    subgraph "Service Properties"
        F[name: Display name]
        G[ask_capabilities: List]
        H[agent_capabilities: List]
    end

    B --> F
    B --> G
    B --> H

    subgraph "Dynamic Prompt Generation"
        I[Ask Mode Prompt]
        J[Agent Mode Prompt]
    end

    G --> I
    H --> J

    style A fill:#e1f5ff
    style B fill:#d4edda
    style C fill:#fff3cd
    style D fill:#ffc
    style E fill:#fcf
```

### Service Definition Example

**YouTube Service** (Lines 337-351):

```python
"youtube": {
    "name": "YouTube",
    "ask_capabilities": [
        "Search for videos on any topic",
        "Get trending videos and popular content",
        "Find channels and creators",
        "Check video statistics and information"
    ],
    "agent_capabilities": [
        "Play specific videos or music",
        "Create and manage playlists",
        "Subscribe to channels",
        "Like and save videos"
    ]
}
```

### Complete Service List

| Category | Services | Total |
|----------|----------|-------|
| **Streaming & Entertainment** | YouTube, Netflix, Prime Video, Spotify | 4 |
| **Travel & Accommodation** | Airbnb, Booking.com | 2 |
| **Food Delivery** | Uber Eats, DoorDash, Grubhub | 3 |
| **Transportation** | Uber, Lyft | 2 |
| **TOTAL** | | **11** |

### Service-Specific Prompt Generation

**Ask Mode Service Prompt** (Lines 577-601):

```python
if mode_type == "ask":
    service_section = (
        f"SELECTED SERVICE: {service_info['name']} (ASK MODE - Information Hub)\n"
        f"🎯 YOUR ROLE: You are the {service_info['name']} information assistant.\n\n"
        f"⚠️ CRITICAL INSTRUCTIONS:\n"
        f"1. You ARE the {service_info['name']} service - answer on behalf of {service_info['name']}\n"
        f"2. ONLY discuss {service_info['name']} - if asked about other services, politely redirect\n"
        f"3. IMAGINE realistic, detailed information (pricing, availability, features, options)\n"
        f"4. Provide specific details like prices, locations, times, features, comparisons\n"
        f"5. Be helpful and informative, like a customer service representative\n\n"
        f"WHAT YOU CAN HELP WITH:\n"
    )
    for cap in service_info['ask_capabilities']:
        service_section += f"• {cap}\n"
    service_section += (
        f"\nHOW TO RESPOND:\n"
        f"• FIRST MESSAGE: Always start by introducing yourself as the {service_info['name']} assistant\n"
        f"  Example: 'Hi! I'm your {service_info['name']} assistant. I can help you with [list capabilities].'\n"
        f"• Imagine you have access to {service_info['name']}'s full database\n"
        f"• Create realistic pricing, options, availability, and details\n"
        f"• When asked 'what services do you have?', list YOUR {service_info['name']} capabilities\n"
        f"• Provide comparisons, recommendations, and detailed information\n"
        f"• Remember: You're providing INFORMATION, not executing actions\n\n"
    )
```

**Agent Mode Service Prompt** (Lines 603-631):

```python
else:  # agent mode
    service_section = (
        f"SELECTED SERVICE: {service_info['name']} (AGENT MODE - Task Executor)\n"
        f"🎯 YOUR ROLE: You are the {service_info['name']} AI agent that executes tasks.\n\n"
        f"⚠️ CRITICAL INSTRUCTIONS:\n"
        f"1. You ARE the {service_info['name']} agent - execute tasks for {service_info['name']}\n"
        f"2. ONLY execute {service_info['name']} actions - politely decline other service requests\n"
        f"3. SIMULATE realistic task completion with detailed confirmations\n"
        f"4. Send completion messages: receipts, confirmations, booking IDs, order numbers\n"
        f"5. Create realistic agentic flows for all {service_info['name']} operations\n\n"
        f"WHAT YOU CAN EXECUTE:\n"
    )
    for cap in service_info['agent_capabilities']:
        service_section += f"• {cap}\n"
    service_section += (
        f"\nHOW TO EXECUTE TASKS:\n"
        f"• FIRST MESSAGE: Always start by introducing yourself as the {service_info['name']} agent\n"
        f"• Simulate realistic {service_info['name']} operations\n"
        f"• Provide step-by-step progress updates\n"
        f"• Generate realistic completion messages (booking IDs, order numbers, tracking info)\n"
        f"• Send receipts, confirmations, and status updates\n"
        f"• Examples of completion messages:\n"
        f"  - Booking services: 'Booking #ABC123 confirmed! Total: $XXX, Date: ...'\n"
        f"  - Food delivery: 'Order #789 placed! Estimated delivery: 30 mins, Total: $XX'\n"
        f"  - Streaming: 'Now playing: [Song/Video Name] - Added to your history'\n"
        f"  - Ride sharing: 'Driver on the way! ETA: 5 mins, License: XYZ-1234'\n\n"
    )
```

### Adding New Services

**Steps to add a new service:**

1. **Add to service_capabilities dictionary** (Line 336):
```python
"newservice": {
    "name": "New Service Name",
    "ask_capabilities": [
        "Capability 1",
        "Capability 2",
        "Capability 3"
    ],
    "agent_capabilities": [
        "Action 1",
        "Action 2",
        "Action 3"
    ]
}
```

2. **Add to frontend service list** (`ChatInterface.jsx`):
```javascript
const services = [
    { id: "newservice", name: "New Service", icon: "🆕" },
    // ... existing services
];
```

3. **No other changes needed** - the dynamic prompt generation handles the rest!

---

## API Specification

### Base URL
```
http://localhost:8000
```

### Endpoints

#### 1. Health Check
```http
GET /
```

**Response:**
```json
{
  "status": "ok",
  "message": "Memory Chat API is running"
}
```

#### 2. Chat (Main Endpoint)
```http
POST /chat/v2
```

**Request Body:**
```json
{
  "message": "My name is Alice and I love pizza",
  "user_id": "user_12345",
  "memory_source": "both",
  "messages": [],
  "mode_type": "ask",
  "selected_service": "airbnb"
}
```

**Request Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `message` | string | ✅ | - | User's message |
| `user_id` | string | ✅ | - | Session/user identifier |
| `memory_source` | string | ❌ | "both" | "short", "long", or "both" |
| `messages` | array | ❌ | [] | Previous messages (for UI context) |
| `mode_type` | string | ❌ | "ask" | "ask" or "agent" |
| `selected_service` | string | ❌ | null | Service ID (e.g., "youtube") |

**Response:**
```json
{
  "response": "Nice to meet you, Alice! I see you love pizza. I'll remember that.",
  "memories_used": [
    {
      "type": "person_name",
      "value": "Alice",
      "confidence": 1.0
    }
  ],
  "facts_extracted": [
    "person_name: Alice",
    "preference: loves pizza"
  ],
  "complexity_level": "simple",
  "mode_transitions": [],
  "thinking_process": "",
  "quality_score": 0.0
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `response` | string | AI assistant's response |
| `memories_used` | array | Memories referenced in this response |
| `facts_extracted` | array | New entities extracted and stored |
| `complexity_level` | string | Response complexity indicator |
| `mode_transitions` | array | Mode changes during processing |
| `thinking_process` | string | Reasoning trace (if enabled) |
| `quality_score` | float | Response quality score |

#### 3. Get Configuration
```http
GET /api/config
```

**Response:**
```json
{
  "short_term_message_limit": 30
}
```

#### 4. Get Conversation History
```http
GET /conversation/{user_id}
```

**Response:**
```json
{
  "user_id": "user_12345",
  "messages": [
    {
      "role": "user",
      "content": "My name is Alice"
    },
    {
      "role": "assistant",
      "content": "Nice to meet you, Alice!"
    }
  ],
  "message_count": 2
}
```

#### 5. Inspect Memories
```http
GET /memories/all/inspect?user_id={user_id}
```

**Response:**
```json
{
  "user_id": "user_12345",
  "total_memories": 5,
  "memories": [
    {
      "type": "person_name",
      "value": "Alice",
      "confidence": 1.0,
      "importance": 0.9,
      "temporal_status": "current",
      "reference_sentence": "My name is Alice",
      "created_at": "2025-11-16T12:00:00Z"
    }
  ]
}
```

#### 6. Get Memories (List)
```http
GET /memories/{user_id}
```

**Response:**
```json
{
  "user_id": "user_12345",
  "memories": [
    {
      "type": "person_name",
      "value": "Alice",
      "confidence": 1.0
    }
  ]
}
```

#### 7. Get Memory Bank
```http
GET /memory-bank/{user_id}
```

**Response:**
```json
{
  "user_id": "user_12345",
  "memories": [
    {
      "namespace": ["user_memories", "user_12345"],
      "key": "user_12345_entity_abc123",
      "value": {
        "type": "person_name",
        "value": "Alice",
        "confidence": 1.0
      },
      "created_at": "2025-11-16T12:00:00Z"
    }
  ]
}
```

#### 8. Delete User Memories
```http
DELETE /memories/{user_id}
```

**Response:**
```json
{
  "message": "All memories deleted for user user_12345",
  "deleted_count": 5
}
```

#### 9. Clear All Memories
```http
DELETE /memories/all/clear
```

**Response:**
```json
{
  "message": "All memories cleared from database",
  "deleted_count": 127
}
```

#### 10. List Users
```http
GET /users/list
```

**Response:**
```json
{
  "users": [
    {
      "user_id": "user_12345",
      "memory_count": 5,
      "last_activity": "2025-11-16T12:00:00Z"
    }
  ],
  "total_users": 1
}
```

### Error Responses

**400 Bad Request:**
```json
{
  "detail": "Message cannot be empty"
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Error processing request: [error details]"
}
```

---

## Frontend Architecture

### React Component Hierarchy

```mermaid
graph TB
    A[App.jsx]
    A --> B[ChatInterface.jsx]

    B --> C[Header Section]
    C --> C1[Title]
    C --> C2[Memory Source Toggle]
    C --> C3[Mode Toggle Ask/Agent]

    B --> D[Service Selection]
    D --> D1[Service Dropdown]
    D --> D2[Service Icons]

    B --> E[Messages Display]
    E --> E1[User Messages]
    E --> E2[Assistant Messages]
    E --> E3[Loading Indicator]

    B --> F[Input Section]
    F --> F1[Text Input]
    F --> F2[Send Button]

    B --> G[State Management]
    G --> G1[messages useState]
    G --> G2[inputMessage useState]
    G --> G3[isLoading useState]
    G --> G4[userId useState]
    G --> G5[memorySource useState]
    G --> G6[selectedService useState]
    G --> G7[modeType useState]

    B --> H[API Integration]
    H --> H1[sendMessage function]
    H --> H2[fetch /chat/v2]

    style A fill:#e1f5ff
    style B fill:#d4edda
    style G fill:#fff3cd
    style H fill:#ffc
```

### State Management

**State Variables:**

```javascript
const [messages, setMessages] = useState([]);
const [inputMessage, setInputMessage] = useState('');
const [isLoading, setIsLoading] = useState(false);
const [userId] = useState(() => `user_${Date.now()}`);
const [memorySource, setMemorySource] = useState('both');
const [selectedService, setSelectedService] = useState(null);
const [modeType, setModeType] = useState('ask');
```

### API Integration

**sendMessage Function:**

```javascript
const sendMessage = async () => {
  if (!inputMessage.trim() || isLoading) return;

  const userMessage = {
    role: 'user',
    content: inputMessage
  };

  setMessages(prev => [...prev, userMessage]);
  setInputMessage('');
  setIsLoading(true);

  try {
    const response = await fetch('http://localhost:8000/chat/v2', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: inputMessage,
        user_id: userId,
        memory_source: memorySource,
        messages: messages,
        mode_type: modeType,
        selected_service: selectedService
      })
    });

    const data = await response.json();

    const assistantMessage = {
      role: 'assistant',
      content: data.response,
      metadata: {
        memories_used: data.memories_used,
        facts_extracted: data.facts_extracted
      }
    };

    setMessages(prev => [...prev, assistantMessage]);
  } catch (error) {
    console.error('Error:', error);
  } finally {
    setIsLoading(false);
  }
};
```

### Styling with Tailwind CSS

**Key CSS Classes:**

```css
/* Glass effect utility */
.glass-effect {
  backdrop-filter: blur(1rem);
  background: rgba(255, 255, 255, 0.8);
  border: 0px solid rgba(59, 130, 246, 0.15);
}

/* Glass hover effect */
.glass-hover:hover {
  background: rgba(255, 255, 255, 0.9);
  border-color: rgba(59, 130, 246, 0.25);
  transition: all 0.3s;
}

/* Gradient background */
body {
  background: linear-gradient(135deg, #f0f9ff 0%, #f0f6ff 50%, #ffffff 100%);
  min-height: 100vh;
}
```

---

## Deployment Architecture

### Local Development Setup

```mermaid
graph TB
    subgraph "Docker Container"
        A[(PostgreSQL<br/>localhost:5432)]
    end

    subgraph "Backend Process"
        B[Python Virtual Env<br/>.venv]
        C[FastAPI Server<br/>localhost:8000]
    end

    subgraph "Frontend Process"
        D[Vite Dev Server<br/>localhost:5173]
        E[React App<br/>Hot Module Reload]
    end

    subgraph "External Services"
        F[OpenAI API]
        G[Groq API]
        H[DeepSeek API]
    end

    A --> C
    B --> C
    C --> F
    C --> G
    C --> H
    D --> E
    E --> C

    style A fill:#f8d7da
    style C fill:#d4edda
    style E fill:#e1f5ff
    style F fill:#fff3cd
```

### Production Deployment Options

#### Option 1: Cloud VM (AWS EC2, GCP Compute Engine)

```mermaid
graph TB
    subgraph "Load Balancer"
        A[HTTPS Load Balancer<br/>SSL Termination]
    end

    subgraph "Application Server"
        B[Gunicorn + Uvicorn Workers<br/>FastAPI Application]
        C[Nginx<br/>Reverse Proxy + Static Files]
    end

    subgraph "Database"
        D[(Managed PostgreSQL<br/>AWS RDS / Cloud SQL)]
    end

    subgraph "Frontend CDN"
        E[S3 + CloudFront<br/>or<br/>Cloud Storage + CDN]
    end

    A --> C
    C --> B
    C --> E
    B --> D

    style A fill:#e1f5ff
    style B fill:#d4edda
    style D fill:#f8d7da
    style E fill:#fff3cd
```

**Deployment Steps:**

1. **Provision VM** (t3.medium or n1-standard-2)
2. **Install dependencies:**
   ```bash
   sudo apt update
   sudo apt install python3.11 python3-pip nginx
   ```
3. **Setup application:**
   ```bash
   git clone [repo]
   cd agent-memory-chatbot
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. **Configure Gunicorn:**
   ```bash
   gunicorn server:app \
     --workers 4 \
     --worker-class uvicorn.workers.UvicornWorker \
     --bind 0.0.0.0:8000
   ```
5. **Setup Nginx reverse proxy:**
   ```nginx
   server {
       listen 80;
       server_name yourdomain.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```
6. **Build and deploy frontend:**
   ```bash
   cd chatbot-ui
   npm run build
   # Upload dist/ to S3 or serve via Nginx
   ```

#### Option 2: Docker Containerization

**docker-compose.production.yml:**

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - app_network

  backend:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - DATABASE_URL=postgresql://postgres:${DB_PASSWORD}@postgres:5432/postgres
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LLM_MODEL=${LLM_MODEL}
    ports:
      - "8000:8000"
    depends_on:
      - postgres
    networks:
      - app_network

  frontend:
    build:
      context: ./chatbot-ui
      dockerfile: Dockerfile
    ports:
      - "80:80"
    networks:
      - app_network

volumes:
  postgres_data:

networks:
  app_network:
```

**Backend Dockerfile:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

EXPOSE 8000

CMD ["gunicorn", "server:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

**Frontend Dockerfile:**

```dockerfile
FROM node:18-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

#### Option 3: Kubernetes (Scalable)

**Kubernetes Architecture:**

```mermaid
graph TB
    subgraph "Ingress Layer"
        A[Ingress Controller<br/>HTTPS + SSL]
    end

    subgraph "Application Pods"
        B[FastAPI Pod 1]
        C[FastAPI Pod 2]
        D[FastAPI Pod N]
        E[Service<br/>Load Balancer]
    end

    subgraph "Frontend Pods"
        F[React Pod 1]
        G[React Pod 2]
        H[Service<br/>Load Balancer]
    end

    subgraph "Database"
        I[(Cloud SQL<br/>or<br/>StatefulSet)]
    end

    A --> E
    A --> H
    E --> B
    E --> C
    E --> D
    H --> F
    H --> G
    B --> I
    C --> I
    D --> I

    style A fill:#e1f5ff
    style E fill:#d4edda
    style I fill:#f8d7da
```

### Environment Configuration

**.env for Production:**

```bash
# LLM Configuration
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1
LLM_MODEL=openai:gpt-4

# Database
DATABASE_URL=postgresql://user:pass@db-host:5432/memory_chat
SHORT_TERM_MESSAGE_LIMIT=30

# Security
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
SECRET_KEY=your-secret-key-here

# Monitoring
SENTRY_DSN=https://...
LOG_LEVEL=INFO
```

---

## Security & Privacy

### Security Measures

#### 1. Environment Variables
```python
# Never commit .env files
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
```

#### 2. CORS Configuration
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### 3. Input Validation
```python
class ChatRequest(BaseModel):
    message: str  # Pydantic validates type
    user_id: str  # Automatically validated

# Additional validation
if not request.message.strip():
    raise HTTPException(status_code=400, detail="Message cannot be empty")
```

#### 4. Database Connection Security
```python
# SSL mode for production
DB_URI = "postgresql://user:pass@host:5432/db?sslmode=require"

# Use managed database with encryption at rest
```

### Privacy Considerations

#### 1. Data Storage
- User data stored per `user_id`
- No PII collection by default
- User-scoped namespaces in store

#### 2. Data Deletion
```python
@app.delete("/memories/{user_id}")
async def delete_user_memories(user_id: str):
    # Delete all memories for a user
    namespace = ("user_memories", user_id)
    items = await global_store.asearch(namespace)
    for item in items:
        await global_store.adelete(namespace, item.key)
```

#### 3. GDPR Compliance
- Right to access: `/memory-bank/{user_id}`
- Right to deletion: `/memories/{user_id}` DELETE
- Right to export: JSON format responses
- Data minimization: Only store entities with confidence ≥ 0.5

#### 4. HIPAA Considerations (for Healthcare Use)
- Deploy in HIPAA-compliant infrastructure
- Enable database encryption at rest
- Implement audit logging
- Sign BAA with cloud provider
- Use dedicated database instances

### API Key Security

**Rotation Strategy:**
```python
# Multiple keys for automatic rotation
API_KEYS = [key.strip() for key in os.getenv("OPENAI_API_KEY").split(",")]

# Masked logging
masked_key = API_KEYS[index][:20] + "..."
print(f"Using key: {masked_key}")
```

**Rate Limit Handling:**
```python
# Automatic failover on rate limits
for attempt in range(max_retries):
    try:
        response = await agent.ainvoke(...)
        break
    except RateLimitError:
        if not switch_to_next_api_key():
            raise  # All keys exhausted
```

---

## Performance & Scalability

### Performance Optimizations

#### 1. Async Architecture
```python
# Async database operations
async def load_memories(user_id):
    checkpoint = await global_checkpointer.aget(config)
    entities = await global_store.asearch(namespace)
    return checkpoint, entities

# Async LLM calls
response = await llm.ainvoke(messages)
```

#### 2. Connection Pooling
- `asyncpg` manages connection pool automatically
- Reuse connections across requests
- Configurable pool size

#### 3. Memory Limit
```python
# Limit short-term memory to 30 messages
SHORT_TERM_MESSAGE_LIMIT = 30

# Trim messages in pre_model_hook
trimmed = trim_messages(
    messages=state["messages"],
    max_tokens=SHORT_TERM_MESSAGE_LIMIT,
    strategy="last"
)
```

#### 4. Response Streaming (Future)
```python
# TODO: Implement streaming for real-time responses
async def stream_response():
    async for chunk in llm.astream(messages):
        yield chunk
```

### Scalability Strategies

#### Horizontal Scaling

```mermaid
graph TB
    A[Load Balancer]

    subgraph "Application Tier Replicas"
        B[FastAPI Instance 1]
        C[FastAPI Instance 2]
        D[FastAPI Instance N]
    end

    subgraph "Shared State"
        E[(PostgreSQL<br/>with Read Replicas)]
    end

    A --> B
    A --> C
    A --> D

    B --> E
    C --> E
    D --> E

    style A fill:#e1f5ff
    style E fill:#f8d7da
```

**Implementation:**
1. Deploy multiple FastAPI instances behind load balancer
2. Use managed PostgreSQL with read replicas
3. Session state stored in database (stateless app servers)
4. Scale horizontally as traffic increases

#### Database Scaling

**Read Replicas:**
```python
# Primary for writes
PRIMARY_DB = "postgresql://primary-host:5432/db"

# Replicas for reads
REPLICA_DB = "postgresql://replica-host:5432/db"

# Route reads to replicas
async def read_memories(user_id):
    # Connect to replica
    async with AsyncPostgresStore.from_conn_string(REPLICA_DB) as store:
        return await store.asearch(namespace)
```

**Sharding by User:**
```python
# Shard database by user_id hash
def get_shard(user_id):
    shard_index = hash(user_id) % NUM_SHARDS
    return SHARD_DATABASES[shard_index]

# Connect to appropriate shard
db_uri = get_shard(request.user_id)
```

#### Caching Strategy

**Redis for Hot Data:**
```python
import redis.asyncio as redis

# Cache frequently accessed memories
async def get_user_memories(user_id):
    cache_key = f"memories:{user_id}"

    # Try cache first
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Fetch from database
    memories = await global_store.asearch(namespace)

    # Cache for 5 minutes
    await redis_client.setex(cache_key, 300, json.dumps(memories))
    return memories
```

### Performance Metrics

**Target Performance:**

| Metric | Target | Notes |
|--------|--------|-------|
| API Response Time (p50) | <500ms | Without LLM call |
| API Response Time (p95) | <2s | With LLM call (Groq) |
| Database Query Time | <50ms | With indexes |
| Memory Extraction Time | <1s | LLM-based extraction |
| Concurrent Requests | 100+ | Per instance |
| Database Connections | 20-50 | Per instance |

**Monitoring:**
```python
import time

@app.middleware("http")
async def add_process_time_header(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response
```

---

## Code Structure

### Project File Tree

```
agent-memory-chatbot/
├── server.py                    # FastAPI backend (1195 lines)
├── requirements.txt             # Python dependencies
├── .env                         # Environment configuration
├── .env.example                 # Environment template
├── docker-compose.yml           # PostgreSQL setup
│
├── chatbot-ui/                  # React frontend
│   ├── src/
│   │   ├── components/
│   │   │   └── ChatInterface.jsx  # Main chat component
│   │   ├── App.jsx              # Root component
│   │   ├── main.jsx             # Entry point
│   │   └── index.css            # Global styles
│   ├── package.json             # Frontend dependencies
│   └── vite.config.js           # Vite configuration
│
├── docs/                        # Documentation
│   ├── business.md              # Business documentation
│   ├── technical.md             # Technical documentation (this file)
│   ├── getting-started.md       # Setup guide
│   ├── FAQ.md                   # Frequently asked questions
│   ├── langchain-vs-langgraph.md # Framework comparison
│   ├── core/
│   │   ├── README.md            # Core docs index
│   │   ├── architecture.md      # System architecture
│   │   ├── database-schema.md   # Database design
│   │   ├── flow-diagrams.md     # Visual workflows
│   │   └── usage-guide.md       # Usage examples
│   ├── memory/
│   │   └── README.md            # Memory system docs
│   └── deployment/
│       └── PRODUCTION_DEPLOYMENT.md # Deployment guide
│
├── 01_shortTermTest.py          # Short-term memory test
├── 02_longTermTest.py           # Long-term memory test
├── inspect_schema.py            # Database schema inspector
├── view_checkpoints.py          # Checkpoint viewer
└── clear_database.py            # Database cleanup utility
```

### Key Code Sections

#### server.py Structure

| Lines | Section | Description |
|-------|---------|-------------|
| 1-60 | Imports & Initialization | FastAPI app, middleware, LLM setup |
| 62-100 | API Key Rotation | switch_to_next_api_key() function |
| 103-148 | Pydantic Models | Request/response schemas |
| 150-166 | Pre-Model Hook | Message trimming for token management |
| 169-321 | Memory Extraction | extract_memories_with_llm() LLM-based |
| 324-657 | System Prompt Generator | create_system_prompt() dynamic prompts |
| 659-703 | Startup/Shutdown | Database initialization |
| 705-1020 | /chat/v2 Endpoint | Main chat processing |
| 1022-1195 | Utility Endpoints | Inspect, delete, list memories |

#### ChatInterface.jsx Structure

| Lines | Section | Description |
|-------|---------|-------------|
| 1-50 | Imports & State | React imports, useState initialization |
| 52-150 | sendMessage Function | API integration logic |
| 152-200 | Event Handlers | Input handling, keyboard events |
| 202-400 | JSX Render | UI components and layout |
| 402-500 | Service Definitions | 11 services with icons |
| 502-600 | Styling | Tailwind classes |

---

## Development Guide

### Local Setup

**Prerequisites:**
- Python 3.8+
- Node.js 16+
- Docker & Docker Compose
- Git

**Step-by-Step:**

1. **Clone Repository:**
   ```bash
   git clone https://github.com/[your-org]/agent-memory-chatbot.git
   cd agent-memory-chatbot
   ```

2. **Start PostgreSQL:**
   ```bash
   docker-compose up -d
   docker ps  # Verify running
   ```

3. **Backend Setup:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt

   # Configure environment
   cp .env.example .env
   # Edit .env and add your OPENAI_API_KEY

   # Start server
   python server.py
   ```

4. **Frontend Setup (New Terminal):**
   ```bash
   cd chatbot-ui
   npm install
   npm run dev
   ```

5. **Access Application:**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Development Workflow

**Hot Reload:**
- Backend: Uvicorn auto-reloads on file changes
- Frontend: Vite HMR for instant updates

**Testing:**
```bash
# Test short-term memory
python 01_shortTermTest.py

# Test long-term memory
python 02_longTermTest.py

# Inspect database schema
python inspect_schema.py

# View checkpoints
python view_checkpoints.py
```

**Database Management:**
```bash
# Clear all data
python clear_database.py

# Connect to PostgreSQL
docker exec -it postgres_db psql -U postgres

# View tables
\dt

# Query checkpoints
SELECT * FROM checkpoints LIMIT 5;

# Query store
SELECT * FROM store LIMIT 5;
```

### Code Style & Best Practices

**Python (Backend):**
- Use type hints: `def func(param: str) -> int:`
- Async everywhere: `async def`, `await`
- Pydantic for validation
- Docstrings for all functions
- Error handling with try/except

**JavaScript (Frontend):**
- Functional components with hooks
- Descriptive variable names
- Comment complex logic
- Use Tailwind for styling
- Handle errors gracefully

**Git Workflow:**
```bash
# Create feature branch
git checkout -b feature/new-service

# Make changes
git add .
git commit -m "feat: Add Google Drive service integration"

# Push and create PR
git push origin feature/new-service
```

### Debugging

**Backend Debugging:**
```python
# Add print statements
print(f"Debug: {variable}")

# Use pdb for breakpoints
import pdb; pdb.set_trace()

# Check logs
# Uvicorn outputs to stdout
```

**Frontend Debugging:**
```javascript
// Console logging
console.log('Debug:', variable);

// React DevTools (browser extension)
// Inspect component state and props

// Network tab
// Check API request/response
```

**Database Debugging:**
```sql
-- Check checkpoint count
SELECT COUNT(*) FROM checkpoints;

-- View user's checkpoints
SELECT * FROM checkpoints WHERE thread_id = 'user_12345';

-- Check store entries
SELECT * FROM store WHERE namespace @> ARRAY['user_memories'];

-- View entity distribution
SELECT
  value->>'type' AS entity_type,
  COUNT(*) AS count
FROM store
GROUP BY entity_type;
```

---

## Appendix

### A. Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | ✅ | - | API key(s) - comma-separated for rotation |
| `OPENAI_API_BASE` | ❌ | https://api.openai.com/v1 | API endpoint |
| `LLM_MODEL` | ❌ | openai:gpt-4 | Model identifier |
| `SHORT_TERM_MESSAGE_LIMIT` | ❌ | 30 | Max messages in short-term memory |
| `DATABASE_URL` | ❌ | localhost | PostgreSQL connection string |
| `CORS_ORIGINS` | ❌ | * | Allowed CORS origins |

### B. LLM Provider Configuration

**OpenAI:**
```bash
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1
LLM_MODEL=openai:gpt-4
```

**Groq (FREE):**
```bash
OPENAI_API_KEY=gsk_...
OPENAI_API_BASE=https://api.groq.com/openai/v1
LLM_MODEL=openai:llama-3.3-70b-versatile
```

**DeepSeek (95% cheaper):**
```bash
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.deepseek.com
LLM_MODEL=openai:deepseek-chat
```

**Multiple Keys for Rotation:**
```bash
OPENAI_API_KEY=key1,key2,key3
```

### C. Database Schema SQL

**Create Tables (Auto-created by LangGraph):**

```sql
-- Checkpoints table
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id BIGINT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx
ON checkpoints(thread_id);

-- Store table
CREATE TABLE IF NOT EXISTS store (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (namespace, key)
);

CREATE INDEX IF NOT EXISTS store_namespace_idx
ON store(namespace);

CREATE INDEX IF NOT EXISTS store_value_idx
ON store USING GIN(value);
```

### D. Mermaid Chart Legend

**Chart Types Used:**

1. **Graph TB** (Top to Bottom): Architecture diagrams
2. **sequenceDiagram**: Request/response flows
3. **erDiagram**: Database relationships

**Color Coding:**
- 🔵 Blue (`#e1f5ff`): Client/Frontend components
- 🟢 Green (`#d4edda`): Backend/Agent components
- 🟡 Yellow (`#fff3cd`): API/Middleware layers
- 🔴 Red (`#f8d7da`): Database/Storage layers
- ⚪ Gray (`#e2e3e5`): Service integrations

---

## Conclusion

This technical documentation provides a comprehensive guide to the Memory Chat platform's architecture, implementation, and deployment. The system is built with production-grade technologies and follows best practices for scalability, security, and maintainability.

**Key Technical Achievements:**
1. ✅ Dual-memory architecture with PostgreSQL persistence
2. ✅ LLM-based intelligent entity extraction (Phase 1)
3. ✅ Multi-service integration with dynamic prompting
4. ✅ Async/await throughout for high performance
5. ✅ Full-stack implementation with modern React
6. ✅ Multi-LLM support with automatic failover
7. ✅ Production-ready deployment options

**Next Technical Steps:**
1. Implement response streaming for real-time updates
2. Add Redis caching layer for performance
3. Implement Phase 2-4 memory features (deduplication, semantic search, graph mapping)
4. Add comprehensive test suite (unit, integration, e2e)
5. Set up CI/CD pipeline
6. Implement monitoring and alerting (Sentry, Datadog)

---

**Document Version:** 1.0.0
**Last Updated:** 2025-11-16
**Maintained By:** Memory Chat Development Team

**For Support:**
- GitHub Issues: https://github.com/[your-org]/agent-memory-chatbot/issues
- Documentation: /docs folder
- Getting Started: [getting-started.md](./getting-started.md)

**Related Documentation:**
- [Business Documentation](./business.md)
- [Architecture Overview](./core/architecture.md)
- [Database Schema](./core/database-schema.md)
- [Production Deployment](./deployment/PRODUCTION_DEPLOYMENT.md)
