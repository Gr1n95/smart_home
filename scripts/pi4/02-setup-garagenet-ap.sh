#!/bin/bash
# Pi4 - Настройка WiFi точки GarageNet (офлайн)
# Делает из Pi4 роутер без интернета: 192.168.4.1/24
# Телефон подключается и открывает HA

set -e

echo "=== Pi4 GarageNet AP Setup ==="

if [ "$EUID" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0"
  exit 1
fi

echo "[1/5] Installing hostapd dnsmasq..."
apt update
apt install -y hostapd dnsmasq

systemctl stop hostapd dnsmasq || true

echo "[2/5] Configuring dhcpcd..."
cat >> /etc/dhcpcd.conf <<'EOF'

# GarageNet AP
interface wlan0
static ip_address=192.168.4.1/24
nohook wpa_supplicant

interface eth0
static ip_address=10.0.0.1/24
EOF

echo "[3/5] Configuring dnsmasq..."
mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig 2>/dev/null || true
cat > /etc/dnsmasq.conf <<'EOF'
interface=wlan0
dhcp-range=192.168.4.10,192.168.4.100,255.255.255.0,24h
domain=garage.local
address=/garage.local/192.168.4.1
EOF

echo "[4/5] Configuring hostapd..."
cat > /etc/hostapd/hostapd.conf <<'EOF'
interface=wlan0
driver=nl80211
ssid=GarageNet
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=Garage2026Secure!
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' > /etc/default/hostapd

# Enable IP forwarding
echo "[5/5] Enable forwarding..."
sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf
sysctl -w net.ipv4.ip_forward=1

# iptables - NAT не нужен (нет инета), но форвардинг между eth0 и wlan0 нужен
iptables -A FORWARD -i eth0 -o wlan0 -j ACCEPT
iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT
# Сохранить
apt install -y iptables-persistent || netfilter-persistent save || true

systemctl unmask hostapd
systemctl enable hostapd
systemctl enable dnsmasq

echo ""
echo "=== GarageNet Ready ==="
echo "Reboot Pi4: sudo reboot"
echo "After reboot:"
echo "  WiFi: GarageNet / Garage2026Secure!"
echo "  Pi4 AP IP: 192.168.4.1"
echo "  Pi4 eth0 to Pi5: 10.0.0.1"
echo "  HA: http://192.168.4.1:8123"
echo "  MQTT: 192.168.4.1:1883 and 10.0.0.1:1883"
echo ""
echo "Pi5 should connect to GarageNet or via eth cable 10.0.0.2"
