# Enterprise SD-WAN Monitoring System - Dockerfile
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for network tools and build requirements
RUN apt-get update && apt-get install -y \
    iputils-ping \
    build-essential \
    python3-dev \
    net-tools \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p data reports uploads

# Copy application files
COPY . /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Expose port
EXPOSE 5000

# Run the application using Gunicorn (production WSGI server)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "120", "app:app"]
