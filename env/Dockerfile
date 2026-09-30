FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /commons
CMD ["sleep", "infinity"]
