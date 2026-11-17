import unittest
import threading
import time
import os
import sys
import tempfile

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../server"))
CLIENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../client"))
for p in (SERVER_DIR, CLIENT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from exam_logic import ExamLogic
import server as server_app
from client import run_student

TEST_PORT = 5056

class TestExamLogic(unittest.TestCase):
    def setUp(self):
        self.exam = ExamLogic()

    def test_question_retrieval_and_masking(self):
        q = self.exam.get_question(0)
        self.assertIsNotNone(q)
        self.assertNotIn("answer", q)
        self.assertEqual(q["question_id"], 1)

    def test_single_scoring_per_question(self):
        self.assertTrue(self.exam.check_answer("S101", 1, 0))
        self.assertFalse(self.exam.check_answer("S101", 1, 0))
        self.assertEqual(self.exam.get_result("S101")["score"], 1)

    def test_invalid_option_validation(self):
        with self.assertRaises(ValueError):
            self.exam.check_answer("S101", 1, 99)
        with self.assertRaises(ValueError):
            self.exam.check_answer("S101", 1, "0")


class TestFullProtocolAndClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def run_server():
            sys.argv = ["server.py", "--port", str(TEST_PORT), "--duration", "10"]
            server_app.main()

        cls.server_thread = threading.Thread(target=run_server, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    def test_full_exam_loop_and_csv_logging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            res = run_student("T201", "Alice", host="127.0.0.1", port=TEST_PORT, results_dir=tmpdir, auto_mode=True, delay=0.01)
            self.assertIsNotNone(res)
            self.assertEqual(res["type"], "RESULT")
            self.assertEqual(res["total"], 3)

            csv_file = os.path.join(tmpdir, "client_events.csv")
            self.assertTrue(os.path.exists(csv_file))
            with open(csv_file, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("ANSWER_SENT", content)
            self.assertIn("ACK_RECEIVED", content)


if __name__ == "__main__":
    unittest.main()