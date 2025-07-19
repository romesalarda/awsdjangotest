# Use slim-buster for smaller image with essential build tools
FROM python:3.10

# Set the working directory
WORKDIR /app

# Install pip requirements
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "awstest.wsgi:application"]
