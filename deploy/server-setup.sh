#!/bin/sh
# One-time setup on a fresh Ubuntu/Debian VPS. Run as root: sh server-setup.sh
set -e
apt-get update && apt-get install -y python3 python3-venv caddy
id hh >/dev/null 2>&1 || useradd -r -m -s /usr/sbin/nologin hh
mkdir -p /opt/hadleys-hope/data
python3 -m venv /opt/hadleys-hope/venv
/opt/hadleys-hope/venv/bin/pip install --no-cache-dir numpy
echo "ADMIN_TOKEN=change-me" > /opt/hadleys-hope/env
chown -R hh:hh /opt/hadleys-hope
cp hadleys-hope.service /etc/systemd/system/hadleys-hope.service
systemctl daemon-reload
systemctl enable hadleys-hope
# Caddy gives https automatically once a domain points at this server. Replace example.com or use :80 for plain http.
cat > /etc/caddy/Caddyfile << 'CADDY'
:80 {
    reverse_proxy 127.0.0.1:8000
}
CADDY
systemctl restart caddy
echo "done. copy hadleys_hope.py to /opt/hadleys-hope/ and run: systemctl start hadleys-hope"
