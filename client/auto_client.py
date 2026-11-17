import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

from client import run_student

def main():
    parser = argparse.ArgumentParser(description="N-student concurrent exam simulator")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Exam server IP")
    parser.add_argument("--port", type=int, default=5000, help="Exam server port")
    parser.add_argument("-n", "--students", type=int, default=5, help="Number of concurrent students")
    parser.add_argument("--results-dir", "--out-dir", dest="results_dir", type=str, default="results/raw/run_1", help="Output directory for CSV logs")
    parser.add_argument("--delay", type=float, default=0.05, help="Delay (seconds) before answering each question")
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)
    print(f"Starting {args.students} simulated students against {args.host}:{args.port} -> {args.results_dir}")

    completed = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=args.students) as pool:
        futures = {}
        for i in range(1, args.students + 1):
            sid = f"S{i:03d}"
            name = f"AutoStudent_{i}"
            fut = pool.submit(
                run_student,
                student_id=sid,
                name=name,
                host=args.host,
                port=args.port,
                results_dir=args.results_dir,
                auto_mode=True,
                delay=args.delay
            )
            futures[fut] = sid

        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                res = fut.result()
                if res:
                    completed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"[{sid}] Error: {e}")
                failed += 1

    print(f"Simulation complete: {completed}/{args.students} succeeded, {failed} failed.")

if __name__ == "__main__":
    main()