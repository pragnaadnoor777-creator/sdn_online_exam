#!/bin/bash
# Background traffic generator. Owner: Member C.
# Run it on the background host (bg) inside Mininet:
#   bg bash experiments/traffic_gen.sh --level none|medium|heavy [--target 10.0.0.100] [--duration 60]
# An iperf UDP server must already be running on the target:
#   srv iperf -s -u -p 5001 &

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$REPO_ROOT/config.json"

# Defaults come from config.json; command-line options override them.
read_cfg() { python3 -c "import json,sys;print(json.load(open('$CONFIG')).get('$1','$2'))" 2>/dev/null || echo "$2"; }
LEVEL=none
TARGET=$(read_cfg server_ip 10.0.0.100)
PORT=$(read_cfg iperf_port 5001)
BOTTLENECK_MBPS=$(read_cfg bottleneck_mbps 10)
DURATION=60

while [[ $# -gt 0 ]]; do
  case $1 in
    --level) LEVEL=$2; shift 2;;
    --target) TARGET=$2; shift 2;;
    --duration) DURATION=$2; shift 2;;
    --port) PORT=$2; shift 2;;
    *) echo "Unknown option $1"; exit 1;;
  esac
done

case $LEVEL in
  none)   echo "No background traffic"; exit 0;;
  medium) RATE="$(( BOTTLENECK_MBPS / 2 ))M";;   # about half of the bottleneck
  heavy)  RATE="$(( BOTTLENECK_MBPS * 2 ))M";;   # more than the bottleneck can carry
  *) echo "Level must be none, medium or heavy"; exit 1;;
esac

echo "Background traffic: level=$LEVEL rate=$RATE target=$TARGET:$PORT duration=${DURATION}s"
iperf -c "$TARGET" -u -b "$RATE" -t "$DURATION" -p "$PORT"