import socket
import json
import argparse
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server IP")
    parser.add_argument("--port", type=int, default=5000, help="Server Port")
    args = parser.parse_args()

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((args.host, args.port))
    
    student_id = input("Enter Student ID (e.g. S101): ").strip()
    name = input("Enter Full Name: ").strip()

    login_msg = {"type": "LOGIN", "student_id": student_id, "name": name}
    client.sendall((json.dumps(login_msg) + "\n").encode('utf-8'))

    buffer = ""
    while True:
        data = client.recv(1024).decode('utf-8')
        if not data:
            break
        buffer += data
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            msg = json.loads(line)
            
            if msg["type"] == "ACK":
                print(f"[SERVER]: {msg['message']}")
            elif msg["type"] == "QUESTION":
                print(f"\nQuestion {msg['question_id']}: {msg['text']}")
                for idx, opt in enumerate(msg["options"]):
                    print(f"  [{idx}] {opt}")
                choice = int(input("Select option index: "))
                
                ans = {"type": "ANSWER", "student_id": student_id, "question_id": msg['question_id'], "selected_option": choice}
                client.sendall((json.dumps(ans) + "\n").encode('utf-8'))
            elif msg["type"] == "RESULT":
                print(f"\n--- EXAM RESULT ---")
                print(f"Score: {msg['score']}/{msg['total']} | Passed: {msg['passed']}")
                client.close()
                sys.exit(0)

if __name__ == "__main__":
    main()