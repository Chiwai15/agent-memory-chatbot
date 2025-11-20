# Memory Chat

A chatbot with dual-memory architecture for persistent, context-aware conversations.

## Demo

https://github.com/user-attachments/assets/demo.MP4

> Note: If the video doesn't load, see [publich/demo.MP4](publich/demo.MP4)

## Features

### Dual-Memory Architecture
- **Short-term Memory**: PostgreSQL-based checkpoints for recent conversation context
- **Long-term Memory**: Mem0-powered semantic memory for persistent entity extraction
- **Memory Compacting**: Automatic deduplication every 30 messages to optimize storage

### Multi-Provider LLM Support
- **Groq** (Free tier, fast inference)
- **DeepSeek** (95% cheaper than OpenAI)
- **OpenAI** (GPT-4, GPT-3.5)

### Modern UI
- WhatsApp-style chat interface
- Mobile responsive with overlay menus
- Memory Pensieve panel for debugging
- Interactive demo mode with sample personas

## Tech Stack

- **Backend**: Python, FastAPI, LangGraph
- **Frontend**: React, Vite, Tailwind CSS
- **Database**: PostgreSQL
- **Memory**: Mem0 for long-term memory extraction
- **Deployment**: Docker Compose, Railway

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Git

### Installation

1. Clone the repository:
```bash
git clone https://github.com/Chiwai15/agent-memory-chatbot.git
cd agent-memory-chatbot
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. Start the application:
```bash
make rebuild
```

4. Access the app at `http://localhost:3000`

### Environment Configuration

```env
# LLM Provider (choose one)
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://api.groq.com/openai/v1
LLM_MODEL=openai:llama-3.3-70b-versatile

# Memory settings
SHORT_TERM_MESSAGE_LIMIT=30
```

## Docker Commands

```bash
make rebuild    # Build and start containers
make restart    # Restart containers
make logs       # View logs
make stop       # Stop containers
```

## Project Structure

```
agent-memory-chatbot/
├── server.py           # FastAPI backend with LangGraph
├── chatbot-ui/         # React frontend
├── docker-compose.yml  # Container orchestration
├── Dockerfile          # Backend container
├── requirements.txt    # Python dependencies
└── docs/              # Additional documentation
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend   │────▶│  PostgreSQL │
│   (React)   │     │  (FastAPI)  │     │ (Short-term)│
└─────────────┘     └──────┬──────┘     └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │    Mem0     │
                   │ (Long-term) │
                   └─────────────┘
```

## Deployment

See [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md) for Railway deployment instructions.

## License

MIT
