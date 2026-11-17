#!/usr/bin/env bash
# Controlled UDP background-traffic generator. Owner: Member C.
# Run inside the Mininet background host (bg).
# Example:
#   bg bash experiments/traffic_gen.sh --level heavy --duration 30

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="$REPO_ROOT/config.json"

read_cfg() {
    local key="$1"
    local fallback="$2"
    python3 - "$CONFIG" "$key" "$fallback" <<'PY' 2>/dev/null || printf '%s\n' "$fallback"
import json
import sys
path, key, fallback = sys.argv[1:]
try:
    with open(path, encoding="utf-8") as f:
        value = json.load(f).get(key, fallback)
    print(value)
except Exception:
    print(fallback)
PY
}

usage() {
    cat <<'USAGE'
Usage: traffic_gen.sh --level none|medium|heavy [options]

Options:
  --target IP       UDP receiver IP (default: config.json server_ip)
  --duration SEC    Test duration in seconds (default: 60)
  --port PORT       UDP receiver port (default: config.json iperf_port)
  --help            Show this help

Rates are calculated from config.json bottleneck_mbps:
  none   no additional UDP traffic
  medium 50% of bottleneck capacity
  heavy  200% of bottleneck capacity (offered load)

Requires classic iperf 2 for medium/heavy tests.
USAGE
}

LEVEL="none"
TARGET="$(read_cfg server_ip 10.0.0.100)"
PORT="$(read_cfg iperf_port 5001)"
BOTTLENECK_MBPS="$(read_cfg bottleneck_mbps 10)"
DURATION=60

while (($#)); do
    case "$1" in
        --level)
            (($# >= 2)) || { echo "Missing value for --level" >&2; exit 2; }
            LEVEL="$2"; shift 2 ;;
        --target)
            (($# >= 2)) || { echo "Missing value for --target" >&2; exit 2; }
            TARGET="$2"; shift 2 ;;
        --duration)
            (($# >= 2)) || { echo "Missing value for --duration" >&2; exit 2; }
            DURATION="$2"; shift 2 ;;
        --port)
            (($# >= 2)) || { echo "Missing value for --port" >&2; exit 2; }
            PORT="$2"; shift 2 ;;
        --help|-h)
            usage; exit 0 ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2 ;;
    esac
done

[[ "$DURATION" =~ ^[1-9][0-9]*$ ]] || { echo "Duration must be a positive integer" >&2; exit 2; }
[[ "$PORT" =~ ^[1-9][0-9]*$ ]] || { echo "Port must be a positive integer" >&2; exit 2; }
[[ "$BOTTLENECK_MBPS" =~ ^[1-9][0-9]*$ ]] || { echo "config.json bottleneck_mbps must be a positive integer" >&2; exit 2; }

case "$LEVEL" in
    none)
        echo "No additional background traffic requested."
        exit 0
        ;;
    medium)
        RATE_MBPS=$((BOTTLENECK_MBPS / 2))
        ((RATE_MBPS > 0)) || RATE_MBPS=1
        ;;
    heavy)
        RATE_MBPS=$((BOTTLENECK_MBPS * 2))
        ;;
    *)
        echo "Level must be none, medium or heavy" >&2
        exit 2
        ;;
esac

if ! command -v iperf >/dev/null 2>&1; then
    echo "iperf was not found. Install classic iperf 2 in the Mininet environment." >&2
    exit 127
fi

RATE="${RATE_MBPS}M"
echo "Background traffic: level=$LEVEL rate=$RATE target=$TARGET:$PORT duration=${DURATION}s"
exec iperf -c "$TARGET" -u -b "$RATE" -t "$DURATION" -p "$PORT"
