import os
import asyncio
import uuid
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

# API Key Rotation Setup
# Support multiple comma-separated API keys for automatic rotation
API_KEYS = [
    key.strip() for key in os.getenv(
        "OPENAI_API_KEY",
        "your-api-key-here").split(",")]
current_api_key_index = 0

print(f"Loaded {len(API_KEYS)} API key(s) for rotation")

# Initialize the LLM with first key
llm = init_chat_model(
    model=os.getenv("LLM_MODEL", "openai:gpt-4"),
    temperature=0.7,
    base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
    api_key=API_KEYS[current_api_key_index]
)

# PostgreSQL connection string - use Railway's DATABASE_URL or fallback to localhost
raw_database_url = os.getenv("DATABASE_URL")
if raw_database_url:
    print(f"Found DATABASE_URL environment variable: {raw_database_url[:30]}...")
    # Railway DATABASE_URL might not have sslmode, add it if missing
    if "sslmode=" not in raw_database_url:
        DB_URI = raw_database_url + "?sslmode=disable"
    else:
        DB_URI = raw_database_url
else:
    print("WARNING: DATABASE_URL not found, using localhost fallback")
    DB_URI = "postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable"

print(f"Connecting to database: {DB_URI[:50]}...")
print(f"DATABASE_URL environment variable present: {bool(raw_database_url)}")
print(f"Total environment variables loaded: {len(os.environ)}")
# Debug: print first few env var names (not values for security)
env_keys = sorted(os.environ.keys())
print(f"Sample env vars: {', '.join(env_keys[:10])}")

# Memory configuration
SHORT_TERM_MESSAGE_LIMIT = int(os.getenv("SHORT_TERM_MESSAGE_LIMIT", "30"))

# Global store and checkpointer (will be initialized on startup)
global_store = None
global_checkpointer = None
global_agent = None
global_store_cm = None  # Context manager
global_checkpointer_cm = None  # Context manager


def switch_to_next_api_key():
    """
    Switch to the next available API key and reinitialize the agent.
    Returns True if switched successfully, False if no more keys available.
    """
    global current_api_key_index, llm, global_agent

    # Try next key
    next_index = current_api_key_index + 1

    if next_index >= len(API_KEYS):
        print(f"All {len(API_KEYS)} API keys exhausted")
        return False

    current_api_key_index = next_index
    masked_key = API_KEYS[current_api_key_index][:20] + "..."
    print(f"Switching to API key #{current_api_key_index + 1}/{len(API_KEYS)} ({masked_key})")

    # Reinitialize LLM with new key
    llm = init_chat_model(
        model=os.getenv("LLM_MODEL", "openai:gpt-4"),
        temperature=0.7,
        base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        api_key=API_KEYS[current_api_key_index]
    )

    # Reinitialize agent with new LLM
    global_agent = create_react_agent(
        llm,
        tools=[],
        checkpointer=global_checkpointer,
        store=global_store
    )

    print(f"Successfully switched to key #{current_api_key_index + 1}")
    return True


# Pydantic models
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    user_id: str
    memory_source: Optional[str] = "both"  # "short", "long", "both"
    messages: Optional[List[Message]] = []
    mode_type: Optional[str] = "ask"  # "ask" or "agent"
    # Service ID like "youtube", "airbnb", etc.
    selected_service: Optional[str] = None


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
    # Temporal context: "past", "current", "future", or None
    temporal_status: Optional[str] = "current"
    # Original sentence for context preservation
    reference_sentence: Optional[str] = None


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
        max_tokens=SHORT_TERM_MESSAGE_LIMIT,
        # Keep last N messages (configured in .env)
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
BAD (Incomplete):
  - fact: "collaborate on lesson plans"
  - preference: "basketball"
  - relationship: "friend"

GOOD (Complete Context):
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
{{"entities": [
    {{"type": "location", "value": "Hong Kong", "confidence": 1.0, "context": "User's past residence", "temporal_status": "past", "reference_sentence": "I lived in Hong Kong"}} ,
    {{"type": "location", "value": "Canada", "confidence": 1.0, "context": "User's current residence", "temporal_status": "current", "reference_sentence": "I moved to Canada now"}} ,
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
{{"entities": [],
  "summary": "No memorable information",
  "importance": 0.0,
  "should_store": false
}}

Analyze the conversation and respond with ONLY valid JSON:"""

        # Create dedicated LLM for memory extraction with higher token limit
        # (Memory extraction needs more tokens to return complete JSON)
        # Use first API key for extraction (reset after potential rotation)
        extraction_key_index = current_api_key_index % len(API_KEYS)  # Ensure valid index
        extraction_llm = init_chat_model(
            model=os.getenv("LLM_MODEL", "openai:gpt-4"),
            temperature=0.3,  # Lower temperature for more structured output
            base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
            api_key=API_KEYS[extraction_key_index],
            model_kwargs={"max_tokens": 500}  # Enough for JSON with multiple entities
        )

        # Use the dedicated extraction LLM
        response = await extraction_llm.ainvoke([
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
            print(f"Failed to parse LLM response as JSON: {e}")
            print(f"Response was: {response.content[:200]}")
            return None

    except Exception as e:
        error_str = str(e)
        # Check if it's a rate limit error - skip memory extraction gracefully
        if "rate_limit" in error_str.lower() or "429" in error_str:
            print(f"Rate limit hit during memory extraction - skipping to save tokens")
            print(f"Memory extraction will resume when rate limit resets")
            return None
        else:
            print(f"Error in extract_memories_with_llm: {e}")
            return None


# Define a function to create dynamic system prompts based on mode and service
def create_system_prompt(mode_type: str = "ask",
                         selected_service: str = None) -> SystemMessage:
    """
    Create a dynamic system prompt based on mode type and selected service.

    Args:
        mode_type: "ask" (information) or "agent" (execution/planning)
        selected_service: Service ID like "youtube", "netflix", "airbnb", etc.
    """

    # Service capabilities catalog
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
        "netflix": {
            "name": "Netflix",
            "ask_capabilities": [
                "Search for movies and TV shows",
                "Get recommendations based on preferences",
                "Check what's new and trending",
                "Find content by genre or actor"
            ],
            "agent_capabilities": [
                "Start playing movies or shows",
                "Add to watchlist",
                "Continue watching from last position",
                "Download content for offline viewing"
            ]
        },
        "primevideo": {
            "name": "Prime Video",
            "ask_capabilities": [
                "Browse Prime Video catalog",
                "Find included vs rental content",
                "Get personalized recommendations",
                "Check new releases and deals"
            ],
            "agent_capabilities": [
                "Stream movies and shows",
                "Rent or purchase content",
                "Add to watchlist",
                "Manage Prime Video channels"
            ]
        },
        "spotify": {
            "name": "Spotify",
            "ask_capabilities": [
                "Search for songs, artists, and albums",
                "Discover new music and podcasts",
                "Find playlists by mood or genre",
                "Check what's trending"
            ],
            "agent_capabilities": [
                "Play songs, albums, or playlists",
                "Create and manage playlists",
                "Like and save songs",
                "Follow artists and podcasts"
            ]
        },
        "airbnb": {
            "name": "Airbnb",
            "ask_capabilities": [
                "Search for accommodations by location",
                "Check prices and availability",
                "View property details and reviews",
                "Compare different listings"
            ],
            "agent_capabilities": [
                "Book accommodations",
                "Send booking requests to hosts",
                "Manage reservations",
                "Process payments and confirmations"
            ]
        },
        "booking": {
            "name": "Booking.com",
            "ask_capabilities": [
                "Search hotels and apartments",
                "Check room rates and availability",
                "View property amenities and reviews",
                "Find deals and discounts"
            ],
            "agent_capabilities": [
                "Make hotel reservations",
                "Complete booking process",
                "Manage existing bookings",
                "Process payments and send confirmations"
            ]
        },
        "ubereats": {
            "name": "Uber Eats",
            "ask_capabilities": [
                "Browse restaurants near you",
                "Check menus and prices",
                "View restaurant ratings and reviews",
                "Find cuisine types and deals"
            ],
            "agent_capabilities": [
                "Place food orders",
                "Track delivery status",
                "Schedule orders",
                "Process payments and send order confirmations"
            ]
        },
        "doordash": {
            "name": "DoorDash",
            "ask_capabilities": [
                "Search for restaurants and stores",
                "Compare delivery times and fees",
                "Check menu items and prices",
                "Find special offers"
            ],
            "agent_capabilities": [
                "Order food and groceries",
                "Schedule deliveries",
                "Track orders in real-time",
                "Complete checkout and send receipts"
            ]
        },
        "grubhub": {
            "name": "Grubhub",
            "ask_capabilities": [
                "Find local restaurants",
                "Browse menus and specials",
                "Check delivery areas and times",
                "View restaurant ratings"
            ],
            "agent_capabilities": [
                "Place food orders",
                "Apply promo codes",
                "Track delivery progress",
                "Process payments and confirmations"
            ]
        },
        "uber": {
            "name": "Uber",
            "ask_capabilities": [
                "Check ride estimates and pricing",
                "View available ride types (UberX, Black, etc.)",
                "Estimate arrival times",
                "Compare ride options"
            ],
            "agent_capabilities": [
                "Request rides",
                "Schedule future rides",
                "Track driver location",
                "Complete bookings and send trip receipts"
            ]
        },
        "lyft": {
            "name": "Lyft",
            "ask_capabilities": [
                "Get price estimates",
                "Check ride availability",
                "View service types",
                "Estimate trip duration"
            ],
            "agent_capabilities": [
                "Book rides",
                "Schedule pickups",
                "Track driver arrival",
                "Process payments and send ride confirmations"
            ]
        },
        "grubhub": {
            "name": "Grubhub",
            "ask_capabilities": [
                "Find local restaurants",
                "Browse menus and specials",
                "Check delivery areas and times",
                "View restaurant ratings"
            ],
            "agent_capabilities": [
                "Place food orders",
                "Apply promo codes",
                "Track delivery progress",
                "Process payments and confirmations"
            ]
        },
        "skyscanner": {
            "name": "Skyscanner",
            "ask_capabilities": [
                "Search for flights by destination",
                "Compare airline prices",
                "Check baggage allowances",
                "View flight schedules and durations"
            ],
            "agent_capabilities": [
                "Book flight tickets",
                "Set price alerts",
                "Complete reservations",
                "Send flight confirmations and itineraries"
            ]
        },
        "lime": {
            "name": "Lime",
            "ask_capabilities": [
                "Find nearby e-scooters and bikes",
                "Check pricing and ride costs",
                "View battery levels and range",
                "Get ride unlock instructions"
            ],
            "agent_capabilities": [
                "Unlock scooter or bike",
                "Start and end rides",
                "Process payments and trip receipts",
                "Report vehicle issues"
            ]
        },
        "yelp": {
            "name": "Yelp",
            "ask_capabilities": [
                "Search for local businesses",
                "Read reviews and ratings",
                "Check business hours and contact info",
                "Browse photos and menus"
            ],
            "agent_capabilities": [
                "Make restaurant reservations",
                "Write and post reviews",
                "Upload photos",
                "Message businesses directly"
            ]
        },
        "deliveroo": {
            "name": "Deliveroo",
            "ask_capabilities": [
                "Browse restaurants and menus",
                "Check delivery times and fees",
                "View special offers",
                "See restaurant ratings"
            ],
            "agent_capabilities": [
                "Place food orders",
                "Track delivery in real-time",
                "Schedule orders",
                "Process payments and send receipts"
            ]
        },
        "amazon": {
            "name": "Amazon",
            "ask_capabilities": [
                "Search for products",
                "Compare prices and sellers",
                "Read product reviews",
                "Check Prime eligibility and delivery times"
            ],
            "agent_capabilities": [
                "Add items to cart and purchase",
                "Track orders and deliveries",
                "Manage subscriptions",
                "Process returns and refunds"
            ]
        },
        "instacart": {
            "name": "Instacart",
            "ask_capabilities": [
                "Browse grocery stores",
                "Search for products",
                "Check prices and availability",
                "View deals and coupons"
            ],
            "agent_capabilities": [
                "Place grocery orders",
                "Schedule delivery times",
                "Track shopper progress",
                "Process payments and send receipts"
            ]
        },
        "shopify": {
            "name": "Shopify",
            "ask_capabilities": [
                "Browse stores and products",
                "Check product availability",
                "View shipping options",
                "Read store policies"
            ],
            "agent_capabilities": [
                "Complete purchases",
                "Track orders",
                "Manage account and preferences",
                "Process payments and confirmations"
            ]
        },
        "etsy": {
            "name": "Etsy",
            "ask_capabilities": [
                "Search for handmade and vintage items",
                "Browse seller shops",
                "Check customization options",
                "Read reviews and ratings"
            ],
            "agent_capabilities": [
                "Purchase items",
                "Message sellers for custom requests",
                "Track orders",
                "Leave reviews and feedback"
            ]
        },
        "googlecalendar": {
            "name": "Google Calendar",
            "ask_capabilities": [
                "View upcoming events",
                "Check availability and free/busy times",
                "Search for past events",
                "View shared calendars"
            ],
            "agent_capabilities": [
                "Create new events and meetings",
                "Send calendar invites",
                "Set reminders and notifications",
                "Manage recurring events"
            ]
        },
        "calendly": {
            "name": "Calendly",
            "ask_capabilities": [
                "View available time slots",
                "Check meeting types offered",
                "See scheduling preferences",
                "View timezone settings"
            ],
            "agent_capabilities": [
                "Schedule meetings",
                "Send meeting invitations",
                "Manage availability",
                "Cancel and reschedule appointments"
            ]
        },
        "outlook": {
            "name": "Outlook",
            "ask_capabilities": [
                "Search emails and calendar",
                "Check meeting schedules",
                "View contacts",
                "Read email threads"
            ],
            "agent_capabilities": [
                "Send emails",
                "Schedule meetings and events",
                "Manage calendar invites",
                "Organize inbox with folders and rules"
            ]
        },
        "zoom": {
            "name": "Zoom",
            "ask_capabilities": [
                "Check upcoming meetings",
                "View meeting details and links",
                "See participant lists",
                "Check recordings availability"
            ],
            "agent_capabilities": [
                "Schedule new meetings",
                "Start instant meetings",
                "Send meeting invitations",
                "Manage meeting settings and recordings"
            ]
        },
        "notion": {
            "name": "Notion",
            "ask_capabilities": [
                "Search pages and databases",
                "View workspace content",
                "Check templates available",
                "Browse team wikis"
            ],
            "agent_capabilities": [
                "Create pages and databases",
                "Edit and organize content",
                "Share pages with team",
                "Set up automations and integrations"
            ]
        },
        "googledrive": {
            "name": "Google Drive",
            "ask_capabilities": [
                "Search for files and folders",
                "Check storage usage",
                "View shared files",
                "See recent documents"
            ],
            "agent_capabilities": [
                "Upload and organize files",
                "Share files and folders",
                "Create Docs, Sheets, and Slides",
                "Manage permissions and access"
            ]
        },
        "slack": {
            "name": "Slack",
            "ask_capabilities": [
                "Search messages and files",
                "Check channels and members",
                "View workspace settings",
                "Browse integrations"
            ],
            "agent_capabilities": [
                "Send messages and files",
                "Create channels",
                "Set reminders and status",
                "Manage notifications and preferences"
            ]
        },
        "microsoft": {
            "name": "Microsoft 365",
            "ask_capabilities": [
                "Search documents across apps",
                "Check OneDrive storage",
                "View Teams meetings",
                "Browse SharePoint sites"
            ],
            "agent_capabilities": [
                "Create and edit Office documents",
                "Schedule Teams meetings",
                "Share files via OneDrive",
                "Collaborate on documents"
            ]
        },
        "strava": {
            "name": "Strava",
            "ask_capabilities": [
                "View activity stats and records",
                "Check training plans",
                "See routes and segments",
                "Browse challenges and clubs"
            ],
            "agent_capabilities": [
                "Log workouts and activities",
                "Track runs and rides",
                "Join challenges",
                "Share activities with followers"
            ]
        },
        "headspace": {
            "name": "Headspace",
            "ask_capabilities": [
                "Browse meditation courses",
                "Check sleep sounds",
                "View mindfulness exercises",
                "See progress and stats"
            ],
            "agent_capabilities": [
                "Start meditation sessions",
                "Track mindfulness practice",
                "Set daily reminders",
                "Complete courses and challenges"
            ]
        },
        "peloton": {
            "name": "Peloton",
            "ask_capabilities": [
                "Browse class schedules",
                "View instructor profiles",
                "Check workout types",
                "See leaderboard and stats"
            ],
            "agent_capabilities": [
                "Join live classes",
                "Start on-demand workouts",
                "Track fitness progress",
                "Set fitness goals and milestones"
            ]
        },
        "tempus": {
            "name": "Tempus AI",
            "ask_capabilities": [
                "View health records",
                "Check test results",
                "Browse treatment options",
                "See medical history"
            ],
            "agent_capabilities": [
                "Schedule appointments",
                "Request prescriptions",
                "Upload health data",
                "Message healthcare providers"
            ]
        },
        "paypal": {
            "name": "PayPal",
            "ask_capabilities": [
                "Check account balance",
                "View transaction history",
                "See payment methods",
                "Check exchange rates"
            ],
            "agent_capabilities": [
                "Send and request money",
                "Make payments",
                "Transfer funds",
                "Process refunds and disputes"
            ]
        },
        "venmo": {
            "name": "Venmo",
            "ask_capabilities": [
                "View recent transactions",
                "Check balance",
                "See payment requests",
                "Browse social feed"
            ],
            "agent_capabilities": [
                "Send money to friends",
                "Request payments",
                "Split bills",
                "Transfer to bank account"
            ]
        },
        "chase": {
            "name": "Chase",
            "ask_capabilities": [
                "Check account balances",
                "View transactions and statements",
                "See credit card rewards",
                "Browse financial products"
            ],
            "agent_capabilities": [
                "Transfer funds between accounts",
                "Pay bills and credit cards",
                "Deposit checks",
                "Set up alerts and notifications"
            ]
        },
        "cashapp": {
            "name": "Cash App",
            "ask_capabilities": [
                "Check Cash App balance",
                "View transaction history",
                "See Bitcoin holdings",
                "Browse boost offers"
            ],
            "agent_capabilities": [
                "Send and receive money",
                "Buy and sell Bitcoin",
                "Invest in stocks",
                "Use Cash Card for payments"
            ]
        },
        "coursera": {
            "name": "Coursera",
            "ask_capabilities": [
                "Browse courses and degrees",
                "Check course schedules",
                "View instructor profiles",
                "See course reviews and ratings"
            ],
            "agent_capabilities": [
                "Enroll in courses",
                "Submit assignments",
                "Track learning progress",
                "Earn certificates and degrees"
            ]
        },
        "udemy": {
            "name": "Udemy",
            "ask_capabilities": [
                "Search for courses",
                "Compare course prices",
                "Read student reviews",
                "Check course curriculum"
            ],
            "agent_capabilities": [
                "Purchase and enroll in courses",
                "Watch video lessons",
                "Complete quizzes and assignments",
                "Track course progress"
            ]
        },
        "khanacademy": {
            "name": "Khan Academy",
            "ask_capabilities": [
                "Browse subjects and topics",
                "View lesson videos",
                "Check practice exercises",
                "See learning paths"
            ],
            "agent_capabilities": [
                "Complete lessons and exercises",
                "Track learning progress",
                "Earn mastery points and badges",
                "Set learning goals"
            ]
        },
        "duolingo": {
            "name": "Duolingo",
            "ask_capabilities": [
                "Check available languages",
                "View lesson structure",
                "See progress and streaks",
                "Browse leaderboards"
            ],
            "agent_capabilities": [
                "Complete language lessons",
                "Practice speaking and listening",
                "Take skill tests",
                "Maintain daily streaks and goals"
            ]
        }
    }

    # Base memory system prompt (always included)
    base_prompt = (
        "You are an AI assistant with dual-memory architecture.\n\n"
        "MEMORY SYSTEM:\n"
        "- Short-term: Last 30 messages (session context)\n"
        "- Long-term: Persistent facts from [STORED MEMORIES] (always trust these over recent conversation)\n"
        "- When user asks 'what do you remember', list all [STORED MEMORIES]\n"
        "- Be honest about what's stored when asked\n\n"
        "CRITICAL - RESPONSE LENGTH:\n"
        "- MAXIMUM 3 SHORT sentences per response\n"
        "- NO bullet points, NO numbered lists, NO examples\n"
        "- Get straight to the point\n"
        "- If you write more than 50 words, you FAILED\n\n")

    # Mode-specific behavior
    if mode_type == "ask":
        mode_section = (
            "MODE: ASK (Information Only)\n"
            "CRITICAL: Detect if user is requesting an ACTION vs asking a QUESTION\n\n"
            "If user requests ACTION (add/play/book/order/send/create/etc):\n"
            "→ STOP. Say ONLY: 'To perform this action, please switch to Agent mode.'\n"
            "→ Do NOT explain why. Do NOT say you're an AI/LLM. Do NOT provide information.\n\n"
        )
    else:  # agent mode
        mode_section = (
            "MODE: AGENT (Planning & Execution)\n"
            "You ARE the service with full capabilities. All actions you perform are REAL.\n"
            "- Execute all requested tasks completely\n"
            "- Provide realistic progress updates during operations\n"
            "- Send completion confirmations with IDs/receipts (booking IDs, order numbers, tracking info)\n"
            "- Never mention limitations or inability to perform actions\n\n")

    # Service-specific context (moved outside mode_type blocks)
    service_section = ""
    if selected_service and selected_service in service_capabilities:
        service_info = service_capabilities[selected_service]

        if mode_type == "ask":
            service_section = f"SERVICE: {service_info['name']}\nYou are the {service_info['name']} assistant. Introduce yourself first, then help with:\n"
            for cap in service_info['ask_capabilities']:
                service_section += f"• {cap}\n"
            service_section += f"Answer questions on behalf of the service. Stay focused on {service_info['name']} only.\n\n"
        else:  # agent mode
            service_section = f"SERVICE: {service_info['name']}\nYou are the {service_info['name']} agent. Introduce yourself first, then execute:\n"
            for cap in service_info['agent_capabilities']:
                service_section += f"• {cap}\n"
            service_section += f"Pretend to execute actions with Completion Emails/Receipts/Messages without mentioning you are llm/pretending. Stay focused on {service_info['name']} only.\n\n"
    else:
        service_section = "SERVICE: None\nHelp users choose services and explain capabilities.\n\n"

    # Combine all sections
    full_prompt = base_prompt + mode_section + service_section

    return SystemMessage(content=full_prompt)


@app.on_event("startup")
async def startup_event():
    """Initialize database connections and agent on startup"""
    global global_checkpointer, global_store, global_agent, global_checkpointer_cm, global_store_cm

    # Initialize PostgreSQL checkpointer (for short-term message history)
    global_checkpointer_cm = AsyncPostgresSaver.from_conn_string(DB_URI)
    global_checkpointer = await global_checkpointer_cm.__aenter__()
    await global_checkpointer.setup()

    # Initialize PostgreSQL store (for long-term memory)
    global_store_cm = AsyncPostgresStore.from_conn_string(DB_URI)
    global_store = await global_store_cm.__aenter__()
    await global_store.setup()

    # Create initial system message with default settings
    system_message = create_system_prompt(
        mode_type="ask", selected_service=None)

    # Create the agent
    global_agent = create_react_agent(
        model=llm,
        tools=[],
        prompt=system_message,
        pre_model_hook=pre_model_hook,
        checkpointer=global_checkpointer,
        store=global_store
    )

    print("Server initialized successfully!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global global_store_cm, global_checkpointer_cm

    if global_store_cm:
        await global_store_cm.__aexit__(None, None, None)
    if global_checkpointer_cm:
        await global_checkpointer_cm.__aexit__(None, None, None)

    print("Server shutdown complete")


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
    global current_api_key_index

    try:
        # Memory source mapping
        # Frontend sends: "short" (conversation history), "long" (persistent
        # facts), "both"
        normalized_source = request.memory_source if request.memory_source in [
            "short", "long", "both"] else "both"

        # Configuration for the agent
        # Use different thread_id for long-term only mode to prevent loading
        # conversation state from checkpointer
        thread_id = request.user_id if normalized_source in [
            "short", "both"] else f"{request.user_id}_long_only"

        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": request.user_id
            }
        }
        print(f"Using thread_id: {thread_id} (mode: {normalized_source})")

        # Create dynamic system prompt based on mode and service
        mode_type = request.mode_type or "ask"
        selected_service = request.selected_service
        dynamic_system_message = create_system_prompt(
            mode_type=mode_type, selected_service=selected_service)
        print(f"Mode: {mode_type}, Service: {selected_service or 'None'}")
        print(f"System prompt preview: {dynamic_system_message.content[:200]}...")

        # Retrieve long-term memories based on memory_source
        memories_context = ""
        retrieved_memories = []

        if normalized_source in ["long", "both"]:
            namespace = ("memories", request.user_id)
            memories = await global_store.asearch(namespace, query="")

            if memories:
                # Build memory entries with reference sentences for richer
                # context
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
            print(f"Retrieved {len(retrieved_memories)} memories for user {request.user_id}")
            print(f"Memory context: {memories_context[:200]}...")
        else:
            augmented_input = request.message
            print(f"No stored memories found for user {request.user_id}")

        # Build message history from request based on memory_source
        message_history = []

        # Only include conversation history if using short-term or both
        if normalized_source in ["short", "both"]:
            # Keep last N messages for context (configured in .env)
            for msg in request.messages[-SHORT_TERM_MESSAGE_LIMIT:]:
                if msg.role == "user":
                    message_history.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    message_history.append(AIMessage(content=msg.content))
            print(
                f"Using short-term memory: {len(message_history)} conversation messages")
        else:
            print(f"Short-term memory disabled (mode: {normalized_source})")

        # Add current user message
        message_history.append(HumanMessage(content=augmented_input))

        # Invoke the agent with automatic API key rotation on rate limits
        max_retries = len(API_KEYS)
        agent_response = None
        last_error = None

        for attempt in range(max_retries):
            try:
                # Create LLM with current API key (don't use global llm)
                current_llm = init_chat_model(
                    model=os.getenv("LLM_MODEL", "openai:gpt-4"),
                    temperature=0.7,
                    base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
                    api_key=API_KEYS[current_api_key_index],
                    model_kwargs={"max_tokens": 150}  # Strict limit: ~100-120 words max
                )

                # Create agent with current LLM
                request_agent = create_react_agent(
                    model=current_llm,
                    tools=[],
                    prompt=dynamic_system_message,
                    pre_model_hook=pre_model_hook,
                    checkpointer=global_checkpointer,
                    store=global_store
                )

                agent_response = await request_agent.ainvoke(
                    {"messages": message_history},
                    config
                )
                break  # Success - exit retry loop

            except Exception as e:
                error_str = str(e)
                last_error = e

                # Check if it's a rate limit error
                if "rate_limit_exceeded" in error_str.lower(
                ) or "rate limit reached" in error_str.lower():
                    print(f"Rate limit hit on API key #{current_api_key_index + 1}")
                    print(f"Raw error message: {error_str}")

                    # Sanitize error message - extract wait time but remove sensitive data
                    import re
                    sanitized_message = "Rate limit reached. "

                    # Extract wait time (e.g., "1m42.816s", "17m29.76s", "6s", "2h30m")
                    # Match any combination of digits, dots, and time units (s/m/h)
                    wait_time_match = re.search(r'try again in ([\d.smh]+)', error_str, re.IGNORECASE)
                    if wait_time_match:
                        wait_time = wait_time_match.group(1)
                        sanitized_message += f"Please try again in {wait_time}."
                    else:
                        sanitized_message += "Please try again later."

                    # Try to switch to next key
                    if attempt < max_retries - 1:  # Not the last attempt
                        current_api_key_index += 1
                        masked_key = API_KEYS[current_api_key_index][:20] + "..." if len(API_KEYS[current_api_key_index]) > 20 else API_KEYS[current_api_key_index]
                        print(f"Rate limit on key #{current_api_key_index}/{len(API_KEYS)}")
                        print(f"Switching to key #{current_api_key_index + 1}/{len(API_KEYS)} ({masked_key})")
                        print(f"Retrying (attempt {attempt + 2}/{max_retries})...")
                        continue  # Retry with new key
                    else:
                        # Last attempt failed
                        masked_key = API_KEYS[current_api_key_index][:20] + "..." if len(API_KEYS[current_api_key_index]) > 20 else API_KEYS[current_api_key_index]
                        error_code = API_KEYS[current_api_key_index][-6:] if len(API_KEYS[current_api_key_index]) >= 6 else API_KEYS[current_api_key_index]
                        debug_info = f"[DEBUG] Last key tried: #{current_api_key_index + 1}/{len(API_KEYS)} ({masked_key})"
                        print(f"429 Error - {debug_info}")
                        print(f"Full error details: {error_str}")
                        raise HTTPException(
                            status_code=429,
                            detail=f"429: {sanitized_message} [Code: {error_code}]")
                else:
                    # Not a rate limit error, re-raise immediately
                    raise

        if agent_response is None:
            raise last_error or Exception("Agent invocation failed")

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

                print(f"Extracted {len(extraction.entities)} entities (importance: {extraction.importance:.2f})")
                print(f"Summary: {extraction.summary}")

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
                            # Format: "location: Hong Kong (past)"
                            "data": data_display,
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

                        print(f"Stored: {entity.type}={entity.value} (confidence: {entity.confidence:.2f})")

                if facts_extracted:
                    facts_extracted.insert(0, f"[LLM Extraction] {extraction.summary}")
            else:
                print(f"No memorable information to store")
                if extraction:
                    print(f"   Reason: should_store={extraction.should_store}, entities={len(extraction.entities)}, importance={extraction.importance:.2f}")

        return ChatResponse(
            response=response_content,
            memories_used=retrieved_memories,
            facts_extracted=facts_extracted,
            complexity_level="simple",
            mode_transitions=[
                "short_term" if request.memory_source == "short" else "long_term"],
            thinking_process="Retrieved context and generated response",
            quality_score=0.9)

    except HTTPException:
        # Re-raise HTTPException as-is (preserves status code and sanitized message)
        raise
    except Exception as e:
        # Only catch non-HTTP exceptions - don't leak sensitive error details
        print(f"Unexpected error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


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
            # Return last N messages (configured in .env)
            "messages": messages[-SHORT_TERM_MESSAGE_LIMIT:]
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
    """Clear all memories AND checkpoints from all users (PostgreSQL store + checkpoints)"""
    try:
        # Step 1: Clear all long-term memories from store table
        # We need to search through all possible namespaces and delete them
        # Since we can't easily iterate all namespaces, we'll use raw SQL
        import asyncpg

        conn = await asyncpg.connect(DB_URI)

        try:
            # Clear store table (long-term memories)
            store_result = await conn.execute("DELETE FROM store;")
            store_count = int(store_result.split()[-1]) if store_result else 0

            # Clear checkpoints table (short-term conversation history)
            checkpoint_result = await conn.execute("DELETE FROM checkpoints;")
            checkpoint_count = int(
                checkpoint_result.split()[-1]) if checkpoint_result else 0

            # Also clear checkpoint writes and blobs for cleanup
            await conn.execute("DELETE FROM checkpoint_writes;")
            await conn.execute("DELETE FROM checkpoint_blobs;")

            return {
                "message": "All memories and conversations cleared successfully",
                "status": "success",
                "cleared": {
                    "store_entries": store_count,
                    "checkpoint_entries": checkpoint_count}}
        finally:
            await conn.close()

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear memories: {str(e)}")


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
            # For now, we return an empty list which will cause the frontend to
            # keep existing sessions
            pass
        except BaseException:
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
