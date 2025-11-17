# Flow Diagrams

**Last Updated**: 2025-01-11

This document contains detailed flow charts for both short-term and long-term memory operations based on the actual codebase.

## Short-Term Memory Flow (01_shortTermTest.py)

### Complete Execution Flow

```mermaid
flowchart TD
    Start([Start Application]) --> LoadEnv[Load Environment Variables]
    LoadEnv --> InitLLM[Initialize LLM<br/>from .env config]
    InitLLM --> DefineTools[Define Custom Tools<br/>book_hotel]
    DefineTools --> ConnectDB[Connect to PostgreSQL<br/>localhost:5432]

    ConnectDB --> InitCheckpointer[Initialize AsyncPostgresSaver<br/>Short-Term Memory]
    InitCheckpointer --> SetupCheckpointer[Setup Database Tables<br/>checkpointer.setup]

    SetupCheckpointer --> CreateAgent[Create ReAct Agent<br/>+ LLM<br/>+ Tools<br/>+ System Message<br/>+ Checkpointer]

    CreateAgent --> SaveGraph{Save Graph<br/>Visualization?}
    SaveGraph -->|Yes| GenGraph[Generate graph.png]
    SaveGraph -->|No| DefineConfig
    GenGraph --> DefineConfig

    DefineConfig[Define Config<br/>thread_id: 1] --> UserInput[User Input<br/>e.g., What is my name?]

    UserInput --> LoadThread{Load Thread State}
    LoadThread -->|Thread Exists| LoadHistory[Load Conversation History<br/>from Database]
    LoadThread -->|New Thread| EmptyState[Empty State]

    LoadHistory --> TrimHook{Pre-Model Hook<br/>Enabled?}
    EmptyState --> TrimHook

    TrimHook -->|Yes| TrimMessages[Trim Messages<br/>Keep last 4 messages]
    TrimHook -->|No| InvokeLLM

    TrimMessages --> InvokeLLM[Invoke LLM<br/>with Context]

    InvokeLLM --> LLMResponse{LLM Response Type}

    LLMResponse -->|Tool Call| ParseTool[Parse Tool Call<br/>Extract: name, args]
    LLMResponse -->|Text Response| FinalAnswer

    ParseTool --> ExecuteTool[Execute Tool<br/>book_hotel]
    ExecuteTool --> ToolResult[Get Tool Result]
    ToolResult --> SendToLLM[Send Result to LLM]
    SendToLLM --> InvokeLLM

    FinalAnswer[Final Answer Generated] --> SaveCheckpoint[Save Checkpoint<br/>Persist to PostgreSQL]

    SaveCheckpoint --> ParseOutput[Parse Messages<br/>Display Details]
    ParseOutput --> PrintResponse[Print Final Response]
    PrintResponse --> End([End])

    style Start fill:#4CAF50,stroke:#2E7D32,color:#fff
    style InitCheckpointer fill:#FF6B6B,stroke:#C92A2A,color:#fff
    style CreateAgent fill:#4A90E2,stroke:#2E5C8A,color:#fff
    style SaveCheckpoint fill:#FF9800,stroke:#E65100,color:#fff
    style End fill:#F44336,stroke:#C62828,color:#fff
```

### Thread State Management

```mermaid
flowchart LR
    subgraph "First Interaction"
        direction TB
        U1[User: My name is Nelson] --> A1[Agent Response]
        A1 --> S1[(Save to Thread 1<br/>Checkpoint)]
    end

    subgraph "Second Interaction"
        direction TB
        L2[(Load Thread 1<br/>Previous Context)] --> U2[User: What is my name?]
        U2 --> A2[Agent: Your name is Nelson]
        A2 --> S2[(Update Thread 1<br/>Checkpoint)]
    end

    subgraph "Third Interaction"
        direction TB
        L3[(Load Thread 1<br/>Full History)] --> U3[User: Book a hotel]
        U3 --> T3[Tool: book_hotel]
        T3 --> A3[Agent: Booking confirmed]
        A3 --> S3[(Update Thread 1<br/>Checkpoint)]
    end

    S1 --> L2
    S2 --> L3

    style S1 fill:#FFE5E5,stroke:#FF6B6B
    style S2 fill:#FFE5E5,stroke:#FF6B6B
    style S3 fill:#FFE5E5,stroke:#FF6B6B
    style L2 fill:#E8F4F8,stroke:#4A90E2
    style L3 fill:#E8F4F8,stroke:#4A90E2
```

### Message Trimming Flow

```mermaid
flowchart TD
    Input[Incoming Messages] --> Check{Message Count<br/>> 4?}

    Check -->|No| UseAll[Use All Messages]
    Check -->|Yes| Strategy[Apply Trimming Strategy]

    Strategy --> Filter1[Keep System Message<br/>include_system: True]
    Filter1 --> Filter2[Start from Human Message<br/>start_on: human]
    Filter2 --> Filter3[Take Last 4 Messages<br/>strategy: last]

    Filter3 --> Trimmed[Trimmed Messages]
    UseAll --> ToLLM[Send to LLM]
    Trimmed --> ToLLM

    ToLLM --> Result[Optimized Context<br/>Reduced Tokens]

    style Input fill:#E1F5FE,stroke:#01579B
    style Strategy fill:#FFF3E0,stroke:#E65100
    style Result fill:#E8F5E9,stroke:#1B5E20
```

## Long-Term Memory Flow (02_longTermTest.py)

### Complete Execution Flow

```mermaid
flowchart TD
    Start([Start Application]) --> LoadEnv[Load Environment Variables]
    LoadEnv --> InitLLM[Initialize LLM]
    InitLLM --> DefineTools[Define Custom Tools]
    DefineTools --> ConnectDB[Connect to PostgreSQL]

    ConnectDB --> InitBoth[Initialize Both:<br/>1. AsyncPostgresSaver<br/>2. AsyncPostgresStore]
    InitBoth --> SetupBoth[Setup Database Tables<br/>+ Checkpoints<br/>+ Store]

    SetupBoth --> CreateAgent[Create ReAct Agent<br/>+ Checkpointer<br/>+ Store<br/>+ Pre-Model Hook]

    CreateAgent --> DefineConfig[Define Config<br/>thread_id: 1<br/>user_id: 1]

    DefineConfig --> ExtractUser[Extract User ID<br/>from Config]
    ExtractUser --> DefineNamespace[Define Namespace<br/>memories, user_id]

    DefineNamespace --> SearchMemories[Search Long-Term Memories<br/>store.asearch]

    SearchMemories --> MemoriesFound{Memories<br/>Found?}

    MemoriesFound -->|Yes| ExtractData[Extract Memory Data<br/>Join all values]
    MemoriesFound -->|No| NoMemories[info = No long-term memory]

    ExtractData --> BuildContext[Build Context String]
    NoMemories --> BuildContext

    BuildContext --> AugmentInput[Augment User Input<br/>with Memory Context]

    AugmentInput --> LoadThread{Load Thread State<br/>Short-Term Memory}

    LoadThread --> TrimHook[Pre-Model Hook<br/>Trim Messages]

    TrimHook --> InvokeLLM[Invoke LLM<br/>with Both Contexts]

    InvokeLLM --> LLMResponse{Response Type}

    LLMResponse -->|Tool Call| ExecuteTool[Execute Tool]
    LLMResponse -->|Text| FinalAnswer

    ExecuteTool --> ToolResult[Get Result]
    ToolResult --> SendToLLM[Send to LLM]
    SendToLLM --> InvokeLLM

    FinalAnswer[Final Answer] --> SaveCheckpoint[Save Short-Term<br/>Checkpoint]

    SaveCheckpoint --> StoreMemory{Store New<br/>Long-Term Memory?}

    StoreMemory -->|Yes| PutMemory[store.aput<br/>Save Memory]
    StoreMemory -->|No| ParseOutput

    PutMemory --> ParseOutput[Parse & Display Messages]
    ParseOutput --> PrintResponse[Print Final Response]
    PrintResponse --> End([End])

    style Start fill:#4CAF50,stroke:#2E7D32,color:#fff
    style InitBoth fill:#9C27B0,stroke:#6A1B9A,color:#fff
    style SearchMemories fill:#9B59B6,stroke:#6C3483,color:#fff
    style SaveCheckpoint fill:#FF6B6B,stroke:#C92A2A,color:#fff
    style PutMemory fill:#9B59B6,stroke:#6C3483,color:#fff
    style End fill:#F44336,stroke:#C62828,color:#fff
```

### Long-Term Memory Storage Flow

```mermaid
flowchart TD
    Start[User Interaction] --> Analyze{Analyze Input<br/>for Memory-worthy<br/>Information}

    Analyze -->|Name Mentioned| ExtractName[Extract: My name is Nelson]
    Analyze -->|Preference Stated| ExtractPref[Extract: Preferences]
    Analyze -->|Regular Query| NoStore

    ExtractName --> CreateMemory1[Create Memory Object<br/>data: My name is Nelson]
    ExtractPref --> CreateMemory2[Create Memory Object<br/>data: Preferences info]

    CreateMemory1 --> GenID1[Generate UUID<br/>Unique Memory ID]
    CreateMemory2 --> GenID2[Generate UUID<br/>Unique Memory ID]

    GenID1 --> DefineNS1[Define Namespace<br/>memories, user_1]
    GenID2 --> DefineNS2[Define Namespace<br/>memories, user_1]

    DefineNS1 --> StoreToDB1[(Store to PostgreSQL<br/>Store Table)]
    DefineNS2 --> StoreToDB2[(Store to PostgreSQL<br/>Store Table)]

    StoreToDB1 --> Success1[Memory Persisted]
    StoreToDB2 --> Success2[Memory Persisted]

    NoStore --> Continue[Continue Processing]
    Success1 --> Continue
    Success2 --> Continue

    Continue --> End([Available for<br/>Future Sessions])

    style CreateMemory1 fill:#E1BEE7,stroke:#9C27B0
    style CreateMemory2 fill:#E1BEE7,stroke:#9C27B0
    style StoreToDB1 fill:#9B59B6,stroke:#6C3483,color:#fff
    style StoreToDB2 fill:#9B59B6,stroke:#6C3483,color:#fff
```

### Long-Term Memory Retrieval Flow

```mermaid
flowchart TD
    NewSession[New Session Starts] --> GetUserID[Get User ID<br/>from Config]
    GetUserID --> BuildNS[Build Namespace<br/>memories, user_id]

    BuildNS --> SearchDB[(Search Store Table<br/>Query: empty string)]

    SearchDB --> Results{Results<br/>Found?}

    Results -->|No Results| EmptyInfo[info = No long-term memory]
    Results -->|Has Results| IterateResults[Iterate Through Results]

    IterateResults --> ExtractValue1[Result 1: Extract data field]
    IterateResults --> ExtractValue2[Result 2: Extract data field]
    IterateResults --> ExtractValue3[Result N: Extract data field]

    ExtractValue1 --> Combine[Combine All Values<br/>Join with spaces]
    ExtractValue2 --> Combine
    ExtractValue3 --> Combine

    Combine --> ContextString[Context String:<br/>My name is Nelson.<br/>Preferences: window, WiFi]

    EmptyInfo --> AugmentInput[Augment User Input]
    ContextString --> AugmentInput

    AugmentInput --> Example[Example Result:<br/>Book hotel, my prefs: window, WiFi]
    Example --> SendToAgent[Send to Agent<br/>for Processing]

    style SearchDB fill:#9B59B6,stroke:#6C3483,color:#fff
    style ContextString fill:#E1BEE7,stroke:#9C27B0
    style SendToAgent fill:#4A90E2,stroke:#2E5C8A,color:#fff
```

### Cross-Session Memory Pattern

```mermaid
sequenceDiagram
    autonumber
    participant S1 as Session 1<br/>(Thread 1)
    participant STM as Short-Term<br/>Memory
    participant LTM as Long-Term<br/>Memory
    participant S2 as Session 2<br/>(Thread 2)

    Note over S1: User: My name is Nelson
    S1->>STM: Save to Thread 1
    S1->>LTM: Store: name=Nelson<br/>namespace: memories/user_1

    Note over S1,STM: Session 1 Ends

    Note over S2: New Session Starts
    S2->>LTM: Search namespace: memories/user_1
    LTM-->>S2: Return: name=Nelson

    Note over S2: User: What is my name?
    S2->>STM: Create Thread 2<br/>(Empty history)
    S2->>S2: Augment with LTM context

    Note over S2: Agent knows name<br/>despite new thread!
```

## Streaming vs Non-Streaming Flow

### Non-Streaming Flow (Default)

```mermaid
flowchart LR
    Input[User Input] --> Invoke[agent.ainvoke]
    Invoke --> Wait[Wait for<br/>Complete Response]
    Wait --> FullResponse[Full Response<br/>Object]
    FullResponse --> Parse[Parse Messages]
    Parse --> Display[Display All at Once]

    style Wait fill:#FFE0B2,stroke:#E65100
    style FullResponse fill:#C8E6C9,stroke:#2E7D32
```

### Streaming Flow (Optional)

```mermaid
flowchart LR
    Input[User Input] --> Stream[agent.astream]
    Stream --> Loop{Next Chunk<br/>Available?}

    Loop -->|Yes| GetChunk[Get Message Chunk]
    Loop -->|No| Complete

    GetChunk --> CheckNode{Check Node Type}
    CheckNode -->|tools| SkipChunk[Skip Tool Output]
    CheckNode -->|agent| CheckContent{Has Content?}

    CheckContent -->|Yes| Display[Display Chunk<br/>Immediately]
    CheckContent -->|No| SkipChunk

    SkipChunk --> Loop
    Display --> Loop

    Complete[Stream Complete] --> End([Done])

    style GetChunk fill:#E1F5FE,stroke:#01579B
    style Display fill:#C8E6C9,stroke:#2E7D32
```

## Error Handling Flow

```mermaid
flowchart TD
    Start[Agent Execution] --> Try{Try Operation}

    Try -->|Success| NormalFlow[Continue Normal Flow]
    Try -->|Database Error| DBError[Handle Database Error]
    Try -->|API Error| APIError[Handle API Error]
    Try -->|Tool Error| ToolError[Handle Tool Error]

    DBError --> CheckDB{Database<br/>Running?}
    CheckDB -->|No| StartDB[Start Docker Compose]
    CheckDB -->|Yes| CheckConn{Connection<br/>String Valid?}
    CheckConn -->|No| FixConn[Fix Connection String]
    CheckConn -->|Yes| Retry

    APIError --> CheckKey{API Key<br/>Valid?}
    CheckKey -->|No| UpdateEnv[Update .env File]
    CheckKey -->|Yes| CheckQuota{Check Quota}
    CheckQuota --> Retry

    ToolError --> LogError[Log Tool Error]
    LogError --> ContinueAgent[Continue Agent<br/>with Error Message]

    StartDB --> Retry[Retry Operation]
    FixConn --> Retry
    UpdateEnv --> Retry

    Retry --> Try
    NormalFlow --> Success([Success])
    ContinueAgent --> Success

    style DBError fill:#FFCDD2,stroke:#C62828
    style APIError fill:#FFE0B2,stroke:#E65100
    style ToolError fill:#FFF9C4,stroke:#F57F17
    style Success fill:#C8E6C9,stroke:#2E7D32
```

## Configuration Flow

```mermaid
flowchart TD
    Start([Application Start]) --> LoadEnv[Load .env File]

    LoadEnv --> CheckKeys{All Keys<br/>Present?}

    CheckKeys -->|No| UseDefaults[Use Default Values]
    CheckKeys -->|Yes| ValidateKeys

    UseDefaults --> Warning[⚠️ Warning:<br/>Using Defaults]
    Warning --> ValidateKeys

    ValidateKeys[Validate API Keys] --> TestConn{Test API<br/>Connection}

    TestConn -->|Success| ConfigOK[Configuration OK]
    TestConn -->|Failure| ConfigError[Configuration Error]

    ConfigError --> DisplayError[Display Error Message<br/>+ Instructions]
    DisplayError --> Exit([Exit])

    ConfigOK --> InitComponents[Initialize Components:<br/>1. LLM<br/>2. Database<br/>3. Memory]

    InitComponents --> Ready([Ready to Run])

    style CheckKeys fill:#FFF3E0,stroke:#E65100
    style ConfigError fill:#FFCDD2,stroke:#C62828
    style ConfigOK fill:#C8E6C9,stroke:#2E7D32
    style Ready fill:#4CAF50,stroke:#2E7D32,color:#fff
```
