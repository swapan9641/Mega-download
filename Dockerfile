# Use the official Python slim image for a smaller footprint
FROM python:3.10-slim

# Set environment variables to prevent Python from writing .pyc files & buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (ffmpeg and megatools)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg megatools && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure the download directory exists
RUN mkdir -p downloads

# Expose the web server port for cloud health checks
EXPOSE 8080

# Start the application
CMD ["python", "bot.py"]
