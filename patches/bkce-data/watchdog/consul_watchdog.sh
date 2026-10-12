#!/bin/sh
# self-healing watchdog for the consul server inside bkce-data
# consul is prone to being OOM-killed by the Docker Desktop VM; respawn on death
while true; do
  if ! pgrep -x consul >/dev/null 2>&1; then
    /usr/bin/consul agent \
      -config-dir=/etc/consul.d -config-dir=/etc/consul.d/service \
      >>/data/bkce/logs/consul_watchdog.log 2>&1 &
  fi
  sleep 5
done
