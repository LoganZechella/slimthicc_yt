FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    ca-certificates \
    openssl \
    file \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create downloads directory with very permissive permissions
RUN mkdir -p /app/downloads /app/tmp && \
    chmod 777 /app/downloads /app/tmp && \
    chown -R appuser:appuser /app/downloads /app/tmp

# Update certificates
RUN update-ca-certificates --fresh
RUN python -m certifi

# Copy YouTube cookies file
COPY youtube.cookies /app/youtube.cookies
RUN chown appuser:appuser /app/youtube.cookies && chmod 600 /app/youtube.cookies

# Copy application code
COPY . .
RUN chown -R appuser:appuser /app

# Set environment variable for temp directory
ENV TMPDIR=/app/tmp

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Start the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"] 