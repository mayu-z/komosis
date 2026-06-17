#!/bin/sh
set -eu

envsubst '${PORT} ${GATEWAY_UPSTREAM}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
