#!/bin/bash
# Pi5 - Проверка Coral M.2 TPU (твой гайд)
# Основано на https://github.com/Gr1n95/Raspberry-Pi5-Edge-M.2-Coral_TPU

set -e

echo "=== Pi5 Coral M.2 Check ==="
echo "Based on Gr1n95/Raspberry-Pi5-Edge-M.2-Coral_TPU"

echo "[1/6] lspci..."
lspci -nn | grep 1ac1 || echo "Coral NOT found in lspci! Check PCIe cable and config.txt"
# Ожидаем: 0000:01:00.0 System peripheral [0880]: Global Unichip Corp. Coral Edge TPU [1ac1:089a]

echo "[2/6] /dev/apex_0..."
ls -lh /dev/apex* || echo "No /dev/apex_0! Check driver gasket"

echo "[3/6] lsmod..."
lsmod | grep -E "gasket|apex" || echo "Modules not loaded, try: sudo modprobe gasket && sudo modprobe apex"

echo "[4/6] dmesg..."
dmesg | grep -i apex | tail -20

echo "[5/6] libedgetpu..."
dpkg -l | grep edgetpu || echo "libedgetpu1-std not installed, install from your repo"

echo "[6/6] Python test..."
python3 - << 'PY'
try:
    from pycoral.utils import edgetpu
    tpus = edgetpu.list_edge_tpus()
    print(f"TPUs found: {tpus}")
    if tpus:
        print("Coral OK! Device:", tpus[0])
    else:
        print("No TPU found via pycoral")
except Exception as e:
    print(f"pycoral not available or error: {e}")
    print("Try: pip install --extra-index-url https://google-coral.github.io/py-repo/ pycoral")

try:
    import tflite_runtime.interpreter as tflite
    print("tflite_runtime OK")
except Exception as e:
    print(f"tflite_runtime missing: {e}")
PY

echo ""
echo "=== Expected OK ==="
echo "lspci shows 1ac1:089a"
echo "/dev/apex_0 exists"
echo "edgetpu.list_edge_tpus() = [{'type': 'pci', 'path': '/dev/apex_0'}]"
echo ""
echo "If OK, test Frigate:"
echo "  docker run --rm --device /dev/apex_0:/dev/apex_0 ghcr.io/blakeblackshear/frigate:stable ls -lh /dev/apex_0"
