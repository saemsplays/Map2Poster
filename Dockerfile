FROM python:3.11.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MPLBACKEND=Agg

# Install system dependencies required for Geo/Mapping stack
RUN apt-get update && apt-get install -y \
    build-essential \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    proj-bin \
    proj-data \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set the GDAL_DATA path (required for some geo operations)
ENV GDAL_DATA=/usr/share/gdal

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port (FastAPI default or Railway's $PORT)
EXPOSE 8000

# Start the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
