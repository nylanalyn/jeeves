# Jeeves Web UI

## Overview

The Jeeves web UI provides a web-based interface for viewing quest leaderboards, player statistics, and command references. The UI has been reorganized into a modular structure for better maintainability and extensibility.

## 📁 Directory Structure

```
web/
├── quest/                      # Quest-specific web components
│   ├── __init__.py            # Package initialization
│   ├── app.py                 # Main application entry point
│   ├── server.py              # HTTP server setup and configuration
│   ├── handlers.py            # HTTP request handlers
│   ├── templates.py           # HTML template generation
│   ├── themes.py              # Theme management and styling
│   └── utils.py               # Utility functions
├── static/                    # Static assets (CSS, JS, images)
│   ├── css/
│   ├── js/
│   └── images/
└── README.md                  # This documentation
```

## 🚀 Quick Start

### **Basic Usage**

```bash
# Start with default settings (127.0.0.1:8080)
python3 quest_web.py

# Start on all interfaces
python3 quest_web.py --host 0.0.0.0 --port 8080

# With custom paths
python3 quest_web.py --games /path/to/games.json --content /path/to/content
```

### **Programmatic Usage**

```python
from web.quest import QuestWebServer

# Create server instance
server = QuestWebServer(
    host="127.0.0.1",
    port=8080,
    games_path="config/games.json",
    content_path="."
)

# Start server
server.start()
```

## 🏗️ Architecture

### **Component Breakdown**

#### **`app.py`** - Main Application
- Entry point for the web UI
- Provides backward compatibility
- Exports main functions for external use

#### **`server.py`** - HTTP Server
- Server setup and configuration
- Command-line argument parsing
- Graceful shutdown handling
- Signal management

#### **`handlers.py`** - Request Handlers
- HTTP request routing and processing
- API endpoints for data retrieval
- Error handling and response formatting
- State management integration

#### **`templates.py`** - HTML Templates
- HTML template generation
- Dynamic content rendering
- Responsive design implementation
- Component-based template system

#### **`themes.py`** - Theme Management
- Theme loading and configuration
- CSS variable generation
- Prestige tier styling
- Visual customization

#### **`utils.py`** - Utility Functions
- Data loading and validation
- Text sanitization and formatting
- Helper functions for templates
- Common utilities

## 🎨 Features

### **Responsive Design**
- Mobile-friendly layout
- Adaptive grid system
- Touch-friendly navigation
- Optimized for all screen sizes

### **Interactive Elements**
- Real-time data display
- Search functionality
- Dynamic sorting and filtering
- API endpoints for data retrieval

### **Theme System**
- CSS variable-based theming
- Prestige tier visual indicators
- Customizable color schemes
- Responsive typography

### **Data Integration**
- Live quest data from games.json
- Challenge path information
- Player class tracking
- Automatic data reloading

## 🔧 Configuration

### **Default Paths**
- Games data: `config/games.json`
- Content directory: Current directory
- Challenge paths: `challenge_paths.json`

### **Command Line Options**
```bash
python3 quest_web.py --help
```

Available options:
- `--host`: Server host (default: 127.0.0.1)
- `--port`: Server port (default: 8080)
- `--games`: Path to games.json file
- `--content`: Path to content directory
- `--debug`: Enable debug logging

### **Environment Variables**
The web UI respects the same environment variables as the main bot:
- `${GAMES_PATH}` - Override games file path
- `${CONTENT_PATH}` - Override content directory

## 🌐 Endpoints

### **Web Pages**
- `/` - Main leaderboard page
- `/commands` - Command reference page

### **API Endpoints**
- `/api/status` - Server status and statistics
- `/api/reload` - Reload quest data (POST)

### **Features**
- **Search**: Search players by username
- **Filtering**: Filter by search terms
- **Statistics**: Real-time player statistics
- **Responsive**: Mobile-friendly design
- **Auto-reload**: Data can be reloaded via API

## 🎯 Theme Customization

### **Default Theme**
- **Name**: midnight-spire
- **Colors**: Dark theme with orange accents
- **Typography**: System fonts with good readability
- **Layout**: Card-based, responsive design

### **Custom Themes**
Create a `theme.json` file in your content directory:

```json
{
    "name": "custom-theme",
    "background": "#1a1a1a",
    "foreground": "#ffffff",
    "accent": "#00ff00",
    "card_background": "#2a2a2a",
    "card_border": "#00ff00",
    "prestige_tiers": [
        {
            "max": 3,
            "icon": "★",
            "class": "tier-star",
            "color": "#ffd700",
            "repeat": 3
        }
    ]
}
```

### **CSS Variables**
All theme values are available as CSS variables:
```css
.your-element {
    background: var(--background);
    color: var(--foreground);
    border-color: var(--card_border);
}
```

## 🔗 Integration

### **With Main Bot**
The web UI automatically reads from the same data files as the main bot:
- Quest player data from `games.json`
- Challenge paths from `challenge_paths.json`
- Content from the bot's content directory

### **API Integration**
Use the API endpoints for external integrations:
```javascript
// Fetch server status
fetch('/api/status')
    .then(response => response.json())
    .then(data => console.log(data));

// Reload data
fetch('/api/reload', { method: 'POST' })
    .then(response => response.json())
    .then(data => console.log(data));
```

## 🛠️ Development

### **Running in Development**
```bash
# Enable debug logging
python3 quest_web.py --debug

# Run on all interfaces for mobile testing
python3 quest_web.py --host 0.0.0.0

# Use custom paths for testing
python3 quest_web.py --games test_games.json --content test_content/
```

### **File Watching**
For development, you can use tools like `watchdog` to auto-reload:
```bash
pip install watchdog
watchdog --patterns="*.json" --command="curl -X POST http://localhost:8080/api/reload" .
```

### **Custom Components**
To extend the web UI:

1. **Add New Pages**: Create new template methods in `templates.py`
2. **Add New Endpoints**: Add handlers in `handlers.py`
3. **Custom Themes**: Create theme variations
4. **Static Assets**: Add CSS/JS to `static/` directory

## 📊 Monitoring

### **Log Files**
Enable debug logging to see detailed information:
```bash
python3 quest_web.py --debug
```

### **Health Checks**
Use the status endpoint for health monitoring:
```bash
curl http://localhost:8080/api/status
```

### **Performance**
- Templates are cached in memory
- Data is loaded on startup and reloaded on demand
- Static responses are optimized for speed

## 🔒 Security

### **Access Control**
- Default bind to localhost (127.0.0.1)
- No sensitive data stored in web UI
- Read-only access to game data

### **Data Sanitization**
- All user input is sanitized before display
- HTML encoding prevents XSS attacks
- Input validation for search terms

### **Network Security**
- No database connections
- No external API calls from web UI
- All data comes from local files

## 🔄 Backward Compatibility

The new structure maintains full backward compatibility:

### **Old Usage (Still Works)**
```bash
python3 quest_web.py --host 127.0.0.1 --port 8080
```

### **New Usage (Recommended)**
```bash
python3 -m web.quest --host 127.0.0.1 --port 8080
```

### **Programmatic Usage**
```python
# Old way (still works)
import quest_web
quest_web.main()

# New way (recommended)
from web.quest import main
main()
```

## 🐛 Troubleshooting

### **Server Won't Start**
1. Check if port is already in use
2. Verify games.json exists and is valid JSON
3. Ensure content directory exists
4. Check file permissions

### **Data Not Loading**
1. Verify games.json contains quest data
2. Check that the bot has been run to generate data
3. Use the `/api/status` endpoint to check data

### **Styling Issues**
1. Clear browser cache
2. Check browser console for errors
3. Verify theme.json format if using custom themes

### **Import Errors**
1. Ensure all required files are present
2. Check Python path includes the jeeves directory
3. Verify all dependencies are installed

## 📚 Related Documentation

- **Configuration Validation Guide**: `CONFIG_VALIDATION_GUIDE.md`
- **Quest Module Guide**: Documentation in the quest module
- **Bot Configuration**: `config.yaml.default`

## 🆘 Migration Guide

### **From Old Structure**
No changes needed - full backward compatibility is maintained.

### **Custom Themes**
If you have custom themes, place them in your content directory:
```bash
# Old: theme.json in root
# New: theme.json in content directory
```

### **Custom Scripts**
Update import paths:
```python
# Old
import quest_web

# New (recommended)
from web.quest import QuestWebServer
```

## 📄 File History

- `quest_web.py` → `quest_web_original.py` (backup)
- New modular structure in `web/quest/`
- Enhanced features and better organization
- Full backward compatibility maintained