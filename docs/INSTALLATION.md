# Installation & Deployment Guide

OpenMusic Archive Manager is designed to run on any Linux Docker host, Proxmox LXC/VM, Synology/TrueNAS system, or local workstation.

---

## 1. Quick Start with Docker Compose (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/Tomajashi/openmusic-archive-manager.git
   cd openmusic-archive-manager
   ```

2. Copy the example environment configuration:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` to configure your NAS music path, `PUID`/`PGID` permissions, and optional API keys:
   ```env
   OPENMUSIC_PORT=8080
   PUID=1000
   PGID=1000
   MUSIC_HOST_PATH=/mnt/nas/music
   JAMENDO_CLIENT_ID=your_jamendo_client_id
   ```

4. Build and start the container:
   ```bash
   docker compose up -d --build
   ```

5. Access the Web UI at:
   - **Web Interface**: `http://localhost:8080`
   - **OpenAPI Docs**: `http://localhost:8080/docs`

---

## 2. Running Alongside Navidrome

To start both **OpenMusic Archive Manager** and **Navidrome** sharing the same `/music` library volume:

```bash
docker compose --profile with-navidrome up -d --build
```
- OpenMusic UI: `http://localhost:8080`
- Navidrome UI: `http://localhost:4533`

In OpenMusic **Settings -> Navidrome Server Integration**, enable auto-rescan and set `http://navidrome:4533` along with your Navidrome credentials.

---

## 3. NAS & Proxmox Permission Configuration

When mounting an NFS or SMB share from a NAS into a Docker host or Proxmox LXC container:
- Set `PUID` and `PGID` in `.env` to match the UID/GID that owns your NAS music share.
- The container's `docker-entrypoint.sh` automatically adjusts ownership of `/app/config` and `/downloads` and drops privileges via `gosu` before launching `uvicorn`.
