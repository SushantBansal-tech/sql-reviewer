FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# Expose port
EXPOSE 8000

# Start the FastAPI server
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]