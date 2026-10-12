#!/bin/bash
# bkce-data entrypoint: consul + mysql + redis + rabbitmq (all bind 172.18.107.16 via configs)
set -m

# ensure system users exist (base image may lack them)
id mysql >/dev/null 2>&1 || useradd -r -s /sbin/nologin mysql
id rabbitmq >/dev/null 2>&1 || useradd -r -d /var/lib/rabbitmq -s /sbin/nologin rabbitmq

# runtime dirs (tmpfs wiped in containers)
mkdir -p /var/run/mysql /var/log/rabbitmq /data/bkce/logs/mysql /data/bkce/logs/rabbitmq /data/bkce/logs/redis /var/log/redis /var/lib/redis/default /var/lib/rabbitmq /var/lib/consul /data/bkce/logs
chown mysql:mysql /var/run/mysql
chown -R mysql:mysql /data/bkce/public/mysql /data/bkce/logs/mysql
chown rabbitmq:rabbitmq /var/log/rabbitmq /var/lib/rabbitmq
chown -R rabbitmq:rabbitmq /data/bkce/public/rabbitmq /data/bkce/logs/rabbitmq

# consul server + DNS (*.service.consul names used by the SaaS containers;
# moved here from the removed paas container in the standalone stack).
# Starts FIRST so SaaS containers resolve mysql-default/rabbitmq immediately.
# Self-healing watchdog respawns it after OOM kills.
setsid /usr/local/bin/consul_watchdog.sh >/dev/null 2>&1 </dev/null &
for i in $(seq 1 30); do consul members >/dev/null 2>&1 && break; sleep 1; done
echo "[entry] consul started"

# mysql
/usr/sbin/mysqld --defaults-file=/etc/mysql/default.my.cnf --daemonize --user=mysql
for i in $(seq 1 60); do mysqladmin ping --socket=/var/run/mysql/default.mysql.socket >/dev/null 2>&1 && break; sleep 1; done
echo "[entry] mysqld started"

# redis + self-healing watchdog (script installed at /usr/local/bin/redis_watchdog.sh)
# redis was found SIGKILLed with no log trace; watchdog respawns it whenever gone
setsid /usr/local/bin/redis_watchdog.sh >/dev/null 2>&1 < /dev/null &
setsid /usr/local/bin/mysql_watchdog.sh >/dev/null 2>&1 </dev/null &
echo "[entry] redis watchdog started"

# rabbitmq (longname node: hostname must be iZbp19vsfom9pxogi15pocZ.node.consul)
export RABBITMQ_NODENAME=$(grep "^NODENAME" /etc/rabbitmq/rabbitmq-env.conf | cut -d= -f2)
su rabbitmq -s /bin/bash -c "/usr/sbin/rabbitmq-server -detached"
for i in $(seq 1 60); do rabbitmqctl -q status >/dev/null 2>&1 && break; sleep 2; done
echo "[entry] rabbitmq started"

echo "[entry] bkce-data ready"
tail -f /dev/null
