import socket
import json
import argparse
import csv
import os
import random
import threading
import time
from datetime import datetime, timezone

csv_lock = threading.Lock()

def log_csv_event(results_dir, student_id, event, question_id="", details=""):
    if not results_dir:
        return
    os.makedirs(results_dir, exist_ok=True)
    csv_path = os.path.join(results_dir, "client_events.csv")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    with csv_lock:
        file_exists = os.path.exists(csv_path)
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "student_id", "event", "question_id", "details"])
            writer.writerow([timestamp, student_id, event, question_id, details])

def run_student(student_id, name, host="127.0.0.1", port=5000, results_dir=None, auto_mode=False, delay=0.05):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(30.0)
    client.connect((host, port))

    login_msg = {"type": "LOGIN", "student_id": student_id, "name": name}
    client.sendall((json.dumps(login_msg) + "\n").encode("utf-8"))

    last_question_id = ""
    result_data = None
    buffer = ""

    try:
        while True:
            data = client.recv(1024).decode("utf-8")
            if not data:
                break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line.strip():
                    continue
                msg = json.loads(line)
                mtype = msg.get("type")

                if mtype == "ACK":
                    if last_question_id != "":
                        log_csv_event(results_dir, student_id, "ACK_RECEIVED", last_question_id, msg.get("message", ""))
                    if not auto_mode:
                        print(f"[SERVER]: {msg.get('message')}")

                elif mtype == "START":
                    if not auto_mode:
                        print(f"[EXAM STARTED] Questions: {msg.get('total_questions')} | Duration: {msg.get('duration_seconds')}s")

                elif mtype == "QUESTION":
                    q_id = msg["question_id"]
                    last_question_id = q_id
                    options = msg["options"]

                    if auto_mode:
                        if delay > 0:
                            time.sleep(delay)
                        choice = random.randint(0, len(options) - 1)
                    else:
                        print(f"\nQuestion {q_id}: {msg['text']}")
                        for idx, opt in enumerate(options):
                            print(f"  [{idx}] {opt}")
                        choice = int(input("Select option index: "))

                    ans = {
                        "type": "ANSWER",
                        "student_id": student_id,
                        "question_id": q_id,
                        "selected_option": choice
                    }
                    log_csv_event(results_dir, student_id, "ANSWER_SENT", q_id, f"selected_option={choice}")
                    client.sendall((json.dumps(ans) + "\n").encode("utf-8"))

                elif mtype == "TIME_UP":
                    if not auto_mode:
                        print(f"\n[TIME UP]: {msg.get('reason')}")

                elif mtype == "RESULT":
                    result_data = msg
                    if not auto_mode:
                        print("\n--- EXAM RESULT ---")
                        print(f"Score: {msg['score']}/{msg['total']} | Passed: {msg['passed']}")
                    return result_data

                elif mtype == "ERROR":
                    if not auto_mode:
                        print(f"[ERROR {msg.get('code')}]: {msg.get('message')}")
                    if msg.get("code") in (401, 409):
                        return None
    finally:
        client.close()

    return result_data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server IP")
    parser.add_argument("--port", type=int, default=5000, help="Server Port")
    parser.add_argument("--results-dir", "--out-dir", dest="results_dir", type=str, default="results/raw/manual", help="Directory for CSV event logs")
    args = parser.parse_args()

    student_id = input("Enter Student ID (e.g. S101): ").strip()
    name = input("Enter Full Name: ").strip()
    run_student(student_id, name, host=args.host, port=args.port, results_dir=args.results_dir, auto_mode=False)

if __name__ == "__main__":
    main()