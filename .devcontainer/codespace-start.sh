#!/usr/bin/env sh
# Codespaces start hook: write .env.research for this codespace, then start
# the service with the same launcher every other machine uses.
set -eu
cd "$(dirname "$0")/.."

[ -f .env.research ] || cp research.env.example .env.research

set_value() {
    # Replace NAME=... in .env.research, or append it.
    grep -v "^$1=" .env.research > .env.research.tmp || true
    printf '%s=%s\n' "$1" "$2" >> .env.research.tmp
    mv .env.research.tmp .env.research
}

# Codespaces secrets (GitHub → Settings → Codespaces → Secrets) arrive as
# environment variables; copy any that match a setting in the template.
for name in $(sed -n 's/^\([A-Z_][A-Z0-9_]*\)=.*/\1/p' research.env.example); do
    value=$(printenv "$name" || true)
    [ -n "$value" ] && set_value "$name" "$value"
done

# The browser reaches the service through the forwarded HTTPS address, so
# the host and origin checks must accept it.
if [ -n "${CODESPACE_NAME:-}" ]; then
    host="${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
    set_value RESEARCH_ALLOWED_HOSTS "localhost,127.0.0.1,$host"
    set_value RESEARCH_PUBLIC_ORIGIN "https://$host"
fi

# docker-in-docker starts its daemon alongside this hook. It selects the
# legacy iptables backend, which newer host kernels no longer provide
# ("can't initialize iptables table 'nat'"); switch to nft so its retries,
# or one restart below, can bring the daemon up.
if [ -x /usr/sbin/iptables-nft ] && sudo -n true 2>/dev/null; then
    sudo -n update-alternatives --set iptables /usr/sbin/iptables-nft >/dev/null 2>&1 || true
    sudo -n update-alternatives --set ip6tables /usr/sbin/ip6tables-nft >/dev/null 2>&1 || true
fi
i=0
until docker info >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -eq 30 ] && [ -x /usr/local/share/docker-init.sh ]; then
        echo "[INFO] Docker 尚未啟動，以 iptables-nft 重新啟動 dockerd" >&2
        (sudo -n /usr/local/share/docker-init.sh true >/dev/null 2>&1 &) || true
    fi
    if [ "$i" -gt 90 ]; then
        echo "[FAIL] Docker daemon 未啟動" >&2
        # docker-in-docker writes the daemon log here; show why it stopped.
        tail -n 40 /tmp/dockerd.log >&2 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

./research.sh start
