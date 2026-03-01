# Use official Python lightweight image
FROM python:3.11-slim

# Install system dependencies needed for yt-dlp and Deno
RUN apt-get update && apt-get install -y \
    unzip \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the bot's code
COPY . .

# Expose port 8000 for Koyeb/Render Health Check
EXPOSE 8000

# Command to run the bot
CMD ["python", "main.py"]
