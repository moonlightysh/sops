#!/bin/sh
# self-healing watchdog for redis inside bkce-data
# health-based check: redis rewrites its proctitle to "redis-server 172.18.107.16:6379",
# so pgrep patterns are unreliable; ping the service itself instead.
# NOTE: redis has requirepass, so an unauthenticated ping returns NOAUTH —
# that still proves the server is alive. Only treat "empty/no reply" as down.
while true; do
  redis-cli -h 172.18.107.16 -p 6379 ping 2>/dev/null | grep -q "PONG\|NOAUTH" || \
    nohup /usr/bin/redis-server /etc/redis/default.conf --daemonize yes >>/data/bkce/logs/redis/watchdog.log 2>&1 &
  sleep 5
done
