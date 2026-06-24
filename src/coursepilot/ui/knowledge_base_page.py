from pathlib import Path

import httpx
import streamlit as st


def render_knowledge_base_page(base_url: str, headers: dict[str, str] | None = None) -> None:
    headers = headers or {}
    st.title("CoursePilot Knowledge Base")

    with st.form("create_course"):
        st.subheader("Create course")
        course_name = st.text_input("Course name")
        course_type = st.text_input("Course type", value="theory")
        student_level = st.text_input("Student level", value="undergraduate")
        student_background = st.text_area("Student background")
        description = st.text_area("Description")
        submitted = st.form_submit_button("Create")
        if submitted:
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
            if response.is_success:
                st.success("Course created")
            else:
                st.error(response.text)

    courses_response = httpx.get(f"{base_url}/api/coursepilot/courses", headers=headers, timeout=30)
    if not courses_response.is_success:
        st.error(f"Failed to load courses: {courses_response.text}")
        return

    courses = courses_response.json()
    if not courses:
        st.info("Create a course before uploading documents.")
        return

    course_options = {f"{course['course_name']} ({course['id']})": course for course in courses}
    selected_label = st.selectbox("Course", options=list(course_options))
    selected_course = course_options[selected_label]
    course_id = selected_course["id"]

    st.subheader("Upload and build")
    source_type = st.selectbox("Source type", options=["textbook", "syllabus", "lecture", "knowledge_graph", "other"])
    uploaded_file = st.file_uploader("Upload PDF/DOCX/TXT/MD/XLSX")
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

    documents_response = httpx.get(
        f"{base_url}/api/coursepilot/courses/{course_id}/documents",
        headers=headers,
        timeout=30,
    )
    documents = documents_response.json() if documents_response.is_success else []
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
        for result in response.json()["results"]:
            source = Path(result.get("source_type") or "source").name
            st.markdown(
                f"**{source}** score={result['score']:.3f} "
                f"chunk=`{result['chunk_id']}` page={result.get('page')}"
            )
            st.write(result["content"][:1000])

    st.subheader("Generate lesson design")
    with st.form("generate_lesson"):
        chapter_range = st.text_input("Chapter range", value="第1章")
        total_sessions = st.number_input("Total sessions", min_value=1, max_value=12, value=2)
        session_duration = st.number_input("Session duration", min_value=15, max_value=240, value=45)
        teaching_template = st.text_input("Teaching template", value="standard")
        teaching_focus = st.text_input("Teaching focus")
        additional_requirements = st.text_area("Additional requirements")
        generate_lesson = st.form_submit_button("Generate lesson design")

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
            st.session_state["coursepilot_last_lesson_id"] = lesson_response["lesson_id"]
            st.json(lesson_response)

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
