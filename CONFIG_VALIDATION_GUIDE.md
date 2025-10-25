# Configuration Validation Guide

## Overview

Jeeves now includes a comprehensive configuration validation system that prevents runtime failures and provides enhanced security through environment variable support.

## 🔧 New Features

### **Configuration Validation**
- **Automatic validation** on bot startup and config reload
- **Detailed error reporting** with specific fixes
- **Type checking** for all configuration values
- **Range validation** for numeric values
- **Format validation** for regex patterns and API keys

### **Environment Variable Support**
- **Secure credential storage** using environment variables
- **Fallback to defaults** when variables aren't set
- **Mixed configuration** (static values + environment variables)
- **Placeholder detection** with helpful warnings

## 🚀 Quick Start

### 1. Basic Usage

Your existing `config.yaml` will work with the new validation system:

```bash
# Start the bot - configuration is automatically validated
python3 jeeves.py
```

### 2. Using Environment Variables

Replace sensitive values with environment variable references:

```yaml
# Before (insecure)
api_keys:
  openai_api_key: "sk-your-secret-key-here"
  deepl_api_key: "your-deepl-key-here"

connection:
  nickserv_pass: "your-nickserv-password"
```

```yaml
# After (secure)
api_keys:
  openai_api_key: "${OPENAI_API_KEY}"
  deepl_api_key: "${DEEPL_API_KEY}"

connection:
  nickserv_pass: "${NICKSERV_PASSWORD}"
```

### 3. Setting Environment Variables

#### Linux/macOS (Bash)
```bash
export OPENAI_API_KEY="sk-your-secret-key-here"
export DEEPL_API_KEY="your-deepl-key-here"
export NICKSERV_PASSWORD="your-nickserv-password"
python3 jeeves.py
```

#### Windows (PowerShell)
```powershell
$env:OPENAI_API_KEY="sk-your-secret-key-here"
$env:DEEPL_API_KEY="your-deepl-key-here"
$env:NICKSERV_PASSWORD="your-nickserv-password"
python3 jeeves.py
```

#### Docker (.env file)
```bash
# .env file
OPENAI_API_KEY=sk-your-secret-key-here
DEEPL_API_KEY=your-deepl-key-here
NICKSERV_PASSWORD=your-nickserv-password

# docker-compose.yml
environment:
  - OPENAI_API_KEY=${OPENAI_API_KEY}
  - DEEPL_API_KEY=${DEEPL_API_KEY}
  - NICKSERV_PASSWORD=${NICKSERV_PASSWORD}
```

## 🔍 Configuration Validation

### **Running Validation Manually**

```bash
# Validate your configuration
python3 config_validator.py

# Validate a specific config file
python3 config_validator.py config/config.yaml

# Enable verbose output
python3 config_validator.py -v
```

### **Validation Levels**

#### 🔴 **Errors** (Critical)
- Prevent bot startup
- Must be fixed before running
- Examples: Missing required fields, invalid types, out-of-range values

#### 🟡 **Warnings** (Recommended)
- Don't prevent startup
- Should be fixed for optimal operation
- Examples: Empty admin lists, placeholder values, format issues

#### 🔵 **Info** (Informational)
- Provide helpful suggestions
- Don't affect operation
- Examples: Environment variable not set (with fallback)

### **Common Validation Issues**

#### Core Configuration
```yaml
# ❌ Error: No administrators
core:
  admins: []

# ✅ Fixed: Add at least one admin
core:
  admins:
    - "YourAdminNick"
```

#### Connection Issues
```yaml
# ❌ Error: Invalid port
connection:
  port: "not_a_number"

# ✅ Fixed: Use integer
connection:
  port: 6697
```

#### API Key Issues
```yaml
# ❌ Warning: Placeholder detected
api_keys:
  youtube: "YourYouTubeDataAPIKey"

# ✅ Fixed: Use environment variable
api_keys:
  youtube: "${YOUTUBE_API_KEY}"
```

## 📝 Environment Variable Syntax

### **Basic Substitution**
```yaml
# Simple variable
api_key: "${API_KEY}"

# With default fallback
timeout: "${TIMEOUT:-30}"
```

### **Advanced Usage**
```yaml
# Multiple variables in one value
database_url: "postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

# Mixed static and dynamic
server: "${SERVER_HOST:-irc.libera.chat}"
port: ${SERVER_PORT:-6697}
```

### **Supported Variable Formats**
- `${VARIABLE_NAME}` - Preferred format
- `$VARIABLE_NAME` - Simple format
- `${VARIABLE_NAME:-default}` - With default value

## 🔧 Configuration Reference

### **Core Settings Validation**
```yaml
core:
  admins:                    # Required: List of admin nicknames
    - "AdminNick"
  module_blacklist:          # Optional: List of modules to blacklist
    - "example_module.py"
  name_pattern: "(?:jeeves|jeevesbot)"  # Required: Valid regex
  debug_mode_on_startup: false             # Required: boolean
  debug_log_file: "debug.log"              # Required: non-empty string
```

### **Connection Validation**
```yaml
connection:
  server: "irc.libera.chat"    # Required: non-empty string
  port: 6697                    # Required: 1-65535
  nick: "JeevesBot"             # Required: 1-30 chars, valid IRC nick
  channel: "#your-channel"      # Required: starts with #
  nickserv_pass: ""             # Optional: string (can be empty)
```

### **API Keys Validation**
```yaml
api_keys:
  giphy: "32-char-alphanumeric"           # Optional: valid format
  youtube: "AIza followed by 35 chars"     # Optional: valid format
  openai_api_key: "sk- followed by 48 chars" # Optional: valid format
  deepl_api_key: "36-char-alphanumeric"    # Optional: valid format
  # Any value will work but warnings for placeholders
```

### **Module Configuration Validation**
```yaml
module_name:
  cooldown_seconds: 300        # Numeric: 0-86400
  response_rate: 0.15          # Numeric: 0.0-1.0
  allowed_channels:            # List of channel names
    - "#channel1"
    - "#channel2"
```

## 🛠️ Troubleshooting

### **Bot Won't Start**
1. Run validation manually: `python3 config_validator.py`
2. Fix all ERROR level issues
3. Check that required fields are present

### **Environment Variables Not Working**
1. Verify variable is set: `echo $VARIABLE_NAME`
2. Check syntax in config file: `${VARIABLE_NAME}`
3. Run validator with verbose mode: `python3 config_validator.py -v`

### **API Key Issues**
1. Replace placeholder values with real keys
2. Use environment variables for sensitive keys
3. Check API key format requirements

### **Module Configuration Issues**
1. Check numeric value ranges
2. Verify channel names start with #
3. Ensure lists are properly formatted

## 📁 Files

- `config_validator.py` - Main validation module
- `config_with_env_vars.yaml.example` - Example with environment variables
- `CONFIG_VALIDATION_GUIDE.md` - This documentation

## 🎯 Best Practices

### **Security**
- ✅ Use environment variables for all API keys and passwords
- ✅ Never commit sensitive data to version control
- ✅ Use different API keys for development/production

### **Configuration Management**
- ✅ Validate configuration before deployment
- ✅ Use version control for config files (without secrets)
- ✅ Document custom configuration values

### **Environment Setup**
- ✅ Use `.env` files for local development
- ✅ Set environment variables in production
- ✅ Provide fallback values where appropriate

### **Monitoring**
- ✅ Check validation output on startup
- ✅ Monitor for configuration warnings
- ✅ Test configuration reloads

## 🔄 Migration Guide

### **From Static Configuration**
1. Identify sensitive values (API keys, passwords)
2. Create environment variables for these values
3. Update config.yaml to use `${VARIABLE_NAME}` syntax
4. Set environment variables in your environment
5. Test with: `python3 config_validator.py`

### **Example Migration**
```yaml
# Before
api_keys:
  openai_api_key: "sk-secret-key-here"
  deepl_api_key: "secret-key-here"

connection:
  nickserv_pass: "password123"
```

```yaml
# After
api_keys:
  openai_api_key: "${OPENAI_API_KEY}"
  deepl_api_key: "${DEEPL_API_KEY}"

connection:
  nickserv_pass: "${NICKSERV_PASSWORD}"
```

```bash
# Set environment variables
export OPENAI_API_KEY="sk-secret-key-here"
export DEEPL_API_KEY="secret-key-here"
export NICKSERV_PASSWORD="password123"
```

## 🆘 Getting Help

If you encounter issues with configuration validation:

1. **Run the validator**: `python3 config_validator.py -v`
2. **Check this guide** for common solutions
3. **Examine error messages** for specific fixes
4. **Test with minimal config** to isolate issues

The validation system is designed to prevent runtime failures and provide clear guidance for fixing configuration issues.