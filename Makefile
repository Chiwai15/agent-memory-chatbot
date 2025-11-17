.PHONY: start stop restart rebuild logs clean help

# Start containers (use existing images)
start:
	docker-compose up -d

# Stop containers
stop:
	docker-compose down

# Restart containers (use this after changing .env)
restart:
	docker-compose down
	docker-compose up -d

# Rebuild and start (use this after code changes)
rebuild:
	docker-compose up -d --build

# View logs (all services)
logs:
	docker-compose logs -f

# View backend logs only
logs-backend:
	docker logs -f memory_chatbot_backend

# View frontend logs only
logs-frontend:
	docker logs -f memory_chatbot_frontend

# Stop and remove everything (including volumes - WARNING: deletes database)
clean:
	docker-compose down -v

# Stop containers and remove images
clean-images:
	docker-compose down --rmi all

# Quick status check
status:
	docker-compose ps

# Help
help:
	@echo "Available commands:"
	@echo "  make start          - Start containers"
	@echo "  make stop           - Stop containers"
	@echo "  make restart        - Restart containers (for .env changes)"
	@echo "  make rebuild        - Rebuild and start (for code changes)"
	@echo "  make logs           - View all logs (Ctrl+C to exit)"
	@echo "  make logs-backend   - View backend logs only"
	@echo "  make logs-frontend  - View frontend logs only"
	@echo "  make status         - Check container status"
	@echo "  make clean          - Stop and remove all (WARNING: deletes database)"
	@echo "  make clean-images   - Stop and remove images"
	@echo "  make help           - Show this help message"
