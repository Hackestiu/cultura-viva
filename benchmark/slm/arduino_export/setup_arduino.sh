#!/usr/bin/env bash
set -e
echo "CulturaViva: setting up Arduino UNO Q (Debian ARM64)"
sudo apt update
sudo apt install -y build-essential python3 python3-pip python3-venv git cpufrequtils

sudo cpufreq-set -g performance || true

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

echo "Compiling llama-cpp-python for Cortex-A53 (-march=armv8-a -mtune=cortex-a53)..."
CMAKE_ARGS="-DCMAKE_C_FLAGS='-march=armv8-a -mtune=cortex-a53'" pip install llama-cpp-python

echo "Setup complete. Run with: ./venv/bin/python run_guide.py --model models/<file>.gguf"
