"""Computes metrics from experiment logs and plots baseline vs SDN. Owner: Member C.

Usage: python3 experiments/analyze.py <results_dir>
Run folders are named <mode>_<N>students_<load>load_<run>, for example sdn_10students_heavyload_1.
Each folder holds client_*.csv (timestamp,student_id,event,detail) and, optionally,
controller_stats.csv (timestamp,srv_link_mbps,utilization_pct,congested,limited_ports).
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


def jain_index(values):
    """Fairness: 1.0 = perfectly fair. (sum x)^2 / (n * sum x^2)."""
    values = [v for v in values if v > 0]
    if not values:
        return float("nan")
    return sum(values) ** 2 / (len(values) * sum(v * v for v in values))


def latency_metrics(folder):
    """Answer round-trip latency (ms) from client logs: ANSWER_SENT -> ACK_RECEIVED."""
    frames = [pd.read_csv(p) for p in glob.glob(os.path.join(folder, "client_*.csv"))]
    if not frames:
        return None
    df = pd.concat(frames)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    sent = df[df.event == "ANSWER_SENT"].set_index(["student_id", "detail"])["timestamp"]
    ack = df[df.event == "ACK_RECEIVED"].set_index(["student_id", "detail"])["timestamp"]
    lat = ((ack - sent).dropna().dt.total_seconds() * 1000).rename("latency_ms").reset_index()
    if lat.empty:
        return None
    per_student = lat.groupby("student_id")["latency_ms"].mean()
    return {
        "mean_latency_ms": lat["latency_ms"].mean(),
        "p95_latency_ms": lat["latency_ms"].quantile(0.95),
        "fairness": jain_index(list(1.0 / per_student)),  # fairness of per-student speed
        "answers": len(lat),
    }


def controller_metrics(folder):
    """Link utilization and time spent congested from the controller statistics (optional)."""
    path = os.path.join(folder, "controller_stats.csv")
    if not os.path.exists(path):
        return {"mean_util_pct": float("nan"), "congested_pct": float("nan")}
    df = pd.read_csv(path)
    return {
        "mean_util_pct": df["utilization_pct"].mean(),
        "congested_pct": df["congested"].mean() * 100,
    }


def main(results_dir):
    rows = []
    for folder in sorted(glob.glob(os.path.join(results_dir, "*"))):
        m = RUN_RE.fullmatch(os.path.basename(folder))
        if not m:
            continue
        lat = latency_metrics(folder)
        if lat:
            rows.append({**m.groupdict(), **lat, **controller_metrics(folder)})
    if not rows:
        print("No run folders with client logs found in", results_dir)
        return
    df = pd.DataFrame(rows)
    df["n"] = df["n"].astype(int)
    cols = ["mean_latency_ms", "p95_latency_ms", "fairness", "mean_util_pct", "congested_pct"]
    summary = df.groupby(["load", "n", "mode"])[cols].mean().round(2)
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
    print("Graphs saved in results/graphs/")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results/raw")