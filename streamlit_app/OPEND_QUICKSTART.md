# 🚀 Quick Start: Running OpenD on macOS

## Step-by-Step Instructions

### 1️⃣ Download OpenD

1. Go to: **https://www.moomoo.com/download/OpenAPI**
2. Click "Download" under **OpenAPI**
3. Choose: **Visualization OpenD** (GUI version - easier!)
4. Download the **macOS** version (file like `opend_mac_v9.6.XXXX.tar`)

### 2️⃣ Extract OpenD

```bash
# Create directory
mkdir -p ~/OpenD

# Extract the downloaded file (replace with actual filename)
cd ~/Downloads
tar -xvf opend_mac_v9.6.XXXX.tar -C ~/OpenD

# Verify extraction
ls ~/OpenD
# Should see: OpenD.app, OpenD.xml, Appdata.dat, etc.
```

### 3️⃣ Run Setup Script (Automated)

```bash
cd /Users/shaurya/Documents/stock-trading/streamlit_app
./setup_opend.sh
```

**The script will:**
- ✅ Check if OpenD is installed
- ✅ Generate MD5 password hash
- ✅ Create OpenD.xml configuration
- ✅ Fix macOS security issues
- ✅ Create startup script

### 4️⃣ Start OpenD

**Option A: Use startup script**
```bash
cd ~/OpenD
./start_opend.sh
```

**Option B: Run directly**
```bash
cd ~/OpenD
./OpenD.app/Contents/MacOS/OpenD -console
```

**Option C: Use GUI version**
```bash
open ~/OpenD/OpenD.app
# Log in via the GUI window
```

### 5️⃣ Verify OpenD is Running

**In another terminal:**

```bash
# Check if OpenD process is running
ps aux | grep OpenD

# Check if port 11111 is listening
lsof -i:11111

# Test connection
telnet 127.0.0.1 11111
# Press Ctrl+] then type 'quit' to exit
```

**Expected output from OpenD console:**
```
login success
listening on port 11111
```

### 6️⃣ Test Python Connection

```bash
cd /Users/shaurya/Documents/stock-trading/streamlit_app
python3 moomoo_fetcher.py
```

---

## 📋 Manual Setup (if script fails)

### Generate MD5 Password:
```bash
python3 << EOF
import hashlib
password = input("Enter your Moomoo password: ")
print("\nMD5 Hash:", hashlib.md5(password.encode()).hexdigest())
EOF
```

### Create OpenD.xml manually:
```bash
cat > ~/OpenD/OpenD.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<config>
    <ip>127.0.0.1</ip>
    <api_port>11111</api_port>
    <login_account>your_email@example.com</login_account>
    <login_pwd>YOUR_MD5_HASH_HERE</login_pwd>
    <lang>en</lang>
    <log_level>info</log_level>
</config>
EOF
```

### Fix macOS Security:
```bash
cd ~/OpenD
xattr -d com.apple.quarantine OpenD.app
chmod +x fixrun.sh
./fixrun.sh
```

---

## ⚠️ Common Issues & Solutions

### Issue: "Cannot open OpenD because it is from an unidentified developer"
**Solution:**
```bash
xattr -d com.apple.quarantine ~/OpenD/OpenD.app
```
Or: System Preferences → Security & Privacy → Click "Open Anyway"

### Issue: "Login failed" or "Invalid password"
**Solution:**
- Regenerate MD5 hash (password must be exact!)
- Check OpenD.xml has correct email
- Try logging in via GUI version first

### Issue: "Port 11111 already in use"
**Solution:**
```bash
# Find what's using the port
lsof -i:11111

# Kill old OpenD process
pkill -f OpenD

# Or change port in OpenD.xml to 11112
```

### Issue: "Connection refused" from Python
**Solution:**
- Make sure OpenD is running: `ps aux | grep OpenD`
- Check logs: `tail -f ~/.com.moomoo.OpenD/Log/opend.log`
- Verify port: `lsof -i:11111`

### Issue: 2FA/Two-factor authentication required
**Solution:**
- OpenD console will prompt for code
- Enter your 2FA code when asked
- Or use GUI version for easier 2FA input

---

## 📊 What's Next After OpenD is Running?

1. **Test basic connection:**
   ```bash
   python3 moomoo_fetcher.py
   ```

2. **Start real-time monitoring:**
   ```bash
   python3 moomoo_realtime_monitor.py
   ```

3. **Integrate with your system:**
   - Combine Moomoo data with news alerts
   - Build multi-source dashboard
   - Set up automated scanning

---

## 🔧 Useful Commands

**Start OpenD in background:**
```bash
cd ~/OpenD
nohup ./OpenD.app/Contents/MacOS/OpenD -console > opend.log 2>&1 &
```

**Stop OpenD:**
```bash
pkill -f OpenD
```

**View logs:**
```bash
tail -f ~/.com.moomoo.OpenD/Log/opend.log
```

**Check OpenD status:**
```bash
ps aux | grep OpenD | grep -v grep
```

---

## 📞 Need Help?

1. Check logs: `~/.com.moomoo.OpenD/Log/opend.log`
2. Official docs: https://openapi.moomoo.com/moomoo-api-doc/en/
3. Share error messages for troubleshooting

**Ready to start? Run:**
```bash
cd /Users/shaurya/Documents/stock-trading/streamlit_app
./setup_opend.sh
```
