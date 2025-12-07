# Jeeves Web Servers Deployment Guide

This guide covers deploying both the Quest and Stats web servers using nginx reverse proxy.

## Architecture

```
Internet → Nginx (Port 80/443)
              ↓
              ├─→ Quest Web Server (localhost:8080)
              └─→ Stats Web Server (localhost:8081)
```

## Two Deployment Options

### Option A: Subdomain-based Routing (Recommended)
- `quest.yourdomain.com` → Quest leaderboard
- `stats.yourdomain.com` → Stats dashboard

**Pros:** Clean URLs, easy to remember
**Cons:** Requires DNS setup for subdomains

### Option B: Path-based Routing
- `jeeves.yourdomain.com/` → Stats dashboard
- `jeeves.yourdomain.com/quest` → Quest leaderboard

**Pros:** Single domain needed
**Cons:** URLs have path prefixes

---

## Quick Start (Development)

Run both servers locally without nginx:

```bash
# Terminal 1: Quest web server
python3 quest_web.py

# Terminal 2: Stats web server
python3 stats_web.py

# Access:
# Quest: http://localhost:8080
# Stats: http://localhost:8081
```

---

## Production Deployment

### Step 1: Install Nginx

```bash
sudo apt update
sudo apt install nginx
```

### Step 2: Choose Your Nginx Configuration

**For subdomain-based routing:**
```bash
sudo cp deployment/nginx-subdomain.conf /etc/nginx/sites-available/jeeves
```

**For path-based routing:**
```bash
sudo cp deployment/nginx-path.conf /etc/nginx/sites-available/jeeves
```

### Step 3: Configure Your Domain

Edit the nginx config and replace `yourdomain.com` with your actual domain:

```bash
sudo nano /etc/nginx/sites-available/jeeves
```

### Step 4: Enable the Site

```bash
# Create symlink to enable site
sudo ln -s /etc/nginx/sites-available/jeeves /etc/nginx/sites-enabled/

# Test nginx configuration
sudo nginx -t

# If test passes, reload nginx
sudo systemctl reload nginx
```

### Step 5: Set Up Systemd Services

Install the systemd service files to run both web servers automatically:

```bash
# Copy service files
sudo cp deployment/jeeves-quest-web.service /etc/systemd/system/
sudo cp deployment/jeeves-stats-web.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services to start on boot
sudo systemctl enable jeeves-quest-web
sudo systemctl enable jeeves-stats-web

# Start services
sudo systemctl start jeeves-quest-web
sudo systemctl start jeeves-stats-web

# Check status
sudo systemctl status jeeves-quest-web
sudo systemctl status jeeves-stats-web
```

### Step 6: Set Up DNS

**For subdomain-based routing:**
Add A records for your subdomains:
- `quest.yourdomain.com` → Your server IP
- `stats.yourdomain.com` → Your server IP

**For path-based routing:**
Add A record:
- `jeeves.yourdomain.com` → Your server IP

### Step 7: Enable HTTPS (Recommended)

Install certbot and get SSL certificates:

```bash
sudo apt install certbot python3-certbot-nginx

# For subdomain-based:
sudo certbot --nginx -d quest.yourdomain.com -d stats.yourdomain.com

# For path-based:
sudo certbot --nginx -d jeeves.yourdomain.com
```

Certbot will automatically configure HTTPS and set up auto-renewal.

---

## Managing the Services

### View Logs

```bash
# Quest web server logs
sudo journalctl -u jeeves-quest-web -f

# Stats web server logs
sudo journalctl -u jeeves-stats-web -f

# Nginx access logs
sudo tail -f /var/log/nginx/jeeves-*-access.log

# Nginx error logs
sudo tail -f /var/log/nginx/jeeves-*-error.log
```

### Restart Services

```bash
# Restart quest web
sudo systemctl restart jeeves-quest-web

# Restart stats web
sudo systemctl restart jeeves-stats-web

# Reload nginx (for config changes)
sudo systemctl reload nginx
```

### Stop Services

```bash
sudo systemctl stop jeeves-quest-web
sudo systemctl stop jeeves-stats-web
```

---

## Testing

### Test Backend Servers Directly

```bash
# Test quest web (should return HTML)
curl http://localhost:8080/

# Test stats web (should return HTML)
curl http://localhost:8081/

# Test stats API (should return JSON)
curl http://localhost:8081/api/stats
```

### Test Through Nginx

**For subdomain-based:**
```bash
curl http://quest.yourdomain.com/
curl http://stats.yourdomain.com/
```

**For path-based:**
```bash
curl http://jeeves.yourdomain.com/
curl http://jeeves.yourdomain.com/quest
```

---

## Updating the Code

When you update the web servers:

```bash
# Pull latest changes
cd /home/nullveil/code/jeeves
git pull

# Restart services
sudo systemctl restart jeeves-quest-web
sudo systemctl restart jeeves-stats-web
```

---

## Troubleshooting

### Services won't start

Check service status and logs:
```bash
sudo systemctl status jeeves-quest-web
sudo journalctl -u jeeves-quest-web -n 50
```

Common issues:
- Port already in use (check with `netstat -tlnp | grep 808`)
- Python path incorrect (update ExecStart in service file)
- Permissions (make sure user can access config files)

### Nginx errors

Test configuration:
```bash
sudo nginx -t
```

Check error logs:
```bash
sudo tail -f /var/log/nginx/error.log
```

### Can't connect from internet

- Check firewall: `sudo ufw status`
- Allow HTTP/HTTPS: `sudo ufw allow 'Nginx Full'`
- Verify DNS with: `dig quest.yourdomain.com`
- Check nginx is listening: `sudo netstat -tlnp | grep nginx`

---

## Port Reference

| Service | Port | Access |
|---------|------|--------|
| Quest Web | 8080 | localhost only |
| Stats Web | 8081 | localhost only |
| Nginx HTTP | 80 | Public |
| Nginx HTTPS | 443 | Public |

Both web servers bind to 127.0.0.1 (localhost only) for security.
Only nginx is exposed to the internet and proxies requests to the backends.

---

## Security Notes

1. **Both web servers only bind to localhost** - They're not directly accessible from the internet
2. **Nginx handles SSL/TLS** - All encryption happens at the nginx layer
3. **Use HTTPS in production** - Always set up certbot for SSL certificates
4. **Keep servers updated** - Regularly update nginx and Python packages
5. **Monitor logs** - Set up log monitoring for suspicious activity

---

## Alternative: Simple Launch Script

If you don't want to use systemd, you can use this simple script:

```bash
# Create start-web-servers.sh
cat > start-web-servers.sh << 'EOF'
#!/bin/bash
cd /home/nullveil/code/jeeves

# Start quest web in background
python3 quest_web.py > logs/quest-web.log 2>&1 &
echo "Quest web started (PID: $!)"

# Start stats web in background
python3 stats_web.py > logs/stats-web.log 2>&1 &
echo "Stats web started (PID: $!)"

echo "Both servers running. Check logs/ directory for output."
EOF

chmod +x start-web-servers.sh
mkdir -p logs
./start-web-servers.sh
```

---

## Need Help?

- Check the nginx error log: `/var/log/nginx/error.log`
- Check service logs: `journalctl -u jeeves-quest-web -f`
- Test nginx config: `nginx -t`
- Check if ports are in use: `netstat -tlnp | grep 808`
