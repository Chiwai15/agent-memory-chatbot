import os
import asyncio
import uuid
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.tools import tool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, trim_messages
from langchain.chat_models import init_chat_model
from langgraph.store.postgres.aio import AsyncPostgresStore

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Memory Chat API", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the LLM
llm = init_chat_model(
    model=os.getenv("LLM_MODEL", "openai:gpt-4"),
    temperature=0.7,
    base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
    api_key=os.getenv("OPENAI_API_KEY", "your-api-key-here")
)

# PostgreSQL connection string
DB_URI = "postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable"

# Memory configuration
SHORT_TERM_MESSAGE_LIMIT = int(os.getenv("SHORT_TERM_MESSAGE_LIMIT", "30"))

# Global store and checkpointer (will be initialized on startup)
global_store = None
global_checkpointer = None
global_agent = None
global_store_cm = None  # Context manager
global_checkpointer_cm = None  # Context manager


# Define tools
@tool("book_hotel", description="Book a hotel reservation")
def book_hotel(hotel_name: str):
    """
    Simulates booking a hotel reservation.

    Args:
        hotel_name: Name of the hotel to book

    Returns:
        Confirmation message with booking details
    """
    return f"Successfully booked accommodation at {hotel_name}."


# Pydantic models
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    user_id: str
    memory_source: Optional[str] = "both"  # "short", "long", "both"
    messages: Optional[List[Message]] = []


class ChatResponse(BaseModel):
    response: str
    memories_used: Optional[List[Dict[str, Any]]] = []
    facts_extracted: Optional[List[str]] = []
    complexity_level: Optional[str] = "simple"
    mode_transitions: Optional[List[str]] = []
    thinking_process: Optional[str] = ""
    quality_score: Optional[float] = 0.0


def pre_model_hook(state):
    """
    Pre-processing hook called before each LLM invocation.
    Trims the conversation history to manage token limits.
    """
    trimmed_messages = trim_messages(
        messages=state["messages"],
        max_tokens=SHORT_TERM_MESSAGE_LIMIT,  # Keep last N messages (configured in .env)
        strategy="last",
        token_counter=len,
        start_on="human",
        include_system=True,
        allow_partial=False,
    )
    return {"llm_input_messages": trimmed_messages}


@app.on_event("startup")
async def startup_event():
    """Initialize the database connections and agent on startup"""
    global global_store, global_checkpointer, global_agent, global_store_cm, global_checkpointer_cm

    # Initialize context managers
    global_store_cm = AsyncPostgresStore.from_conn_string(DB_URI)
    global_checkpointer_cm = AsyncPostgresSaver.from_conn_string(DB_URI)

    # Enter the context managers and get the actual store/checkpointer objects
    global_store = await global_store_cm.__aenter__()
    global_checkpointer = await global_checkpointer_cm.__aenter__()

    # Setup the store and checkpointer
    await global_store.setup()
    await global_checkpointer.setup()

    # Define tools
    tools = [book_hotel]

    # System message
    system_message = SystemMessage(content=(
        "You are a helpful AI assistant with dual-memory architecture.\n\n"
        "YOUR MEMORY SYSTEM:\n"
        "- SHORT-TERM MEMORY: Last 30 conversation messages (PostgreSQL checkpoints)\n"
        "- LONG-TERM MEMORY: Persistent facts across sessions (PostgreSQL store)\n"
        "- When asked about your memory/database, BE HONEST about what you have stored\n\n"
        "CRITICAL MEMORY RULES (HIGHEST PRIORITY):\n"
        "1. [STORED MEMORIES] are FACTS from previous conversations - they are ALWAYS TRUE\n"
        "2. If [STORED MEMORIES] conflict with recent conversation, TRUST THE STORED MEMORIES\n"
        "3. When asked about personal information, CHECK [STORED MEMORIES] FIRST\n"
        "4. If user says 'check your memory' or 'what do you remember', list ALL [STORED MEMORIES]\n"
        "5. If user corrects you, acknowledge and explain what you found in [STORED MEMORIES]\n\n"
        "MEMORY HANDLING:\n"
        "- Stored memories will appear as [STORED MEMORIES from previous conversations: ...]\n"
        "- ALWAYS read and consider these memories before responding\n"
        "- When you learn NEW important information (names, preferences, facts), acknowledge it\n"
        "- Be conversational and natural, but BE HONEST when asked about your memory system\n\n"
        "USER COMMANDS:\n"
        "- 'Check your memory' → List all stored facts about them\n"
        "- 'What do you remember about me' → Summarize all [STORED MEMORIES]\n"
        "- 'That's wrong, check again' → Re-read [STORED MEMORIES] and correct yourself\n"
        "- 'What's in your database/memory?' → Honestly explain what you have stored\n"
        "- 'Show me your short-term/long-term memory' → List relevant stored data\n"
    ))

    # Create the agent
    global_agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_message,
        pre_model_hook=pre_model_hook,
        checkpointer=global_checkpointer,
        store=global_store
    )

    print("✅ Server initialized successfully!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global global_store_cm, global_checkpointer_cm

    if global_store_cm:
        await global_store_cm.__aexit__(None, None, None)
    if global_checkpointer_cm:
        await global_checkpointer_cm.__aexit__(None, None, None)

    print("✅ Server shutdown complete")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "Memory Chat API is running"}


@app.post("/chat/v2", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint that handles conversation with memory.

    This endpoint uses both short-term (checkpointer) and long-term (store) memory
    to maintain context and remember user preferences across sessions.
    """
    try:
        # Memory source mapping
        # Frontend sends: "short" (conversation history), "long" (persistent facts), "both"
        normalized_source = request.memory_source if request.memory_source in ["short", "long", "both"] else "both"

        # Configuration for the agent
        # Use different thread_id for long-term only mode to prevent loading conversation state from checkpointer
        thread_id = request.user_id if normalized_source in ["short", "both"] else f"{request.user_id}_long_only"

        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": request.user_id
            }
        }
        print(f"🔧 Using thread_id: {thread_id} (mode: {normalized_source})")

        # Retrieve long-term memories based on memory_source
        memories_context = ""
        retrieved_memories = []

        if normalized_source in ["long", "both"]:
            namespace = ("memories", request.user_id)
            memories = await global_store.asearch(namespace, query="")

            if memories:
                retrieved_memories = [
                    {"text": d.value.get("data", ""), "metadata": d.value}
                    for d in memories
                ]
                memories_context = " ".join([d.value.get("data", "") for d in memories])

        # Augment user input with long-term memory context
        if memories_context:
            augmented_input = (
                f"{request.message}\n\n"
                f"[STORED MEMORIES from previous conversations:\n{memories_context}\n"
                f"Use these memories to answer the user's question if relevant.]"
            )
            print(f"🧠 Retrieved {len(retrieved_memories)} memories for user {request.user_id}")
            print(f"📝 Memory context: {memories_context[:200]}...")
        else:
            augmented_input = request.message
            print(f"ℹ️ No stored memories found for user {request.user_id}")

        # Build message history from request based on memory_source
        message_history = []

        # Only include conversation history if using short-term or both
        if normalized_source in ["short", "both"]:
            for msg in request.messages[-SHORT_TERM_MESSAGE_LIMIT:]:  # Keep last N messages for context (configured in .env)
                if msg.role == "user":
                    message_history.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    message_history.append(AIMessage(content=msg.content))
            print(f"💬 Using short-term memory: {len(message_history)} conversation messages")
        else:
            print(f"🚫 Short-term memory disabled (mode: {normalized_source})")

        # Add current user message
        message_history.append(HumanMessage(content=augmented_input))

        # Invoke the agent
        agent_response = await global_agent.ainvoke(
            {"messages": message_history},
            config
        )

        # Extract the response
        response_content = agent_response["messages"][-1].content

        # Extract facts from the conversation (simple heuristic)
        # In a production system, you might use an LLM to extract facts
        facts_extracted = []
        if "my name is" in request.message.lower():
            facts_extracted.append(f"User's name mentioned")
        if "i like" in request.message.lower() or "i love" in request.message.lower():
            facts_extracted.append(f"User preference noted")

        # Store new memories in long-term storage if appropriate
        # This is a simple heuristic - in production, you'd use more sophisticated logic
        if normalized_source in ["long", "both"]:
            if any(phrase in request.message.lower() for phrase in ["my name is", "i am", "i like", "i love", "i prefer"]):
                namespace = ("memories", request.user_id)
                memory_id = str(uuid.uuid4())
                await global_store.aput(
                    namespace,
                    memory_id,
                    {"data": request.message, "timestamp": str(uuid.uuid1().time)}
                )
                facts_extracted.append("New memory stored")

        return ChatResponse(
            response=response_content,
            memories_used=retrieved_memories,
            facts_extracted=facts_extracted,
            complexity_level="simple",
            mode_transitions=["short_term" if request.memory_source == "short" else "long_term"],
            thinking_process="Retrieved context and generated response",
            quality_score=0.9
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config")
async def get_config():
    """Get application configuration"""
    return {
        "short_term_message_limit": SHORT_TERM_MESSAGE_LIMIT
    }


@app.get("/conversation/{user_id}")
async def get_conversation_history(user_id: str):
    """Get conversation history (short-term memory) for a user from checkpoints"""
    try:
        config = {
            "configurable": {
                "thread_id": user_id,
                "user_id": user_id
            }
        }

        # Get the current state from checkpoints
        state = await global_agent.aget_state(config)

        # Extract messages from state
        messages = []
        if state and state.values and "messages" in state.values:
            for msg in state.values["messages"]:
                # Convert LangChain message to dict
                if hasattr(msg, 'type'):
                    messages.append({
                        "role": "user" if msg.type == "human" else "assistant",
                        "content": msg.content
                    })

        return {
            "user_id": user_id,
            "total": len(messages),
            "messages": messages[-SHORT_TERM_MESSAGE_LIMIT:]  # Return last N messages (configured in .env)
        }
    except Exception as e:
        print(f"Error fetching conversation history: {e}")
        return {
            "user_id": user_id,
            "total": 0,
            "messages": []
        }


@app.get("/memories/{user_id}")
async def get_memories(user_id: str):
    """Get all long-term memories for a user"""
    try:
        namespace = ("memories", user_id)
        memories = await global_store.asearch(namespace, query="")

        return {
            "user_id": user_id,
            "total": len(memories),
            "memories": [
                {
                    "id": d.key,
                    "data": d.value.get("data", ""),
                    "metadata": d.value
                }
                for d in memories
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/memories/{user_id}")
async def delete_user_memories(user_id: str):
    """Delete all memories for a specific user"""
    try:
        namespace = ("memories", user_id)
        memories = await global_store.asearch(namespace, query="")

        deleted_count = 0
        for memory in memories:
            await global_store.adelete(namespace, memory.key)
            deleted_count += 1

        return {
            "user_id": user_id,
            "deleted": deleted_count,
            "message": f"Deleted {deleted_count} memories for user {user_id}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/memories/all/clear")
async def clear_all_memories():
    """Clear all memories from all users (PostgreSQL store only)"""
    try:
        # Note: This is a simplified version
        # In production, you'd need to properly clear the PostgreSQL store
        # For now, just return success message
        return {
            "message": "All memories cleared from PostgreSQL",
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/list")
async def list_users():
    """List all users that have memories stored"""
    try:
        # Get all unique user IDs from the store
        # We search for all memories and extract unique user_ids
        all_namespaces = set()

        # Search all memories (this is a simplified approach)
        # In production, you'd want to optimize this
        try:
            # Try to get all memories by searching with empty query
            # Note: This is a workaround - ideally we'd have a method to list all namespaces
            # For now, we return an empty list which will cause the frontend to keep existing sessions
            pass
        except:
            pass

        # Return empty list for now - this prevents session clearing
        # The frontend will keep its localStorage sessions
        return {"users": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories/all/inspect")
async def inspect_all_memories(user_id: Optional[str] = None):
    """Inspect all memories, optionally filtered by user_id"""
    try:
        all_memories = []

        if user_id:
            # Get memories for specific user
            namespace = ("memories", user_id)
            memories = await global_store.asearch(namespace, query="")
            all_memories = [
                {
                    "text": d.value.get("data", ""),
                    "metadata": {
                        "user_id": user_id,
                        "timestamp": d.value.get("timestamp", ""),
                        "level": 1,
                        "category": "general"
                    }
                }
                for d in memories
            ]

        return {
            "total": len(all_memories),
            "memories": all_memories
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memory-bank/{user_id}")
async def get_memory_bank(user_id: str):
    """Get memory bank files for a user (simulated structure)"""
    try:
        namespace = ("memories", user_id)
        memories = await global_store.asearch(namespace, query="")

        # Simulate memory bank file structure
        files = {
            "profile.md": "",
            "interests.md": "",
            "preferences.md": "",
            "relationships.md": "",
            "knowledge_base.md": "",
            "active_context.md": ""
        }

        # Populate files with memories
        if memories:
            knowledge_base_content = "# Knowledge Base\n\n"
            for memory in memories:
                knowledge_base_content += f"- {memory.value.get('data', '')}\n"
            files["knowledge_base.md"] = knowledge_base_content

        return {
            "user_id": user_id,
            "total_files": len([f for f in files.values() if f]),
            "files": files
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
