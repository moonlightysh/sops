#!/bin/sh
# self-healing watchdog for mysqld inside bkce-data
# cold boot / OOM can leave mysqld dead; respawn it whenever gone
while true; do
  if ! pgrep -x mysqld >/dev/null 2>&1; then
    /usr/sbin/mysqld --defaults-file=/etc/mysql/default.my.cnf --daemonize --user=mysql >>/data/bkce/logs/mysql_watchdog.log 2>&1
  fi
  sleep 5
done
