from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from supabase import Client, create_client


# -----------------------------------------------------------------------------
# CONFIGURACIÓN
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


# -----------------------------------------------------------------------------
# SUPABASE
# -----------------------------------------------------------------------------
def secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
        return str(value).strip() if value is not None else default
    except Exception:
        return default


@st.cache_resource
def public_db() -> Client:
    url = secret("SUPABASE_URL")
    key = secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY en Streamlit Secrets.")
    return create_client(url, key)


@st.cache_resource
def admin_db() -> Client | None:
    url = secret("SUPABASE_URL")
    key = secret("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def fetch_rows(table: str, columns: str = "*") -> list[dict[str, Any]]:
    result = public_db().table(table).select(columns).execute()
    return list(result.data or [])


def safe_fetch(table: str, columns: str = "*") -> list[dict[str, Any]]:
    try:
        return fetch_rows(table, columns)
    except Exception:
        return []


def load_all_data() -> dict[str, list[dict[str, Any]]]:
    try:
        public_db().table("establecimientos").select("id").limit(1).execute()
    except Exception as exc:
        st.error(f"No fue posible conectar con Supabase: {exc}")
        return {
            "establecimientos": [],
            "contratos": [],
            "planes": [],
            "plan_trabajo": [],
        }

    return {
        "establecimientos": [
            row
            for row in safe_fetch("establecimientos", "id,nombre,codigo,activo")
            if row.get("activo", True)
        ],
        "contratos": safe_fetch("contratos"),
        "planes": safe_fetch("planes"),
        "plan_trabajo": safe_fetch("plan_trabajo"),
    }


# -----------------------------------------------------------------------------
# UTILIDADES
# -----------------------------------------------------------------------------
def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", text)


def detect_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {normalize_text(column): column for column in columns}
    for candidate in candidates:
        candidate_normalized = normalize_text(candidate)
        if candidate_normalized in normalized:
            return normalized[candidate_normalized]
    for column in columns:
        normalized_column = normalize_text(column)
        if any(normalize_text(candidate) in normalized_column for candidate in candidates):
            return column
    return None


def normalize_level(value: Any) -> str:
    level = normalize_text(value)
    if "rojo" in level:
        return "Rojo"
    if "amarillo" in level:
        return "Amarillo"
    if "verde" in level:
        return "Verde"
    return str(value or "").strip().title()


def dataframe_from_upload(uploaded_file) -> pd.DataFrame:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".csv":
        try:
            return pd.read_csv(uploaded_file, sep=None, engine="python")
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, sep=None, engine="python", encoding="latin-1")
    return pd.read_excel(uploaded_file)


# -----------------------------------------------------------------------------
# PAYLOADS PARA EL DASHBOARD
# -----------------------------------------------------------------------------
def contract_payload(
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


def official_plan_payload(
    planes: list[dict[str, Any]],
    plan_rows: list[dict[str, Any]],
    establishments: list[dict[str, Any]],
) -> dict[str, Any]:
    if not planes:
        return {"meta": None, "items": []}

    latest = sorted(
        planes,
        key=lambda row: (
            str(row.get("fecha_publicacion") or ""),
            int(row.get("id") or 0),
        ),
        reverse=True,
    )[0]

    names = {row.get("id"): row.get("nombre", "") for row in establishments}
    items = []
    for row in plan_rows:
        establishment = (
            row.get("establecimiento")
            or names.get(row.get("establecimiento_id"))
            or ""
        )
        if not establishment:
            continue
        items.append(
            {
                "estab": establishment,
                "nivel": normalize_level(row.get("nivel")),
                "pct": row.get("porcentaje") or row.get("pct") or "",
                "causas": row.get("causas") or "",
                "medidas": row.get("medidas") or row.get("acciones") or "",
                "compromisos": row.get("compromisos") or row.get("observaciones") or "",
                "responsable": row.get("responsable") or "",
                "fecha": str(row.get("fecha_compromiso") or ""),
            }
        )

    return {
        "meta": {
            "id": latest.get("id"),
            "fileName": latest.get("nombre_archivo") or "",
            "reporte": latest.get("reporte") or "",
            "periodo": latest.get("periodo") or "",
            "publishedAt": str(latest.get("fecha_publicacion") or ""),
            "establecimientos": latest.get("establecimientos") or len(items),
            "rojos": latest.get("rojos") or 0,
            "amarillos": latest.get("amarillos") or 0,
            "verdes": latest.get("verdes") or 0,
        },
        "items": items,
    }


# -----------------------------------------------------------------------------
# ADMINISTRACIÓN
# -----------------------------------------------------------------------------
def require_admin_login() -> bool:
    password = secret("ADMIN_PASSWORD")
    if not password:
        st.error("Falta configurar ADMIN_PASSWORD en Streamlit Secrets.")
        return False

    if st.session_state.get("admin_authenticated"):
        return True

    st.markdown("## 🔐 Administración")
    with st.form("admin_login"):
        entered = st.text_input("Contraseña administrativa", type="password")
        submitted = st.form_submit_button("Ingresar")
    if submitted:
        if entered == password:
            st.session_state["admin_authenticated"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    return False


def render_contract_admin(
    db: Client,
    establishments: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
) -> None:
    establishment_options = {
        row["nombre"]: row["id"]
        for row in establishments
        if row.get("nombre") and row.get("id") is not None
    }
    if not establishment_options:
        st.error("No existen establecimientos disponibles.")
        return

    id_to_name = {value: key for key, value in establishment_options.items()}
    options = {"Crear nuevo contrato": {}}
    for contract in contracts:
        label = (
            f"{contract.get('licitacion', 'Sin código')} · "
            f"{id_to_name.get(contract.get('establecimiento_id'), 'Sin establecimiento')}"
        )
        options[label] = contract

    selected_label = st.selectbox("Contrato a gestionar", list(options))
    selected = options[selected_label]

    establishment_names = list(establishment_options)
    selected_establishment = id_to_name.get(
        selected.get("establecimiento_id"),
        establishment_names[0],
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
            award_default = date.fromisoformat(str(raw_date)) if raw_date else date.today()
        except ValueError:
            award_default = date.today()

        award_date = st.date_input("Fecha de adjudicación", value=award_default)

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
            "Responsable",
            value=str(selected.get("responsable") or ""),
        )
        observations = st.text_area(
            "Observaciones",
            value=str(selected.get("observaciones") or ""),
        )
        save = st.form_submit_button(
            "💾 Guardar gestión contractual",
            use_container_width=True,
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


def build_plan_rows(
    dataframe: pd.DataFrame,
    establishments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    columns = [str(column).strip() for column in dataframe.columns]
    dataframe.columns = columns

    establishment_column = detect_column(
        columns,
        ["establecimiento", "hospital", "centro", "nombre establecimiento"],
    )
    level_column = detect_column(
        columns,
        ["nivel", "clasificacion", "riesgo", "semaforo", "color"],
    )

    if not establishment_column or not level_column:
        raise ValueError(
            "El archivo debe contener una columna de establecimiento y otra de nivel/clasificación."
        )

    action_column = detect_column(columns, ["acciones", "medidas"])
    responsible_column = detect_column(columns, ["responsable"])
    date_column = detect_column(columns, ["fecha compromiso", "fecha"])
    observation_column = detect_column(
        columns,
        ["observaciones", "compromisos", "causas"],
    )

    establishment_map = {
        normalize_text(row.get("nombre")): row.get("id")
        for row in establishments
        if row.get("id") is not None
    }

    aliases = {
        "felix bulnes": "hospital dr. felix bulnes cerda",
        "san juan de dios": "hospital san juan de dios",
        "talagante": "hospital de talagante",
        "melipilla": "hospital de melipilla",
        "penaflor": "hospital de penaflor",
        "crs s. allende": "crs salvador allende",
        "inst. traumatologico": "instituto traumatologico",
        "ssmocc direccion": "ssmocc (direccion)",
    }

    rows: list[dict[str, Any]] = []
    unmatched: list[str] = []
    counts = {"Rojo": 0, "Amarillo": 0, "Verde": 0}

    for _, record in dataframe.iterrows():
        establishment_name = str(record.get(establishment_column) or "").strip()
        if not establishment_name or establishment_name.lower() == "nan":
            continue

        normalized_name = normalize_text(establishment_name)
        normalized_name = aliases.get(normalized_name, normalized_name)
        establishment_id = establishment_map.get(normalized_name)

        if establishment_id is None:
            unmatched.append(establishment_name)
            continue

        level = normalize_level(record.get(level_column))
        if level in counts:
            counts[level] += 1

        row = {
            "establecimiento_id": establishment_id,
            "nivel": level,
            "acciones": (
                str(record.get(action_column) or "").strip()
                if action_column
                else ""
            ),
            "responsable": (
                str(record.get(responsible_column) or "").strip()
                if responsible_column
                else ""
            ),
            "estado": "Publicado",
            "observaciones": (
                str(record.get(observation_column) or "").strip()
                if observation_column
                else ""
            ),
        }

        if date_column:
            value = record.get(date_column)
            if pd.notna(value):
                try:
                    row["fecha_compromiso"] = pd.to_datetime(value).date().isoformat()
                except Exception:
                    pass

        rows.append(row)

    return rows, counts, sorted(set(unmatched))


def render_plan_admin(
    db: Client,
    establishments: list[dict[str, Any]],
    planes: list[dict[str, Any]],
) -> None:
    st.subheader("☁️ Publicar plan oficial")

    if planes:
        latest = sorted(
            planes,
            key=lambda row: (
                str(row.get("fecha_publicacion") or ""),
                int(row.get("id") or 0),
            ),
            reverse=True,
        )[0]
        st.success(
            f"Plan vigente: {latest.get('nombre_archivo') or 'Sin nombre'} · "
            f"{latest.get('establecimientos') or 0} establecimientos · "
            f"{latest.get('rojos') or 0} rojo · "
            f"{latest.get('amarillos') or 0} amarillo · "
            f"{latest.get('verdes') or 0} verde."
        )

    uploaded = st.file_uploader(
        "Archivo oficial (Excel o CSV)",
        type=["xlsx", "xls", "csv"],
    )

    col1, col2 = st.columns(2)
    reporte = col1.text_input("Reporte", value="Reporte 1")
    periodo = col2.text_input("Período", value="Enero–Marzo 2026")
    publication_date = st.date_input("Fecha de publicación", value=date.today())

    preview_rows: list[dict[str, Any]] = []
    counts = {"Rojo": 0, "Amarillo": 0, "Verde": 0}
    unmatched: list[str] = []

    if uploaded is not None:
        try:
            dataframe = dataframe_from_upload(uploaded)
            preview_rows, counts, unmatched = build_plan_rows(
                dataframe,
                establishments,
            )
            st.write(
                f"Se detectaron **{len(preview_rows)} establecimientos válidos**: "
                f"{counts['Rojo']} rojos, {counts['Amarillo']} amarillos y "
                f"{counts['Verde']} verdes."
            )
            if unmatched:
                st.warning(
                    "No se reconocieron estos establecimientos: "
                    + ", ".join(unmatched)
                )
            st.dataframe(dataframe.head(20), use_container_width=True)
        except Exception as exc:
            st.error(f"No fue posible leer el archivo: {exc}")

    publish = st.button(
        "☁️ Publicar plan oficial en Supabase",
        type="primary",
        use_container_width=True,
        disabled=uploaded is None or not preview_rows,
    )

    if publish and uploaded is not None:
        metadata = {
            "nombre_archivo": uploaded.name,
            "reporte": reporte.strip(),
            "periodo": periodo.strip(),
            "fecha_publicacion": publication_date.isoformat(),
            "establecimientos": len(preview_rows),
            "rojos": counts["Rojo"],
            "amarillos": counts["Amarillo"],
            "verdes": counts["Verde"],
            "url_archivo": "",
        }

        try:
            db.table("plan_trabajo").delete().neq("id", 0).execute()
            if preview_rows:
                db.table("plan_trabajo").insert(preview_rows).execute()
            db.table("planes").insert(metadata).execute()

            st.success(
                f"Plan oficial publicado en Supabase: {len(preview_rows)} establecimientos."
            )
            st.rerun()
        except Exception as exc:
            st.error(f"No fue posible publicar el plan: {exc}")

    if planes:
        st.divider()
        st.subheader("Planes publicados")
        for plan in sorted(
            planes,
            key=lambda row: int(row.get("id") or 0),
            reverse=True,
        ):
            col_info, col_delete = st.columns([6, 1])
            col_info.write(
                f"**{plan.get('nombre_archivo') or 'Sin nombre'}** — "
                f"{plan.get('reporte') or ''} · {plan.get('periodo') or ''} · "
                f"{plan.get('fecha_publicacion') or ''}"
            )
            if col_delete.button(
                "Eliminar",
                key=f"delete_plan_{plan.get('id')}",
            ):
                try:
                    db.table("planes").delete().eq("id", plan["id"]).execute()
                    if len(planes) == 1:
                        db.table("plan_trabajo").delete().neq("id", 0).execute()
                    st.success("Plan eliminado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No fue posible eliminar el plan: {exc}")


def render_admin(data: dict[str, list[dict[str, Any]]]) -> None:
    if not require_admin_login():
        return

    db = admin_db()
    if db is None:
        st.error("Falta configurar SUPABASE_SERVICE_KEY en Streamlit Secrets.")
        return

    top_left, top_right = st.columns([6, 1])
    top_left.success("Sesión administrativa activa.")
    if top_right.button("Cerrar sesión"):
        st.session_state["admin_authenticated"] = False
        st.query_params.clear()
        st.rerun()

    tab_contracts, tab_plan = st.tabs(
        ["📄 Gestión contractual", "☁️ Plan oficial"]
    )

    with tab_contracts:
        render_contract_admin(
            db,
            data["establecimientos"],
            data["contratos"],
        )

    with tab_plan:
        render_plan_admin(
            db,
            data["establecimientos"],
            data["planes"],
        )

    if st.button("← Volver al dashboard"):
        st.query_params.clear()
        st.rerun()


# -----------------------------------------------------------------------------
# DASHBOARD HTML
# -----------------------------------------------------------------------------
def load_dashboard_html() -> str:
    path = next(
        (candidate for candidate in HTML_CANDIDATES if candidate.exists()),
        None,
    )
    if path is None:
        raise FileNotFoundError("No se encontró index.html junto a app.py.")
    return path.read_text(encoding="utf-8")


def replace_admin_button(html: str) -> str:
    pattern = re.compile(
        r"<button(?P<attrs>[^>]*)>(?P<body>(?:(?!</button>).)*Administrador(?:(?!</button>).)*)</button>",
        re.IGNORECASE | re.DOTALL,
    )

    def replacement(match: re.Match[str]) -> str:
        attrs = re.sub(
            r"\s+onclick\s*=\s*(['\"]).*?\1",
            "",
            match.group("attrs"),
            flags=re.IGNORECASE | re.DOTALL,
        )
        return (
            f'<a{attrs} href="?admin=1" target="_top">'
            f'{match.group("body")}</a>'
        )

    return pattern.sub(replacement, html, count=1)


def inject_supabase_data(
    html: str,
    contracts_payload: dict[str, dict[str, Any]],
    plan_payload: dict[str, Any],
) -> str:
    contracts_json = json.dumps(
        contracts_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    plan_json = json.dumps(
        plan_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    plan_keys = re.findall(
        r"(?:const|let|var)\s+PLAN_KEY\s*=\s*['\"]([^'\"]+)['\"]",
        html,
    )
    plan_key = plan_keys[0] if plan_keys else "ssmocc_plan_oficial_v1"

    preload = f"""
    <script>
      window.__SUPABASE_CONTRACTS__ = {contracts_json};
      window.__SUPABASE_PLAN__ = {plan_json};
      try {{
        localStorage.setItem({json.dumps(plan_key)}, JSON.stringify(window.__SUPABASE_PLAN__));
      }} catch (e) {{}}
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

    old_save = (
        "function saveLic(){ try{localStorage.setItem("
        "LIC_KEY,JSON.stringify(LIC));}catch(e){} }"
    )
    new_save = (
        "function saveLic(){"
        "try{toast('Use Administrador para guardar en Supabase');}"
        "catch(e){}"
        "}"
    )
    html = html.replace(old_save, new_save, 1)

    return replace_admin_button(html)


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


# -----------------------------------------------------------------------------
# EJECUCIÓN
# -----------------------------------------------------------------------------
def main() -> None:
    data = load_all_data()

    admin_requested = str(st.query_params.get("admin", "0")) == "1"
    if admin_requested or st.session_state.get("admin_authenticated"):
        render_admin(data)
        st.stop()

    try:
        html = load_dashboard_html()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    html = inject_supabase_data(
        html,
        contract_payload(data["contratos"], data["establecimientos"]),
        official_plan_payload(
            data["planes"],
            data["plan_trabajo"],
            data["establecimientos"],
        ),
    )
    html = apply_layout_patch(html)

    components.html(html, height=4300, scrolling=False)


if __name__ == "__main__":
    main()
