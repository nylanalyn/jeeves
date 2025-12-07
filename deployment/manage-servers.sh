#!/bin/bash
# Helper script to manage both Jeeves web servers

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_DIR/logs"

# Create logs directory if it doesn't exist
mkdir -p "$LOGS_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

function print_status() {
    echo -e "${BLUE}==>${NC} $1"
}

function print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

function print_error() {
    echo -e "${RED}✗${NC} $1"
}

function print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

function start_servers() {
    print_status "Starting Jeeves web servers..."

    cd "$PROJECT_DIR"

    # Check if already running
    if pgrep -f "quest_web.py" > /dev/null; then
        print_warning "Quest web server is already running"
    else
        python3 quest_web.py > "$LOGS_DIR/quest-web.log" 2>&1 &
        QUEST_PID=$!
        print_success "Quest web server started (PID: $QUEST_PID) on http://localhost:8080"
    fi

    if pgrep -f "stats_web.py" > /dev/null; then
        print_warning "Stats web server is already running"
    else
        python3 stats_web.py > "$LOGS_DIR/stats-web.log" 2>&1 &
        STATS_PID=$!
        print_success "Stats web server started (PID: $STATS_PID) on http://localhost:8081"
    fi

    echo ""
    print_status "Logs location:"
    echo "  Quest: $LOGS_DIR/quest-web.log"
    echo "  Stats: $LOGS_DIR/stats-web.log"
}

function stop_servers() {
    print_status "Stopping Jeeves web servers..."

    # Stop quest web
    if pgrep -f "quest_web.py" > /dev/null; then
        pkill -f "quest_web.py"
        print_success "Quest web server stopped"
    else
        print_warning "Quest web server was not running"
    fi

    # Stop stats web
    if pgrep -f "stats_web.py" > /dev/null; then
        pkill -f "stats_web.py"
        print_success "Stats web server stopped"
    else
        print_warning "Stats web server was not running"
    fi
}

function restart_servers() {
    stop_servers
    sleep 2
    start_servers
}

function status_servers() {
    print_status "Checking server status..."
    echo ""

    # Check quest web
    if pgrep -f "quest_web.py" > /dev/null; then
        QUEST_PID=$(pgrep -f "quest_web.py")
        print_success "Quest web server is running (PID: $QUEST_PID)"
        echo "  URL: http://localhost:8080"
    else
        print_error "Quest web server is not running"
    fi

    # Check stats web
    if pgrep -f "stats_web.py" > /dev/null; then
        STATS_PID=$(pgrep -f "stats_web.py")
        print_success "Stats web server is running (PID: $STATS_PID)"
        echo "  URL: http://localhost:8081"
    else
        print_error "Stats web server is not running"
    fi

    # Check if ports are listening
    echo ""
    print_status "Port status:"

    if netstat -tln 2>/dev/null | grep -q ":8080"; then
        print_success "Port 8080 is listening"
    else
        print_error "Port 8080 is not listening"
    fi

    if netstat -tln 2>/dev/null | grep -q ":8081"; then
        print_success "Port 8081 is listening"
    else
        print_error "Port 8081 is not listening"
    fi
}

function tail_logs() {
    print_status "Tailing logs (Ctrl+C to stop)..."
    tail -f "$LOGS_DIR/quest-web.log" "$LOGS_DIR/stats-web.log"
}

function show_help() {
    cat << EOF
Jeeves Web Server Management Script

Usage: $0 [command]

Commands:
    start       Start both web servers
    stop        Stop both web servers
    restart     Restart both web servers
    status      Show status of both servers
    logs        Tail logs from both servers
    help        Show this help message

Examples:
    $0 start
    $0 status
    $0 logs

Server URLs:
    Quest Web: http://localhost:8080
    Stats Web: http://localhost:8081

Log files are stored in: $LOGS_DIR/
EOF
}

# Main script logic
case "${1:-}" in
    start)
        start_servers
        ;;
    stop)
        stop_servers
        ;;
    restart)
        restart_servers
        ;;
    status)
        status_servers
        ;;
    logs)
        tail_logs
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: ${1:-}"
        echo ""
        show_help
        exit 1
        ;;
esac
