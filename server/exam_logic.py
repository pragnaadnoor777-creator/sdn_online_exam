class ExamLogic:
    def __init__(self):
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
            }
        ]
        self.student_scores = {}

    def get_question(self, index):
        if 0 <= index < len(self.questions):
            q = self.questions[index].copy()
            del q["answer"]  # Do not expose the answer key to client
            return q
        return None

    def check_answer(self, student_id, question_id, selected_option):
        for q in self.questions:
            if q["question_id"] == question_id:
                is_correct = (q["answer"] == selected_option)
                if student_id not in self.student_scores:
                    self.student_scores[student_id] = 0
                if is_correct:
                    self.student_scores[student_id] += 1
                return is_correct
        return False

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