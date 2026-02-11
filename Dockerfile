FROM python:3.11-slim

LABEL io.modelcontextprotocol.server.name="io.github.jasondostal/cairn-mcp"

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

# Install from lockfile for reproducible builds
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# Copy application code
COPY pyproject.toml .
COPY cairn/ cairn/
COPY scripts/ scripts/

# Install the package itself (deps already satisfied by lockfile)
RUN pip install --no-cache-dir --no-deps .

# Non-root user for runtime security
RUN useradd --create-home --shell /bin/bash cairn \
    && chown -R cairn:cairn /app

# Pre-download the embedding model as the cairn user
ENV HF_HOME=/home/cairn/.cache/huggingface
USER cairn
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Auto-run migrations on container start (copy as root, then switch back)
USER root
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh && chown cairn:cairn entrypoint.sh

USER cairn
ENTRYPOINT ["./entrypoint.sh"]

# Default: run the MCP server (transport controlled by CAIRN_TRANSPORT env var)
CMD ["python", "-m", "cairn.server"]
