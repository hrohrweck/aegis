FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/
COPY config/ config/

# Install Python dependencies
RUN pip install --no-cache-dir .

# Create data and log directories
RUN mkdir -p data logs

# Expose dashboard port
EXPOSE 8080

# Run the application
CMD ["python", "-m", "src.main"]
