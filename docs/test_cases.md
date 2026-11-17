# Test Cases and Verification Status

Owner: Member C. Updated: 2026-11-18.

This document distinguishes **implementation status** from **execution status**. A feature appearing in source code does not mean its test has already passed. Record the date, environment and output when the team actually runs each test.

## 1. Test environment

Required for full network tests:

- Ubuntu Linux with Mininet and Open vSwitch installed.
- Ryu available as `ryu-manager` in the controller's Python environment.
- Classic iperf 2 installed.
- Python 3 available to Mininet hosts and project scripts.
- `pandas` and `matplotlib` installed for analysis.
- Ryu and Mininet running on the same Linux machine because the topology connects to `127.0.0.1:6653`.

Run commands from the repository root unless specified otherwise.

## 2. Functional test cases

| ID | Test | Procedure / stimulus | Expected result | Implementation status | Execution result |
|---|---|---|---|---|---|
| T1 | One student completes an exam | Start the topology; connect one interactive or automated client to `10.0.0.100:5000`; answer all delivered questions. | Server accepts the login, sends questions, checks answers and returns a result. | Server/client flow is present. The supplied `server/questions.json` is empty; the default `ExamLogic()` uses its built-in fallback only when its relative `questions.json` path does not exist. | Not recorded — run and attach evidence. |
| T2 | Multiple concurrent students | Run `client/auto_client.py --students N` against the server. | Each client gets its own connection/session and result; one student's messages/scores do not become another's. | Thread-per-client server and `ThreadPoolExecutor` automated client are present. | Not recorded — run and attach evidence. |
| T3 | Exam timer expires | Start server with a short `--duration`; allow a client session to remain unfinished until the timer expires. | Server sends `TIME_UP`, attempts to send the current result and closes the connection. | Timer exists. There is no distinct `LATE_ANSWER` response path; an answer submitted after the timer closes the connection is not a separately documented rejection response. | Partial behavior — run and record exact output. |
| T4 | Student disconnects mid-exam | Connect a student, then terminate the client before the exam is complete. | Server handler cleans up the connection and active-student entry; server continues accepting other clients. | Cleanup in the handler's `finally` block is present. | Not recorded — run and attach server log. |
| T5 | Duplicate concurrent login | Keep a session logged in; open a second client using the same student ID before the first session exits. | Second login receives an `ERROR` with code 409; first session remains active. | Active-student set and duplicate check are present. The check applies while the ID is active. | Not recorded — run and attach client/server output. |
| T6 | Heavy background load and SDN reaction | Start Ryu with `EXAM_MODE=sdn`; run the topology; generate heavy UDP traffic from `bg` to `srv`; inspect controller log and switch meter/flow state. | Server-link utilization reaches the configured threshold; controller identifies an eligible sender and installs the meter-limited flow. Matching exam TCP traffic uses the higher-priority exam flow. | Congestion polling and rate-limit code are present. Successful meter installation depends on switch support and must be verified from logs/statistics. | Not recorded — run and attach controller/iperf evidence. |
| T7 | Link failure and rerouting | Disconnect/fail the only server-facing link and observe connectivity. | A resilient topology would reroute traffic over an alternate path. | Not implemented / out of scope: the supplied topology has one switch and one path to `srv`. Do not mark as passed. | Not applicable to current topology. |

## 3. Member C integration test

| ID | Test | Procedure | Expected result | Implementation status | Execution result |
|---|---|---|---|---|---|
| C1 | Notifier succeeds against dummy listener | Start `python3 integration/test_listener.py`; temporarily configure notifier target as `127.0.0.1:8081`; call `notify_controller('exam_start', {'port': 5000})`. | Listener prints the POST path/body and notifier returns `True`. | Dummy listener and notifier transport are present. | Not recorded — run and attach output. |
| C2 | Notifier handles unavailable listener | Stop dummy listener; call `notify_controller(...)` again. | Notifier logs the failure and returns `False`; it does not raise into the exam application. | Exception handling is present. | Not recorded — run and attach output. |
| C3 | Real server-to-controller event delivery | Run the exam server in Mininet and direct notifier to the actual controller endpoint. | Actual controller receives `/exam/event` and returns a successful HTTP response. | Not implemented in the supplied `controller/trustme.py`; it does not define an HTTP `/exam/event` route. Requires Member B's REST endpoint and a reachable controller address. | Blocked pending Member B integration. |

## 4. Experiment and analysis checks

| ID | Test | Procedure | Expected result | Status |
|---|---|---|---|---|
| E1 | Traffic generator `none` | `bash experiments/traffic_gen.sh --level none` | Prints that no additional background traffic is requested and exits successfully. | Script-level check; record execution. |
| E2 | Traffic generator `medium` | With topology running and iperf receiver on `srv`, run it on `bg` for a short duration. | Offers approximately 5 Mbps UDP traffic when bottleneck is 10 Mbps. Actual received rate can be lower. | Script-level check; record sender and receiver output. |
| E3 | Traffic generator `heavy` | Same setup, `--level heavy`. | Offers approximately 20 Mbps UDP traffic into the 10 Mbps bottleneck. Loss/received rate must be read at receiver, not inferred from sender rate. | Script-level check; record sender and receiver output. |
| E4 | Run-folder and CSV generation | Run the experiment runner with a small student count and short duration. | A unique `results/raw/<mode>_<N>students_<load>load_<run>/` folder contains client and controller data plus console logs. | Requires live Ryu/Mininet verification. |
| E5 | Analyzer input compatibility | Run `python3 experiments/analyze.py results/raw`. | Analyzer reads `client_events.csv` with `question_id` and `details`, pairs `ANSWER_SENT`/`ACK_RECEIVED`, reads controller CSV, and writes summary/latency plots. | Verify using a real run folder; synthetic fixtures can test calculations only. |
| E6 | Baseline/SDN comparison | Repeat matching student/load/duration conditions with `EXAM_MODE=baseline` and `EXAM_MODE=sdn`. | Results are stored separately and can be compared for latency, fairness and link utilization. | Requires multiple real runs; no improvement claim until data exists. |

## 5. Commands for a basic verification pass

### Static checks

```bash
bash -n experiments/run_experiment.sh
bash -n experiments/traffic_gen.sh
python3 -m py_compile experiments/analyze.py integration/notifier.py integration/test_listener.py
python3 -m json.tool config.json >/dev/null
git diff --check
```

### Existing functional tests

```bash
python3 -m unittest discover -s tests/functional -v
```

### Basic Mininet connectivity

With Ryu running on the same Linux host:

```bash
sudo mn -c
sudo /usr/bin/python3 topology/topology.py --students 3
```

At the `mininet>` prompt:

```text
nodes
net
pingall
```

Expected: all created hosts are listed and `pingall` reports 0% packet loss. Exit with `exit`.

### Automated experiment smoke test

Close manually started controllers/topologies, activate the Ryu environment and run:

```bash
source ~/ryu-env/bin/activate
bash experiments/run_experiment.sh --mode sdn --students 2 --load medium --duration 10
```

Then inspect the created directory under `results/raw/`. Repeat with `--mode baseline` using the same student count, load and duration.

### Analyze collected runs

```bash
python3 experiments/analyze.py results/raw
```

Expected outputs (when runs contain paired client events) are `results/graphs/summary.csv` and `results/graphs/latency_<load>.png`.

## 6. Test evidence to retain

For each executed case, record:

- Date and Linux environment (VirtualBox Ubuntu or WSL; do not mix the controller and Mininet between them).
- Exact command and configuration (mode, number of students, load and duration).
- Client output and `client_events.csv`.
- Ryu `controller.log` and `controller_stats.csv`.
- `topology.log`, `iperf_receiver.log` and `traffic_sender.log`.
- Whether the expected result occurred. Keep failures as failures; do not change a test to passed solely because the script exited without an error.
