#!/bin/bash
# Customizes a Pi OS image into the Magora Node image
# Usage: sudo bash customize-image.sh <image.img>
# Run by GitHub Actions — not intended for manual use

set -e

IMAGE=$1
if [ -z "$IMAGE" ]; then
  echo "Usage: $0 <image.img>"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FIRMWARE_DIR="$SCRIPT_DIR/../firmware"
MOUNT_DIR=$(mktemp -d)

cleanup() {
  echo "Cleaning up mounts..."
  umount "$MOUNT_DIR/root/dev/pts" 2>/dev/null || true
  umount "$MOUNT_DIR/root/dev"     2>/dev/null || true
  umount "$MOUNT_DIR/root/sys"     2>/dev/null || true
  umount "$MOUNT_DIR/root/proc"    2>/dev/null || true
  umount "$MOUNT_DIR/boot" 2>/dev/null || true
  umount "$MOUNT_DIR/root" 2>/dev/null || true
  [ -n "$LOOP" ] && losetup -d "$LOOP" 2>/dev/null || true
  rm -rf "$MOUNT_DIR"
}
trap cleanup EXIT

echo "=== Magora Image Builder ==="
echo "Image: $IMAGE"

LOOP=$(losetup -f --show -P "$IMAGE")
echo "Loop device: $LOOP"

mkdir -p "$MOUNT_DIR/boot" "$MOUNT_DIR/root"
mount "${LOOP}p1" "$MOUNT_DIR/boot"
mount "${LOOP}p2" "$MOUNT_DIR/root"

# Install firstrun script
echo "Installing magora-firstrun.sh..."
cp "$FIRMWARE_DIR/magora-firstrun.sh" "$MOUNT_DIR/root/usr/local/bin/magora-firstrun.sh"
chmod +x "$MOUNT_DIR/root/usr/local/bin/magora-firstrun.sh"

# Install firstrun service
echo "Installing magora-firstrun.service..."
cp "$FIRMWARE_DIR/magora-firstrun.service" "$MOUNT_DIR/root/etc/systemd/system/magora-firstrun.service"

# Enable firstrun service
echo "Enabling magora-firstrun.service..."
mkdir -p "$MOUNT_DIR/root/etc/systemd/system/multi-user.target.wants"
ln -sf /etc/systemd/system/magora-firstrun.service \
  "$MOUNT_DIR/root/etc/systemd/system/multi-user.target.wants/magora-firstrun.service"

# Enable SSH (try both possible paths for Bookworm)
echo "Enabling SSH..."
SSH_SRC=""
for candidate in \
  "$MOUNT_DIR/root/lib/systemd/system/ssh.service" \
  "$MOUNT_DIR/root/usr/lib/systemd/system/ssh.service"; do
  [ -f "$candidate" ] && { SSH_SRC="${candidate#$MOUNT_DIR/root}"; break; }
done
if [ -n "$SSH_SRC" ]; then
  ln -sf "$SSH_SRC" \
    "$MOUNT_DIR/root/etc/systemd/system/multi-user.target.wants/ssh.service"
fi
# Belt-and-suspenders: ssh touchfile on bootfs
touch "$MOUNT_DIR/boot/ssh"

# Create debug SSH user: pi / magora123
# Lets you SSH in and run: journalctl -u birdnet -f
echo "Creating debug SSH user (pi / magora123)..."
HASH=$(openssl passwd -6 'magora123')
echo "pi:$HASH" > "$MOUNT_DIR/boot/userconf.txt"

# Enable I2S mic overlay
echo "Enabling I2S mic overlay..."
CONFIG_TXT="$MOUNT_DIR/boot/config.txt"
grep -q "adau7002-simple" "$CONFIG_TXT" 2>/dev/null || \
  printf "\ndtparam=i2s=on\ndtoverlay=adau7002-simple\n" >> "$CONFIG_TXT"

# Pre-install Python environment using chroot + QEMU
# Runs on the GitHub Actions x86_64 runner, installs ARM64 packages via QEMU emulation.
# This eliminates all runtime pip install issues on the Pi.
echo "Pre-installing Python environment (this takes a few minutes)..."
cp /usr/bin/qemu-aarch64-static "$MOUNT_DIR/root/usr/bin/"
cp /etc/resolv.conf "$MOUNT_DIR/root/etc/resolv.conf"
mount --bind /proc    "$MOUNT_DIR/root/proc"
mount --bind /sys     "$MOUNT_DIR/root/sys"
mount --bind /dev     "$MOUNT_DIR/root/dev"
mount --bind /dev/pts "$MOUNT_DIR/root/dev/pts"

chroot "$MOUNT_DIR/root" /bin/bash << 'CHROOT_EOF'
set -e
export DEBIAN_FRONTEND=noninteractive

echo "-- Updating package lists..."
apt-get update -q

echo "-- Installing python3-venv..."
apt-get install -y -q python3-venv

echo "-- Creating magora user..."
useradd -r -s /bin/bash -d /home/magora magora 2>/dev/null || true
mkdir -p /home/magora

echo "-- Creating Python venv..."
python3 -m venv /home/magora/birdnet-env

echo "-- Installing Python packages (this is the slow part)..."
/home/magora/birdnet-env/bin/pip install --prefer-binary -q \
  numpy requests astral soundfile ai-edge-litert birdnetlib

# librosa may fail in QEMU emulation (aarch64 wheels not always available).
# firstrun.sh will install it at runtime on real hardware if missing.
echo "-- Attempting librosa install (non-fatal if it fails in QEMU)..."
/home/magora/birdnet-env/bin/pip install --prefer-binary -q librosa 2>&1 || \
  echo "librosa not pre-installed — firstrun.sh will install it on the device"

echo "-- Writing tflite_runtime shim..."
PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
TFLITE="/home/magora/birdnet-env/lib/python${PYVER}/site-packages/tflite_runtime"
mkdir -p "$TFLITE"
printf '' > "$TFLITE/__init__.py"
cat > "$TFLITE/interpreter.py" << 'SHIMEOF'
from ai_edge_litert.interpreter import Interpreter
try:
    from ai_edge_litert.interpreter import load_delegate
except ImportError:
    load_delegate = None
SHIMEOF

echo "-- Setting ownership..."
chown -R magora:magora /home/magora

echo "-- Verifying birdnetlib import..."
/home/magora/birdnet-env/bin/python3 -c "import birdnetlib; print('birdnetlib OK')"
/home/magora/birdnet-env/bin/python3 -c "import librosa; print('librosa OK')" 2>/dev/null || \
  echo "librosa not in pre-baked env — firstrun.sh will install it at runtime"

echo "-- Python environment pre-installed."
CHROOT_EOF

umount "$MOUNT_DIR/root/dev/pts" 2>/dev/null || true
umount "$MOUNT_DIR/root/dev"     2>/dev/null || true
umount "$MOUNT_DIR/root/sys"     2>/dev/null || true
umount "$MOUNT_DIR/root/proc"    2>/dev/null || true
rm -f "$MOUNT_DIR/root/usr/bin/qemu-aarch64-static"

echo "=== Image customization complete ==="
