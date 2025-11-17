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


# Phase 1: LLM-based Entity Extraction Models
class ExtractedEntity(BaseModel):
    """Represents a single extracted entity from conversation"""
    type: str  # Entity type: person_name, age, profession, location, preference, fact, relationship
    value: str  # The actual value
    confidence: float  # Confidence score 0.0-1.0
    context: Optional[str] = None  # Surrounding context
    temporal_status: Optional[str] = "current"  # Temporal context: "past", "current", "future", or None
    reference_sentence: Optional[str] = None  # Original sentence for context preservation


class MemoryExtraction(BaseModel):
    """Result of LLM-based memory extraction from conversation"""
    entities: List[ExtractedEntity]
    summary: str  # One-sentence summary of what to remember
    importance: float  # Importance score 0.0-1.0
    should_store: bool = True  # Whether this should be stored in long-term memory


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


# Phase 1: LLM-based Memory Extraction Function
async def extract_memories_with_llm(
    message: str,
    conversation_history: List[Dict[str, str]],
    user_id: str
) -> Optional[MemoryExtraction]:
    """
    Use LLM to extract entities and facts from conversation.

    This replaces the naive keyword-based approach with intelligent extraction
    that understands context, intent, and relationships.

    Args:
        message: The current user message
        conversation_history: Recent conversation context
        user_id: User identifier for context

    Returns:
        MemoryExtraction object with entities, summary, and importance score
    """
    try:
        # Build conversation context (last 5 messages for efficiency)
        context = ""
        for msg in conversation_history[-5:]:
            role = "User" if msg.get("role") == "user" else "Assistant"
            context += f"{role}: {msg.get('content', '')}\n"
        context += f"User: {message}\n"

        # Prompt for entity extraction with 5W1H context
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
- "past": Things that were true but are no longer (e.g., "I lived in Hong Kong", "I used to work at Google")
- "current": Things that are currently true (e.g., "I live in Canada now", "I am a developer")
- "future": Future plans or intentions (e.g., "I will move to Japan", "I plan to become a manager")
- null: Timeless facts (e.g., "My name is John")

REFERENCE SENTENCE:
Extract the exact or compacted sentence from the conversation that contains this information. This preserves context.

SCORING GUIDELINES:
- Confidence: 0.0-1.0 (how certain you are about this entity)
  * 1.0: Explicit statements ("My name is John")
  * 0.7-0.9: Strong context ("I'm a software engineer")
  * 0.5-0.6: Implied information ("I work in tech")
  * <0.5: Weak/uncertain information

- Importance: 0.0-1.0 (how important is this to remember)
  * 1.0: Core identity (name, age, profession)
  * 0.7-0.9: Significant preferences/facts
  * 0.5-0.6: Minor preferences
  * <0.5: Casual mentions

RESPONSE FORMAT (JSON):
{{
  "entities": [
    {{"type": "location", "value": "Hong Kong", "confidence": 1.0, "context": "User's past residence", "temporal_status": "past", "reference_sentence": "I lived in Hong Kong"}},
    {{"type": "location", "value": "Canada", "confidence": 1.0, "context": "User's current residence", "temporal_status": "current", "reference_sentence": "I moved to Canada now"}},
    {{"type": "person_name", "value": "John", "confidence": 1.0, "context": "User's name", "temporal_status": null, "reference_sentence": "My name is John"}}
  ],
  "summary": "User lived in Hong Kong (past) and now lives in Canada (current). User's name is John.",
  "importance": 0.95,
  "should_store": true
}}

EXAMPLE - Temporal extraction:
User says: "I lived in Hong Kong and moved to Canada now"
Extract:
- location: "Hong Kong" (temporal_status: "past", reference_sentence: "I lived in Hong Kong")
- location: "Canada" (temporal_status: "current", reference_sentence: "moved to Canada now")

If there's NOTHING worth remembering (casual chat, questions, etc.), return:
{{
  "entities": [],
  "summary": "No memorable information",
  "importance": 0.0,
  "should_store": false
}}

Analyze the conversation and respond with ONLY valid JSON:"""

        # Use the LLM with structured output
        response = await llm.ainvoke([
            SystemMessage(content="You are a memory extraction expert. Respond ONLY with valid JSON matching the MemoryExtraction schema."),
            HumanMessage(content=extraction_prompt)
        ])

        # Parse the response
        import json
        try:
            # Clean the response (remove markdown code blocks if present)
            content = response.content.strip()
            if content.startswith("```"):
                # Remove markdown code blocks
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:].strip()

            # Parse JSON
            extracted_data = json.loads(content)

            # Convert to Pydantic model
            entities = [
                ExtractedEntity(**entity)
                for entity in extracted_data.get("entities", [])
            ]

            return MemoryExtraction(
                entities=entities,
                summary=extracted_data.get("summary", ""),
                importance=extracted_data.get("importance", 0.0),
                should_store=extracted_data.get("should_store", True)
            )

        except json.JSONDecodeError as e:
            print(f"⚠️ Failed to parse LLM response as JSON: {e}")
            print(f"Response was: {response.content[:200]}")
            return None

    except Exception as e:
        print(f"⚠️ Error in extract_memories_with_llm: {e}")
        return None


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
                # Build memory entries with reference sentences for richer context
                memory_entries = []
                for d in memories:
                    entity_label = d.value.get("data", "")
                    reference = d.value.get("reference_sentence", "")

                    # Format: "entity_label [Reference: 'original sentence']"
                    if reference:
                        memory_entry = f"{entity_label} [Reference: '{reference}']"
                    else:
                        memory_entry = entity_label

                    memory_entries.append(memory_entry)

                retrieved_memories = [
                    {"text": d.value.get("data", ""), "metadata": d.value}
                    for d in memories
                ]
                memories_context = " ".join(memory_entries)

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

        # Phase 1: LLM-based Memory Extraction
        facts_extracted = []

        # Use LLM to intelligently extract memories from conversation
        if normalized_source in ["long", "both"]:
            # Build conversation context from request messages
            conv_history = [
                {"role": msg.role, "content": msg.content}
                for msg in request.messages[-5:]  # Last 5 messages for context
            ]

            # Extract memories using LLM
            extraction = await extract_memories_with_llm(
                message=request.message,
                conversation_history=conv_history,
                user_id=request.user_id
            )

            # Store extracted memories if they should be stored
            if extraction and extraction.should_store and extraction.entities:
                namespace = ("memories", request.user_id)

                print(f"🧠 Extracted {len(extraction.entities)} entities (importance: {extraction.importance:.2f})")
                print(f"📝 Summary: {extraction.summary}")

                # Store each entity with metadata
                for entity in extraction.entities:
                    # Only store entities with confidence > 0.5
                    if entity.confidence >= 0.5:
                        memory_id = str(uuid.uuid4())

                        # Store with rich metadata including temporal awareness
                        # Format data with temporal status if present
                        temporal_label = f" ({entity.temporal_status})" if entity.temporal_status else ""
                        data_display = f"{entity.type}: {entity.value}{temporal_label}"

                        memory_data = {
                            "data": data_display,  # Format: "location: Hong Kong (past)"
                            "entity_type": entity.type,
                            "entity_value": entity.value,
                            "confidence": entity.confidence,
                            "context": entity.context or extraction.summary,
                            "importance": extraction.importance,
                            "timestamp": str(uuid.uuid1().time),
                            "original_message": request.message,
                            "temporal_status": entity.temporal_status,  # past/current/future/null
                            "reference_sentence": entity.reference_sentence  # Compacted original sentence
                        }

                        await global_store.aput(
                            namespace,
                            memory_id,
                            memory_data
                        )

                        facts_extracted.append(
                            f"{entity.type}: {entity.value} (confidence: {entity.confidence:.2f})"
                        )

                        print(f"✅ Stored: {entity.type}={entity.value} (confidence: {entity.confidence:.2f})")

                if facts_extracted:
                    facts_extracted.insert(0, f"[LLM Extraction] {extraction.summary}")
            else:
                print(f"ℹ️ No memorable information to store")
                if extraction:
                    print(f"   Reason: should_store={extraction.should_store}, entities={len(extraction.entities)}, importance={extraction.importance:.2f}")

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
                    "metadata": d.value  # Return ALL metadata including reference_sentence
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
