#!/bin/sh
# One-time setup on a fresh Ubuntu server. Run as root from the repository root: sh deploy/server-setup.sh
set -e
apt-get update && apt-get install -y python3 python3-venv git caddy
id hh >/dev/null 2>&1 || useradd -r -m -s /usr/sbin/nologin hh
mkdir -p /opt/hadleys-hope/data
python3 -m venv /opt/hadleys-hope/venv
/opt/hadleys-hope/venv/bin/pip install --no-cache-dir --upgrade pip numpy
[ -f /opt/hadleys-hope/env ] || echo "ADMIN_TOKEN=change-me" > /opt/hadleys-hope/env
cp hadleys_hope.py /opt/hadleys-hope/hadleys_hope.py
chown -R hh:hh /opt/hadleys-hope
cp deploy/hadleys-hope.service /etc/systemd/system/hadleys-hope.service
systemctl daemon-reload
systemctl enable hadleys-hope
cat > /etc/caddy/Caddyfile << 'CADDY'
:80 {
    reverse_proxy 127.0.0.1:8000
}
CADDY
systemctl restart caddy
echo "done. set ADMIN_TOKEN in /opt/hadleys-hope/env, then: systemctl start hadleys-hope"
