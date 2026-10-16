# Relay Production Deployment Guide

This guide details the procedure for deploying Relay to a production Linux Virtual Private Server (Ubuntu 22.04/24.04 LTS or Debian 12) using Docker Compose.

---

## 1. System Requirements & Architecture

- **Operating System:** Ubuntu 22.04 / 24.04 LTS, Debian 12, or AlmaLinux 9
- **Hardware Minimum:** 2 vCPU, 4 GB RAM, 20 GB SSD
- **Network Ports:**
  - `80/tcp` (HTTP - forwarded by reverse proxy / Let's Encrypt)
  - `443/tcp` (HTTPS - production TLS traffic)
  - `22/tcp` (SSH administration)

```
                    Internet
                       │
                       ▼
           [ Host Firewall (UFW) ]
             Ports 80, 443 only
                       │
                       ▼
        [ Reverse Proxy: Nginx (Container) ]
           Rate Limiting, Security Headers
                       │
         ┌─────────────┴─────────────┐ (Docker internal network: relay-internal)
         ▼                           ▼
  [ Relay API:8000 ]      [ Order Service:8001 ]
         │                           │
         └─────────────┬─────────────┘
                       ▼
            [ PostgreSQL 16 (internal) ]
```

---

## 2. Server Preparation

### 2.1 Update System & Install Docker
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git ufw fail2ban ca-certificates gnupg

# Install official Docker CE and Docker Compose plugin
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow non-root docker usage (optional)
sudo usermod -aG docker $USER
```

### 2.2 Configure Firewall (UFW)
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'
sudo ufw --force enable
sudo ufw status verbose
```
> [!NOTE]
> Database port `5432` and simulated order service port `8001` are kept on internal Docker network and **never** exposed to the public Internet.

---

## 3. Application Deployment

### 3.1 Clone Repository
```bash
git clone https://github.com/souro26/relay.git /opt/relay
cd /opt/relay
```

### 3.2 Configure Production Environment Variables
Generate strong passwords and API keys:
```bash
# Generate database password
DB_PASS=$(openssl rand -hex 24)
DEMO_KEY=$(openssl rand -hex 24)

cp .env.production.template .env.production
chmod 600 .env.production
```

Edit `.env.production` to insert secrets and production values:
```bash
nano .env.production
```
Ensure the following keys are set:
- `POSTGRES_PASSWORD`: The generated random secret
- `DATABASE_URL`: `postgresql+psycopg://relay:${POSTGRES_PASSWORD}@postgres:5432/relay_production`
- `LLM_API_KEY`: Your NVIDIA NIM or OpenAI API key
- `DEMO_API_KEY`: The generated secret key for public demo protection

### 3.3 Launch Services
```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Container startup sequence:
1. `postgres` starts and completes healthcheck (`pg_isready`).
2. `order-service` starts and verifies schema connection.
3. `relay` starts, applies database migrations via Alembic (`alembic upgrade head`), and starts Uvicorn.
4. `proxy` starts Nginx reverse proxy on port 80.

---

## 4. Verification and Health Checks

### 4.1 Check Container Status
```bash
docker compose -f docker-compose.prod.yml ps
```
All containers (`relay-postgres-prod`, `relay-order-service-prod`, `relay-api-prod`, `relay-proxy-prod`) should show status `Up` or `healthy`.

### 4.2 Validate HTTP Health Endpoints
```bash
# Test application liveness
curl -i http://localhost/health

# Test database readiness
curl -i http://localhost/ready

# Test operational metrics endpoint
curl -i http://localhost/api/v1/metrics
```

Expected readiness output:
```json
{"status":"ready","service":"relay","database":"connected"}
```

### 4.3 Inspect Logs
```bash
docker compose -f docker-compose.prod.yml logs -f relay
```
Structured JSON logs should stream indicating correlation IDs, startup steps, and HTTP request timings.

---

## 5. SSL/TLS Certificate Setup (HTTPS)

### Option A: Certbot on Host (Recommended)
1. Stop port 80 proxy temporarily or use webroot challenge:
```bash
sudo apt install -y certbot python3-certbot-nginx
```
2. Set up Certbot to terminate TLS on the host and forward traffic to `127.0.0.1:80` (or configure certificates into `./docker/nginx/certs` mounted to the Nginx container).

---

## 6. Automated Backup Strategy

Make backup scripts executable:
```bash
chmod +x scripts/backup_db.sh scripts/restore_db.sh
```

### 6.1 Run Manual Backup Test
```bash
./scripts/backup_db.sh
```
Check `./backups/` for the compressed `.sql.gz` file.

### 6.2 Configure Nightly Cron Backup
```bash
crontab -e
```
Add the following line to run backups nightly at 02:00 AM UTC with 14-day automated retention:
```cron
0 2 * * * /opt/relay/scripts/backup_db.sh >> /var/log/relay_backup.log 2>&1
```

### 6.3 Test Database Restoration
To restore a snapshot:
```bash
./scripts/restore_db.sh ./backups/relay_relay_production_YYYYMMDD_HHMMSS.sql.gz
```

---

## 7. Zero-Downtime Application Updates

When updating the application with new code:
```bash
cd /opt/relay
git pull origin main

# Rebuild images and restart containers with updated migrations
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```
Alembic migrations will automatically apply on container startup before serving traffic.
