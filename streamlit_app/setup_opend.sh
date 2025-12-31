#!/bin/bash
# OpenD Setup Helper Script for macOS

echo "🔧 Moomoo OpenD Setup Helper"
echo "================================"
echo ""

# Step 1: Check if OpenD exists
echo "📁 Step 1: Checking for OpenD installation..."
OPEND_DIR="$HOME/OpenD"

if [ ! -d "$OPEND_DIR" ]; then
    echo "❌ OpenD directory not found at $OPEND_DIR"
    echo ""
    echo "Please download OpenD first:"
    echo "1. Visit: https://www.moomoo.com/download/OpenAPI"
    echo "2. Download macOS version (e.g., opend_mac_v9.6.XXXX.tar)"
    echo "3. Extract to $HOME/OpenD"
    echo ""
    echo "Then run this script again."
    exit 1
else
    echo "✅ Found OpenD at $OPEND_DIR"
fi

# Step 2: Generate MD5 password
echo ""
echo "🔐 Step 2: Generate MD5 password"
echo "================================"
echo -n "Enter your Moomoo password: "
read -s PASSWORD
echo ""

MD5_HASH=$(python3 -c "import hashlib; print(hashlib.md5(b'$PASSWORD').hexdigest())")
echo "✅ MD5 Hash generated: $MD5_HASH"

# Step 3: Get email
echo ""
echo "📧 Step 3: Account information"
echo -n "Enter your Moomoo email/account ID: "
read ACCOUNT
echo "✅ Account: $ACCOUNT"

# Step 4: Create OpenD.xml
echo ""
echo "📝 Step 4: Creating OpenD.xml configuration..."
CONFIG_FILE="$OPEND_DIR/OpenD.xml"

cat > "$CONFIG_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<config>
    <ip>127.0.0.1</ip>
    <api_port>11111</api_port>
    <login_account>$ACCOUNT</login_account>
    <login_pwd>$MD5_HASH</login_pwd>
    <lang>en</lang>
    <log_level>info</log_level>
</config>
EOF

echo "✅ Configuration saved to $CONFIG_FILE"

# Step 5: Fix macOS security issues
echo ""
echo "🔓 Step 5: Removing macOS quarantine..."
cd "$OPEND_DIR"
xattr -d com.apple.quarantine OpenD.app 2>/dev/null || true
if [ -f "fixrun.sh" ]; then
    chmod +x fixrun.sh
    ./fixrun.sh 2>/dev/null || true
fi
echo "✅ Security attributes cleared"

# Step 6: Create startup script
echo ""
echo "🚀 Step 6: Creating startup script..."
STARTUP_SCRIPT="$OPEND_DIR/start_opend.sh"

cat > "$STARTUP_SCRIPT" << 'SCRIPT'
#!/bin/bash
OPEND_DIR="$HOME/OpenD"
cd "$OPEND_DIR"

echo "Starting OpenD..."
echo "Press Ctrl+C to stop"
echo ""

./OpenD.app/Contents/MacOS/OpenD \
  -cfg_file="$OPEND_DIR/OpenD.xml" \
  -console

SCRIPT

chmod +x "$STARTUP_SCRIPT"
echo "✅ Startup script created: $STARTUP_SCRIPT"

# Summary
echo ""
echo "================================"
echo "✅ SETUP COMPLETE!"
echo "================================"
echo ""
echo "📋 Configuration Summary:"
echo "   OpenD Location: $OPEND_DIR"
echo "   Config File: $CONFIG_FILE"
echo "   API Port: 11111"
echo "   Account: $ACCOUNT"
echo ""
echo "🚀 Next Steps:"
echo ""
echo "1. Start OpenD:"
echo "   cd $OPEND_DIR && ./start_opend.sh"
echo ""
echo "2. Or run directly:"
echo "   cd $OPEND_DIR"
echo "   ./OpenD.app/Contents/MacOS/OpenD -console"
echo ""
echo "3. Watch for login success in console output"
echo ""
echo "4. In another terminal, verify connection:"
echo "   lsof -i:11111"
echo ""
echo "5. Then run your Python scripts:"
echo "   cd /Users/$(whoami)/Documents/stock-trading/streamlit_app"
echo "   python3 moomoo_fetcher.py"
echo ""
echo "📖 View full setup guide: MOOMOO_SETUP.md"
echo ""
