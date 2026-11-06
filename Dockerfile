FROM python:3.12-slim

WORKDIR /app

# Ensure unbuffered python output for real-time logging
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

# Copy application files
COPY . /app/

# Expose ports
# Web Dashboard: 8080
# Cloud Mock: 8866 (TCP), 8867 (TLS)
# HTTP/HTTPS: 80, 443
# DNS & Beacon: 53/udp, 9131/udp
EXPOSE 8080 8866 8867 80 443 53/udp 9131/udp

CMD ["python", "ambi_hub.py"]

