"""Computes metrics from experiment runs and plots baseline vs SDN. Owner: Member C.

Usage (from the repo root):  python3 experiments/analyze.py [results/raw]

Each run folder is named  <mode>_<N>students_<load>load_<run>  and holds:
  client_events.csv     timestamp,student_id,event,question_id,details       (written by client/auto_client.py)
  controller_stats.csv  timestamp,srv_link_mbps,utilization_pct,congested,limited_ports   (written by the controller)
  iperf_receiver.log    UDP report of the background traffic (optional)

Latency of one answer = time between ANSWER_SENT and ACK_RECEIVED of the same student and question.
Records are paired by student_id + question_id; if the same student answers the same question several times,
the 1st ANSWER_SENT is paired with the 1st ACK_RECEIVED, the 2nd with the 2nd, and so on.
Outputs: results/graphs/summary.csv, results/graphs/latency_<load>.png, results/graphs/utilization.png
"""
import glob
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RUN_RE = re.compile(r"(?P<mode>baseline|sdn)_(?P<n>\d+)students_(?P<load>[a-z]+?)load_(?P<run>\d+)")
UDP_RE = re.compile(r"([\d.]+)\s+([KMG])bits/sec.*?(\d+)\s*/\s*(\d+)\s*\(([\d.]+)%\)")


def parse_ts(series):
    """ISO strings or epoch seconds -> datetime."""
    num = pd.to_numeric(series, errors="coerce")
    if num.notna().all():
        return pd.to_datetime(num, unit="s")
    return pd.to_datetime(series, errors="coerce")


def jain_index(values):
    """Fairness: 1.0 = perfectly fair. (sum x)^2 / (n * sum x^2)."""
    values = [v for v in values if v > 0]
    if not values:
        return float("nan")
    return sum(values) ** 2 / (len(values) * sum(v * v for v in values))


def client_metrics(folder):
    path = os.path.join(folder, "client_events.csv")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    df = pd.read_csv(path)
    needed = {"timestamp", "student_id", "event", "question_id"}
    if not needed.issubset(df.columns):
        print("  skipped {}: client_events.csv has columns {} (expected {})".format(
            os.path.basename(folder), list(df.columns), sorted(needed)))
        return None
    df["timestamp"] = parse_ts(df["timestamp"])
    df["question_id"] = df["question_id"].astype(str)
    sent = df[df.event == "ANSWER_SENT"].copy()
    ack = df[df.event == "ACK_RECEIVED"].copy()
    keys = ["student_id", "question_id"]
    sent["k"] = sent.groupby(keys).cumcount()
    ack["k"] = ack.groupby(keys).cumcount()
    pairs = sent.merge(ack, on=keys + ["k"], suffixes=("_sent", "_ack"))
    pairs["latency_ms"] = (pairs["timestamp_ack"] - pairs["timestamp_sent"]).dt.total_seconds() * 1000
    pairs = pairs[pairs["latency_ms"] >= 0]
    if pairs.empty:
        print("  skipped {}: no ANSWER_SENT / ACK_RECEIVED pairs".format(os.path.basename(folder)))
        return None
    per_student = pairs.groupby("student_id")["latency_ms"].mean()
    errors = df["event"].astype(str).str.contains("ERROR|TIMEOUT|FAIL", case=False).sum()
    return {
        "answers": len(pairs),
        "unanswered": max(len(sent) - len(pairs), 0),
        "mean_latency_ms": pairs["latency_ms"].mean(),
        "p95_latency_ms": pairs["latency_ms"].quantile(0.95),
        "max_latency_ms": pairs["latency_ms"].max(),
        "fairness": jain_index(list(1.0 / per_student[per_student > 0])),   # fairness of per-student speed
        "error_events": int(errors),
    }


def controller_metrics(folder):
    path = os.path.join(folder, "controller_stats.csv")
    empty = {"mean_util_pct": float("nan"), "max_util_pct": float("nan"),
             "congested_pct": float("nan"), "limit_active_pct": float("nan")}
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return empty
    df = pd.read_csv(path)
    if "utilization_pct" not in df.columns:
        return empty
    congested = df["congested"].astype(str).str.strip().str.lower().isin(["1", "true", "yes"])
    limited = ~df["limited_ports"].astype(str).str.strip().str.lower().isin(["", "[]", "none", "nan", "{}"])
    return {"mean_util_pct": df["utilization_pct"].mean(), "max_util_pct": df["utilization_pct"].max(),
            "congested_pct": congested.mean() * 100, "limit_active_pct": limited.mean() * 100}


def iperf_metrics(folder):
    """Loss and throughput of the background UDP traffic, from the iperf receiver report (optional)."""
    path = os.path.join(folder, "iperf_receiver.log")
    out = {"bg_mbps": float("nan"), "bg_loss_pct": float("nan")}
    if not os.path.exists(path):
        return out
    last = None
    for line in open(path, errors="ignore"):
        m = UDP_RE.search(line)
        if m:
            last = m
    if last:
        rate, unit = float(last.group(1)), last.group(2)
        out["bg_mbps"] = rate * {"K": 0.001, "M": 1, "G": 1000}[unit]
        out["bg_loss_pct"] = float(last.group(5))
    return out


def main(results_dir):
    rows = []
    for folder in sorted(glob.glob(os.path.join(results_dir, "*"))):
        m = RUN_RE.fullmatch(os.path.basename(folder))
        if not m or not os.path.isdir(folder):
            continue
        cm = client_metrics(folder)
        if cm:
            rows.append({**m.groupdict(), **cm, **controller_metrics(folder), **iperf_metrics(folder)})
    if not rows:
        print("No usable run folders in", results_dir)
        return
    df = pd.DataFrame(rows)
    df["n"] = df["n"].astype(int)
    order = {"none": 0, "medium": 1, "heavy": 2}
    cols = ["answers", "mean_latency_ms", "p95_latency_ms", "max_latency_ms", "fairness", "error_events",
            "mean_util_pct", "congested_pct", "limit_active_pct", "bg_mbps", "bg_loss_pct"]
    summary = df.groupby(["load", "n", "mode"])[cols].mean().round(2)
    summary = summary.sort_index(key=lambda idx: idx.map(order) if idx.name == "load" else idx)
    pd.set_option("display.width", 200, "display.max_columns", 20)
    print(summary)
    os.makedirs("results/graphs", exist_ok=True)
    summary.to_csv("results/graphs/summary.csv")

    for load, sub in df.groupby("load"):
        pivot = sub.groupby(["n", "mode"])["mean_latency_ms"].mean().unstack()
        pivot.plot(kind="bar", title="Mean answer latency, load={}".format(load))
        plt.xlabel("Number of students")
        plt.ylabel("Latency (ms)")
        plt.tight_layout()
        plt.savefig("results/graphs/latency_{}.png".format(load))
        plt.close()
    if df["mean_util_pct"].notna().any():
        pivot = df.groupby(["load", "mode"])["mean_util_pct"].mean().unstack()
        pivot.plot(kind="bar", title="Mean utilization of the srv link")
        plt.ylabel("Utilization (%)")
        plt.tight_layout()
        plt.savefig("results/graphs/utilization.png")
        plt.close()
    print("Saved results/graphs/summary.csv and the graphs")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results/raw")