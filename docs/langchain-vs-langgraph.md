# LangChain vs LangGraph - Understanding the Memory Chat Architecture

This document explains the difference between LangChain and LangGraph, and how they work together in the Memory Chat project.

---

## 🔵 LangChain - The Foundation

**What it is**: A framework for building LLM applications (think: "toolkit for talking to AI models")

**Core Purpose**: Makes it easy to:
- Connect to different LLMs (OpenAI, Groq, DeepSeek, etc.)
- Chain together LLM calls
- Manage prompts and messages
- Work with embeddings and vector stores

**Example Use Case**: Simple chatbot
```python
from langchain.chat_models import init_chat_model

# Initialize any LLM with unified interface
llm = init_chat_model("openai:gpt-4")

# Send a message
response = llm.invoke("What's the capital of France?")
# Response: "Paris"
```

---

## 🟢 LangGraph - The State Machine

**What it is**: A framework for building **stateful, multi-step agents** with complex workflows

**Core Purpose**: Makes it easy to:
- Build agents with **persistent state**
- Create **workflows with multiple steps** (nodes)
- Handle **decision-making** (routing between nodes)
- **Checkpointing** (save/restore conversation state)
- **Memory management** (short-term + long-term)

**Example Use Case**: ReAct Agent (Reasoning + Acting)
```python
from langgraph.prebuilt import create_react_agent

# Create agent that can think and use tools
agent = create_react_agent(
    llm=llm,
    tools=[search_tool, calculator_tool],
    checkpointer=checkpointer  # Saves state between calls
)

# Agent can:
# 1. Reason about what to do
# 2. Use tools (search, calculate)
# 3. Remember conversation state
```

---

## 🔄 Key Differences

| Aspect | LangChain | LangGraph |
|--------|-----------|-----------|
| **Focus** | LLM integration & chains | Stateful workflows & agents |
| **State** | Stateless (no memory) | Stateful (persistent memory) |
| **Complexity** | Simple chains | Complex multi-step workflows |
| **Memory** | Basic message history | Advanced checkpointing + stores |
| **Use Case** | Q&A, summarization | Agents, assistants, workflows |

---

## 📊 How They Work in Memory Chat Project

### **LangChain Components** (Basic Building Blocks)

#### 1. LLM Initialization (`server.py:13`)
```python
from langchain.chat_models import init_chat_model

llm = init_chat_model(
    model="openai:llama-3.3-70b-versatile",
    api_key="gsk_...",
    base_url="https://api.groq.com/openai/v1"
)
```
**Purpose**: Handles connecting to Groq/DeepSeek/OpenAI with unified API

#### 2. Message Types (`server.py:12`)
```python
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

messages = [
    SystemMessage(content="You are a helpful assistant"),
    HumanMessage(content="What's my name?"),
    AIMessage(content="Your name is Alice")
]
```
**Purpose**: Structuring conversation messages

#### 3. Tools (`server.py:9`)
```python
from langchain_core.tools import tool

@tool("book_hotel", description="Book a hotel reservation")
def book_hotel(location: str, checkin: str):
    return f"Hotel booked in {location} for {checkin}"
```
**Purpose**: Defining what actions the agent can take

---

### **LangGraph Components** (Advanced Agent Logic)

#### 1. Checkpointer - Short-term Memory (`server.py:10`)
```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

global_checkpointer = AsyncPostgresSaver.from_conn_string(DB_URI)
await global_checkpointer.setup()
```
**Purpose**:
- Saving last 30 messages to PostgreSQL
- Conversation continuity across page refreshes
- Stores in `checkpoints` table

#### 2. Store - Long-term Memory (`server.py:14`)
```python
from langgraph.store.postgres.aio import AsyncPostgresStore

global_store = AsyncPostgresStore.from_conn_string(DB_URI)
await global_store.setup()
```
**Purpose**:
- Storing extracted entities forever
- Remember user facts across sessions
- Stores in `store` table

#### 3. ReAct Agent - The Brain (`server.py:11`)
```python
from langgraph.prebuilt import create_react_agent

global_agent = create_react_agent(
    llm=llm,                          # LangChain component
    tools=[book_hotel],               # LangChain component
    checkpointer=global_checkpointer, # LangGraph component
    store=global_store                # LangGraph component
)
```
**Purpose**:
- Orchestrating the entire conversation flow
- Reasoning, tool usage, memory management

---

## 🔄 How They Work Together - Real Example

Let's trace what happens when a user sends: **"My name is Alice and I live in Paris"**

### Step 1: **LangChain** - Message Handling
```python
# LangChain structures the message
message = HumanMessage(content="My name is Alice and I live in Paris")
```

### Step 2: **LangGraph ReAct Agent** - Processing
```python
# Agent processes through multiple nodes:
# 1. Check memory (checkpointer + store)
# 2. Reason about the input
# 3. Decide if tools are needed
# 4. Generate response
# 5. Extract & save memories
```

### Step 3: **LangGraph Checkpointer** - Save Conversation
```python
# Saves to PostgreSQL checkpoints table
await global_checkpointer.put({
    "messages": [
        HumanMessage("My name is Alice and I live in Paris"),
        AIMessage("Nice to meet you Alice! I see you live in Paris.")
    ]
})
# Keeps last 30 messages for context
```

### Step 4: **LangGraph Store** - Extract Entities
```python
# Your custom extraction logic uses LangChain LLM
extraction_result = await llm.invoke(extraction_prompt)

# Then LangGraph Store saves it
await global_store.aput(
    namespace=("memories", "user_123"),
    key="person_name_001",
    value={
        "data": "person_name: Alice (current)",
        "reference_sentence": "My name is Alice",
        "confidence": 1.0,
        "temporal_status": "current"
    }
)
```

---

## 📊 Visual Flow in Memory Chat

```
User Message: "My name is Alice"
        ↓
┌─────────────────────────────────────────────┐
│  LANGCHAIN (Basic Components)               │
│  • Converts to HumanMessage                 │
│  • Sends to LLM (Groq/DeepSeek)            │
└─────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────┐
│  LANGGRAPH ReAct Agent (Orchestration)      │
│  1. Load recent context (checkpointer)      │
│  2. Load user facts (store)                 │
│  3. Reason: "User introduced themselves"    │
│  4. Generate response                       │
│  5. Trigger memory extraction               │
└─────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────┐
│  LANGGRAPH Checkpointer (Short-term)        │
│  • Saves last 30 messages                   │
│  • PostgreSQL: checkpoints table            │
│  • Survives page refresh (same session)     │
└─────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────┐
│  LANGGRAPH Store (Long-term)                │
│  • Extracts entity: "person_name: Alice"    │
│  • PostgreSQL: store table                  │
│  • Survives across ALL sessions             │
└─────────────────────────────────────────────┘
```

---

## 🎯 Why Use Both?

| Need | Framework | Example in Memory Chat |
|------|-----------|------------------------|
| Connect to LLM | LangChain | `init_chat_model()` for Groq/DeepSeek |
| Define tools | LangChain | `@tool` decorator for `book_hotel` |
| Structure messages | LangChain | `HumanMessage`, `AIMessage` |
| **Agent workflow** | **LangGraph** | `create_react_agent()` |
| **Persistent memory** | **LangGraph** | `AsyncPostgresSaver` (30 msgs) |
| **Entity storage** | **LangGraph** | `AsyncPostgresStore` (entities) |
| **State management** | **LangGraph** | `checkpointer` + `store` |

---

## 💡 Simple Analogy

**LangChain** = Individual LEGO bricks
- LLM connections
- Message types
- Tools
- Prompts

**LangGraph** = LEGO instruction manual + storage box
- How to assemble the bricks (workflow)
- Where to save progress (checkpointer)
- Where to store completed builds (store)
- How to resume building (state management)

---

## 🔧 Memory Chat Architecture

```python
# server.py initialization flow:

# 1. LangChain sets up LLM
llm = init_chat_model(...)  # Can talk to Groq/DeepSeek/OpenAI

# 2. LangGraph sets up memory
checkpointer = AsyncPostgresSaver(...)  # Short-term (30 msgs)
store = AsyncPostgresStore(...)          # Long-term (entities)

# 3. LangGraph creates agent with LangChain components
agent = create_react_agent(
    llm=llm,                    # LangChain: Which AI to use
    tools=[book_hotel],         # LangChain: What actions available
    checkpointer=checkpointer,  # LangGraph: Conversation memory
    store=store                 # LangGraph: Entity memory
)
```

---

## 📝 Summary

**LangChain**:
- Foundation for LLM interactions
- Provides basic building blocks (LLM clients, messages, tools)
- Stateless by default
- Think: "How to talk to AI models"

**LangGraph**:
- Advanced agent orchestration
- Adds persistent state and memory
- Manages complex workflows
- Think: "How to build stateful agents with memory"

**Together in Memory Chat**:
- **LangChain** handles LLM communication and message formatting
- **LangGraph** manages the agent workflow and dual-memory system
- **Result**: A stateful chatbot that remembers conversations (30 msgs) and user facts (forever)

---

## 📚 Related Documentation

- [Memory System Guide](memory/README.md) - How dual-memory works
- [Architecture Overview](core/architecture.md) - System design
- [Database Schema](core/database-schema.md) - PostgreSQL structure

---

**Last Updated**: 2025-11-16
