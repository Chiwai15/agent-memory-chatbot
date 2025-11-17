# Getting Started with Memory Chat

Complete guide to run the full-stack Memory Chat application with React UI and FastAPI backend.

## Prerequisites

- Python 3.8+ with virtual environment
- Node.js 16+ and npm
- Docker (for PostgreSQL)
- OpenAI API key or compatible endpoint

## Quick Start (3 Steps)

### Step 1: Start PostgreSQL Database

```bash
# Navigate to project directory
cd /Users/ny/Desktop/Nelson/Projects/AI/MemoryChat/03_ReActAgentMemoryTest

# Start the database
docker-compose up -d

# Verify it's running
docker ps | grep postgres
```

### Step 2: Start the Backend API Server

```bash
# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies (first time only)
pip install -r requirements.txt

# Make sure .env file exists with your API key
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Start the FastAPI server
python server.py
```

The backend will start at `http://localhost:8000`

**Expected output:**
```
✅ Server initialized successfully!
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Keep this terminal open!** The backend needs to keep running.

### Step 3: Start the Frontend UI

**Open a NEW terminal window**, then:

```bash
cd /Users/ny/Desktop/Nelson/Projects/AI/MemoryChat/03_ReActAgentMemoryTest/chatbot-ui

# Install dependencies (first time only)
npm install

# Start the dev server
npm run dev
```

**Expected output:**
```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

### Step 4: Open the Chat Interface

Open your browser and go to:
```
http://localhost:5173
```

You should see the Memory Chat interface with:
- Chat area in the center
- Session management sidebar on the left
- Memory Pensieve debug panel on the right (⛲️)
- Input box at the bottom

## Testing the System

### Quick Test 1: Basic Conversation
```
1. Type: "My name is Alice and I love pizza"
   → Bot should acknowledge

2. Type: "What's my name?"
   → Bot should respond: "Your name is Alice"

3. Check the Memory Pensieve panel (right side)
   → You should see memories stored
```

### Quick Test 2: Memory Persistence
```
1. Type: "My name is Alice and I love pizza"
2. Refresh the page (F5)
3. Type: "What do you remember about me?"
   → Bot should recall: "You're Alice and you love pizza"
```

### Quick Test 3: Multi-Session
```
1. Create Session 1, type: "My name is Alice"
2. Create Session 2 (+ button), type: "My name is Bob"
3. Switch back to Session 1
4. Ask: "What's my name?"
   → Should say "Alice" (not Bob!)
```

## Architecture Overview

```
Browser (localhost:5173)
    ↓ HTTP/REST
React Frontend
    ↓
FastAPI Backend (localhost:8000)
    ↓
LangGraph ReAct Agent
    ↓
PostgreSQL (localhost:5432)
    ├── checkpoints (short-term: last 30 messages)
    └── store (long-term: unlimited persistent facts)
```

## Memory System Explained

### Short-term Memory (PostgreSQL Checkpoints)
- Stores conversation history for each session
- Keeps **last 30 messages**
- Automatically managed by LangGraph
- Survives page refreshes

**Example:**
```
You: "My name is Alice"
Bot: "Nice to meet you, Alice!"
You: "What's my name?"
Bot: "Your name is Alice" ← Retrieved from conversation history
```

### Long-term Memory (PostgreSQL Store)
- Stores persistent facts across sessions
- **Unlimited storage** - all facts are recalled
- Triggered by specific phrases
- Survives session changes and restarts

**Trigger Phrases:**
- "My name is..."
- "I am..."
- "I like..."
- "I love..."
- "I prefer..."

**Example:**
```
Session 1:
You: "My name is Alice and I love pizza"
Bot: "Got it, Alice! I'll remember that you love pizza"
[Stored in long-term memory]

[Later, in Session 2:]
You: "What do you remember about me?"
Bot: "You're Alice and you love pizza!" ← Retrieved from store
```

### Memory Modes

In the UI, you can select different modes:
- **Short-term**: Uses only last 30 conversation messages
- **Long-term**: Uses only stored facts
- **Both** (Recommended): Uses last 30 messages + all stored facts

## Configuration

### Backend (.env in root directory)

```bash
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1
LLM_MODEL=openai:gpt-4
```

### Frontend (chatbot-ui/.env)

```bash
VITE_API_URL=http://localhost:8000
```

## Troubleshooting

### Backend won't start - "Could not connect to PostgreSQL"

**Problem:** PostgreSQL isn't running

**Solution:**
```bash
# Check Docker is running
docker ps

# Restart PostgreSQL
docker-compose restart

# Check logs
docker logs postgres_db
```

### Frontend shows "Failed to fetch"

**Problem:** Backend isn't running

**Solution:** Check backend terminal for errors, make sure you see "Server initialized successfully"

### Port already in use (8000 or 5173)

**Problem:** Another service is using the port

**Solution:**
```bash
# Kill process on port 8000 (backend)
lsof -ti:8000 | xargs kill -9

# Kill process on port 5173 (frontend)
lsof -ti:5173 | xargs kill -9
```

### No memories showing in Debug Panel

**Problem:** Memories not being stored

**Solution:**
```bash
# Check database has tables
python inspect_schema.py

# Should show: checkpoints, checkpoint_writes, store tables

# Try sending a message with "My name is..." to trigger storage
```

## Stopping the System

### To Stop:
```bash
# Kill frontend (in terminal running npm)
Ctrl+C

# Kill backend (in terminal running python)
Ctrl+C

# Or kill by port
lsof -ti:5173 | xargs kill -9  # Frontend
lsof -ti:8000 | xargs kill -9  # Backend
```

### To Restart Backend:
```bash
source .venv/bin/activate
python server.py
```

### To Restart Frontend:
```bash
cd chatbot-ui
npm run dev
```

## API Endpoints

The frontend communicates with these backend endpoints:

- `POST /chat/v2` - Send messages and get AI responses
- `GET /memories/all/inspect?user_id={id}` - View all memories for a user
- `GET /memory-bank/{user_id}` - Get long-term memory organized as files
- `DELETE /memories/{user_id}` - Delete all memories for a user
- `DELETE /memories/all/clear` - Clear all memories (all users)
- `GET /users/list` - List all users with stored memories

## Next Steps

1. ✅ Experiment with different memory modes (Short/Long/Both)
2. ✅ Create multiple sessions to see memory isolation
3. ✅ Inspect the Memory Pensieve to see stored memories
4. ✅ Read the [Memory Guide](docs/memory/README.md) for deeper understanding
5. ✅ Check [Architecture Documentation](docs/core/architecture.md) for system design
6. ✅ See [Production Deployment Guide](docs/deployment/PRODUCTION_DEPLOYMENT.md) for deployment

## Need Help?

- **Backend logs:** Check the terminal where `python server.py` is running
- **Frontend logs:** Press F12 in browser → Console tab
- **Database:** Run `python inspect_schema.py` to see what's stored
- **Complete Documentation:** See `docs/` folder

---

**Built with:**
- LangGraph 1.0.2 (ReAct agent)
- FastAPI 0.115.0 (backend API)
- React 19.1.1 (frontend UI)
- PostgreSQL 15 (persistent storage)
- OpenAI GPT-4 (language model)

**Last Updated:** 2025-01-11
