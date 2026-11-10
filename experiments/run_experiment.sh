#!/bin/bash
# Background traffic generator. Owner: Member C.
# Usage: bash experiments/traffic_gen.sh --level none|medium|heavy --target 10.0.0.1 --duration 60
LEVEL=none; TARGET=10.0.0.1; DURATION=60
BOTTLENECK_MBPS=${BOTTLENECK_MBPS:-10}   # must match the bottleneck set in topo.py

while [[ $# -gt 0 ]]; do
  case $1 in
    --level) LEVEL=$2; shift 2;;
    --target) TARGET=$2; shift 2;;
    --duration) DURATION=$2; shift 2;;
    *) echo "Unknown option $1"; exit 1;;
  esac
done

case $LEVEL in
  none)   echo "No background traffic"; exit 0;;
  medium) RATE=$(( BOTTLENECK_MBPS / 2 ))M;;
  heavy)  RATE=$(( BOTTLENECK_MBPS * 2 ))M;;
  *) echo "Level must be none, medium or heavy"; exit 1;;
esac

echo "Background traffic: $LEVEL ($RATE) to $TARGET for ${DURATION}s"
iperf -c "$TARGET" -u -b "$RATE" -t "$DURATION" -p 5001