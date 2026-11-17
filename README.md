# Online Examination Network (SDN + TCP Sockets)

SDN-Socket Programming Jackfruit Mini Project, Topic #18.

A multi-user online examination application built with TCP sockets and deployed in a Mininet network managed by an SDN controller. The controller monitors the server-facing link and, in SDN mode, applies a meter-based rate limit when the link becomes congested. Experiments compare the same topology in baseline and SDN modes.

## Team

| Member | Responsibility |
|---|---|
| Member A — Poornaprajna | Application: server, client, examination protocol |
| Member B — Rampranav | SDN and network: Mininet topology, OpenFlow controller |
| Member C — Pragna Adnoor | Integration, experiments, configuration and documentation |

## 1. Project objective

The project demonstrates an online examination system while background traffic competes for network capacity. Students connect to an examination server using TCP. A separate background host sends controlled UDP traffic to the server. The SDN controller monitors the switch's server-facing port and, in SDN mode, rate-limits the heaviest sender when the configured utilization threshold is reached.

The project compares:

- **Baseline mode:** The same controller operates as a learning switch and records port statistics, but does not install the SDN exam-priority rule or trigger the rate-limit flow.
- **SDN mode:** The controller installs a higher-priority flow for TCP examination traffic and can apply a meter-based rate limit to a heavy sender.

This repository's current topology has one switch and one server-facing bottleneck. It has no alternate path, so link-failure rerouting is not implemented.

## 2. Actual architecture and host mapping

The source of truth for the topology is `topology/topology.py`.

| Mininet node | IP address | Switch port | Purpose | Link settings |
|---|---|---:|---|---|
| `srv` | `10.0.0.100/24` | 1 | TCP exam server and UDP iperf receiver | 10 Mbps, 30 ms |
| `bg` | `10.0.0.200/24` | 2 | Background UDP traffic source | 100 Mbps; no delay specified |
| `h1` | `10.0.0.1/24` | 3 | Student host | 100 Mbps, 30 ms |
| `h2` | `10.0.0.2/24` | 4 | Student host | 100 Mbps, 30 ms |
| `h3` onward | `10.0.0.3/24` onward | 5 onward | Student hosts | 100 Mbps, 30 ms |

The number of student hosts is controlled by `--students` (default 10, maximum 99). `srv` and `bg` are added before the student hosts. Switch port numbering follows the `addLink` order, so the controller expects the server to remain on port 1 and the background host on port 2.

The server-facing link is the 10 Mbps bottleneck. Student and background links have higher configured bandwidth, so traffic destined for `srv` ultimately competes for the 10 Mbps server link.

```text
                        Ryu controller
                     127.0.0.1:6653
                           |
                   OpenFlow 1.3 control
                           |
                    Open vSwitch s1
                 /        |        \\
          port 1 /   port 2|         \\ port 3 onward
               /          |          \\
      srv 10.0.0.100   bg 10.0.0.200   h1 ... hN
      10 Mbps/30 ms    100 Mbps       student hosts
      TCP 5000
      UDP 5001
```

## 3. Repository structure and ownership

Only edit files assigned to your team role. Ask the relevant owner before changing another member's implementation.

```text
.
├── README.md                         # C
├── config.json                       # C; A and B read it
├── requirements.txt                  # C
├── .gitignore                        # C
├── server/                           # A: server.py, exam_logic.py, questions.json
├── client/                           # A: client.py, auto_client.py
├── tests/functional/                 # A
├── controller/trustme.py             # B
├── topology/topology.py               # B
├── integration/                      # C: notifier.py, test_listener.py
├── experiments/                      # C: run_experiment.sh, traffic_gen.sh, analyze.py
├── results/raw/                       # C: experiment outputs
├── results/graphs/                    # C: summaries and plots
└── docs/
    ├── protocol.md                    # A
    ├── sdn_design.md                  # B
    ├── architecture.md                # C
    └── test_cases.md                  # C
```

## 4. Ports and configuration

The current topology and source use these service ports:

| Port | Protocol | Purpose |
|---:|---|---|
| 6653 | TCP | OpenFlow connection from switch to Ryu |
| 5000 | TCP | Examination server |
| 5001 | UDP | iperf background-traffic receiver |
| 8080 | TCP/HTTP | Configured notifier target port; the controller endpoint is not implemented in `trustme.py` |
| 8081 | TCP/HTTP | Default port of the local dummy notifier listener after the C-owned port change |

`config.json` currently defines `server_ip=10.0.0.100`, `server_port=5000`, `bg_host_ip=10.0.0.200`, `iperf_port=5001`, and `bottleneck_mbps=10`. Its `controller_ip=10.0.0.254` is a placeholder until the team supplies a reachable controller address for processes inside the Mininet host namespace. `controller_rest_port=8080` is the notifier target setting.

Do not set `controller_ip` to `127.0.0.1` for the exam server inside Mininet: loopback inside `srv` refers to `srv` itself, not the Linux host running Ryu. The current controller source does not implement the `/exam/event` HTTP endpoint, so the real notifier-to-controller REST integration remains incomplete. The notifier is designed to fail safely and not crash the exam server if the endpoint is unreachable.

## 5. Software requirements

Use one Linux environment for Ryu and Mininet. The switch connects to `127.0.0.1:6653`, so running Ryu in VirtualBox and Mininet in WSL (or vice versa) will not make that loopback address connect.

System packages on Ubuntu:

```bash
sudo apt update
sudo apt install mininet openvswitch-switch iperf iproute2 python3-pip python3-venv git -y
```

The controller source imports `ryu.*`, so this revision expects `ryu-manager` from a working Ryu Python environment. Mininet is commonly installed for the system Python; use `/usr/bin/python3` for the topology when needed. Install the analysis dependencies in the Python environment used for `analyze.py`:

```bash
python3 -m pip install pandas matplotlib
```

Check prerequisites:

```bash
which ryu-manager
ryu-manager --version
which mn
mn --version
iperf --version
/usr/bin/python3 -c "import mininet; print('Mininet import OK')"
```

The traffic generator uses classic iperf 2 command-line syntax (`iperf -s -u` and `iperf -c ... -u`).

## 6. Configuration and controller modes

The topology reads `config.json`. The controller also reads `server_ip`, `server_port`, and `bottleneck_mbps` from that file.

Both modes use `controller/trustme.py`. The environment variable `EXAM_MODE` selects the controller behavior:

```bash
EXAM_MODE=sdn ryu-manager --ofp-tcp-listen-port 6653 controller/trustme.py
```

or:

```bash
EXAM_MODE=baseline ryu-manager --ofp-tcp-listen-port 6653 controller/trustme.py
```

The default is `sdn` when `EXAM_MODE` is not set. The topology's `--mode` argument is accepted for compatibility but is ignored by the current topology source. **Do not use `--mode` on the topology to select baseline or SDN. Set `EXAM_MODE` before starting Ryu.**

Controller parameters in `controller/trustme.py`:

| Parameter | Current value | Meaning |
|---|---:|---|
| `POLL_INTERVAL` | 2 s | Port-statistics polling interval |
| `THRESHOLD_PCT` | 80% | Congestion trigger |
| `LIMIT_KBPS` | 2000 | Meter rate (2 Mbps) |
| `LIMIT_SECONDS` | 30 s | Hard timeout on the limit flow |
| `MIN_SENDER_MBPS` | 1.0 | Ignore senders below this input rate |
| `SERVER_PORT` | 1 | Switch port connected to `srv` |
| `EXAM_PORT` | 5000 | TCP exam destination port |

In SDN mode the controller installs an exam TCP flow at priority 20. Its rate-limit flow has priority 10 and matches IPv4 traffic from a selected input port to the server. The table-miss rule has priority 0 and learned flows have priority 1. The higher-priority exam flow is intended to keep matching TCP exam traffic out of the lower-priority rate-limit rule.

## 7. Manual run procedure

Run all commands from the repository root. Keep Ryu and Mininet in the same Linux environment.

**Terminal 1 — start Ryu:**

```bash
cd ~/sdn_online_exam
source ~/ryu-env/bin/activate
mkdir -p logs
EXAM_MODE=sdn STATS_CSV="$PWD/logs/controller_stats.csv" \
  ryu-manager --ofp-tcp-listen-port 6653 controller/trustme.py
```

For baseline, stop Ryu and restart it with `EXAM_MODE=baseline`.

**Terminal 2 — start Mininet:**

```bash
cd ~/sdn_online_exam
sudo mn -c
sudo /usr/bin/python3 topology/topology.py --students 5
```

The topology itself starts the TCP exam server and UDP iperf receiver on `srv`. Do not start duplicate server or iperf receiver processes manually.

At the `mininet>` prompt:

```text
nodes
net
pingall
```

Check that all nodes appear and that `pingall` has 0% packet loss. The controller terminal should report that switch `s1` connected.

Run automated students from a student host:

```text
h1 python3 client/auto_client.py --host 10.0.0.100 --port 5000 --students 5 --results-dir /absolute/path/to/sdn_online_exam/results/raw/manual
```

Generate background traffic from the dedicated `bg` host:

```text
bg bash experiments/traffic_gen.sh --level medium --target 10.0.0.100 --duration 20
bg bash experiments/traffic_gen.sh --level heavy --target 10.0.0.100 --duration 30
```

The topology automatically starts the UDP receiver on `srv:5001`. The traffic generator defaults to the IP, port and bottleneck rate in `config.json` if `--target` and `--port` are omitted.

Exit Mininet with `exit`. Stop Ryu with Ctrl+C.

## 8. Automated experiment runner

The C-owned runner automates one run, creates a unique folder under `results/raw/`, starts Ryu, starts the topology, runs `auto_client.py`, generates background traffic, and collects logs. It uses the same `controller/trustme.py` for both modes and sets `EXAM_MODE` for the selected mode.

Close any manually running Mininet topology and controller first. Activate the Ryu environment, then run from the repository root:

```bash
source ~/ryu-env/bin/activate
bash experiments/run_experiment.sh --mode sdn --students 5 --load medium --duration 20
bash experiments/run_experiment.sh --mode baseline --students 5 --load medium --duration 20
```

Other valid loads are `none` and `heavy`; valid student counts are 1 through 99. The runner starts a new unique run directory such as:

```text
results/raw/sdn_5students_mediumload_1/
```

Typical output files include `client_events.csv`, `controller_stats.csv`, `controller.log`, `topology.log`, `auto_client.log`, `traffic_sender.log`, `iperf_receiver.log`, and `run_info.txt`. A `server.log` is collected when the topology process's working directory is inherited by the server process.

The automated runner is a shell orchestrator around an interactive Mininet CLI. Its behavior must be verified in the team's actual Linux/Ryu/Mininet environment; syntax checks alone do not prove the whole experiment works.

## 9. Analyze experiment results

Install pandas and matplotlib, then run:

```bash
python3 experiments/analyze.py results/raw
```

The analyzer reads the current client CSV schema:

```text
 timestamp,student_id,event,question_id,details
```

It pairs `ANSWER_SENT` and `ACK_RECEIVED` by student and question ID, then calculates mean answer latency, 95th-percentile latency and Jain's fairness index using reciprocal per-student mean latency. It also reads the controller schema:

```text
 timestamp,srv_link_mbps,utilization_pct,congested,limited_ports
```

Outputs are written to `results/graphs/summary.csv` and `results/graphs/latency_<load>.png`.

Do not report improvement until you have matching baseline and SDN runs with the same number of students, load and duration. Repeat each condition several times and compare the averages.

## 10. Notifier test

The notifier sends HTTP POST requests to the configured `controller_ip:controller_rest_port` and `/exam/event`. The current controller source does not include this endpoint, so test the notifier independently using the C-owned dummy listener.

Terminal 1:

```bash
python3 integration/test_listener.py
```

It listens on `127.0.0.1:8081` by default. For the test only, temporarily set `controller_ip` to `127.0.0.1` and `controller_rest_port` to `8081` in `config.json`, run `notify_controller(...)`, and then restore the original configuration. Do not confuse this dummy listener with the real Ryu controller REST service.

## 11. Test cases

See [`docs/test_cases.md`](docs/test_cases.md) for the scenarios, expected outcomes, current implementation status and commands. A source-code implementation status is not the same as a test that has actually been run and passed.

## 12. Known limitations

- The network is emulated in Mininet rather than built from physical switches and hosts.
- The topology has one switch and one server-facing bottleneck, with no alternate path or link-failure rerouting.
- The controller's exam-event REST endpoint is not present in `controller/trustme.py`; the notifier can be tested with the dummy listener, but end-to-end HTTP event integration is not complete.
- `config.json` has a placeholder `controller_ip` for the notifier. The controller address reachable from a Mininet host must be agreed and configured before real event delivery.
- `server/questions.json` is empty in the supplied project snapshot. `ExamLogic` uses its built-in questions only when the relative `questions.json` path does not exist; an empty JSON file is not a valid question bank. Member A should provide a valid question bank or correct the loading behavior.
- Ryu/Open vSwitch meter support must be verified on the actual machine; an OpenFlow error in the controller log means the corresponding meter operation may not have succeeded.
- The current controller rate-limits the heaviest sender's IPv4 traffic to the server. It does not implement a general QoS scheduler or rerouting.
- Traffic is not encrypted.
- Experiment outputs depend on the runtime environment and must be collected before performance claims are made.

## 13. Contributing and Git workflow

1. Edit only files assigned to you. Ask the owner before changing another member's files.
2. Do not commit directly to `main`; create a task branch such as `c/experiment-runner`.
3. Run syntax and functional checks before committing.
4. Stage only files you own; do not use `git add .` when other members' changes are present.
5. Pull/rebase from `origin/main` only after coordinating any shared changes. Resolve conflicts without discarding other members' work.
6. Push your branch and open a pull request for review.
7. Never force-push to the shared branch.

## 14. Documentation index

| Document | Owner | Contents |
|---|---|---|
| `docs/protocol.md` | A | Application messages and error codes |
| `docs/sdn_design.md` | B | OpenFlow rules, policies and thresholds |
| `docs/architecture.md` | C | Components, topology and communication flow |
| `docs/test_cases.md` | C | Test scenarios and implementation/test status |
