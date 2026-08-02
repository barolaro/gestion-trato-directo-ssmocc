from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="Monitoreo Trato Directo SSMOCC",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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

# Elimina directamente las clases Tailwind que dejan fijo el menú lateral.
dashboard_html = dashboard_html.replace(" lg:sticky", "")
dashboard_html = dashboard_html.replace(" lg:top-[132px]", "")
dashboard_html = dashboard_html.replace(" lg:max-h-[calc(100vh-152px)]", "")
dashboard_html = dashboard_html.replace(" overflow-y-auto", "")

# Sincroniza la fila elegida en el semáforo con el Plan de trabajo.
old_row_handler = (
    "tb.querySelectorAll('tr[data-e]').forEach(tr=>tr.onclick=()=>{"
    "tdState.selected=tr.dataset.e;renderTD();});"
)
new_row_handler = (
    "tb.querySelectorAll('tr[data-e]').forEach(tr=>tr.onclick=()=>{"
    "tdState.selected=tr.dataset.e;"
    "tdState.planSel=tr.dataset.e;"
    "renderTD();});"
)
dashboard_html = dashboard_html.replace(old_row_handler, new_row_handler, 1)

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

  @media (min-width: 821px) {
    #sidebar {
      position: static !important;
      inset: auto !important;
      transform: none !important;
      max-height: none !important;
      height: auto !important;
      overflow: visible !important;
      width: 232px !important;
      flex: 0 0 232px !important;
      align-self: flex-start !important;
    }
  }

  @media (max-width: 1500px) and (min-width: 1024px) {
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

  @media (max-width: 820px) {
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
      overflow-y: auto !important;
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
    height=3400,
    scrolling=False,
)
