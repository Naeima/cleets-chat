# CLEETS-CHAT Docker Image
# Build: docker build -t cleets-chat .
# Run: docker run -e ANTHROPIC_API_KEY=sk-ant-... -p 8050:8050 cleets-chat

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8050

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files and knowledge graphs
COPY app.py kg_service.py qa.py qa_with_humanization.py methods.py about.py analyze_feedback.py ./
COPY data/ ./data/
COPY assets/ ./assets/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# Expose port
EXPOSE ${PORT}

# Run Dash app via Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8050", "--workers", "2", "--worker-class", "sync", "--timeout", "60", "app:server"]
