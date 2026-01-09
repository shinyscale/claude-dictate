#!/bin/bash
# Setup script for Claude Dictate
# Installs whisper.cpp and downloads models

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           Claude Dictate - Setup Script                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
    OS="windows"
fi

echo "Detected OS: $OS"
echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Check if whisper.cpp is already installed
if command -v whisper &> /dev/null; then
    echo "✅ whisper.cpp already installed"
    WHISPER_PATH=$(which whisper)
else
    echo ""
    echo "🔧 Installing whisper.cpp..."
    
    # Create directory
    WHISPER_DIR="$HOME/whisper.cpp"
    
    if [ ! -d "$WHISPER_DIR" ]; then
        git clone https://github.com/ggerganov/whisper.cpp.git "$WHISPER_DIR"
    fi
    
    cd "$WHISPER_DIR"
    
    # Build based on OS
    if [[ "$OS" == "macos" ]]; then
        # Check for Metal support
        if system_profiler SPDisplaysDataType | grep -q "Metal"; then
            echo "Building with Metal acceleration..."
            make clean
            WHISPER_METAL=1 make -j
        else
            make clean
            make -j
        fi
    elif [[ "$OS" == "linux" ]]; then
        # Check for CUDA
        if command -v nvcc &> /dev/null; then
            echo "Building with CUDA acceleration..."
            make clean
            WHISPER_CUDA=1 make -j
        else
            make clean
            make -j
        fi
    else
        make clean
        make -j
    fi
    
    WHISPER_PATH="$WHISPER_DIR/main"
fi

echo ""
echo "📥 Downloading Whisper models..."

# Download models
MODELS_DIR="$HOME/.cache/whisper"
mkdir -p "$MODELS_DIR"

# Download base.en model (default)
if [ ! -f "$MODELS_DIR/ggml-base.en.bin" ]; then
    echo "Downloading base.en model..."
    if [ -f "$HOME/whisper.cpp/models/download-ggml-model.sh" ]; then
        cd "$HOME/whisper.cpp/models"
        ./download-ggml-model.sh base.en
        cp ggml-base.en.bin "$MODELS_DIR/"
    else
        curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin" -o "$MODELS_DIR/ggml-base.en.bin"
    fi
fi

# Optionally download small.en for better accuracy
read -p "Download small.en model for better accuracy? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ ! -f "$MODELS_DIR/ggml-small.en.bin" ]; then
        echo "Downloading small.en model..."
        if [ -f "$HOME/whisper.cpp/models/download-ggml-model.sh" ]; then
            cd "$HOME/whisper.cpp/models"
            ./download-ggml-model.sh small.en
            cp ggml-small.en.bin "$MODELS_DIR/"
        else
            curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin" -o "$MODELS_DIR/ggml-small.en.bin"
        fi
    fi
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete!                           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Whisper path: $WHISPER_PATH"
echo "Models directory: $MODELS_DIR"
echo ""
echo "To run Claude Dictate:"
echo "  python claude_dictate.py --gui"
echo ""
echo "Or with CLI mode:"
echo "  python claude_dictate.py --record"
echo ""

# Create config file with detected paths
cat > config.json << EOF
{
    "whisper_cpp_path": "$WHISPER_PATH",
    "whisper_model": "base.en",
    "sample_rate": 16000,
    "channels": 1,
    "chunk_size": 1024,
    "hotkey": "ctrl+shift",
    "ollama_url": "http://localhost:11434",
    "lm_studio_url": "http://localhost:1234/v1",
    "default_llm": "ollama",
    "default_model": "llama3.2",
    "output_dir": "./outputs"
}
EOF

echo "Config saved to config.json"
