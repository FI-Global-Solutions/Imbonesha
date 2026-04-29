FROM python:3.11-slim

WORKDIR /app

# System deps needed by rasterio (GDAL) and shapely.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

# Ensure setuptools + wheel are available (needed to build rasterio from source).
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# PyTorch CPU-only wheel — keeps the image under 2 GB.
# For GPU production builds, swap the index URL for the CUDA variant.
RUN pip install --no-cache-dir \
    torch==2.4.1 \
    torchvision==0.19.1 \
    --index-url https://download.pytorch.org/whl/cpu

# Remaining Python deps.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY app/ ./app/
COPY checkpoints/ ./checkpoints/

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
