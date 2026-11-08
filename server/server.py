import socket
import threading
import json
import argparse
from datetime import datetime, timezone
from exam_logic import ExamLogic

LOG_FILE = "server.log"
exam = ExamLogic()

def log_event(student_id, event, details=""):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_line = f"{timestamp} | {student_id} | {event} | {details}\n"
    print(log_line.strip())
    with open(LOG_FILE, "a") as f:
        f.write(log_line)

def notify_controller(event_name, data):
    # Stub: Leave until Member C's notifier.py and B's controller endpoint are merged
    pass

def handle_client(conn, addr):
    student_id = "UNKNOWN"
    log_event(student_id, "connection_established", f"ip={addr[0]} port={addr[1]}")
    
    try:
        buffer = ""
        while True:
            data = conn.recv(1024).decode('utf-8')
            if not data:
                break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line.strip():
                    continue
                
                msg = json.loads(line)
                msg_type = msg.get("type")

                if msg_type == "LOGIN":
                    student_id = msg.get("student_id")
                    log_event(student_id, "student_joined", f"ip={addr[0]} port={addr[1]}")
                    notify_controller("student_joined", {"student_id": student_id})
                    
                    ack = {"type": "ACK", "status": "OK", "message": "Login successful"}
                    conn.sendall((json.dumps(ack) + "\n").encode('utf-8'))
                    
                    q1 = exam.get_question(0)
                    if q1:
                        q1_msg = {"type": "QUESTION", **q1}
                        conn.sendall((json.dumps(q1_msg) + "\n").encode('utf-8'))

                elif msg_type == "ANSWER":
                    q_id = msg.get("question_id")
                    sel = msg.get("selected_option")
                    correct = exam.check_answer(student_id, q_id, sel)
                    log_event(student_id, "answer_submitted", f"q_id={q_id} correct={correct}")

                    res = exam.get_result(student_id)
                    conn.sendall((json.dumps(res) + "\n").encode('utf-8'))

    except Exception as e:
        log_event(student_id, "error", str(e))
    finally:
        log_event(student_id, "student_left", "reason=disconnected")
        notify_controller("student_left", {"student_id": student_id})
        conn.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on")
    args = parser.parse_args()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", args.port))
    server.listen(5)
    print(f"Server started listening on 0.0.0.0:{args.port}")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()

if __name__ == "__main__":
    main()