# Lightweight Discord-only bot (no dashboard, no browser, no Node CLI backends)
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir '.[discord,litellm]'

# ---- Runtime stage ----
FROM python:3.12-slim

# Git for cloning/reading public repos
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN groupadd --system pocketpaw && \
    useradd --system --gid pocketpaw --create-home pocketpaw && \
    mkdir -p /home/pocketpaw/.pocketpaw && \
    chown -R pocketpaw:pocketpaw /home/pocketpaw

USER pocketpaw
WORKDIR /home/pocketpaw

CMD ["pocketpaw", "--discord"]
