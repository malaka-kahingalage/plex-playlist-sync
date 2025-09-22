# Dockerfile for plexPlayList sync application
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install system dependencies (if any needed for python-plexapi, thefuzz, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt ./

# Install Python dependencies (including spotdl)
RUN pip install --no-cache-dir -r requirements.txt


# Copy application code
COPY . .
# Copy static files for web frontend
COPY static ./static

# Set environment variable for Python output
ENV PYTHONUNBUFFERED=1

# To persist downloads, map a host directory to /app/downloads:
#   docker run -v $(pwd)/downloads:/app/downloads ...
# Your downloaded files will appear in the local downloads folder.

CMD ["python", "main.py"]
