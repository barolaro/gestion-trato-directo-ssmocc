from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="Monitoreo Trato Directo SSMOCC",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BASE_DIR = Path(__file__).resolve().parent
HTML_CANDIDATES = (
    BASE_DIR / "index.html",
    BASE_DIR / "dashboard_ssmocc_td_v9.html",
)

dashboard_path = next((path for path in HTML_CANDIDATES if path.exists()), None)

if dashboard_path is None:
    st.error(
        "No se encontró el dashboard. Suba a GitHub el archivo "
        "'index.html' o 'dashboard_ssmocc_td_v9.html' en la misma carpeta que app.py."
    )
    st.stop()

dashboard_html = dashboard_path.read_text(encoding="utf-8")

components.html(
    dashboard_html,
    height=5200,
    scrolling=True,
)
