from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="Monitoreo Trato Directo SSMOCC",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Quita los márgenes y límites de ancho que Streamlit agrega alrededor del componente.
st.markdown(
    """
    <style>
      #MainMenu, footer, [data-testid="stHeader"], [data-testid="stToolbar"] {
        display: none !important;
      }
      [data-testid="stAppViewContainer"],
      [data-testid="stMain"],
      [data-testid="stMainBlockContainer"],
      .block-container {
        width: 100% !important;
        max-width: 100vw !important;
        padding: 0 !important;
        margin: 0 !important;
      }
      [data-testid="stVerticalBlock"] {
        gap: 0 !important;
      }
      iframe[title="streamlit.components.v1.html"] {
        width: 100% !important;
        max-width: 100% !important;
        border: 0 !important;
        display: block !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
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

# Ajustes responsivos aplicados al HTML al momento de publicarlo en Streamlit.
responsive_patch = """
<style>
  html, body {
    width: 100% !important;
    max-width: 100% !important;
    overflow-x: hidden !important;
  }

  [class~="max-w-[1600px]"] {
    max-width: 100% !important;
  }

  @media (max-width: 1500px) and (min-width: 1024px) {
    #sidebar {
      width: 232px !important;
    }

    body > div[class*="max-w-[1600px]"] {
      gap: 0.75rem !important;
    }

    .dt {
      font-size: 11.5px !important;
    }

    .dt td,
    .dt th {
      padding-left: 0.5rem !important;
      padding-right: 0.5rem !important;
    }
  }

  @media (max-width: 1180px) {
    #sidebar {
      position: fixed !important;
      left: 0 !important;
      top: 0 !important;
      bottom: 0 !important;
      z-index: 60 !important;
      width: 264px !important;
      transform: translateX(-100%) !important;
      border-radius: 0 !important;
      margin-top: 0 !important;
      max-height: 100vh !important;
    }

    #sidebar.open {
      transform: none !important;
    }

    #burger {
      display: flex !important;
    }

    #scrim.open {
      display: block !important;
    }
  }
</style>
"""

dashboard_html = dashboard_html.replace(
    "</head>", responsive_patch + "\n</head>", 1
)

components.html(
    dashboard_html,
    height=3200,
    scrolling=True,
)
