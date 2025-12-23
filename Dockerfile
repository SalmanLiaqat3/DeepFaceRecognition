# Multi-stage build for production-grade Docker image
# Stage 1: Build stage
FROM python:3.10-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies to /usr/local
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install gunicorn for production WSGI server
RUN pip install --no-cache-dir gunicorn

# Stage 2: Production stage
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime dependencies for OpenCV and system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgtk-3-0 \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage (installed globally in /usr/local)
COPY --from=builder /usr/local/lib/python3.10 /usr/local/lib/python3.10
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app.py build_embeddings.py facetracker.py ./
COPY templates/ ./templates/
COPY static/ ./static/
COPY model/ ./model/
COPY data/ ./data/

# Create necessary directories with proper permissions
RUN mkdir -p /app/data/users /app/data/Attendance /app/static/results && \
    chown -R appuser:appuser /app

# Make sure scripts are executable
RUN chmod +x app.py build_embeddings.py

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5000

# Health check (using curl or wget instead of requests)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/', timeout=5)" || exit 1

# Use gunicorn for production WSGI server
# Adjust workers based on your server resources (CPU cores * 2 + 1)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--threads", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app:app"]

