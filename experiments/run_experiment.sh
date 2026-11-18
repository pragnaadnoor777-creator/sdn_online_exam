#!/bin/bash
# Runs ONE experiment end to end. Owner: Member C.
#
# Usage (from the repo root):
#   bash experiments/run_experiment.sh --mode sdn|baseline --students N --load none|medium|heavy [--run 1] [--duration 60] [--warmup 10]
#
# What it does:
#   1. starts the Ryu controller (controller/trustme.py) with EXAM_MODE=<mode> and STATS_CSV=<run folder>/controller_stats.csv
#   2. starts topology/topology.py (it starts the exam server and the iperf receiver on srv itself)
#      and drives its Mininet CLI through stdin
#   3. starts background UDP traffic from bg (experiments/traffic_gen.sh), waits --warmup seconds,
#      then runs client/auto_client.py on h1 in rounds for --duration seconds (one round = N students take the exam)
#   4. collects everything into results/raw/<mode>_<N>students_<load>load_<run>/
#
# Output files: client_events.csv controller_stats.csv controller.log topology.log auto_client.log traffic_sender.log
#               server.log exam_server_console.log iperf_receiver.log preflight.txt mininet_commands.txt run_info.txt
#
# EXAM_NOTIFY: the exam server's notifier is switched OFF by default (EXAM_NOTIFY=0) because the controller has no
# /exam/event endpoint yet; this keeps baseline and sdn runs identical. Use EXAM_NOTIFY=1 to turn it on.

# ---------------- settings you may need to change ----------------
CONTROLLER=${CONTROLLER:-controller/trustme.py}
TOPOLOGY=${TOPOLOGY:-topology/topology.py}
AUTO_CLIENT=${AUTO_CLIENT:-client/auto_client.py}
CLIENT_NODE=${CLIENT_NODE:-h1}          # Mininet host that runs all simulated students
TOPO_HOSTS=${TOPO_HOSTS:-1}             # value of topology.py --students (number of student hosts h1..hN)
RYU_VENV=${RYU_VENV:-$HOME/ryu-env}
OF_PORT=${OF_PORT:-6653}
TOPO_WAIT=${TOPO_WAIT:-5}               # seconds after the Mininet CLI starts before the first command
SUDO=${SUDO-sudo}                       # set SUDO= to run without sudo (only for testing this script)
MN_CLEAN=${MN_CLEAN:-"sudo mn -c"}
NOTIFY=${EXAM_NOTIFY:-0}                # 0 = exam server does not send events to the controller
# files the topology writes at fixed paths
SERVER_CONSOLE_LOG=${SERVER_CONSOLE_LOG:-/tmp/exam_server.log}
IPERF_RECEIVER_LOG=${IPERF_RECEIVER_LOG:-/tmp/iperf_srv.log}
# ------------------------------------------------------------------

MODE=sdn; STUDENTS=5; LOAD=none; RUN=1; DURATION=60; WARMUP=10
need_val() { [[ $# -ge 2 ]] || { echo "ERROR: $1 needs a value" >&2; exit 1; }; }
while [[ $# -gt 0 ]]; do
  case $1 in
    --mode)     need_val "$@"; MODE=$2; shift 2;;
    --students) need_val "$@"; STUDENTS=$2; shift 2;;
    --load)     need_val "$@"; LOAD=$2; shift 2;;
    --run)      need_val "$@"; RUN=$2; shift 2;;
    --duration) need_val "$@"; DURATION=$2; shift 2;;   # seconds during which students keep taking exams
    --warmup)   need_val "$@"; WARMUP=$2; shift 2;;     # seconds of background load before the students start
    *) echo "Unknown option $1"; exit 1;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }
cd "$(dirname "$0")/.." || exit 1
REPO=$(pwd)

[[ $MODE == sdn || $MODE == baseline ]] || die "--mode must be sdn or baseline"
[[ $LOAD == none || $LOAD == medium || $LOAD == heavy ]] || die "--load must be none, medium or heavy"
[[ $STUDENTS =~ ^[0-9]+$ && $STUDENTS -ge 1 ]] || die "--students must be a positive number"
[[ $RUN =~ ^[0-9]+$ ]] || die "--run must be a number (analyze.py expects digits in the folder name)"
[[ $DURATION =~ ^[0-9]+$ && $WARMUP =~ ^[0-9]+$ ]] || die "--duration and --warmup must be numbers"

# ---------- pre-flight checks ----------
for f in "$CONTROLLER" "$TOPOLOGY" experiments/traffic_gen.sh config.json; do [ -f "$f" ] || die "missing file: $f"; done
[ -s "$AUTO_CLIENT" ] || die "$AUTO_CLIENT is missing or empty"
for f in experiments/*.sh; do
  grep -q $'\r' "$f" && die "$f has Windows (CRLF) line endings. Run: sed -i 's/\\r\$//' experiments/*.sh"
done
[ -f "$RYU_VENV/bin/activate" ] || die "Ryu environment not found at $RYU_VENV (set RYU_VENV=...)"
command -v iperf > /dev/null || die "iperf (classic iperf 2) is not installed"
command -v timeout > /dev/null || die "'timeout' command not found"
if [ "$MN_CLEAN" = "sudo mn -c" ]; then command -v mn > /dev/null || die "Mininet (mn) is not installed"; fi

SERVER_IP=$(python3 -c "import json;print(json.load(open('config.json'))['server_ip'])") || die "cannot read config.json"
SERVER_PORT=$(python3 -c "import json;print(json.load(open('config.json'))['server_port'])")

OUT="$REPO/results/raw/${MODE}_${STUDENTS}students_${LOAD}load_${RUN}"
[ -e "$OUT" ] && die "$OUT already exists. Use another --run number or delete it."
mkdir -p "$OUT"

echo "=== mode=$MODE students=$STUDENTS load=$LOAD run=$RUN duration=${DURATION}s warmup=${WARMUP}s notify=$NOTIFY ==="

# ---------- 1. clean old state ----------
$MN_CLEAN > /dev/null 2>&1
rm -f "$SERVER_CONSOLE_LOG" "$IPERF_RECEIVER_LOG"

CTRL_PID=""
cleanup() {
  [ -n "$CTRL_PID" ] && kill "$CTRL_PID" 2>/dev/null
  # the exam server / iperf receiver are started inside Mininet hosts and can survive "mn -c";
  # the [x] trick stops pkill from matching its own command line
  $SUDO pkill -f "$REPO/[s]erver/server.py" > /dev/null 2>&1
  $SUDO pkill -f "[i]perf -s -u" > /dev/null 2>&1
  $MN_CLEAN > /dev/null 2>&1
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# ---------- 2. controller (inside the Ryu environment) ----------
( source "$RYU_VENV/bin/activate" && EXAM_MODE=$MODE STATS_CSV="$OUT/controller_stats.csv" exec ryu-manager "$REPO/$CONTROLLER" ) > "$OUT/controller.log" 2>&1 &
CTRL_PID=$!
for i in $(seq 1 30); do
  (echo > /dev/tcp/127.0.0.1/$OF_PORT) 2>/dev/null && break
  kill -0 "$CTRL_PID" 2>/dev/null || die "controller exited early, see $OUT/controller.log"
  sleep 1
done
(echo > /dev/tcp/127.0.0.1/$OF_PORT) 2>/dev/null || die "controller is not listening on port $OF_PORT, see $OUT/controller.log"
echo "controller up (pid $CTRL_PID, EXAM_MODE=$MODE)"

# ---------- 3. Mininet CLI script ----------
# IMPORTANT: every host command below is started in the background with stdin from /dev/null.
# The Mininet CLI forwards its own stdin to a foreground host command, which would swallow the rest of this script.
# (The CLI also replaces any word that is exactly a node name (h1, srv, bg, s1) by that node's IP, so avoid such words.)
TRAFFIC_SECS=$(( WARMUP + DURATION ))
WAITMAX=$(( DURATION + 90 ))
CMDS="$OUT/mininet_commands.txt"
cat > "$CMDS" << 'TEMPLATE'
sh sleep @TOPO_WAIT@
@NODE@ bash -c 'ping -c 3 -W 2 @SERVER_IP@ > @OUT@/preflight.txt 2>&1' < /dev/null &
sh sleep 5
bg bash -c 'bash @REPO@/experiments/traffic_gen.sh --level @LOAD@ --target @SERVER_IP@ --duration @TRAFFIC_SECS@ > @OUT@/traffic_sender.log 2>&1' < /dev/null &
sh sleep @WARMUP@
@NODE@ bash -c 'cd @REPO@; end=$((SECONDS+@DURATION@)); n=0; while [ $SECONDS -lt $end ]; do n=$((n+1)); python3 @AUTO_CLIENT@ --host @SERVER_IP@ --port @SERVER_PORT@ -n @STUDENTS@ --results-dir @OUT@ >> @OUT@/auto_client.log 2>&1; sleep 1; done; echo $n > @OUT@/.rounds; touch @OUT@/.client_done' < /dev/null &
sh for i in $(seq 1 @WAITMAX@); do [ -f @OUT@/.client_done ] && break; sleep 1; done
sh sleep 6
exit
TEMPLATE
sed -i -e "s|@TOPO_WAIT@|$TOPO_WAIT|g" -e "s|@NODE@|$CLIENT_NODE|g" -e "s|@SERVER_IP@|$SERVER_IP|g" \
       -e "s|@SERVER_PORT@|$SERVER_PORT|g" -e "s|@OUT@|$OUT|g" -e "s|@REPO@|$REPO|g" -e "s|@LOAD@|$LOAD|g" \
       -e "s|@TRAFFIC_SECS@|$TRAFFIC_SECS|g" -e "s|@WARMUP@|$WARMUP|g" -e "s|@DURATION@|$DURATION|g" \
       -e "s|@AUTO_CLIENT@|$AUTO_CLIENT|g" -e "s|@STUDENTS@|$STUDENTS|g" -e "s|@WAITMAX@|$WAITMAX|g" "$CMDS"
grep -q '@[A-Z_]*@' "$CMDS" && die "unreplaced placeholder left in $CMDS"

# ---------- 4. topology (system Python, NOT the venv) ----------
# Started from inside the run folder, so the exam server's server.log lands there.
# "env EXAM_NOTIFY=..." is needed because sudo drops the caller's environment.
echo "starting topology; this takes about $(( TOPO_WAIT + 5 + WARMUP + DURATION + 10 )) seconds ..."
( cd "$OUT" && timeout -k 15 $(( TOPO_WAIT + 5 + WARMUP + DURATION + 150 )) $SUDO env EXAM_NOTIFY="$NOTIFY" python3 "$REPO/$TOPOLOGY" --students "$TOPO_HOSTS" < "$CMDS" > "$OUT/topology.log" 2>&1 )
TOPO_EXIT=$?

# ---------- 5. stop controller, collect logs, sanity checks ----------
kill "$CTRL_PID" 2>/dev/null; CTRL_PID=""
sleep 1
cp "$SERVER_CONSOLE_LOG" "$OUT/exam_server_console.log" 2>/dev/null || echo "WARNING: $SERVER_CONSOLE_LOG not found"
cp "$IPERF_RECEIVER_LOG" "$OUT/iperf_receiver.log" 2>/dev/null || echo "WARNING: $IPERF_RECEIVER_LOG not found"
ROUNDS=$(cat "$OUT/.rounds" 2>/dev/null || echo 0)
rm -f "$OUT/.client_done" "$OUT/.rounds"

# NOTE: Ryu itself logs "connected socket" for every TCP connection (even the port probe above),
# so match the controller's own "Switch <dpid> connected" line instead.
grep -Eq "Switch [0-9a-f]+ connected" "$OUT/controller.log" || echo "WARNING: the switch never connected to the controller (see controller.log); this run is not valid"
if [ -f "$OUT/preflight.txt" ]; then
  grep -q " 0 received\|100% packet loss" "$OUT/preflight.txt" && echo "WARNING: ping to srv failed (see preflight.txt)"
else
  echo "WARNING: preflight.txt missing, the Mininet commands may not have run (see topology.log)"
fi
SENT=$(grep -c ANSWER_SENT "$OUT/client_events.csv" 2>/dev/null); ACKS=$(grep -c ACK_RECEIVED "$OUT/client_events.csv" 2>/dev/null)
[ "${SENT:-0}" -gt 0 ] || echo "WARNING: no answers recorded in client_events.csv, this run has no latency data"
[ "${SENT:-0}" -eq "${ACKS:-0}" ] || echo "WARNING: answers sent (${SENT:-0}) != acks received (${ACKS:-0}); some answers were never acknowledged"
grep -Eq " [1-9][0-9]* failed" "$OUT/auto_client.log" 2>/dev/null && echo "WARNING: some simulated students failed (see auto_client.log)"
# the controller writes a header line first, so a useful file has more than one line
[ "$(wc -l < "$OUT/controller_stats.csv" 2>/dev/null || echo 0)" -gt 1 ] || echo "WARNING: controller_stats.csv has no samples"

{
  echo "mode=$MODE"; echo "students=$STUDENTS"; echo "load=$LOAD"; echo "run=$RUN"
  echo "duration=${DURATION}s"; echo "warmup=${WARMUP}s"; echo "rounds=$ROUNDS"
  echo "answers_sent=${SENT:-0}"; echo "acks_received=${ACKS:-0}"
  echo "client_node=$CLIENT_NODE"; echo "topology_hosts=$TOPO_HOSTS"; echo "server=$SERVER_IP:$SERVER_PORT"
  echo "exam_notify=$NOTIFY"
  echo "controller=$CONTROLLER EXAM_MODE=$MODE"; echo "topology=$TOPOLOGY (exit code $TOPO_EXIT)"
  echo "git_commit=$(git rev-parse --short HEAD 2>/dev/null)"; echo "finished=$(date -Is)"
} > "$OUT/run_info.txt"

$SUDO chown -R "$(id -un):$(id -gn)" "$OUT" 2>/dev/null
echo "=== done: $OUT (rounds=$ROUNDS, answers sent=${SENT:-0}, acks=${ACKS:-0}) ==="
ls -1 "$OUT"