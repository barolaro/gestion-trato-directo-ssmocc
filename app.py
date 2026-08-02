from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
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


def load_data() -> dict[str, list[dict[str, Any]]]:
    try:
        public_client().table("establecimientos").select("id").limit(1).execute()
    except Exception as exc:
        st.error(f"No fue posible conectar con Supabase: {exc}")
        return {
            "establecimientos": [],
            "contratos": [],
            "planes": [],
            "plan_trabajo": [],
        }

    establishments = safe_read("establecimientos", "id,nombre,codigo,activo")
    return {
        "establecimientos": [
            row for row in establishments if row.get("activo", True)
        ],
        "contratos": safe_read("contratos"),
        "planes": safe_read("planes"),
        "plan_trabajo": safe_read("plan_trabajo"),
    }


# -----------------------------------------------------------------------------
# NORMALIZACIÓN
# -----------------------------------------------------------------------------
def normalize(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def level_name(value: Any) -> str:
    text = normalize(value)
    if "rojo" in text:
        return "Rojo"
    if "amarillo" in text:
        return "Amarillo"
    if "verde" in text:
        return "Verde"
    return str(value or "").strip().title()


DASHBOARD_NAMES = {
    "curacavi": "Curacaví",
    "hospital de curacavi": "Curacaví",
    "hospital dr felix bulnes cerda": "Félix Bulnes",
    "hospital felix bulnes": "Félix Bulnes",
    "felix bulnes": "Félix Bulnes",
    "hospital de melipilla": "Melipilla",
    "hospital melipilla": "Melipilla",
    "melipilla": "Melipilla",
    "hospital de penaflor": "Peñaflor",
    "hospital penaflor": "Peñaflor",
    "penaflor": "Peñaflor",
    "crs salvador allende": "CRS S. Allende",
    "centro de referencia salud occidente salvador allende": "CRS S. Allende",
    "crs s allende": "CRS S. Allende",
    "hospital san juan de dios": "San Juan de Dios",
    "san juan de dios": "San Juan de Dios",
    "ssmocc direccion": "SSMOCC (Dirección)",
    "direccion del servicio metropolitano occidente": "SSMOCC (Dirección)",
    "direccion servicio salud metropolitano occidente": "SSMOCC (Dirección)",
    "instituto traumatologico": "Inst. Traumatológico",
    "instituto traumatologico dr teodoro gebauer": "Inst. Traumatológico",
    "inst traumatologico": "Inst. Traumatológico",
    "hospital de talagante": "Talagante",
    "hospital talagante": "Talagante",
    "talagante": "Talagante",
}


def dashboard_name(value: Any) -> str:
    text = str(value or "").strip()
    return DASHBOARD_NAMES.get(normalize(text), text)


# -----------------------------------------------------------------------------
# PAYLOADS PARA EL HTML
# -----------------------------------------------------------------------------
def contracts_for_html(
    contracts: list[dict[str, Any]],
    establishments: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    names = {row.get("id"): row.get("nombre", "") for row in establishments}
    payload: dict[str, dict[str, Any]] = {}

    for row in contracts:
        raw_establishment = (
            row.get("establecimiento")
            or names.get(row.get("establecimiento_id"))
            or ""
        )
        establishment = dashboard_name(raw_establishment)
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


def decode_observations(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return (
                str(parsed.get("causas") or "").strip(),
                str(parsed.get("medidas") or "").strip(),
            )
    except (ValueError, TypeError):
        pass

    causas = ""
    medidas = ""
    causas_match = re.search(
        r"Principales causas:\s*(.*?)(?=\n\s*\nMedidas implementadas:|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    medidas_match = re.search(
        r"Medidas implementadas:\s*(.*)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if causas_match:
        causas = causas_match.group(1).strip()
    if medidas_match:
        medidas = medidas_match.group(1).strip()
    return causas, medidas


def latest_plan(planes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not planes:
        return None
    return max(
        planes,
        key=lambda row: (
            str(row.get("fecha_publicacion") or ""),
            int(row.get("id") or 0),
        ),
    )


def plan_for_html(
    planes: list[dict[str, Any]],
    plan_rows: list[dict[str, Any]],
    establishments: list[dict[str, Any]],
) -> dict[str, Any]:
    metadata = latest_plan(planes)
    if metadata is None:
        return {"meta": None, "items": []}

    names = {row.get("id"): row.get("nombre", "") for row in establishments}
    items: list[dict[str, Any]] = []

    for row in plan_rows:
        raw_establishment = (
            row.get("establecimiento")
            or names.get(row.get("establecimiento_id"))
            or ""
        )
        establishment = dashboard_name(raw_establishment)
        if not establishment:
            continue

        causas, medidas = decode_observations(row.get("observaciones"))
        items.append(
            {
                "estab": establishment,
                "nivel": level_name(row.get("nivel")),
                "periodo": str(metadata.get("periodo") or ""),
                "causas": causas,
                "medidas": medidas,
                "compromisos": str(row.get("acciones") or "").strip(),
                "responsable": str(row.get("responsable") or "").strip(),
                "fecha": str(row.get("fecha_compromiso") or "").strip(),
            }
        )

    published_at = metadata.get("creado") or metadata.get("fecha_publicacion")
    if published_at:
        timestamp = str(published_at)
        if "T" not in timestamp:
            timestamp += "T12:00:00"
    else:
        timestamp = datetime.now().isoformat()

    return {
        "meta": {
            "filename": str(metadata.get("nombre_archivo") or "Anexo N°1"),
            "ts": timestamp,
            "reporte": str(metadata.get("reporte") or "Anexo N°1"),
            "periodo": str(metadata.get("periodo") or ""),
        },
        "items": items,
    }


# -----------------------------------------------------------------------------
# ADMINISTRACIÓN
# -----------------------------------------------------------------------------
def admin_login() -> bool:
    configured = secret("ADMIN_PASSWORD")
    if not configured:
        st.error("Falta configurar ADMIN_PASSWORD en Streamlit Secrets.")
        return False

    if st.session_state.get("admin_authenticated"):
        return True

    st.markdown("## 🔐 Administración")
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


def render_contract_admin(
    data: dict[str, list[dict[str, Any]]],
    db: Client,
) -> None:
    establishments = data["establecimientos"]
    contracts = data["contratos"]
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
            "Duración (meses)", 1, 240, int(selected.get("duracion_meses") or 12)
        )
        renewal = col2.number_input(
            "Anticipación de renovación (meses)",
            0,
            36,
            int(selected.get("anticipacion_renovacion") or 6),
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
                db.table("contratos").update(payload).eq(
                    "id", selected["id"]
                ).execute()
            else:
                db.table("contratos").insert(payload).execute()
            st.success("Contrato guardado correctamente en Supabase.")
            st.rerun()
        except Exception as exc:
            st.error(f"No fue posible guardar el contrato: {exc}")


def find_header_row(uploaded_file, sheet_name: str) -> int:
    preview = pd.read_excel(
        uploaded_file,
        sheet_name=sheet_name,
        header=None,
        nrows=20,
    )
    uploaded_file.seek(0)
    for index, row in preview.iterrows():
        cells = {normalize(value) for value in row.tolist() if pd.notna(value)}
        if "establecimiento" in cells and "compromisos" in cells:
            return int(index)
    raise ValueError(
        "No se encontró la fila de encabezados con Establecimiento y Compromisos."
    )


def parse_annex(
    uploaded_file,
    establishments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int], list[str], str]:
    excel = pd.ExcelFile(uploaded_file)
    preferred = next(
        (
            name
            for name in excel.sheet_names
            if normalize(name) == "anexo n1 minsal"
        ),
        excel.sheet_names[0],
    )
    uploaded_file.seek(0)
    header_row = find_header_row(uploaded_file, preferred)
    frame = pd.read_excel(
        uploaded_file,
        sheet_name=preferred,
        header=header_row,
    )
    uploaded_file.seek(0)
    frame.columns = [str(column).strip() for column in frame.columns]

    normalized_columns = {normalize(column): column for column in frame.columns}
    required_keys = [
        "establecimiento",
        "nivel de riesgo",
        "principales causas",
        "medidas implementadas",
        "compromisos",
        "responsable",
        "fecha comprometida",
    ]
    missing = [key for key in required_keys if key not in normalized_columns]
    if missing:
        raise ValueError(
            "Faltan columnas obligatorias: " + ", ".join(missing)
        )

    establishment_col = normalized_columns["establecimiento"]
    level_col = normalized_columns["nivel de riesgo"]
    causes_col = normalized_columns["principales causas"]
    measures_col = normalized_columns["medidas implementadas"]
    commitments_col = normalized_columns["compromisos"]
    responsible_col = normalized_columns["responsable"]
    date_col = normalized_columns["fecha comprometida"]
    period_col = normalized_columns.get("periodo")

    establishment_map = {
        dashboard_name(row.get("nombre")): row.get("id")
        for row in establishments
        if row.get("id") is not None
    }

    rows: list[dict[str, Any]] = []
    unmatched: list[str] = []
    counts = {"Rojo": 0, "Amarillo": 0, "Verde": 0}
    detected_period = ""

    def clean(value: Any) -> str:
        return "" if pd.isna(value) else str(value).strip()

    for _, record in frame.iterrows():
        raw_name = clean(record.get(establishment_col))
        if not raw_name:
            continue
        canonical_name = dashboard_name(raw_name)
        establishment_id = establishment_map.get(canonical_name)
        if establishment_id is None:
            unmatched.append(raw_name)
            continue

        level = level_name(record.get(level_col))
        if level in counts:
            counts[level] += 1

        if period_col and not detected_period:
            detected_period = clean(record.get(period_col))

        commitment_date = None
        raw_date = record.get(date_col)
        if pd.notna(raw_date):
            try:
                commitment_date = pd.to_datetime(raw_date).date().isoformat()
            except (ValueError, TypeError):
                commitment_date = None

        observation_data = {
            "causas": clean(record.get(causes_col)),
            "medidas": clean(record.get(measures_col)),
        }
        row: dict[str, Any] = {
            "establecimiento_id": establishment_id,
            "nivel": level,
            "acciones": clean(record.get(commitments_col)),
            "responsable": clean(record.get(responsible_col)),
            "estado": "Publicado",
            "observaciones": json.dumps(
                observation_data,
                ensure_ascii=False,
            ),
        }
        if commitment_date:
            row["fecha_compromiso"] = commitment_date
        rows.append(row)

    return rows, counts, sorted(set(unmatched)), detected_period


def render_plan_admin(
    data: dict[str, list[dict[str, Any]]],
    db: Client,
) -> None:
    st.subheader("☁️ Plan de trabajo oficial · Anexo N°1")
    st.caption(
        "El archivo se valida y sus compromisos quedan guardados permanentemente en Supabase."
    )

    current = latest_plan(data["planes"])
    if current:
        st.success(
            f"Plan vigente: {current.get('nombre_archivo') or 'Anexo N°1'} · "
            f"{current.get('establecimientos') or 0} establecimientos · "
            f"publicado {current.get('fecha_publicacion') or ''}."
        )

    uploaded = st.file_uploader(
        "Seleccionar Anexo N°1",
        type=["xlsx", "xls"],
    )
    col1, col2 = st.columns(2)
    report = col1.text_input("Reporte", value="Reporte 1")
    period = col2.text_input("Período", value="Enero–Marzo 2026")
    publication_date = st.date_input("Fecha de publicación", value=date.today())

    rows: list[dict[str, Any]] = []
    counts = {"Rojo": 0, "Amarillo": 0, "Verde": 0}
    unmatched: list[str] = []
    detected_period = ""

    if uploaded is not None:
        try:
            rows, counts, unmatched, detected_period = parse_annex(
                uploaded,
                data["establecimientos"],
            )
            st.success(
                f"Archivo validado: {len(rows)} establecimientos · "
                f"{counts['Rojo']} rojos · "
                f"{counts['Amarillo']} amarillos · "
                f"{counts['Verde']} verdes."
            )
            if detected_period:
                st.caption(f"Período detectado en el archivo: {detected_period}")
            if unmatched:
                st.warning("No se reconocieron: " + ", ".join(unmatched))
        except Exception as exc:
            st.error(f"No fue posible procesar el Anexo: {exc}")

    publish = st.button(
        "☁️ Publicar plan oficial en Supabase",
        type="primary",
        use_container_width=True,
        disabled=uploaded is None or not rows,
    )

    if publish and uploaded is not None:
        metadata = {
            "nombre_archivo": uploaded.name,
            "reporte": report.strip(),
            "periodo": (detected_period or period).strip(),
            "fecha_publicacion": publication_date.isoformat(),
            "establecimientos": len(rows),
            "rojos": counts["Rojo"],
            "amarillos": counts["Amarillo"],
            "verdes": counts["Verde"],
            "url_archivo": "",
        }
        try:
            existing_rows = (
                db.table("plan_trabajo").select("id").execute().data or []
            )
            for existing in existing_rows:
                if existing.get("id") is not None:
                    db.table("plan_trabajo").delete().eq(
                        "id", existing["id"]
                    ).execute()

            db.table("plan_trabajo").insert(rows).execute()
            db.table("planes").insert(metadata).execute()
            st.success(
                f"Plan oficial publicado: {len(rows)} establecimientos guardados en Supabase."
            )
            st.rerun()
        except Exception as exc:
            st.error(f"No fue posible publicar el plan: {exc}")

    st.caption(
        f"Registros disponibles actualmente en plan_trabajo: {len(data['plan_trabajo'])}."
    )


def render_admin(data: dict[str, list[dict[str, Any]]]) -> None:
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

    contracts_tab, plan_tab = st.tabs(
        ["📄 Gestión contractual", "☁️ Plan oficial"]
    )
    with contracts_tab:
        render_contract_admin(data, db)
    with plan_tab:
        render_plan_admin(data, db)

    if st.button("← Volver al dashboard"):
        st.query_params.clear()
        st.rerun()


# -----------------------------------------------------------------------------
# HTML
# -----------------------------------------------------------------------------
def load_html() -> str:
    for path in HTML_FILES:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("No se encontró index.html junto a app.py.")


def inject_native_data(
    html: str,
    contract_payload: dict[str, dict[str, Any]],
    plan_payload: dict[str, Any],
) -> str:
    contracts_json = json.dumps(
        contract_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    plan_json = json.dumps(
        plan_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    preload = f"""
    <script>
      window.__SUPABASE_CONTRACTS__ = {contracts_json};
      window.__SUPABASE_PLAN__ = {plan_json};
    </script>
    """
    html = html.replace("</head>", preload + "\n</head>", 1)

    old_contract_loader = (
        "function loadLic(){ try{LIC=JSON.parse("
        "localStorage.getItem(LIC_KEY)||'{}');}catch(e){LIC={};} }"
    )
    new_contract_loader = (
        "function loadLic(){"
        "try{LIC=window.__SUPABASE_CONTRACTS__||{};}"
        "catch(e){LIC={};}"
        "}"
    )
    html = html.replace(old_contract_loader, new_contract_loader, 1)

    old_plan_loader = (
        "function loadPlan(){ try{PLAN=JSON.parse(localStorage.getItem(PLAN_KEY))"
        "||{meta:null,items:[]};}catch(e){PLAN={meta:null,items:[]};} }"
    )
    new_plan_loader = (
        "function loadPlan(){"
        "try{PLAN=window.__SUPABASE_PLAN__||{meta:null,items:[]};}"
        "catch(e){PLAN={meta:null,items:[]};}"
        "}"
    )
    html = html.replace(old_plan_loader, new_plan_loader, 1)

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
    data = load_data()

    admin_requested = str(st.query_params.get("admin", "0")) == "1"
    if admin_requested or st.session_state.get("admin_authenticated"):
        render_admin(data)
        st.stop()

    try:
        html = load_html()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    html = inject_native_data(
        html,
        contracts_for_html(data["contratos"], data["establecimientos"]),
        plan_for_html(
            data["planes"],
            data["plan_trabajo"],
            data["establecimientos"],
        ),
    )
    html = apply_layout_patch(html)

    components.html(html, height=4300, scrolling=False)


if __name__ == "__main__":
    main()
