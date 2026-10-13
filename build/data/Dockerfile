# bkce-data — MySQL / Redis / RabbitMQ / Consul (standalone stack)
#
# consul moved here from the retired paas container: the binary was extracted
# from a bkce-paas image. It is gitignored; regenerate if missing:
#   docker cp bkce-data:/usr/bin/consul build/data/consul
ARG REGISTRY=moonlightysh
ARG BASE_TAG=v2
FROM ${REGISTRY}/bkce-data:${BASE_TAG}

# consul server binary (DNS :53 + HTTP :8500, serves *.service.consul names)
COPY build/data/consul /usr/bin/consul

# entrypoint: consul starts FIRST (SaaS containers resolve mysql-default/rabbitmq
# via consul DNS), then mysqld + rabbitmq; watchdogs for consul/mysql/redis
COPY patches/bkce-data/entrypoint.sh /entrypoint.sh
COPY patches/bkce-data/watchdog/consul_watchdog.sh /usr/local/bin/consul_watchdog.sh
COPY patches/bkce-data/watchdog/mysql_watchdog.sh /usr/local/bin/mysql_watchdog.sh
COPY patches/bkce-data/watchdog/redis_watchdog.sh /usr/local/bin/redis_watchdog.sh
RUN chmod +x /entrypoint.sh /usr/local/bin/consul_watchdog.sh \
                            /usr/local/bin/mysql_watchdog.sh \
                            /usr/local/bin/redis_watchdog.sh

# consul server config + declarative service defs (TCP checks on 172.18.107.16)
COPY patches/bkce-data/consul/consul.json /etc/consul.d/consul.json
COPY patches/bkce-data/consul/server.json /etc/consul.d/server.json
COPY patches/bkce-data/consul/service/ /etc/consul.d/service/
