import os

import streamlit as st
from dotenv import load_dotenv

from coursepilot.ui.knowledge_base_page import render_knowledge_base_page

APP_TITLE = "CoursePilot"
APP_ICON = "CP"


def _agent_base_url() -> str:
    agent_url = os.getenv("AGENT_URL")
    if agent_url:
        return agent_url
    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", "8080")
    return f"http://{host}:{port}"


def _auth_headers() -> dict[str, str]:
    auth_secret = os.getenv("AUTH_SECRET")
    if not auth_secret:
        return {}
    return {"Authorization": f"Bearer {auth_secret}"}


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, menu_items={})
    st.html(
        """
        <style>
        [data-testid="stStatusWidget"] {
            visibility: hidden;
            height: 0%;
            position: fixed;
        }
        </style>
        """,
    )
    render_knowledge_base_page(_agent_base_url(), _auth_headers())


if __name__ == "__main__":
    main()
