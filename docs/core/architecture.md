# System Architecture

**Last Updated**: 2025-01-11
**Verified Package Versions**: Yes

This document provides a comprehensive overview of the ReAct Agent Memory System architecture.

## High-Level Architecture

```mermaid
graph TB
    subgraph "User Layer"
        User[User/Application]
    end

    subgraph "Agent Layer"
        Agent[ReAct Agent]
        LLM[Language Model<br/>GPT-4/Claude]
        Tools[Custom Tools<br/>book_hotel]
    end

    subgraph "Memory Layer"
        STM[Short-Term Memory<br/>Checkpointer]
        LTM[Long-Term Memory<br/>Store]
    end

    subgraph "Storage Layer"
        PG[(PostgreSQL<br/>Database)]
        CheckpointTable[(checkpoints table)]
        StoreTable[(store table)]
    end

    User -->|Query| Agent
    Agent -->|Invoke| LLM
    Agent -->|Execute| Tools
    Agent -->|Read/Write| STM
    Agent -->|Search/Store| LTM
    STM -->|Persist| CheckpointTable
    LTM -->|Persist| StoreTable
    CheckpointTable --> PG
    StoreTable --> PG
    Agent -->|Response| User

    style Agent fill:#4A90E2,stroke:#2E5C8A,color:#fff
    style LLM fill:#50C878,stroke:#2E7D4E,color:#fff
    style STM fill:#FF6B6B,stroke:#C92A2A,color:#fff
    style LTM fill:#9B59B6,stroke:#6C3483,color:#fff
    style PG fill:#336791,stroke:#1A3A52,color:#fff
```

## Component Architecture

```mermaid
graph LR
    subgraph "ReAct Agent Components"
        direction TB
        SM[System Message]
        PM[Pre-Model Hook<br/>Message Trimming]
        AN[Agent Node<br/>LLM Processing]
        TN[Tools Node<br/>Tool Execution]

        SM --> PM
        PM --> AN
        AN --> TN
        TN --> AN
    end

    subgraph "Memory Components"
        direction TB
        CP[Checkpointer<br/>AsyncPostgresSaver]
        ST[Store<br/>AsyncPostgresStore]
    end

    AN <-->|Thread State| CP
    AN <-->|User Memories| ST

    style SM fill:#E8F4F8,stroke:#4A90E2
    style PM fill:#FFF4E6,stroke:#FF9800
    style AN fill:#E8F5E9,stroke:#4CAF50
    style TN fill:#F3E5F5,stroke:#9C27B0
    style CP fill:#FFEBEE,stroke:#F44336
    style ST fill:#E1F5FE,stroke:#03A9F4
```

## Data Flow Architecture

```mermaid
sequenceDiagram
    participant U as User
    participant A as Agent
    participant PM as Pre-Model Hook
    participant LLM as Language Model
    participant T as Tools
    participant STM as Short-Term Memory
    participant LTM as Long-Term Memory
    participant DB as PostgreSQL

    U->>A: Submit Query
    A->>STM: Load Thread State
    STM->>DB: Fetch Checkpoints
    DB-->>STM: Return State
    STM-->>A: Thread History

    A->>LTM: Search Memories
    LTM->>DB: Query Store
    DB-->>LTM: Return Memories
    LTM-->>A: User Context

    A->>PM: Process Messages
    PM-->>A: Trimmed Messages

    A->>LLM: Invoke with Context
    LLM-->>A: Response/Tool Call

    alt Tool Execution Required
        A->>T: Execute Tool
        T-->>A: Tool Result
        A->>LLM: Continue with Result
        LLM-->>A: Final Response
    end

    A->>STM: Save State
    STM->>DB: Persist Checkpoint

    A-->>U: Return Response
```

## Technology Stack

```mermaid
graph TD
    subgraph "Application Layer"
        Python[Python 3.8+]
        AsyncIO[AsyncIO<br/>Async/Await]
    end

    subgraph "Framework Layer"
        LG[LangGraph 1.0.2<br/>Agent Orchestration]
        LC[LangChain 1.0.3<br/>LLM Integration]
        LCO[LangChain-OpenAI 1.0.1<br/>Model Connector]
    end

    subgraph "Memory Layer"
        LGCP[LangGraph-Checkpoint-Postgres 3.0.0<br/>Short-Term Memory]
        LGST[LangGraph-Store-Postgres<br/>Long-Term Memory]
    end

    subgraph "Storage Layer"
        PG[PostgreSQL 15<br/>Persistent Storage]
        Docker[Docker<br/>Containerization]
    end

    Python --> AsyncIO
    AsyncIO --> LG
    LG --> LC
    LC --> LCO
    LG --> LGCP
    LG --> LGST
    LGCP --> PG
    LGST --> PG
    PG --> Docker

    style Python fill:#3776AB,stroke:#2C5F8D,color:#fff
    style LG fill:#1C3C3C,stroke:#0F1E1E,color:#fff
    style LC fill:#1C3C3C,stroke:#0F1E1E,color:#fff
    style LGCP fill:#FF6B6B,stroke:#C92A2A,color:#fff
    style LGST fill:#9B59B6,stroke:#6C3483,color:#fff
    style PG fill:#336791,stroke:#1A3A52,color:#fff
    style Docker fill:#2496ED,stroke:#1A6FB4,color:#fff
```

## Memory Architecture

```mermaid
graph TB
    subgraph "Short-Term Memory (Thread-Level)"
        direction LR
        T1[Thread 1<br/>User A Session 1]
        T2[Thread 2<br/>User A Session 2]
        T3[Thread 3<br/>User B Session 1]
    end

    subgraph "Long-Term Memory (Cross-Thread)"
        direction LR
        U1[User A Namespace<br/>Preferences, History]
        U2[User B Namespace<br/>Preferences, History]
    end

    subgraph "PostgreSQL Database"
        direction TB
        CPT[(Checkpoints Table)]
        STO[(Store Table)]
    end

    T1 -->|thread_id: 1| CPT
    T2 -->|thread_id: 2| CPT
    T3 -->|thread_id: 3| CPT

    U1 -->|namespace: memories/user_1| STO
    U2 -->|namespace: memories/user_2| STO

    T1 -.->|user_id: 1| U1
    T2 -.->|user_id: 1| U1
    T3 -.->|user_id: 2| U2

    style T1 fill:#FFE5E5,stroke:#FF6B6B
    style T2 fill:#FFE5E5,stroke:#FF6B6B
    style T3 fill:#FFE5E5,stroke:#FF6B6B
    style U1 fill:#E5E5FF,stroke:#9B59B6
    style U2 fill:#E5E5FF,stroke:#9B59B6
    style CPT fill:#336791,stroke:#1A3A52,color:#fff
    style STO fill:#336791,stroke:#1A3A52,color:#fff
```

## ReAct Agent Workflow

```mermaid
stateDiagram-v2
    [*] --> Start
    Start --> LoadMemory: User Query
    LoadMemory --> TrimMessages: Load Thread State + Long-Term Context
    TrimMessages --> InvokeLLM: Apply Pre-Model Hook

    InvokeLLM --> CheckResponse: Process with LLM

    CheckResponse --> ExecuteTool: Tool Call Detected
    CheckResponse --> SaveState: Final Answer Generated

    ExecuteTool --> InvokeLLM: Tool Result

    SaveState --> Return: Persist to Database
    Return --> [*]: Response to User

    note right of LoadMemory
        Short-Term: Thread history
        Long-Term: User preferences
    end note

    note right of TrimMessages
        Optimize context window
        Reduce token usage
    end note

    note right of ExecuteTool
        Execute custom tools
        e.g., book_hotel
    end note
```

## Deployment Architecture

```mermaid
graph TB
    subgraph "Development Environment"
        IDE[PyCharm/VS Code]
        Local[Local Python Env]
    end

    subgraph "Container Environment"
        DC[Docker Compose]
        PGC[PostgreSQL Container<br/>Port 5432]
        Volume[(pgdata Volume)]
    end

    subgraph "External Services"
        OpenAI[OpenAI API<br/>api.openai.com]
        Anthropic[Anthropic API<br/>api.anthropic.com]
    end

    IDE --> Local
    Local --> DC
    DC --> PGC
    PGC --> Volume
    Local -->|HTTPS| OpenAI
    Local -->|HTTPS| Anthropic

    style IDE fill:#61DAFB,stroke:#21A1C4
    style DC fill:#2496ED,stroke:#1A6FB4,color:#fff
    style PGC fill:#336791,stroke:#1A3A52,color:#fff
    style OpenAI fill:#10A37F,stroke:#0D8C6B,color:#fff
    style Anthropic fill:#D97757,stroke:#B85A3E,color:#fff
```

## Key Design Principles

### 1. **Separation of Concerns**
- **Agent Logic**: Handles reasoning and tool orchestration
- **Memory Management**: Manages state persistence independently
- **Storage Layer**: Provides durable data persistence

### 2. **Asynchronous Processing**
- All database operations use `async/await` for non-blocking I/O
- Supports concurrent memory reads/writes
- Efficient resource utilization

### 3. **Modularity**
- Tools are easily pluggable
- Memory components can be swapped (e.g., Redis, SQLite)
- LLM providers are interchangeable

### 4. **Scalability**
- Thread-based isolation prevents state conflicts
- Namespace-based memory organization supports multi-tenancy
- PostgreSQL provides production-grade persistence

### 5. **Security**
- Environment variables for sensitive credentials
- `.gitignore` prevents credential leaks
- Database credentials should be rotated in production

## Performance Considerations

### Memory Trimming
The `pre_model_hook` function optimizes token usage by:
- Limiting conversation history to recent messages
- Reducing API costs
- Staying within context window limits

### Connection Pooling
PostgreSQL connections are managed efficiently through:
- Async context managers
- Automatic connection cleanup
- Connection reuse across operations

### Caching Strategy
- Short-term memory: Checkpoints cached per thread
- Long-term memory: Searchable index for fast retrieval
- Database indexes on frequently queried fields
