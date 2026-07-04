"""
Streamlit 前端界面
用页面控件收集 CoursePilot 业务参数，然后通过 httpx 调 FastAPI 后端接口，展示返回结果
每次用户交互后，脚本通常会从上到下重新执行一次
"""
from pathlib import Path

import httpx
import streamlit as st


def render_knowledge_base_page(base_url: str, headers: dict[str, str] | None = None) -> None:
    """
    base_url: str, FastAPI 后端服务的 base URL
    headers: dict[str, str] | None, 可选的 HTTP 请求头，用于身份验证等
    """
    headers = headers or {}
    st.title("CoursePilot Knowledge Base")

    # 创建课程
    with st.form("create_course"):  # 把多个输入控件包成一个表单
        st.subheader("Create course")
        course_name = st.text_input("Course name")
        course_type = st.text_input("Course type", value="theory")
        student_level = st.text_input("Student level", value="undergraduate")
        student_background = st.text_area("Student background")
        description = st.text_area("Description")
        # 点击button后提交
        submitted = st.form_submit_button("Create")
        if submitted:
            # 调用后端创建课程接口
            response = httpx.post(
                f"{base_url}/api/coursepilot/courses",
                headers=headers,
                json={
                    "course_name": course_name,
                    "course_type": course_type,
                    "student_level": student_level,
                    "student_background": student_background,
                    "description": description,
                },
                timeout=30,
            )
            # 处理后端响应返回状态
            if response.is_success:
                st.success("Course created")
            else:
                st.error(response.text)
    
    # 加载已创建的课程
    courses_response = httpx.get(f"{base_url}/api/coursepilot/courses", headers=headers, timeout=30)
    if not courses_response.is_success:
        st.error(f"Failed to load courses: {courses_response.text}")
        return

    courses = courses_response.json()
    if not courses:
        st.info("Create a course before uploading documents.")
        return

    # 选择课程
    course_options = {f"{course['course_name']} ({course['id']})": course for course in courses}
    selected_label = st.selectbox("Course", options=list(course_options))
    selected_course = course_options[selected_label]
    course_id = selected_course["id"]

    # 上传文档
    st.subheader("Upload and build")
    source_type = st.selectbox("Source type", options=["textbook", "syllabus", "lecture", "knowledge_graph", "other"])
    uploaded_file = st.file_uploader("Upload PDF/DOCX/TXT/MD/XLSX")
    # 点击上传按钮后构造上传请求（元信息存数据库）
    if uploaded_file and st.button("Upload document"):
        files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
        data = {"source_type": source_type}
        response = httpx.post(
            f"{base_url}/api/coursepilot/courses/{course_id}/documents/upload",
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )
        if response.is_success:
            st.success("Document uploaded")
            st.json(response.json())
        else:
            st.error(response.text)
    
    # 构建知识库
    # 获取已上传的文档列表
    documents_response = httpx.get(
        f"{base_url}/api/coursepilot/courses/{course_id}/documents",
        headers=headers,
        timeout=30,
    )
    documents = documents_response.json() if documents_response.is_success else []
    # 如有，则可选择并构建知识库（解析文档、切 chunk、写 Chroma、写数据库）
    if documents:
        document_options = {f"{doc['file_name']} [{doc['parse_status']}]": doc for doc in documents}
        selected_document_label = st.selectbox("Document", options=list(document_options))
        selected_document = document_options[selected_document_label]
        if st.button("Build knowledge base"):
            response = httpx.post(
                f"{base_url}/api/coursepilot/documents/{selected_document['id']}/build-kb",
                headers=headers,
                timeout=300,
            )
            if response.is_success:
                st.success("Knowledge base build finished")
                st.json(response.json())
            else:
                st.error(response.text)
    
    # 检索知识库
    st.subheader("Search")
    query = st.text_input("Query")
    top_k = st.slider("Top K", min_value=1, max_value=20, value=5)
    if query and st.button("Search knowledge base"):
        response = httpx.post(
            f"{base_url}/api/coursepilot/courses/{course_id}/kb/search",
            headers=headers,
            json={"query": query, "top_k": top_k},
            timeout=60,
        )
        if not response.is_success:
            st.error(response.text)
            return
        # 逐条展示检索结果
        for result in response.json()["results"]:
            source = Path(result.get("source_type") or "source").name
            st.markdown(
                f"**{source}** score={result['score']:.3f} "
                f"chunk=`{result['chunk_id']}` page={result.get('page')}"
            )
            st.write(result["content"][:1000])
    
    # 功能2：生成课程设计/教案
    st.subheader("Generate lesson design")  
    # 把多个输入控件包成一个表单form
    with st.form("generate_lesson"):
        chapter_range = st.text_input("Chapter range", value="第1章")
        total_sessions = st.number_input("Total sessions", min_value=1, max_value=12, value=2)
        session_duration = st.number_input("Session duration", min_value=15, max_value=240, value=45)
        teaching_template = st.text_input("Teaching template", value="standard")
        teaching_focus = st.text_input("Teaching focus")
        additional_requirements = st.text_area("Additional requirements")
        generate_lesson = st.form_submit_button("Generate lesson design")
    # 发送请求
    if generate_lesson:
        response = httpx.post(
            f"{base_url}/api/coursepilot/courses/{course_id}/lessons/generate",
            headers=headers,
            json={
                "chapter_range": chapter_range,
                "total_sessions": int(total_sessions),
                "session_duration": int(session_duration),
                "teaching_template": teaching_template,
                "teaching_focus": teaching_focus or None,
                "additional_requirements": additional_requirements or None,
            },
            timeout=180,
        )
        if not response.is_success:
            st.error(response.text)
        else:
            st.success("Lesson design generated")
            lesson_response = response.json()
            # 保存 lesson id，实现跨 Streamlit rerun 保留状态（防止页面刷新导致ID丢失）
            st.session_state["coursepilot_last_lesson_id"] = lesson_response["lesson_id"]
            st.json(lesson_response)
    
    # 导出文档
    lesson_id = st.text_input(
        "Lesson ID",
        value=st.session_state.get("coursepilot_last_lesson_id", ""),
    )
    if lesson_id and st.button("Export lesson DOCX"):
        response = httpx.post(
            f"{base_url}/api/coursepilot/lessons/{lesson_id}/export",
            headers=headers,
            timeout=120,
        )
        if response.is_success:
            st.success("Lesson DOCX exported")
            st.json(response.json())
        else:
            st.error(response.text)

    # 生成试卷
    st.subheader("Generate exam")
    # 获取试卷配置需求
    with st.form("create_exam_blueprint"):
        exam_chapter_range = st.text_input("Exam chapter range", value="Chapter 1")
        generation_type = st.selectbox("Generation type", options=["exam", "homework"])
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            single_count = st.number_input("Single choice", min_value=0, max_value=50, value=5)
            single_score = st.number_input("Single score", min_value=1, max_value=20, value=2)
        with col2:
            multiple_count = st.number_input("Multiple choice", min_value=0, max_value=50, value=2)
            multiple_score = st.number_input("Multiple score", min_value=1, max_value=20, value=3)
        with col3:
            judgement_count = st.number_input("Judgement", min_value=0, max_value=50, value=3)
            judgement_score = st.number_input("Judgement score", min_value=1, max_value=20, value=1)
        with col4:
            short_count = st.number_input("Short answer", min_value=0, max_value=20, value=2)
            short_score = st.number_input("Short score", min_value=1, max_value=50, value=10)
        additional_exam_requirements = st.text_area("Exam additional requirements")
        
        create_blueprint = st.form_submit_button("Create exam blueprint")
    # 创建蓝图/大纲
    if create_blueprint:
        # 组装 payload
        payload = {
            "chapter_range": exam_chapter_range,
            "generation_type": generation_type,
            "question_counts": {
                "single_choice": int(single_count),
                "multiple_choice": int(multiple_count),
                "judgement": int(judgement_count),
                "short_answer": int(short_count),
            },
            "score_per_question": {
                "single_choice": int(single_score),
                "multiple_choice": int(multiple_score),
                "judgement": int(judgement_score),
                "short_answer": int(short_score),
            },
            "additional_requirements": additional_exam_requirements or None,
        }
        # 请求后端
        response = httpx.post(
            f"{base_url}/api/coursepilot/courses/{course_id}/exams/blueprint",
            headers=headers,
            json=payload,
            timeout=120,
        )
        if response.is_success:
            st.success("Exam blueprint created")
            blueprint_response = response.json()
            # 保存blueprint_id
            st.session_state["coursepilot_last_exam_blueprint_id"] = blueprint_response["blueprint_id"]
            st.json(blueprint_response)
        else:
            st.error(response.text)
    
    # 调取当前blueprint_id
    exam_blueprint_id = st.text_input(
        "Exam blueprint ID",
        value=st.session_state.get("coursepilot_last_exam_blueprint_id", ""),
    )

    # 按钮交互
    col_confirm, col_generate, col_export = st.columns(3)
    with col_confirm:
        confirm_exam = st.button("Confirm blueprint", disabled=not bool(exam_blueprint_id))
    with col_generate:
        generate_exam = st.button("Generate questions", disabled=not bool(exam_blueprint_id))
    with col_export:
        export_exam = st.button("Export exam DOCX", disabled=not bool(exam_blueprint_id))
    # 人工确认
    if confirm_exam:
        response = httpx.post(
            f"{base_url}/api/coursepilot/exams/{exam_blueprint_id}/confirm",
            headers=headers,
            timeout=60,
        )
        if response.is_success:
            st.success("Exam blueprint confirmed")
            st.json(response.json())
        else:
            st.error(response.text)
    # 生成试卷
    if generate_exam:
        response = httpx.post(
            f"{base_url}/api/coursepilot/exams/{exam_blueprint_id}/generate",
            headers=headers,
            timeout=180,
        )
        if response.is_success:
            st.success("Exam questions generated")
            st.json(response.json())
        else:
            st.error(response.text)
    # 导出试卷
    if export_exam:
        response = httpx.post(
            f"{base_url}/api/coursepilot/exams/{exam_blueprint_id}/export",
            headers=headers,
            timeout=120,
        )
        if response.is_success:
            st.success("Exam files exported")
            st.json(response.json())
        else:
            st.error(response.text)

    st.subheader("Generate PPT")
    with st.form("generate_ppt"):
        ppt_lesson_id = st.text_input(
            "PPT lesson ID",
            value=st.session_state.get("coursepilot_last_lesson_id", ""),
        )
        ppt_slide_count = st.number_input("Slide count", min_value=3, max_value=60, value=8)
        ppt_style = st.text_input("PPT style template", value="standard")
        include_references = st.checkbox("Include references slide", value=True)
        generate_ppt = st.form_submit_button("Generate PPT outline")

    if generate_ppt:
        response = httpx.post(
            f"{base_url}/api/coursepilot/lessons/{ppt_lesson_id}/ppt/generate",
            headers=headers,
            json={
                "slide_count": int(ppt_slide_count),
                "style_template": ppt_style,
                "include_references": include_references,
            },
            timeout=120,
        )
        if response.is_success:
            st.success("PPT outline generated")
            ppt_response = response.json()
            st.session_state["coursepilot_last_ppt_outline_id"] = ppt_response["outline_id"]
            st.json(ppt_response)
        else:
            st.error(response.text)

    ppt_outline_id = st.text_input(
        "PPT outline ID",
        value=st.session_state.get("coursepilot_last_ppt_outline_id", ""),
    )
    col_ppt_export, col_ppt_review, col_ppt_writeback = st.columns(3)
    with col_ppt_export:
        export_ppt = st.button("Export PPTX", disabled=not bool(ppt_outline_id))
    with col_ppt_review:
        approve_ppt = st.button("Approve PPT", disabled=not bool(ppt_outline_id))
    with col_ppt_writeback:
        write_back_ppt = st.button(
            "Write back approved PPT",
            disabled=not bool(st.session_state.get("coursepilot_last_review_id")),
        )

    if export_ppt:
        response = httpx.post(
            f"{base_url}/api/coursepilot/ppt/{ppt_outline_id}/export",
            headers=headers,
            timeout=120,
        )
        if response.is_success:
            st.success("PPTX exported")
            st.json(response.json())
        else:
            st.error(response.text)

    if approve_ppt:
        response = httpx.post(
            f"{base_url}/api/coursepilot/reviews",
            headers=headers,
            json={
                "target_type": "ppt_outline",
                "target_id": ppt_outline_id,
                "review_status": "approved",
                "comment": "Approved from Streamlit demo.",
            },
            timeout=60,
        )
        if response.is_success:
            st.success("PPT approved")
            review_response = response.json()
            st.session_state["coursepilot_last_review_id"] = review_response["id"]
            st.json(review_response)
        else:
            st.error(response.text)

    if write_back_ppt:
        review_id = st.session_state.get("coursepilot_last_review_id")
        response = httpx.post(
            f"{base_url}/api/coursepilot/reviews/{review_id}/write-back",
            headers=headers,
            timeout=120,
        )
        if response.is_success:
            st.success("Approved PPT written back to knowledge base")
            st.json(response.json())
        else:
            st.error(response.text)
