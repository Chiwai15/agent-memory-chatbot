# Railway Deployment Guide

This guide explains how to deploy the Memory Chatbot application to Railway.

## Architecture

The application consists of three services:
1. **PostgreSQL Database** - Managed by Railway's PostgreSQL addon
2. **FastAPI Backend** - Python API server
3. **Vite Frontend** - React UI served by Nginx

## Prerequisites

- Railway account (sign up at https://railway.app)
- GitHub repository with your code
- OpenAI or DeepSeek API key

## Deployment Steps

### 1. Create a New Project on Railway

1. Go to https://railway.app/new
2. Select "Deploy from GitHub repo"
3. Choose your repository
4. Railway will detect the project automatically

### 2. Add PostgreSQL Database

1. Click "+ New" in your Railway project
2. Select "Database" → "Add PostgreSQL"
3. Railway will automatically provision a PostgreSQL instance
4. The `DATABASE_URL` environment variable will be automatically set

### 3. Deploy Backend Service

1. Click "+ New" → "GitHub Repo" or use the detected service
2. Set the following in Settings:
   - **Root Directory**: `/` (leave empty)
   - **Dockerfile Path**: `Dockerfile`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`

3. Add environment variables (Settings → Variables):
   ```
   OPENAI_API_KEY=your-api-key-here
   OPENAI_API_BASE=https://api.deepseek.com
   LLM_MODEL=openai:deepseek-chat
   SHORT_TERM_MESSAGE_LIMIT=30
   ```

4. Railway will automatically connect the `DATABASE_URL` from PostgreSQL service

### 4. Deploy Frontend Service

1. Click "+ New" → "GitHub Repo"
2. Set the following in Settings:
   - **Root Directory**: `chatbot-ui`
   - **Dockerfile Path**: `chatbot-ui/Dockerfile`

3. Add environment variable:
   ```
   VITE_API_BASE_URL=https://your-backend-url.railway.app
   ```
   (Replace with your backend Railway URL after backend is deployed)

### 5. Configure Custom Domains (Optional)

1. Go to Settings → Networking → Public Networking
2. Click "Generate Domain" for both services
3. Or add your custom domain

## Environment Variables Reference

### Backend Service
| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string (auto-set by Railway) | `postgresql://user:pass@host:5432/db` |
| `OPENAI_API_KEY` | Your LLM API key | `sk-...` |
| `OPENAI_API_BASE` | API endpoint | `https://api.deepseek.com` |
| `LLM_MODEL` | Model to use | `openai:deepseek-chat` |
| `SHORT_TERM_MESSAGE_LIMIT` | Recent message limit | `30` |
| `PORT` | Port to run on (auto-set by Railway) | `8000` |

### Frontend Service
| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | Backend API URL | `https://your-backend.railway.app` |

## Local Development with Docker

To test the deployment locally:

```bash
# Start all services
docker-compose up --build

# Access the application
# Frontend: http://localhost
# Backend: http://localhost:8000
# Database: localhost:5432
```

## Troubleshooting

### Backend won't start
- Check that `DATABASE_URL` is set correctly
- Verify all required environment variables are present
- Check logs in Railway dashboard

### Frontend can't connect to backend
- Verify `VITE_API_BASE_URL` points to the correct backend URL
- Ensure backend service is running
- Check CORS settings in backend if needed

### Database connection errors
- Ensure PostgreSQL service is running
- Check `DATABASE_URL` format
- Verify network connectivity between services

## Cost Optimization

Railway offers:
- Free tier with $5 credit/month
- Hobby plan at $5/month + usage
- Pay-as-you-go for resources used

Tips to reduce costs:
- Use DeepSeek API (95% cheaper than OpenAI)
- Set appropriate memory/CPU limits
- Use sleep mode for non-production environments

## Monitoring

Railway provides:
- Real-time logs for each service
- Metrics dashboard (CPU, memory, network)
- Deployment history
- Custom health checks

## Continuous Deployment

Railway automatically deploys when you push to your GitHub repository:
1. Push changes to your repo
2. Railway detects changes
3. Builds and deploys automatically
4. Zero-downtime deployments

## Security Best Practices

1. Never commit `.env` files
2. Use Railway's environment variables for secrets
3. Enable Railway's private networking between services
4. Regularly update dependencies
5. Use non-root user in Docker containers (already configured)

## Support

- Railway Documentation: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- GitHub Issues: Create an issue in your repository
