FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application files
COPY . .

# Create volume mount points
VOLUME ["/app"]

# Set default timezone (can be overridden)
ENV TZ=America/Los_Angeles

# Run the bot
CMD ["python", "run.py"]
