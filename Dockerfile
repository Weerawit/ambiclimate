# Use python:3.9-slim-buster for native compatibility with Raspbian 10 Buster (avoids clone3 / libseccomp issue)
FROM python:3.9-slim-buster

WORKDIR /app

# Ensure unbuffered python output for real-time logging
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

# Install tzdata for accurate OS timezone support
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY . /app/

# Expose ports
# Web Dashboard: 9090
# Cloud Mock: 8866 (TCP), 8867 (TLS)
# HTTP/HTTPS: 80, 443
# DNS & Beacon: 53/udp, 9131/udp
EXPOSE 9090 8866 8867 80 443 53/udp 9131/udp

CMD ["python", "ambi_hub.py"]

