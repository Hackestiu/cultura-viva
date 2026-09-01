#!/usr/bin/env bash
# ==============================================================================
# Setup & compilation script for whisper.cpp with ARM NEON on Arduino UNO Q
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS_DIR="${SCRIPT_DIR}/models"
WHISPER_CPP_DIR="${MODELS_DIR}/whisper.cpp"
MODEL_VARIANT="${1:-base.en-q5_0}"

echo "=========================================================="
echo " Setting up whisper.cpp (ARM NEON optimized for UNO Q)"
echo " Target Model: ggml-${MODEL_VARIANT}.bin"
echo "=========================================================="

mkdir -p "${MODELS_DIR}"

# 1. Shallow clone whisper.cpp to save disk space
if [ ! -d "${WHISPER_CPP_DIR}/.git" ]; then
    echo "[1/4] Cloning whisper.cpp repository (shallow depth=1)..."
    git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git "${WHISPER_CPP_DIR}"
else
    echo "[1/4] whisper.cpp repository already exists."
fi

cd "${WHISPER_CPP_DIR}"

# 2. Compile with CMake & ARM NEON vector flags
echo "[2/4] Compiling whisper-cli with ARM NEON optimizations..."
cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_NATIVE=ON \
    -DWHISPER_BUILD_TESTS=OFF \
    -DWHISPER_BUILD_EXAMPLES=OFF

cmake --build build --config Release -j4 --target whisper-cli

# Strip binary symbols to reduce binary size to ~2.5 MB
if command -v strip &>/dev/null; then
    strip build/bin/whisper-cli || true
fi

# 3. Clean up intermediate build artifacts to save disk space on Uno Q
echo "[3/4] Cleaning temporary build files..."
rm -rf build/CMakeFiles build/ggml/src/CMakeFiles

# 4. Download GGML Quantized Model
MODEL_FILE="${MODELS_DIR}/ggml-${MODEL_VARIANT}.bin"
if [ ! -f "${MODEL_FILE}" ]; then
    echo "[4/4] Downloading GGML model ggml-${MODEL_VARIANT}.bin..."
    HF_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-${MODEL_VARIANT}.bin"
    if command -v curl &>/dev/null; then
        curl -L -f -o "${MODEL_FILE}" "${HF_URL}"
    elif command -v wget &>/dev/null; then
        wget -O "${MODEL_FILE}" "${HF_URL}"
    else
        echo "[ERROR] Neither curl nor wget found. Please download ${HF_URL} manually to ${MODEL_FILE}."
        exit 1
    fi
    echo "Downloaded ${MODEL_FILE} ($(du -h "${MODEL_FILE}" | cut -f1))"
else
    echo "[4/4] Model file already present: ${MODEL_FILE}"
fi

echo "=========================================================="
echo " Setup complete! Binary is at: ${WHISPER_CPP_DIR}/build/bin/whisper-cli"
echo " Model is at: ${MODEL_FILE}"
echo "=========================================================="

