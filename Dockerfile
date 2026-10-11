# Use a lightweight Python image as the base environment
FROM python:3.12-slim

# Prevent Python from creating unnecessary bytecode files
ENV PYTHONDONTWRITEBYTECODE=1

# Send Python logs directly to the terminal
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install the Python dependencies first
COPY requirements.txt .

# Install dependencies without retaining pip's download cache
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code into the image
COPY app/ ./app/

# Copy the admin setup script into the image
COPY scripts/ ./scripts/

# Run the API as an unprivileged user
RUN addgroup --system app && adduser --system --ingroup app app
USER app

# Document the port used by the FastAPI application
EXPOSE 8000

# Check that the API health endpoint is responding
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# Start FastAPI using one Uvicorn worker
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
