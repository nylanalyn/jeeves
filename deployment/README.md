# Jeeves Web Servers Deployment

This directory contains configuration files and scripts for deploying the Jeeves web servers.

## Quick Reference

### Development (Local Testing)

```bash
# Easy way - use the management script
./deployment/manage-servers.sh start
./deployment/manage-servers.sh status
./deployment/manage-servers.sh logs
./deployment/manage-servers.sh stop

# Manual way
python3 quest_web.py  # Port 8080
python3 stats_web.py  # Port 8081
```

### Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for full instructions.

**TL;DR:**
1. Choose nginx config (subdomain or path-based)
2. Copy to `/etc/nginx/sites-available/jeeves`
3. Update domain names in config
4. Enable site and reload nginx
5. Install systemd services
6. Set up DNS and SSL (certbot)

---

## Files

### Nginx Configurations

- **nginx-subdomain.conf** - Routes different subdomains to different servers
  - `quest.yourdomain.com` → Quest leaderboard (port 8080)
  - `stats.yourdomain.com` → Stats dashboard (port 8081)

- **nginx-path.conf** - Routes different paths on same domain
  - `jeeves.yourdomain.com/` → Stats dashboard (port 8081)
  - `jeeves.yourdomain.com/quest` → Quest leaderboard (port 8080)

### Systemd Services

- **jeeves-quest-web.service** - Systemd service for quest web server
- **jeeves-stats-web.service** - Systemd service for stats web server

### Scripts

- **manage-servers.sh** - Helper script for development (start/stop/status/logs)

### Documentation

- **DEPLOYMENT.md** - Complete deployment guide
- **README.md** - This file

---

## Architecture

```
                    ┌─────────────┐
                    │   Internet  │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │    Nginx    │
                    │  Port 80/443│
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
       ┌─────────────┐          ┌─────────────┐
       │  Quest Web  │          │  Stats Web  │
       │  Port 8080  │          │  Port 8081  │
       │ (localhost) │          │ (localhost) │
       └──────┬──────┘          └──────┬──────┘
              │                         │
              └────────────┬────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │Config Files │
                    │games.json   │
                    │stats.json   │
                    │users.json   │
                    │absurdia.db  │
                    └─────────────┘
```

---

## URLs

### Development (Local)
- Quest: http://localhost:8080
- Stats: http://localhost:8081

### Production (Subdomain-based)
- Quest: http://quest.yourdomain.com
- Stats: http://stats.yourdomain.com

### Production (Path-based)
- Stats: http://jeeves.yourdomain.com/
- Quest: http://jeeves.yourdomain.com/quest

---

## Management Commands

### Development
```bash
./deployment/manage-servers.sh start     # Start both servers
./deployment/manage-servers.sh stop      # Stop both servers
./deployment/manage-servers.sh restart   # Restart both servers
./deployment/manage-servers.sh status    # Check status
./deployment/manage-servers.sh logs      # Tail logs
```

### Production (Systemd)
```bash
sudo systemctl start jeeves-quest-web    # Start quest server
sudo systemctl start jeeves-stats-web    # Start stats server
sudo systemctl status jeeves-quest-web   # Check status
sudo journalctl -u jeeves-quest-web -f   # View logs
sudo systemctl restart jeeves-quest-web  # Restart service
```

---

## Troubleshooting

**Servers won't start?**
- Check if ports are already in use: `netstat -tlnp | grep 808`
- Check logs: `cat logs/quest-web.log` or `cat logs/stats-web.log`

**Can't access from internet?**
- Check nginx is running: `sudo systemctl status nginx`
- Check firewall: `sudo ufw status`
- Test nginx config: `sudo nginx -t`

**Services keep restarting?**
- Check service logs: `sudo journalctl -u jeeves-quest-web -n 50`
- Verify Python path in service files
- Check file permissions on config files

---

## Next Steps

1. Test locally with `./deployment/manage-servers.sh start`
2. Choose subdomain or path-based routing
3. Follow DEPLOYMENT.md for production setup
4. Set up SSL with certbot
5. Configure DNS records
6. Monitor logs for issues

---

For detailed instructions, see [DEPLOYMENT.md](DEPLOYMENT.md).
