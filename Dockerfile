# Use slim-buster for smaller image with essential build tools
FROM python:3.10

# Set the working directory
WORKDIR /app

# Install system dependencies for Uvicorn and healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pip requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8000

# Default command (overridden in docker-compose for different services)
CMD ["uvicorn", "core.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
