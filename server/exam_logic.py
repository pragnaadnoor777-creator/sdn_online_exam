import json
import os

class ExamLogic:
    def __init__(self, questions_file="questions.json"):
        if os.path.exists(questions_file):
            with open(questions_file, "r", encoding="utf-8") as f:
                self.questions = json.load(f)
        else:
            self.questions = [
                {
                    "question_id": 1,
                    "text": "What does SDN stand for?",
                    "options": [
                        "Software-Defined Networking",
                        "System-Defined Network",
                        "Secure Data Node",
                        "Synchronous Data Transmission"
                    ],
                    "answer": 0
                },
                {
                    "question_id": 2,
                    "text": "Which protocol is commonly used by SDN controllers?",
                    "options": ["BGP", "OpenFlow", "OSPF", "RIP"],
                    "answer": 1
                },
                {
                    "question_id": 3,
                    "text": "Which Mininet link class configures bandwidth and delay?",
                    "options": ["Link", "TCLink", "Intf", "OVSLink"],
                    "answer": 1
                }
            ]
        self.student_scores = {}
        self.answered_questions = {}

    def total_questions(self):
        return len(self.questions)

    def get_question(self, index):
        if 0 <= index < len(self.questions):
            q = self.questions[index].copy()
            q.pop("answer", None)
            return q
        return None

    def check_answer(self, student_id, question_id, selected_option):
        if isinstance(selected_option, bool) or not isinstance(selected_option, int):
            raise ValueError("selected_option must be an integer")

        for q in self.questions:
            if q["question_id"] == question_id:
                if not (0 <= selected_option < len(q["options"])):
                    raise ValueError("selected_option out of valid option range")

                answered = self.answered_questions.setdefault(student_id, set())
                if question_id in answered:
                    return False  # Already answered; cannot score twice

                answered.add(question_id)
                self.student_scores.setdefault(student_id, 0)
                is_correct = (q["answer"] == selected_option)
                if is_correct:
                    self.student_scores[student_id] += 1
                return is_correct

        raise ValueError(f"Invalid question_id: {question_id}")

    def get_result(self, student_id):
        score = self.student_scores.get(student_id, 0)
        total = len(self.questions)
        return {
            "type": "RESULT",
            "student_id": student_id,
            "score": score,
            "total": total,
            "passed": score >= (total / 2)
        }