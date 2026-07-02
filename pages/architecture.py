import streamlit as st
import pathlib

st.set_page_config(page_title="Ed-Copilot Architecture", page_icon="🏗️", layout="wide")

html_path = pathlib.Path(__file__).parent.parent / "architecture.html"
html_content = html_path.read_text(encoding="utf-8")

st.components.v1.html(html_content, height=2400, scrolling=True)
