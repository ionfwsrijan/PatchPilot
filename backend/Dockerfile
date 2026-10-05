FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# Gitleaks
ARG GITLEAKS_VERSION=8.18.4
RUN curl -sSL https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz \
    | tar -xz -C /usr/local/bin gitleaks

# OSV-Scanner
ARG OSV_VERSION=1.9.2
RUN curl -sSL -o /usr/local/bin/osv-scanner \
    https://github.com/google/osv-scanner/releases/download/v${OSV_VERSION}/osv-scanner_linux_amd64 \
    && chmod +x /usr/local/bin/osv-scanner

# Run as non-root
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

# Install dependencies
COPY --chown=user requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir semgrep \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-ml.txt

# Copy backend code
COPY --chown=user . .

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]