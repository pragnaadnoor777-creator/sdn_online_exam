import socket
import threading
import json
import argparse
import os
import sys
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from exam_logic import ExamLogic

try:
    from integration.notifier import notify_controller
except ImportError:
    def notify_controller(event_name, data=None):
        pass

LOG_FILE = "server.log"
exam = ExamLogic()
active_students = set()
active_students_lock = threading.Lock()
had_students = False

def load_config():
    cfg_path = os.path.join(PROJECT_ROOT, "config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def log_event(student_id, event, details=""):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_line = f"{timestamp} | {student_id} | {event} | {details}\n"
    print(log_line.strip())
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line)

def emit_controller_event(event_name, payload):
    try:
        notify_controller(event_name, payload)
    except Exception as e:
        log_event("SYSTEM", "notifier_error", f"event={event_name} err={e}")

def send_json(conn, send_lock, payload):
    with send_lock:
        conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))

def send_error(conn, send_lock, code, message):
    send_json(conn, send_lock, {"type": "ERROR", "code": code, "message": message})

def handle_client(conn, addr, exam_duration):
    global had_students
    student_id = None
    current_q_idx = 0
    finished = False
    timer = None
    send_lock = threading.Lock()

    log_event("UNKNOWN", "connection_established", f"ip={addr[0]} port={addr[1]}")

    def on_time_up():
        nonlocal finished
        if finished or not student_id:
            return
        finished = True
        log_event(student_id, "time_up", f"duration={exam_duration}s")
        try:
            send_json(conn, send_lock, {"type": "TIME_UP", "reason": "Exam duration expired"})
            send_json(conn, send_lock, exam.get_result(student_id))
            conn.close()
        except OSError:
            pass

    try:
        buffer = ""
        while not finished:
            data = conn.recv(1024).decode("utf-8")
            if not data:
                break
            buffer += data
            while "\n" in buffer and not finished:
                line, buffer = buffer.split("\n", 1)
                if not line.strip():
                    continue

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    send_error(conn, send_lock, 400, "Invalid JSON format")
                    continue

                msg_type = msg.get("type")
                if not msg_type:
                    send_error(conn, send_lock, 400, "Missing 'type' field")
                    continue

                if msg_type == "LOGIN":
                    sid = msg.get("student_id")
                    if not sid:
                        send_error(conn, send_lock, 400, "Missing 'student_id'")
                        continue

                    with active_students_lock:
                        if sid in active_students:
                            send_error(conn, send_lock, 409, f"Student {sid} already logged in")
                            log_event(sid, "login_failed", "reason=already_logged_in")
                            continue
                        active_students.add(sid)
                        had_students = True

                    student_id = sid
                    log_event(student_id, "student_joined", f"ip={addr[0]} port={addr[1]}")
                    emit_controller_event("student_joined", {"student_id": student_id, "ip": addr[0]})

                    send_json(conn, send_lock, {"type": "ACK", "status": "OK", "message": "Login successful"})
                    send_json(conn, send_lock, {
                        "type": "START",
                        "duration_seconds": exam_duration,
                        "total_questions": exam.total_questions()
                    })

                    timer = threading.Timer(exam_duration, on_time_up)
                    timer.daemon = True
                    timer.start()

                    q = exam.get_question(current_q_idx)
                    if q:
                        send_json(conn, send_lock, {"type": "QUESTION", **q})

                elif msg_type == "ANSWER":
                    if not student_id:
                        send_error(conn, send_lock, 401, "Unauthorized: Must LOGIN first")
                        continue

                    q_id = msg.get("question_id")
                    sel = msg.get("selected_option")
                    if q_id is None or sel is None:
                        send_error(conn, send_lock, 400, "Missing question_id or selected_option")
                        continue

                    try:
                        correct = exam.check_answer(student_id, q_id, sel)
                    except ValueError as ve:
                        send_error(conn, send_lock, 400, str(ve))
                        continue

                    log_event(student_id, "answer_submitted", f"q_id={q_id} correct={correct}")
                    send_json(conn, send_lock, {
                        "type": "ACK",
                        "status": "OK",
                        "question_id": q_id,
                        "message": "Answer recorded"
                    })

                    current_q_idx += 1
                    next_q = exam.get_question(current_q_idx)
                    if next_q:
                        send_json(conn, send_lock, {"type": "QUESTION", **next_q})
                    else:
                        finished = True
                        if timer:
                            timer.cancel()
                        send_json(conn, send_lock, exam.get_result(student_id))

                else:
                    send_error(conn, send_lock, 400, f"Unknown message type: {msg_type}")

    except OSError:
        pass
    except Exception as e:
        log_event(student_id or "UNKNOWN", "error", str(e))
    finally:
        if timer:
            timer.cancel()
        if student_id:
            all_done = False
            with active_students_lock:
                active_students.discard(student_id)
                if had_students and len(active_students) == 0:
                    all_done = True
            log_event(student_id, "student_left", "reason=disconnected")
            emit_controller_event("student_left", {"student_id": student_id})
            if all_done:
                log_event("SYSTEM", "exam_end", "reason=all_students_completed")
                emit_controller_event("exam_end", {"reason": "all_students_completed"})
        try:
            conn.close()
        except OSError:
            pass

def main():
    cfg = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=cfg.get("server_port", 5000), help="Port to listen on")
    parser.add_argument("--duration", type=int, default=cfg.get("exam_duration", 60), help="Exam duration in seconds")
    args = parser.parse_args()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", args.port))
    server.listen(64)

    log_event("SYSTEM", "exam_start", f"port={args.port} duration={args.duration}s")
    emit_controller_event("exam_start", {"port": args.port, "duration": args.duration})

    try:
        while True:
            conn, addr = server.accept()
            threading.Thread(
                target=handle_client,
                args=(conn, addr, args.duration),
                daemon=True
            ).start()
    except KeyboardInterrupt:
        log_event("SYSTEM", "exam_end", "reason=server_shutdown")
        emit_controller_event("exam_end", {"reason": "server_shutdown"})
    finally:
        server.close()

if __name__ == "__main__":
    main()