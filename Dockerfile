# Use slim-buster for smaller image with essential build tools
FROM python:3.10-slim-bookworm

# Set the working directory
WORKDIR /app

# Install system dependencies FIRST (critical for psycopg2, pillow, cryptography)
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    zlib1g-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pip requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "awstest.wsgi:application"]
