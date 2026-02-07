FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install PyTorch CPU-only FIRST — avoids the ~2GB CUDA download.
# When sentence-transformers resolves its torch dep, it's already satisfied.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy everything needed for install
COPY pyproject.toml .
COPY cairn/ cairn/

# Install the package (torch already present, skips CUDA pull)
RUN pip install --no-cache-dir .

# Pre-download the embedding model at build time (cached in image)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Auto-run migrations on container start
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]

# Default: run the MCP server (transport controlled by CAIRN_TRANSPORT env var)
CMD ["python", "-m", "cairn.server"]
