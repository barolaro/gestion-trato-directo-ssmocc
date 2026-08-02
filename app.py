from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from supabase import Client, create_client

st.set_page_config(
    page_title="Inteligencia de Adquisiciones SSMOCC",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BASE_DIR = Path(__file__).resolve().parent
HTML_FILES = (
    BASE_DIR / "index.html",
    BASE_DIR / "index_dashboard_final_corregido_gestion.html",
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
      [data-testid="stVerticalBlock"] { gap: 0 !important; }
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


def secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
        return str(value).strip() if value is not None else default
    except Exception:
        return default


@st.cache_resource
def public_client() -> Client:
    url = secret("SUPABASE_URL")
    key = secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY en Streamlit Secrets.")
    return create_client(url, key)


@st.cache_resource
def service_client() -> Client | None:
    url = secret("SUPABASE_URL")
    key = secret("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def safe_read(table: str, columns: str = "*") -> list[dict[str, Any]]:
    try:
        response = public_client().table(table).select(columns).execute()
        return list(response.data or [])
    except Exception as exc:
        st.warning(f"No fue posible leer {table}: {exc}")
        return []


def load_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        public_client().table("establecimientos").select("id").limit(1).execute()
    except Exception as exc:
        st.error(f"No fue posible conectar con Supabase: {exc}")
        return [], []

    establishments = [
        row
        for row in safe_read("establecimientos", "id,nombre,codigo,activo")
        if row.get("activo", True)
    ]
    contracts = safe_read("contratos")
    return establishments, contracts


def contracts_for_html(
    contracts: list[dict[str, Any]],
    establishments: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    names = {row.get("id"): row.get("nombre", "") for row in establishments}
    payload: dict[str, dict[str, Any]] = {}

    for row in contracts:
        establishment = (
            row.get("establecimiento")
            or names.get(row.get("establecimiento_id"))
            or ""
        )
        tender = str(row.get("licitacion") or "").strip()
        if not establishment or not tender:
            continue

        payload[f"{establishment}||{tender}"] = {
            "adj": float(row.get("monto_adjudicado") or 0),
            "awardDate": str(row.get("fecha_adjudicacion") or ""),
            "durationMonths": int(row.get("duracion_meses") or 0),
            "renewalLead": int(row.get("anticipacion_renovacion") or 6),
            "manager": str(row.get("responsable") or ""),
            "contractStatus": str(row.get("estado") or "Vigente"),
            "notes": str(row.get("observaciones") or ""),
            "updatedAt": str(row.get("ultima_actualizacion") or ""),
        }

    return payload


def admin_login() -> bool:
    configured = secret("ADMIN_PASSWORD")
    if not configured:
        st.error("Falta configurar ADMIN_PASSWORD en Streamlit Secrets.")
        return False

    if st.session_state.get("admin_authenticated"):
        return True

    st.markdown("## 🔐 Administración contractual")
    with st.form("admin_login"):
        password = st.text_input("Contraseña administrativa", type="password")
        submitted = st.form_submit_button("Ingresar")

    if submitted:
        if password == configured:
            st.session_state["admin_authenticated"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")

    return False


def render_admin(
    establishments: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
) -> None:
    if not admin_login():
        return

    db = service_client()
    if db is None:
        st.error("Falta configurar SUPABASE_SERVICE_KEY en Streamlit Secrets.")
        return

    left, right = st.columns([6, 1])
    left.success("Sesión administrativa activa.")
    if right.button("Cerrar sesión"):
        st.session_state["admin_authenticated"] = False
        st.query_params.clear()
        st.rerun()

    establishment_options = {
        row["nombre"]: row["id"]
        for row in establishments
        if row.get("nombre") and row.get("id") is not None
    }
    if not establishment_options:
        st.error("No existen establecimientos disponibles en Supabase.")
        return

    id_to_name = {value: key for key, value in establishment_options.items()}
    contract_options: dict[str, dict[str, Any]] = {"Crear nuevo contrato": {}}
    for contract in contracts:
        label = (
            f"{contract.get('licitacion', 'Sin código')} · "
            f"{id_to_name.get(contract.get('establecimiento_id'), 'Sin establecimiento')}"
        )
        contract_options[label] = contract

    selected_label = st.selectbox("Contrato a gestionar", list(contract_options))
    selected = contract_options[selected_label]

    establishment_names = list(establishment_options)
    selected_establishment = id_to_name.get(
        selected.get("establecimiento_id"), establishment_names[0]
    )

    with st.form("contract_form"):
        establishment = st.selectbox(
            "Establecimiento",
            establishment_names,
            index=establishment_names.index(selected_establishment),
        )
        tender = st.text_input(
            "Licitación / instrumento",
            value=str(selected.get("licitacion") or ""),
        )
        amount = st.number_input(
            "Monto adjudicado",
            min_value=0.0,
            step=100000.0,
            value=float(selected.get("monto_adjudicado") or 0),
            format="%.0f",
        )

        raw_date = selected.get("fecha_adjudicacion")
        try:
            default_date = date.fromisoformat(str(raw_date)) if raw_date else date.today()
        except ValueError:
            default_date = date.today()

        award_date = st.date_input("Fecha de adjudicación", value=default_date)

        col1, col2 = st.columns(2)
        duration = col1.number_input(
            "Duración (meses)",
            min_value=1,
            max_value=240,
            value=int(selected.get("duracion_meses") or 12),
        )
        renewal = col2.number_input(
            "Anticipación de renovación (meses)",
            min_value=0,
            max_value=36,
            value=int(selected.get("anticipacion_renovacion") or 6),
        )

        statuses = [
            "Vigente",
            "En renovación",
            "Prorrogado",
            "Finalizado",
            "Suspendido",
        ]
        current_status = str(selected.get("estado") or "Vigente")
        status = st.selectbox(
            "Estado administrativo",
            statuses,
            index=statuses.index(current_status) if current_status in statuses else 0,
        )
        manager = st.text_input(
            "Responsable", value=str(selected.get("responsable") or "")
        )
        observations = st.text_area(
            "Observaciones", value=str(selected.get("observaciones") or "")
        )
        save = st.form_submit_button(
            "💾 Guardar gestión contractual", use_container_width=True
        )

    if save:
        if not tender.strip():
            st.error("Debes ingresar la licitación o instrumento.")
            return

        payload = {
            "establecimiento_id": establishment_options[establishment],
            "licitacion": tender.strip(),
            "monto_adjudicado": amount,
            "fecha_adjudicacion": award_date.isoformat(),
            "duracion_meses": int(duration),
            "anticipacion_renovacion": int(renewal),
            "estado": status,
            "responsable": manager.strip(),
            "observaciones": observations.strip(),
        }

        try:
            if selected.get("id") is not None:
                db.table("contratos").update(payload).eq("id", selected["id"]).execute()
            else:
                db.table("contratos").insert(payload).execute()
            st.success("Contrato guardado correctamente en Supabase.")
            st.rerun()
        except Exception as exc:
            st.error(f"No fue posible guardar el contrato: {exc}")

    if st.button("← Volver al dashboard"):
        st.query_params.clear()
        st.rerun()


def load_html() -> str:
    for path in HTML_FILES:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("No se encontró index.html junto a app.py.")


def inject_contracts(html: str, payload: dict[str, dict[str, Any]]) -> str:
    payload_json = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")

    preload = f"""
    <script>
      window.__SUPABASE_CONTRACTS__ = {payload_json};
    </script>
    """
    html = html.replace("</head>", preload + "\n</head>", 1)

    old_load = (
        "function loadLic(){ try{LIC=JSON.parse("
        "localStorage.getItem(LIC_KEY)||'{}');}catch(e){LIC={};} }"
    )
    new_load = (
        "function loadLic(){"
        "try{LIC=window.__SUPABASE_CONTRACTS__||{};}"
        "catch(e){LIC={};}"
        "}"
    )
    html = html.replace(old_load, new_load, 1)

    return html


def apply_layout_patch(html: str) -> str:
    patch = """
    <style>
      html, body {
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: hidden !important;
      }
      [class~="max-w-[1600px]"] { max-width: 100% !important; }
      @media (min-width: 1024px) {
        #sidebar {
          position: static !important;
          inset: auto !important;
          transform: none !important;
          max-height: none !important;
          height: auto !important;
          overflow: visible !important;
          align-self: flex-start !important;
        }
      }
    </style>
    """
    return html.replace("</head>", patch + "\n</head>", 1)


def main() -> None:
    establishments, contracts = load_data()

    admin_requested = str(st.query_params.get("admin", "0")) == "1"
    if admin_requested or st.session_state.get("admin_authenticated"):
        render_admin(establishments, contracts)
        st.stop()

    try:
        html = load_html()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    html = inject_contracts(
        html,
        contracts_for_html(contracts, establishments),
    )
    html = apply_layout_patch(html)

    components.html(html, height=4300, scrolling=False)


if __name__ == "__main__":
    main()
