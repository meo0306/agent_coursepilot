"""
Streamlit 前端界面
用页面控件收集 CoursePilot 业务参数，然后通过 CoursePilotClient 调 FastAPI 后端接口，展示返回结果
每次用户交互后，脚本通常会从上到下重新执行一次
"""

from pathlib import Path

import streamlit as st

from client import AgentClientError, CoursePilotClient


def render_knowledge_base_page(base_url: str, headers: dict[str, str] | None = None) -> None:
    """
    base_url: str, FastAPI 后端服务的 base URL
    headers: dict[str, str] | None, 可选的 HTTP 请求头，用于身份验证等
    """
    # 初始化 CoursePilotClient
    headers = headers or {}
    client = CoursePilotClient(base_url=base_url, headers=headers, timeout=30)
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
            try:
                course = client.create_course(
                    {
                        "course_name": course_name,
                        "course_type": course_type,
                        "student_level": student_level,
                        "student_background": student_background,
                        "description": description,
                    }
                )
                st.success("Course created")
                st.json(course)
            except AgentClientError as exc:
                st.error(str(exc))

    # 加载已创建的课程
    try:
        courses = client.list_courses()
    except AgentClientError as exc:
        st.error(f"Failed to load courses: {exc}")
        return
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
    source_type = st.selectbox(
        "Source type",
        options=["textbook", "syllabus", "lecture", "knowledge_graph", "other"],
    )
    uploaded_file = st.file_uploader("Upload PDF/DOCX/TXT/MD/XLSX")
    # 点击上传按钮后调用后端接口上传文档
    if uploaded_file and st.button("Upload document"):
        try:
            uploaded = client.upload_document(
                course_id,
                filename=uploaded_file.name,
                content=uploaded_file.getvalue(),
                source_type=source_type,
            )
            st.success("Document uploaded")
            st.json(uploaded)
        except AgentClientError as exc:
            st.error(str(exc))

    # 构建知识库
    # 获取已上传的文档列表
    try:
        documents = client.list_documents(course_id)
    except AgentClientError:
        documents = []
    # 如有，则可选择并构建知识库（解析文档、切 chunk、写 Chroma、写数据库）
    if documents:
        document_options = {f"{doc['file_name']} [{doc['parse_status']}]": doc for doc in documents}
        selected_document_label = st.selectbox("Document", options=list(document_options))
        selected_document = document_options[selected_document_label]
        if st.button("Build knowledge base"):
            try:
                build = client.build_kb(selected_document["id"])
                st.success("Knowledge base build finished")
                st.json(build)
            except AgentClientError as exc:
                st.error(str(exc))

    # 功能1：检索知识库
    st.subheader("Search")
    query = st.text_input("Query")
    top_k = st.slider("Top K", min_value=1, max_value=20, value=5)
    if query and st.button("Search knowledge base"):
        try:
            search_response = client.search_kb(course_id, {"query": query, "top_k": top_k})
        except AgentClientError as exc:
            st.error(str(exc))
            return
        # 逐条展示检索结果
        for result in search_response["results"]:
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
        session_duration = st.number_input(
            "Session duration", min_value=15, max_value=240, value=45
        )
        teaching_template = st.text_input("Teaching template", value="standard")
        teaching_focus = st.text_input("Teaching focus")
        additional_requirements = st.text_area("Additional requirements")
        generate_lesson = st.form_submit_button("Generate lesson design")
    # 发送请求
    if generate_lesson:
        try:
            lesson_response = client.generate_lesson(
                course_id,
                {
                    "chapter_range": chapter_range,
                    "total_sessions": int(total_sessions),
                    "session_duration": int(session_duration),
                    "teaching_template": teaching_template,
                    "teaching_focus": teaching_focus or None,
                    "additional_requirements": additional_requirements or None,
                },
            )
            st.success("Lesson design generated")
            # 保存 lesson id，实现跨 Streamlit rerun 保留状态（防止页面刷新导致ID丢失）
            st.session_state["coursepilot_last_lesson_id"] = lesson_response["lesson_id"]
            st.json(lesson_response)
        except AgentClientError as exc:
            st.error(str(exc))

    # 导出文档
    lesson_id = st.text_input(
        "Lesson ID",
        value=st.session_state.get("coursepilot_last_lesson_id", ""),
    )
    if lesson_id and st.button("Export lesson DOCX"):
        try:
            export_response = client.export_lesson(lesson_id)
            st.success("Lesson DOCX exported")
            st.json(export_response)
        except AgentClientError as exc:
            st.error(str(exc))

    # 功能3：生成试卷
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
        try:
            blueprint_response = client.create_exam_blueprint(course_id, payload)
            st.success("Exam blueprint created")
            # 保存blueprint_id
            st.session_state["coursepilot_last_exam_blueprint_id"] = blueprint_response[
                "blueprint_id"
            ]
            st.json(blueprint_response)
        except AgentClientError as exc:
            st.error(str(exc))

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
        try:
            confirm_response = client.confirm_exam_blueprint(exam_blueprint_id)
            st.success("Exam blueprint confirmed")
            st.json(confirm_response)
        except AgentClientError as exc:
            st.error(str(exc))
    # 生成试卷
    if generate_exam:
        try:
            generated_response = client.generate_questions(exam_blueprint_id)
            st.success("Exam questions generated")
            st.json(generated_response)
        except AgentClientError as exc:
            st.error(str(exc))
    # 导出试卷
    if export_exam:
        try:
            export_response = client.export_exam(exam_blueprint_id)
            st.success("Exam files exported")
            st.json(export_response)
        except AgentClientError as exc:
            st.error(str(exc))

    # 功能4：生成PPT
    st.subheader("Generate PPT")
    # 获取用户输入基本配置
    with st.form("generate_ppt"):
        ppt_lesson_id = st.text_input(
            "PPT lesson ID",
            value=st.session_state.get("coursepilot_last_lesson_id", ""),
        )
        ppt_slide_count = st.number_input("Slide count", min_value=3, max_value=60, value=8)
        ppt_style = st.text_input("PPT style template", value="standard")
        include_references = st.checkbox("Include references slide", value=True)
        generate_ppt = st.form_submit_button("Generate PPT outline")
    # 点击按钮后请求后端生成
    if generate_ppt:
        try:
            ppt_response = client.generate_ppt_outline(
                ppt_lesson_id,
                {
                    "slide_count": int(ppt_slide_count),
                    "style_template": ppt_style,
                    "include_references": include_references,
                },
            )
            st.success("PPT outline generated")
            st.session_state["coursepilot_last_ppt_outline_id"] = ppt_response["outline_id"]
            st.json(ppt_response)
        except AgentClientError as exc:
            st.error(str(exc))

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
    # 点击导出按钮后调用后端接口
    if export_ppt:
        try:
            export_response = client.export_ppt(ppt_outline_id)
            st.success("PPTX exported")
            st.json(export_response)
        except AgentClientError as exc:
            st.error(str(exc))

    if approve_ppt:
        try:
            review_response = client.create_review(
                {
                    "target_type": "ppt_outline",
                    "target_id": ppt_outline_id,
                    "review_status": "approved",
                    "comment": "Approved from Streamlit demo.",
                }
            )
            st.success("PPT approved")
            st.session_state["coursepilot_last_review_id"] = review_response["id"]
            st.json(review_response)
        except AgentClientError as exc:
            st.error(str(exc))

    if write_back_ppt:
        review_id = st.session_state.get("coursepilot_last_review_id")
        if not isinstance(review_id, str) or not review_id:
            st.warning("Approve a PPT outline before writing it back")
        else:
            try:
                write_back_response = client.write_back_review(review_id)
                st.success("Approved PPT written back to knowledge base")
                st.json(write_back_response)
            except AgentClientError as exc:
                st.error(str(exc))
