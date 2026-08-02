from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from supabase import Client, create_client


# -----------------------------------------------------------------------------
# CONFIGURACIÓN GENERAL
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Inteligencia de Adquisiciones SSMOCC",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BASE_DIR = Path(__file__).resolve().parent
HTML_CANDIDATES = (
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


# -----------------------------------------------------------------------------
# SUPABASE
# -----------------------------------------------------------------------------
def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
        return str(value).strip() if value is not None else default
    except Exception:
        return default


@st.cache_resource
def get_public_client() -> Client:
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Faltan SUPABASE_URL o SUPABASE_KEY en los Secrets de Streamlit."
        )
    return create_client(url, key)


@st.cache_resource
def get_admin_client() -> Client | None:
    url = get_secret("SUPABASE_URL")
    service_key = get_secret("SUPABASE_SERVICE_KEY")
    if not url or not service_key:
        return None
    return create_client(url, service_key)


def fetch_rows(table: str, columns: str = "*") -> list[dict[str, Any]]:
    client = get_public_client()
    result = client.table(table).select(columns).execute()
    return list(result.data or [])


def fetch_contracts() -> list[dict[str, Any]]:
    try:
        return fetch_rows("contratos")
    except Exception as exc:
        st.warning(f"No fue posible leer la tabla contratos: {exc}")
        return []


def fetch_establishments() -> list[dict[str, Any]]:
    try:
        rows = fetch_rows("establecimientos", "id,nombre,codigo,activo")
        return [row for row in rows if row.get("activo", True)]
    except Exception as exc:
        st.warning(f"No fue posible leer establecimientos: {exc}")
        return []


def contract_payload_for_dashboard(
    contracts: list[dict[str, Any]],
    establishments: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    establishment_names = {
        row.get("id"): row.get("nombre", "") for row in establishments
    }
    payload: dict[str, dict[str, Any]] = {}

    for row in contracts:
        establishment = (
            row.get("establecimiento")
            or establishment_names.get(row.get("establecimiento_id"))
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
            "contractStatus": str(
                row.get("estado_administrativo")
                or row.get("estado")
                or "Vigente"
            ),
            "notes": str(row.get("observaciones") or ""),
            "updatedAt": str(
                row.get("actualizado_en")
                or row.get("ultima_actualizacion")
                or ""
            ),
        }

    return payload


# -----------------------------------------------------------------------------
# ADMINISTRACIÓN CONTRACTUAL
# -----------------------------------------------------------------------------
def admin_authenticated() -> bool:
    return bool(
        get_secret("ADMIN_PASSWORD")
        and st.session_state.get("admin_authenticated")
    )


def render_admin_panel(
    contracts: list[dict[str, Any]],
    establishments: list[dict[str, Any]],
) -> None:
    st.markdown("## 🔐 Administración contractual (Supabase)")

    if not get_secret("ADMIN_PASSWORD"):
        st.error("Falta configurar ADMIN_PASSWORD en Streamlit Secrets.")
        return

    if not admin_authenticated():
        with st.form("admin_login"):
            password = st.text_input("Contraseña administrativa", type="password")
            submitted = st.form_submit_button("Ingresar")
        if submitted:
            if password == get_secret("ADMIN_PASSWORD"):
                st.session_state["admin_authenticated"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
        return

    col_user, col_logout = st.columns([5, 1])
    with col_user:
        st.success("Sesión administrativa activa.")
    with col_logout:
        if st.button("Cerrar sesión"):
            st.session_state["admin_authenticated"] = False
            st.query_params.clear()
            st.rerun()

    admin_client = get_admin_client()
    if admin_client is None:
        st.warning(
            "Para guardar debes agregar SUPABASE_SERVICE_KEY en los Secrets de Streamlit."
        )
        return

    establishment_options = {
        row["nombre"]: row["id"]
        for row in establishments
        if row.get("nombre") and row.get("id") is not None
    }
    if not establishment_options:
        st.error("No existen establecimientos disponibles en Supabase.")
        return

    existing_options = ["Crear nuevo contrato"]
    existing_map: dict[str, dict[str, Any]] = {}
    for contract in contracts:
        establishment_name = next(
            (
                name
                for name, establishment_id in establishment_options.items()
                if establishment_id == contract.get("establecimiento_id")
            ),
            "Sin establecimiento",
        )
        label = f"{contract.get('licitacion', 'Sin código')} · {establishment_name}"
        existing_options.append(label)
        existing_map[label] = contract

    selected_contract_label = st.selectbox(
        "Contrato a gestionar", existing_options
    )
    selected_contract = existing_map.get(selected_contract_label, {})
    current_establishment_id = selected_contract.get("establecimiento_id")

    establishment_names = list(establishment_options)
    default_establishment_index = 0
    if current_establishment_id is not None:
        for index, name in enumerate(establishment_names):
            if establishment_options[name] == current_establishment_id:
                default_establishment_index = index
                break

    with st.form("contract_form", clear_on_submit=False):
        establishment_name = st.selectbox(
            "Establecimiento",
            establishment_names,
            index=default_establishment_index,
        )
        tender = st.text_input(
            "Licitación / instrumento",
            value=str(selected_contract.get("licitacion") or ""),
            placeholder="Ejemplo: 1288-32-LR24",
        )
        amount = st.number_input(
            "Monto adjudicado",
            min_value=0.0,
            step=100000.0,
            value=float(selected_contract.get("monto_adjudicado") or 0),
            format="%.0f",
        )

        award_date_value = selected_contract.get("fecha_adjudicacion")
        if award_date_value:
            try:
                award_date_default = date.fromisoformat(str(award_date_value))
            except ValueError:
                award_date_default = date.today()
        else:
            award_date_default = date.today()

        award_date = st.date_input(
            "Fecha de adjudicación", value=award_date_default
        )

        col_duration, col_lead = st.columns(2)
        with col_duration:
            duration = st.number_input(
                "Duración (meses)",
                min_value=1,
                max_value=240,
                value=int(selected_contract.get("duracion_meses") or 12),
                step=1,
            )
        with col_lead:
            renewal_lead = st.number_input(
                "Anticipación de renovación (meses)",
                min_value=0,
                max_value=36,
                value=int(selected_contract.get("anticipacion_renovacion") or 6),
                step=1,
            )

        status_options = [
            "Vigente",
            "En renovación",
            "Prorrogado",
            "Finalizado",
            "Suspendido",
        ]
        current_status = str(
            selected_contract.get("estado_administrativo")
            or selected_contract.get("estado")
            or "Vigente"
        )
        status = st.selectbox(
            "Estado administrativo",
            status_options,
            index=(
                status_options.index(current_status)
                if current_status in status_options
                else 0
            ),
        )
        manager = st.text_input(
            "Responsable",
            value=str(selected_contract.get("responsable") or ""),
        )
        observations = st.text_area(
            "Observaciones",
            value=str(selected_contract.get("observaciones") or ""),
            height=100,
        )
        save = st.form_submit_button(
            "💾 Guardar gestión contractual", use_container_width=True
        )

    if save:
        if not tender.strip():
            st.error("Debes ingresar el código de la licitación o instrumento.")
            return

        payload = {
            "establecimiento_id": establishment_options[establishment_name],
            "licitacion": tender.strip(),
            "monto_adjudicado": amount,
            "fecha_adjudicacion": award_date.isoformat(),
            "duracion_meses": int(duration),
            "anticipacion_renovacion": int(renewal_lead),
            "estado": status,
            "responsable": manager.strip(),
            "observaciones": observations.strip(),
        }

        try:
            if selected_contract.get("id") is not None:
                admin_client.table("contratos").update(payload).eq(
                    "id", selected_contract["id"]
                ).execute()
            else:
                admin_client.table("contratos").insert(payload).execute()
            st.success("Gestión contractual guardada correctamente en Supabase.")
            st.rerun()
        except Exception as exc:
            st.error(f"No fue posible guardar el contrato: {exc}")


# -----------------------------------------------------------------------------
# DASHBOARD HTML
# -----------------------------------------------------------------------------
def load_dashboard_html() -> str:
    path = next((candidate for candidate in HTML_CANDIDATES if candidate.exists()), None)
    if path is None:
        raise FileNotFoundError(
            "No se encontró index.html en la misma carpeta que app.py."
        )
    return path.read_text(encoding="utf-8")


def inject_supabase_contracts(
    dashboard_html: str,
    contracts_payload: dict[str, dict[str, Any]],
) -> str:
    payload_json = json.dumps(
        contracts_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    preload_script = f"""
    <script>
      window.__SUPABASE_CONTRACTS__ = {payload_json};
    </script>
    """
    dashboard_html = dashboard_html.replace(
        "</head>", preload_script + "\n</head>", 1
    )

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
    dashboard_html = dashboard_html.replace(old_load, new_load, 1)

    old_save = (
        "function saveLic(){ try{localStorage.setItem("
        "LIC_KEY,JSON.stringify(LIC));}catch(e){} }"
    )
    new_save = (
        "function saveLic(){"
        "try{"
        "if(typeof toast==='function'){"
        "toast('Use el botón Administrador para guardar en Supabase');"
        "}"
        "}catch(e){}"
        "}"
    )
    dashboard_html = dashboard_html.replace(old_save, new_save, 1)

    admin_button = '<button id="admin-btn" class="flex-none flex items-center gap-2 bg-govblue-d hover:bg-govblue text-white text-[13px] font-semibold rounded-lg px-3.5 py-2 transition">'
    admin_link = '<a id="admin-btn" href="https://td-ssmocc.streamlit.app/?admin=1" target="_top" class="flex-none flex items-center gap-2 bg-govblue-d hover:bg-govblue text-white text-[13px] font-semibold rounded-lg px-3.5 py-2 transition">'
    if admin_button in dashboard_html:
        dashboard_html = dashboard_html.replace(admin_button, admin_link, 1)
        button_start = dashboard_html.find(admin_link)
        button_end = dashboard_html.find("</button>", button_start)
        if button_end != -1:
            dashboard_html = (
                dashboard_html[:button_end]
                + "</a>"
                + dashboard_html[button_end + len("</button>") :]
            )

    return dashboard_html


def apply_streamlit_layout_patch(dashboard_html: str) -> str:
    patch = """
    <style>
      html, body {
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: hidden !important;
      }

      [class~="max-w-[1600px]"] {
        max-width: 100% !important;
      }

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
    return dashboard_html.replace("</head>", patch + "\n</head>", 1)


# -----------------------------------------------------------------------------
# EJECUCIÓN
# -----------------------------------------------------------------------------
def main() -> None:
    try:
        public_client = get_public_client()
        public_client.table("establecimientos").select("id").limit(1).execute()
        connected = True
    except Exception as exc:
        connected = False
        st.error(f"No fue posible conectar con Supabase: {exc}")

    contracts = fetch_contracts() if connected else []
    establishments = fetch_establishments() if connected else []

    admin_requested = str(st.query_params.get("admin", "0")) == "1"
    if admin_requested or st.session_state.get("admin_authenticated", False):
        render_admin_panel(contracts, establishments)
        if st.button("← Volver al dashboard"):
            st.session_state["admin_authenticated"] = False
            st.query_params.clear()
            st.rerun()
        st.stop()

    try:
        dashboard_html = load_dashboard_html()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    dashboard_html = inject_supabase_contracts(
        dashboard_html,
        contract_payload_for_dashboard(contracts, establishments),
    )
    dashboard_html = apply_streamlit_layout_patch(dashboard_html)

    components.html(dashboard_html, height=4300, scrolling=False)


if __name__ == "__main__":
    main()
