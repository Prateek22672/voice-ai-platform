#!/bin/sh
# Inject SIP trunk credentials from the environment (.env via docker-compose) into pjsip.conf.
# Keeps secrets out of git — the config in the repo only holds CHANGE_ME placeholders.
set -e
CONF=/etc/asterisk/pjsip.conf
sed -i "s|CHANGE_ME_SIP_USER|${SIP_TRUNK_USER:-unset}|g" "$CONF"
sed -i "s|CHANGE_ME_SIP_PASS|${SIP_TRUNK_PASS:-unset}|g" "$CONF"
sed -i "s|CHANGE_ME_DID|${SIP_DID_NUMBER:-anonymous}|g" "$CONF"
echo "[entrypoint] pjsip.conf templated (user=${SIP_TRUNK_USER:-unset}, did=${SIP_DID_NUMBER:-anonymous})"
exec asterisk -f -vvv
