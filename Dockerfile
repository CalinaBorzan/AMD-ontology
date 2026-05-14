# =============================================================================
# Stage 1 — build the Vue frontend
# =============================================================================
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund

COPY frontend/ ./
# Build with VITE_API_URL="" so axios uses relative paths (same origin as backend)
ENV VITE_API_URL=""
RUN npm run build

# =============================================================================
# Stage 2 — Python backend + serve the built frontend
# =============================================================================
FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential default-jre-headless wget unzip \
    && rm -rf /var/lib/apt/lists/*

# Download DL-Learner 1.5.0
RUN wget -q https://github.com/SmartDataAnalytics/DL-Learner/releases/download/1.5.0/dllearner-1.5.0.zip \
    && unzip -q dllearner-1.5.0.zip \
    && rm dllearner-1.5.0.zip \
    && chmod +x dllearner-1.5.0/bin/cli

# Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application source (excluded via .dockerignore: .venv, node_modules, backups)
COPY backend/        ./backend/
COPY data/           ./data/
COPY results/        ./results/
COPY ontology/       ./ontology/
COPY evaluation/     ./evaluation/

# Built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Hugging Face Spaces runs on port 7860 by default
ENV PORT=7860
EXPOSE 7860

CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
