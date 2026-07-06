"""
review write-back service
对已审核通过的教学设计、PPT大纲和题目进行写回
将其内容写入课程知识库供后续检索和使用
"""

from sqlalchemy.orm import Session

from coursepilot.models import Document, KnowledgeChunk, LessonDesign, Question, ReviewRecord, SlideOutline
from coursepilot.rag.vector_store import ChromaVectorStore, collection_name_for_course
from coursepilot.schemas.lesson_schema import LessonDesignContent
from coursepilot.schemas.ppt_schema import SlideOutlineContent
from coursepilot.schemas.review_schema import ReviewCreate, ReviewRead, ReviewWriteBackResponse


class ReviewService:
    def __init__(self, session: Session, vector_store: ChromaVectorStore | None = None):
        self.session = session
        self.vector_store = vector_store or ChromaVectorStore()

    def create_review(self, payload: ReviewCreate) -> ReviewRead:
        """创建审核记录，并更新目标对象的状态"""
        # 解析目标对象的课程ID
        course_id = self._resolve_course_id(payload.target_type, payload.target_id)
        if course_id is None:
            raise ValueError(f"Review target not found: {payload.target_type}/{payload.target_id}")
        # 创建审核记录
        review = ReviewRecord(
            course_id=course_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            review_status=payload.review_status,
            comment=payload.comment,
            write_back_status="pending" if payload.review_status == "approved" else "not_written",
        )
        # 将审核记录写入数据库，并更新目标对象的状态
        self.session.add(review)
        self._apply_target_status(payload.target_type, payload.target_id, payload.review_status)
        self.session.commit()
        self.session.refresh(review)
        return ReviewRead.model_validate(review)

    def write_back(self, review_id: str) -> ReviewWriteBackResponse | None:
        """将已审核通过的教学设计、PPT大纲或题目写回课程知识库"""
        # 1. 获取审核记录
        review = self.session.get(ReviewRecord, review_id)
        # 2. 分支处理流程
        # 2.1 如果审核记录不存在，返回 None
        if review is None:
            return None
        # 2.2 如果审核记录的状态不是 approved，则不写回，直接返回 write_back_status 为 skipped
        # 说明：只有审核通过的内容才会写回知识库，其他状态的内容不写回
        if review.review_status != "approved":
            review.write_back_status = "skipped"
            self.session.commit()
            return ReviewWriteBackResponse(
                review_id=review.id,
                target_type=review.target_type,
                target_id=review.target_id,
                write_back_status=review.write_back_status,
            )
        # 2.3 如果审核记录的状态是 approved，则进行写回操作
        # 
        review_document = self._create_review_document(review)
        chunks = self._chunks_for_review(review, review_document.id)
        texts = [chunk["text"] for chunk in chunks]
        ids = [chunk["id"] for chunk in chunks]
        metadatas = [chunk["metadata"] for chunk in chunks]
        # 将 chunks 写入 Chroma 向量库
        self.vector_store.add_verified_texts(
            course_id=review.course_id,
            texts=texts,
            ids=ids,
            metadatas=metadatas,
        )
        # 将 chunks 写入数据库
        collection = collection_name_for_course(review.course_id)
        for chunk in chunks:
            metadata = chunk["metadata"]
            self.session.add(
                KnowledgeChunk(
                    id=chunk["id"],
                    course_id=review.course_id,
                    document_id=review_document.id,
                    source_type=str(metadata["source_type"]),
                    chapter=metadata.get("chapter"),
                    section=metadata.get("section"),
                    page=metadata.get("page"),
                    title=metadata.get("title"),
                    content_preview=chunk["text"][:1000],
                    knowledge_points_json=chunk["knowledge_points"],
                    verified=True,
                    chroma_collection=collection,
                    chroma_doc_id=chunk["id"],
                )
            )
        # 更新审核记录的写回状态
        review.write_back_status = "written"
        self._apply_target_status(review.target_type, review.target_id, "approved")
        self.session.commit()
        return ReviewWriteBackResponse(
            review_id=review.id,
            target_type=review.target_type,
            target_id=review.target_id,
            write_back_status=review.write_back_status,
            written_chunk_ids=ids,
        )

    def _create_review_document(self, review: ReviewRecord) -> Document:
        """为审核记录创建一个虚拟的文档对象，用于存储写回的内容"""
        document = Document(
            course_id=review.course_id,
            file_name=f"review_{review.target_type}_{review.target_id}.json",
            file_path=f"review://{review.id}",
            file_type="review",
            source_type=f"reviewed_{review.target_type}",
            parse_status="built",
        )
        self.session.add(document)
        self.session.flush()
        return document

    def _chunks_for_review(self, review: ReviewRecord, document_id: str) -> list[dict]:
        """
        为审核记录生成内容块
        分块原理是：
        """
        # 根据目标类型，获取对应的内容并生成 chunks
        if review.target_type == "ppt_outline":
            # PPT outline：按 slide 切
            outline = self.session.get(SlideOutline, review.target_id)
            if outline is None:
                raise ValueError("PPT outline not found")
            content = SlideOutlineContent.model_validate(outline.outline_json)
            chunks = []
            for slide in content.slides:
                # 每一页 slide 生成一个 chunk
                chunk_id = f"review-{review.id}-slide-{slide.slide_index}"
                chunks.append(
                    {
                        "id": chunk_id,
                        "text": self._slide_text(content, slide.slide_index),
                        "knowledge_points": slide.bullet_points[:10],
                        "metadata": {
                            "chunk_id": chunk_id,
                            "document_id": document_id,
                            "source_type": "reviewed_ppt",
                            "chapter": content.chapter,
                            "section": f"slide-{slide.slide_index}",
                            "title": slide.title,
                            "verified": True,
                        },
                    }
                )
            return chunks
        if review.target_type == "lesson_design":
            # Lesson design：按 session 切
            lesson = self.session.get(LessonDesign, review.target_id)
            if lesson is None:
                raise ValueError("Lesson design not found")
            content = LessonDesignContent.model_validate(lesson.content_json)
            chunks = []
            for session in content.sessions:
                chunk_id = f"review-{review.id}-lesson-session-{session.session_index}"
                text = "\n".join(
                    [
                        content.course_name,
                        content.chapter,
                        session.session_title,
                        *session.teaching_objectives,
                        *session.key_points,
                        *[item.content for item in session.teaching_process],
                    ]
                )
                chunks.append(
                    {
                        "id": chunk_id,
                        "text": text,
                        "knowledge_points": session.key_points[:10],
                        "metadata": {
                            "chunk_id": chunk_id,
                            "document_id": document_id,
                            "source_type": "reviewed_lesson",
                            "chapter": content.chapter,
                            "section": f"session-{session.session_index}",
                            "title": session.session_title,
                            "verified": True,
                        },
                    }
                )
            return chunks
        if review.target_type == "question":
            # Question：一题一个 chunk
            question = self.session.get(Question, review.target_id)
            if question is None:
                raise ValueError("Question not found")
            chunk_id = f"review-{review.id}-question-{question.id}"
            parts = [
                question.question_text,
                f"Answer: {question.correct_answer}",
                f"Explanation: {question.explanation}",
            ]
            # 如果有选项，则把选项也加入 chunk 内容
            if question.options_json:
                parts.extend(f"{key}. {value}" for key, value in question.options_json.items())
            return [
                {
                    "id": chunk_id,
                    "text": "\n".join(parts),
                    "knowledge_points": [question.knowledge_point],
                    "metadata": {
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                        "source_type": "reviewed_question",
                        "chapter": None,
                        "section": question.question_type,
                        "title": question.knowledge_point,
                        "verified": True,
                    },
                }
            ]
        raise ValueError(f"Unsupported review target type: {review.target_type}")

    def _slide_text(self, outline: SlideOutlineContent, slide_index: int) -> str:
        """提取单个幻灯片的文本内容"""
        slide = outline.slides[slide_index - 1]
        parts = [outline.course_name, outline.chapter, slide.title, *slide.bullet_points]
        if slide.speaker_notes:
            parts.append(slide.speaker_notes)
        return "\n".join(parts)

    def _resolve_course_id(self, target_type: str, target_id: str) -> str | None:
        """解析目标对象的课程ID"""
        if target_type == "ppt_outline":
            target = self.session.get(SlideOutline, target_id)
        elif target_type == "lesson_design":
            target = self.session.get(LessonDesign, target_id)
        elif target_type == "question":
            target = self.session.get(Question, target_id)
        else:
            return None
        return target.course_id if target is not None else None

    def _apply_target_status(self, target_type: str, target_id: str, review_status: str) -> None:
        """根据审核状态更新目标对象的状态"""
        if target_type == "ppt_outline":
            target = self.session.get(SlideOutline, target_id)
        elif target_type == "lesson_design":
            target = self.session.get(LessonDesign, target_id)
        elif target_type == "question":
            target = self.session.get(Question, target_id)
        else:
            target = None
        if target is not None and hasattr(target, "status"):
            target.status = review_status
