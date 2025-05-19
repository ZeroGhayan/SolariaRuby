#!/bin/bash
# monitor.sh - Script for monitoring system resources and logging results.

# Variables
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/monitor.log"

# Ensure the logs directory exists
[ -d "$LOG_DIR" ] || mkdir "$LOG_DIR"

# Function to log a message
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Log system resources
echo "Logging system resources..."
log_message "--- System Resource Monitoring Start ---"

# Log CPU usage
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2 + $4}')
log_message "CPU Usage: $CPU_USAGE%"

# Log Memory usage
MEMORY_USAGE=$(free -m | awk '/Mem:/ { printf("%.2f", $3/$2 * 100.0) }')
log_message "Memory Usage: $MEMORY_USAGE%"

# Log Disk usage
DISK_USAGE=$(df -h / | awk 'NR==2 { print $5 }')
log_message "Disk Usage: $DISK_USAGE"

# Log Active Processes
ACTIVE_PROCESSES=$(ps aux --no-heading | wc -l)
log_message "Active Processes: $ACTIVE_PROCESSES"

# Log Current Network Connections
NETWORK_CONNECTIONS=$(netstat -an | grep ESTABLISHED | wc -l)
log_message "Established Network Connections: $NETWORK_CONNECTIONS"

# Log Project Operations Status
echo "Checking project operations status..."
OP_STATUS="OK"
if ! curl -s http://localhost:5000 >/dev/null; then
    OP_STATUS="ERROR"
fi
log_message "Project Operations Status: $OP_STATUS"

# Completion Message
log_message "--- System Resource Monitoring End ---"
echo "Monitoring completed. Log written to $LOG_FILE."
