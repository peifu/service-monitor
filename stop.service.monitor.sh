#!/bin/sh

PID=$(pgrep -f "service_monitor.py")

if [ -z "$PID" ]; then
    echo "服务监控进程未运行"
else
    kill $PID
    echo "已停止服务监控进程 (PID: $PID)"
fi