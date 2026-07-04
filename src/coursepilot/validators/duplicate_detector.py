from coursepilot.rag.embeddings import HashingEmbeddings
from coursepilot.schemas.question_schema import QuestionItem


class DuplicateDetector:
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self.embeddings = HashingEmbeddings()

    def detect(self, questions: list[QuestionItem]) -> tuple[float, list[tuple[int, int]]]:
        if len(questions) < 2:
            return 0.0, []

        vectors = self.embeddings.embed_documents([question.question_text for question in questions])
        duplicate_pairs: list[tuple[int, int]] = []
        for i in range(len(vectors)):
            for j in range(i + 1, len(vectors)):
                similarity = sum(a * b for a, b in zip(vectors[i], vectors[j], strict=False))
                if similarity >= self.threshold:
                    duplicate_pairs.append((i + 1, j + 1))

        total_pairs = len(questions) * (len(questions) - 1) / 2
        duplicate_rate = len(duplicate_pairs) / total_pairs if total_pairs else 0.0
        return duplicate_rate, duplicate_pairs

