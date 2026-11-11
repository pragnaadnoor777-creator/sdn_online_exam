import unittest
import socket
import json
import threading
import time
import os
import sys

# Add server/ directory directly to sys.path so server.py can locate exam_logic
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../server'))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from exam_logic import ExamLogic
import server as server_app

TEST_PORT = 5055

class TestExamLogic(unittest.TestCase):
    def setUp(self):
        self.exam = ExamLogic()

    def test_question_retrieval_and_masking(self):
        q = self.exam.get_question(0)
        self.assertIsNotNone(q)
        self.assertNotIn("answer", q, "Server must not expose answer key to clients")
        self.assertEqual(q["question_id"], 1)

    def test_scoring_logic(self):
        correct = self.exam.check_answer("S101", 1, 0)
        self.assertTrue(correct)
        
        result = self.exam.get_result("S101")
        self.assertEqual(result["score"], 1)
        self.assertTrue(result["passed"])

    def test_incorrect_answer(self):
        correct = self.exam.check_answer("S102", 1, 3)
        self.assertFalse(correct)
        
        result = self.exam.get_result("S102")
        self.assertEqual(result["score"], 0)


class TestServerProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def run_server():
            sys.argv = ["server.py", "--port", str(TEST_PORT)]
            server_app.main()

        cls.server_thread = threading.Thread(
            target=run_server, 
            daemon=True
        )
        cls.server_thread.start()
        time.sleep(0.3)

    def connect_client(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", TEST_PORT))
        s.settimeout(2.0)
        rfile = s.makefile('r', encoding='utf-8')
        return s, rfile

    def send_json(self, sock, data):
        sock.sendall((json.dumps(data) + "\n").encode('utf-8'))

    def recv_json(self, rfile):
        line = rfile.readline()
        if not line:
            raise ConnectionResetError("Socket closed before receiving line")
        return json.loads(line)

    def test_login_flow(self):
        s, rfile = self.connect_client()
        self.send_json(s, {"type": "LOGIN", "student_id": "T101", "name": "Test User"})
        
        ack = self.recv_json(rfile)
        self.assertEqual(ack.get("type"), "ACK")
        self.assertEqual(ack.get("status"), "OK")
        
        q1 = self.recv_json(rfile)
        self.assertEqual(q1.get("type"), "QUESTION")
        
        rfile.close()
        s.close()


if __name__ == "__main__":
    unittest.main()