# Memory Chat - ReAct Agent with Dual-Memory Architecture

A production-ready AI agent system with dual-memory architecture (short-term + long-term) using LangGraph, PostgreSQL, FastAPI, and React.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph 1.0.2](https://img.shields.io/badge/LangGraph-1.0.2-green.svg)](https://langchain-ai.github.io/langgraph/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Features

- **Dual-Memory System**: Short-term (30 messages) + Long-term (unlimited persistent entities)
- **Phase 1: Intelligent Memory Extraction**
  - LLM-based entity extraction (GPT-4 powered)
  - Temporal awareness (past/current/future states)
  - 7 entity types with confidence scoring (≥ 0.5 threshold)
  - Reference sentence preservation for context
  - Rich metadata (confidence, importance, timestamps)
- **Full-Stack Application**: FastAPI backend + React UI
- **PostgreSQL Storage**: Reliable persistence with checkpointing
- **ReAct Agent Pattern**: Reasoning + Acting with tool execution
- **Session Management**: Multi-user support with isolated memories
- **Production Ready**: Async architecture, connection pooling, error handling

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+ with virtual environment
- Node.js 16+ and npm
- Docker (for PostgreSQL)
- OpenAI API key or compatible endpoint

### Step 1: Start PostgreSQL Database

```bash
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

# Configure environment
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

### Step 3: Start the Frontend UI

**Open a new terminal:**

```bash
cd chatbot-ui

# Install dependencies (first time only)
npm install

# Start the dev server
npm run dev
```

The frontend will start at `http://localhost:5173`

### Step 4: Open the Chat Interface

Open your browser: `http://localhost:5173`

**Quick Test:**
```
1. Type: "My name is Alice and I love pizza"
2. Type: "What's my name?"
   → Bot should respond: "Your name is Alice"
3. Refresh the page
4. Type: "What do you remember about me?"
   → Bot should recall: "You're Alice and you love pizza"
```

---

## 🧠 Memory System

### Short-Term Memory (Checkpoints)
- **Storage**: Last 30 conversation messages
- **Persistence**: Survives page refreshes (same session)
- **Scope**: Single session only
- **Use Case**: Recent conversation context

### Long-Term Memory (Store) - Phase 1: Intelligent Extraction

**Phase 1 Implementation (Current)**: LLM-based entity extraction with temporal awareness

- **Storage**: Structured entities with metadata (unlimited)
- **Persistence**: Forever (until deleted)
- **Scope**: Cross-session (same user_id)
- **Extraction**: GPT-4 powered intelligent analysis

**Extracted Entity Types:**
1. `person_name` - User's name or names of people mentioned
2. `age` - Age information
3. `profession` - Jobs, careers, occupations
4. `location` - Cities, countries, addresses
5. `preference` - Likes, dislikes, hobbies, interests
6. `fact` - General facts about the user
7. `relationship` - Family, friends, colleagues

**Temporal Awareness:**
Each entity includes temporal context:
- **Past**: `location: Hong Kong (past)` - "I lived in Hong Kong"
- **Current**: `location: Canada (current)` - "I live in Canada now"
- **Future**: `profession: doctor (future)` - "I plan to become a doctor"

**Rich Metadata Storage:**
- Confidence scoring (0.0-1.0) - Only entities with confidence ≥ 0.5 are stored
- Importance weighting (0.0-1.0) - Prioritizes critical information
- Reference sentences - Preserves original context
- Temporal status - Tracks past/current/future states
- Timestamps - Records when information was captured

**Example:**
```
User: "I lived in Hong Kong and moved to Canada now"

Extracted:
- Entity 1: location: "Hong Kong" (past, confidence: 1.0)
  Reference: "I lived in Hong Kong"

- Entity 2: location: "Canada" (current, confidence: 1.0)
  Reference: "moved to Canada now"
```

**Memory Modes:**
- **Short-term**: Uses only last 30 messages
- **Long-term**: Uses only stored entities
- **Both** (Recommended): Combines recent context + persistent entities

---

## 📊 Architecture Overview

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
    ├── checkpoints table (short-term: last 30 messages)
    └── store table (long-term: unlimited facts)
```

### Core Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| **LangGraph** | 1.0.2 | Agent orchestration & state management |
| **LangChain** | 1.0.3 | LLM framework |
| **FastAPI** | 0.115.0 | Backend API |
| **React** | 19.1.1 | Frontend UI |
| **PostgreSQL** | 15 | Persistent storage |
| **asyncpg** | 0.30.0 | Async PostgreSQL driver |

---

## 📁 Project Structure

```
agent-memory-chatbot/
├── README.md                    # This file
├── server.py                    # FastAPI backend
├── requirements.txt             # Python dependencies
├── docker-compose.yml           # PostgreSQL setup
├── .env.example                 # Environment template
├── 01_shortTermTest.py          # Short-term memory demo
├── 02_longTermTest.py           # Long-term memory demo
├── inspect_schema.py            # Database schema inspector
├── chatbot-ui/                  # React frontend
│   ├── src/
│   │   ├── components/
│   │   │   └── ChatInterface.jsx
│   │   └── App.jsx
│   └── package.json
└── docs/                        # Complete documentation
    ├── getting-started.md       # Detailed setup guide
    ├── memory/                  # Memory system docs
    │   └── README.md            # How memory works
    ├── core/                    # Technical documentation
    │   ├── README.md            # Documentation index
    │   ├── usage-guide.md       # 5 real-world use cases
    │   ├── architecture.md      # System architecture
    │   ├── database-schema.md   # Database design
    │   └── flow-diagrams.md     # Visual workflows
    └── deployment/              # Deployment guides
        └── PRODUCTION_DEPLOYMENT.md
```

---

## 📚 Documentation

### Getting Started
- **[Complete Setup Guide](docs/getting-started.md)** - Detailed 3-step setup, configuration, testing, and troubleshooting

### Core Documentation
- **[Documentation Index](docs/core/README.md)** - Navigation hub for all technical docs
- **[Usage Guide](docs/core/usage-guide.md)** - 5 complete real-world use cases with code
- **[Architecture](docs/core/architecture.md)** - System design and component architecture
- **[Database Schema](docs/core/database-schema.md)** - Complete database design and ERD
- **[Flow Diagrams](docs/core/flow-diagrams.md)** - Visual workflows and execution paths

### Memory System
- **[Memory Guide](docs/memory/README.md)** - Complete guide on short-term (30 msgs) + long-term (unlimited) memory system

### Deployment
- **[Production Deployment](docs/deployment/PRODUCTION_DEPLOYMENT.md)** - Deploy to production with AWS, GCP, Docker, Kubernetes

---

## 🛠️ Configuration

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

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat/v2` | POST | Send messages and get AI responses |
| `/memories/all/inspect?user_id={id}` | GET | View all memories for a user |
| `/memory-bank/{user_id}` | GET | Get long-term memories |
| `/memories/{user_id}` | DELETE | Delete all memories for a user |
| `/memories/all/clear` | DELETE | Clear all memories (all users) |
| `/users/list` | GET | List all users with stored memories |

---

## 🧪 Testing

### Test 1: Basic Memory
```bash
# Start the system
docker-compose up -d
python server.py
cd chatbot-ui && npm run dev

# In browser (http://localhost:5173):
1. Type: "My name is Alice and I love pizza"
2. Type: "What's my name?"
   → Should respond: "Alice"
```

### Test 2: Memory Persistence
```bash
# After Test 1:
1. Refresh the page
2. Type: "What do you remember about me?"
   → Should respond: "You're Alice and you love pizza"
```

### Test 3: Multi-Session
```bash
1. Create Session 1, type: "My name is Alice"
2. Create Session 2 (+ button), type: "My name is Bob"
3. Switch back to Session 1
4. Ask: "What's my name?"
   → Should say "Alice" (not Bob!)
```

---

## 🐛 Troubleshooting

### Backend won't start - "Could not connect to PostgreSQL"

```bash
# Check Docker is running
docker ps

# Restart PostgreSQL
docker-compose restart

# Check logs
docker logs postgres_db
```

### Frontend shows "Failed to fetch"

```bash
# Check backend is running
curl http://localhost:8000/

# Should return: {"status":"ok","message":"Memory Chat API is running"}
```

### Port already in use

```bash
# Kill process on port 8000 (backend)
lsof -ti:8000 | xargs kill -9

# Kill process on port 5173 (frontend)
lsof -ti:5173 | xargs kill -9
```

---

## 🎯 Use Cases

### 1. Customer Support Chatbot
- Remembers user issues across sessions
- Maintains conversation context
- Stores customer preferences

### 2. Personal Assistant
- Remembers user's schedule and preferences
- Cross-session context
- Personalized recommendations

### 3. E-commerce Shopping Assistant
- Remembers shopping preferences
- Purchase history
- Product recommendations

### 4. Educational Tutor
- Tracks student progress
- Remembers learning style
- Personalized curriculum

### 5. Healthcare Assistant
- Medical history (with proper security)
- Appointment scheduling
- Medication reminders

**See [Usage Guide](docs/core/usage-guide.md) for complete code examples.**

---

## 🔒 Security Notes

- Never commit `.env` files with real API keys
- Use environment variables for all secrets
- Implement proper authentication for production
- Enable SSL/TLS for database connections
- Use managed PostgreSQL services in production
- Implement rate limiting for API endpoints

---

## 🚀 Deployment

For production deployment, see:
- **[Production Deployment Guide](docs/deployment/PRODUCTION_DEPLOYMENT.md)** - Complete guide for AWS, GCP, Docker, Kubernetes

Key recommendations:
- Use managed PostgreSQL (AWS RDS, Google Cloud SQL, etc.)
- Set proper CORS origins in `server.py`
- Use environment variables for all secrets
- Build frontend: `cd chatbot-ui && npm run build`
- Deploy backend with process manager (gunicorn, systemd)
- Use HTTPS with SSL certificates

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

---

## 📄 License

MIT License - See LICENSE file for details.

---

## 🙏 Acknowledgments

Built with:
- [LangGraph](https://langchain-ai.github.io/langgraph/) - Agent framework
- [LangChain](https://python.langchain.com/) - LLM framework
- [FastAPI](https://fastapi.tiangolo.com/) - Backend framework
- [React](https://react.dev/) - Frontend framework
- [PostgreSQL](https://www.postgresql.org/) - Database

---

## 📧 Support

- **Issues**: Create an issue in the GitHub repository
- **Documentation**: Check the [docs/](docs/) folder
- **Questions**: See [Getting Started Guide](docs/getting-started.md)

---

**Built with ❤️ using LangGraph, FastAPI, React, and PostgreSQL**

**Last Updated**: 2025-11-16
