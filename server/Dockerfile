FROM python:3.12-slim

# Set environment variables to reduce Python behavior that could cause security or performance issues
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    TMPDIR=/app/tmp

# Create app directory first so we can set permissions once
RUN mkdir -p /app /app/downloads /app/tmp

# Install system dependencies with security best practices
# - Use apt-get instead of apt for scripting
# - Clean up in the same layer to reduce image size
# - Install only what's needed
# - Run apt-get update and install in same layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    openssl \
    file \
    procps \
    curl \
    libxml2-dev \
    libxslt-dev \
    gcc \
    python3-dev \
    build-essential \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates --fresh

# Install Rust for pydantic-core compilation
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Create non-root user
RUN adduser --disabled-password --gecos "" --uid 1000 appuser

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Update vulnerable packages and install dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade certifi yt-dlp

# Create directories with appropriate permissions
RUN chmod 755 /app /app/tmp && \
    chmod 1777 /app/downloads && \
    chown -R appuser:appuser /app

# Copy YouTube cookies file (with restricted permissions)
COPY youtube.cookies /app/youtube.cookies
RUN chown appuser:appuser /app/youtube.cookies && chmod 600 /app/youtube.cookies

# Copy application code
COPY . .
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Healthcheck to verify the application is running properly
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Start the FastAPI application directly with uvicorn
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--workers", "4", "--bind", "0.0.0.0:8000", "src.main:app"] 