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
import gspread
from google.oauth2.service_account import Credentials


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
# GOOGLE SHEETS · CAPA DE DATOS
# -----------------------------------------------------------------------------
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_SCHEMAS: dict[str, list[str]] = {
    "establecimientos": ["id", "nombre", "codigo", "activo"],
    "contratos": [
        "id", "establecimiento_id", "licitacion", "monto_adjudicado",
        "fecha_adjudicacion", "duracion_meses", "anticipacion_renovacion",
        "estado", "responsable", "observaciones", "ultima_actualizacion",
    ],
    "planes": [
        "id", "nombre_archivo", "reporte", "periodo", "fecha_publicacion",
        "establecimientos", "rojos", "amarillos", "verdes", "url_archivo",
    ],
    "plan_trabajo": [
        "id", "establecimiento_id", "nivel", "acciones", "responsable",
        "fecha_compromiso", "estado", "observaciones",
    ],
}

DEFAULT_ESTABLISHMENTS = [
    [1, "Hospital San Juan de Dios", "HSJD", "TRUE"],
    [2, "Instituto Traumatológico", "IT", "TRUE"],
    [3, "Hospital Dr. Félix Bulnes Cerda", "HFBC", "TRUE"],
    [4, "Hospital de Talagante", "HTAL", "TRUE"],
    [5, "Hospital de Peñaflor", "HPE", "TRUE"],
    [6, "Hospital de Melipilla", "HMEL", "TRUE"],
    [7, "Hospital de Curacaví", "HCUR", "TRUE"],
    [8, "CRS Salvador Allende", "CRS", "TRUE"],
    [9, "SSMOCC Dirección", "DSS", "TRUE"],
]


def secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
        return str(value).strip() if value is not None else default
    except Exception:
        return default


def _coerce(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    return value


def _to_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return value


def _same_value(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return str(left).strip() == str(right).strip()


class SheetResult:
    def __init__(self, data: list[dict[str, Any]]):
        self.data = data


class SheetQuery:
    def __init__(self, worksheet: gspread.Worksheet):
        self._ws = worksheet
        self._operation = "select"
        self._columns = "*"
        self._payload: Any = None
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None

    def select(self, columns: str = "*") -> "SheetQuery":
        self._operation, self._columns = "select", columns
        return self

    def insert(self, payload: Any) -> "SheetQuery":
        self._operation, self._payload = "insert", payload
        return self

    def update(self, payload: dict[str, Any]) -> "SheetQuery":
        self._operation, self._payload = "update", payload
        return self

    def delete(self) -> "SheetQuery":
        self._operation = "delete"
        return self

    def eq(self, column: str, value: Any) -> "SheetQuery":
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> "SheetQuery":
        self._filters.append(("neq", column, value))
        return self

    def limit(self, count: int) -> "SheetQuery":
        self._limit = count
        return self

    def _rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, record in enumerate(self._ws.get_all_records()):
            row = {key: _coerce(value) for key, value in record.items()}
            if row.get("id") not in ("", None):
                try:
                    row["id"] = int(row["id"])
                except (TypeError, ValueError):
                    pass
            row["__rownum__"] = index + 2
            rows.append(row)
        return rows

    def _matches(self, row: dict[str, Any]) -> bool:
        for kind, column, expected in self._filters:
            equal = _same_value(row.get(column), expected)
            if (kind == "eq" and not equal) or (kind == "neq" and equal):
                return False
        return True

    def execute(self) -> SheetResult:
        if self._operation == "select":
            rows = [row for row in self._rows() if self._matches(row)]
            for row in rows:
                row.pop("__rownum__", None)
            if self._limit is not None:
                rows = rows[:self._limit]
            if self._columns != "*":
                columns = [column.strip() for column in self._columns.split(",")]
                rows = [{column: row.get(column) for column in columns} for row in rows]
            return SheetResult(rows)

        headers = self._ws.row_values(1)
        if not headers:
            raise RuntimeError(f"La hoja {self._ws.title} no tiene encabezados.")

        if self._operation == "insert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            ids = [row["id"] for row in self._rows() if isinstance(row.get("id"), int)]
            next_id = max(ids, default=0) + 1
            values = []
            for payload in payloads:
                record = dict(payload)
                if "id" in headers and not record.get("id"):
                    record["id"] = next_id
                    next_id += 1
                values.append([_to_cell(record.get(header, "")) for header in headers])
            if values:
                self._ws.append_rows(values, value_input_option="RAW")
            return SheetResult(payloads)

        if self._operation == "update":
            targets = [row for row in self._rows() if self._matches(row)]
            for row in targets:
                row_number = row["__rownum__"]
                current = self._ws.row_values(row_number)
                values = [
                    _to_cell(self._payload[header])
                    if header in self._payload
                    else (current[index] if index < len(current) else "")
                    for index, header in enumerate(headers)
                ]
                self._ws.update(
                    range_name=f"A{row_number}",
                    values=[values],
                    value_input_option="RAW",
                )
            return SheetResult([self._payload])

        if self._operation == "delete":
            targets = [row for row in self._rows() if self._matches(row)]
            for row in sorted(targets, key=lambda item: item["__rownum__"], reverse=True):
                self._ws.delete_rows(row["__rownum__"])
            return SheetResult([])

        return SheetResult([])


class SheetClient:
    def __init__(self, spreadsheet: gspread.Spreadsheet):
        self._spreadsheet = spreadsheet
        self._worksheets: dict[str, gspread.Worksheet] = {}

    def table(self, name: str) -> SheetQuery:
        if name not in self._worksheets:
            try:
                worksheet = self._spreadsheet.worksheet(name)
            except gspread.WorksheetNotFound:
                headers = SHEET_SCHEMAS.get(name)
                if not headers:
                    raise RuntimeError(f"No existe la hoja '{name}'.")
                worksheet = self._spreadsheet.add_worksheet(
                    title=name, rows=200, cols=len(headers)
                )
                worksheet.update("A1", [headers], value_input_option="RAW")
                if name == "establecimientos":
                    worksheet.append_rows(
                        DEFAULT_ESTABLISHMENTS, value_input_option="RAW"
                    )
            self._worksheets[name] = worksheet
        return SheetQuery(self._worksheets[name])


@st.cache_resource
def _spreadsheet() -> gspread.Spreadsheet | None:
    try:
        account_info = dict(st.secrets["gcp_service_account"])
    except Exception:
        return None
    sheet_id = secret("GSHEET_ID") or secret("GOOGLE_SHEET_ID")
    if not account_info or not sheet_id:
        return None
    credentials = Credentials.from_service_account_info(
        account_info, scopes=GOOGLE_SCOPES
    )
    return gspread.authorize(credentials).open_by_key(sheet_id)


@st.cache_resource
def _sheet_client() -> SheetClient | None:
    spreadsheet = _spreadsheet()
    return SheetClient(spreadsheet) if spreadsheet is not None else None


def public_client() -> SheetClient:
    client = _sheet_client()
    if client is None:
        raise RuntimeError(
            "Faltan gcp_service_account y GSHEET_ID en Streamlit Secrets."
        )
    return client


def service_client() -> SheetClient | None:
    return _sheet_client()


def safe_read(table: str, columns: str = "*") -> list[dict[str, Any]]:
    try:
        result = public_client().table(table).select(columns).execute()
        return list(result.data or [])
    except Exception as exc:
        st.warning(f"No fue posible leer {table}: {exc}")
        return []


def load_data() -> dict[str, list[dict[str, Any]]]:
    try:
        client = public_client()
        for table_name in SHEET_SCHEMAS:
            client.table(table_name)
    except Exception as exc:
        st.error(f"No fue posible conectar con Google Sheets: {exc}")
        return {
            "establecimientos": [],
            "contratos": [],
            "planes": [],
            "plan_trabajo": [],
        }

    establishments = safe_read("establecimientos", "id,nombre,codigo,activo")
    return {
        "establecimientos": [
            row for row in establishments if row.get("activo", True) not in (False, "")
        ],
        "contratos": safe_read("contratos"),
        "planes": safe_read("planes"),
        "plan_trabajo": safe_read("plan_trabajo"),
    }


# -----------------------------------------------------------------------------
# NORMALIZACIÓN Y NOMBRES
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
    raw = str(value or "").strip()
    return DASHBOARD_NAMES.get(normalize(raw), raw)


# -----------------------------------------------------------------------------
# DATOS PARA EL DASHBOARD NATIVO
# -----------------------------------------------------------------------------
def contracts_for_html(
    contracts: list[dict[str, Any]],
    establishments: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    names = {row.get("id"): row.get("nombre", "") for row in establishments}
    payload: dict[str, dict[str, Any]] = {}

    for row in contracts:
        establishment = dashboard_name(
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

    causes_match = re.search(
        r"Principales causas:\s*(.*?)(?=\n\s*\nMedidas implementadas:|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    measures_match = re.search(
        r"Medidas implementadas:\s*(.*)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return (
        causes_match.group(1).strip() if causes_match else "",
        measures_match.group(1).strip() if measures_match else "",
    )


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
    if metadata is None or not plan_rows:
        return {"meta": None, "items": []}

    names = {row.get("id"): row.get("nombre", "") for row in establishments}
    items: list[dict[str, Any]] = []

    for row in plan_rows:
        establishment = dashboard_name(
            row.get("establecimiento")
            or names.get(row.get("establecimiento_id"))
            or ""
        )
        if not establishment:
            continue

        causes, measures = decode_observations(row.get("observaciones"))
        items.append(
            {
                "estab": establishment,
                "nivel": level_name(row.get("nivel")),
                "periodo": str(metadata.get("periodo") or ""),
                "causas": causes,
                "medidas": measures,
                "compromisos": str(row.get("acciones") or "").strip(),
                "responsable": str(row.get("responsable") or "").strip(),
                "fecha": str(row.get("fecha_compromiso") or "").strip(),
            }
        )

    published_at = metadata.get("creado") or metadata.get("fecha_publicacion")
    timestamp = str(published_at or datetime.now().isoformat())
    if "T" not in timestamp:
        timestamp += "T12:00:00"

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
    data: dict[str, list[dict[str, Any]]], db: SheetClient
) -> None:
    establishments = data["establecimientos"]
    contracts = data["contratos"]
    establishment_options = {
        row["nombre"]: row["id"]
        for row in establishments
        if row.get("nombre") and row.get("id") is not None
    }
    if not establishment_options:
        st.error("No existen establecimientos disponibles en Google Sheets.")
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
            st.success("Contrato guardado correctamente en Google Sheets.")
            st.rerun()
        except Exception as exc:
            st.error(f"No fue posible guardar el contrato: {exc}")


def find_header_row(uploaded_file, sheet_name: str) -> int:
    preview = pd.read_excel(
        uploaded_file, sheet_name=sheet_name, header=None, nrows=25
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
    uploaded_file, establishments: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, int], list[str], str]:
    excel = pd.ExcelFile(uploaded_file)
    sheet_name = next(
        (
            sheet
            for sheet in excel.sheet_names
            if normalize(sheet) == "anexo n1 minsal"
        ),
        excel.sheet_names[0],
    )
    uploaded_file.seek(0)
    header_row = find_header_row(uploaded_file, sheet_name)
    frame = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=header_row)
    uploaded_file.seek(0)
    frame.columns = [str(column).strip() for column in frame.columns]
    columns = {normalize(column): column for column in frame.columns}

    required = [
        "establecimiento",
        "nivel de riesgo",
        "principales causas",
        "medidas implementadas",
        "compromisos",
        "responsable",
        "fecha comprometida",
    ]
    missing = [name for name in required if name not in columns]
    if missing:
        raise ValueError("Faltan columnas: " + ", ".join(missing))

    establishment_ids = {
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
        raw_establishment = clean(record.get(columns["establecimiento"]))
        if not raw_establishment:
            continue
        establishment = dashboard_name(raw_establishment)
        establishment_id = establishment_ids.get(establishment)
        if establishment_id is None:
            unmatched.append(raw_establishment)
            continue

        level = level_name(record.get(columns["nivel de riesgo"]))
        if level in counts:
            counts[level] += 1

        if "periodo" in columns and not detected_period:
            detected_period = clean(record.get(columns["periodo"]))

        raw_date = record.get(columns["fecha comprometida"])
        commitment_date = None
        if pd.notna(raw_date):
            try:
                commitment_date = pd.to_datetime(raw_date).date().isoformat()
            except (ValueError, TypeError):
                commitment_date = None

        observations = json.dumps(
            {
                "causas": clean(record.get(columns["principales causas"])),
                "medidas": clean(record.get(columns["medidas implementadas"])),
            },
            ensure_ascii=False,
        )
        row: dict[str, Any] = {
            "establecimiento_id": establishment_id,
            "nivel": level,
            "acciones": clean(record.get(columns["compromisos"])),
            "responsable": clean(record.get(columns["responsable"])),
            "estado": "Publicado",
            "observaciones": observations,
        }
        if commitment_date:
            row["fecha_compromiso"] = commitment_date
        rows.append(row)

    return rows, counts, sorted(set(unmatched)), detected_period


def render_plan_admin(
    data: dict[str, list[dict[str, Any]]], db: SheetClient
) -> None:
    st.subheader("☁️ Plan de trabajo oficial · Anexo N°1")
    st.info(
        "La clasificación del Anexo es oficial y se muestra en el Plan de trabajo. "
        "El semáforo principal mantiene el cálculo automático por % de Trato Directo."
    )

    current = latest_plan(data["planes"])
    if current:
        st.success(
            f"Plan vigente: {current.get('nombre_archivo') or 'Anexo N°1'} · "
            f"{current.get('establecimientos') or 0} establecimientos · "
            f"{current.get('rojos') or 0} rojos · "
            f"{current.get('amarillos') or 0} amarillos · "
            f"{current.get('verdes') or 0} verdes."
        )

    uploaded = st.file_uploader(
        "Seleccionar Anexo N°1", type=["xlsx", "xls"]
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
                uploaded, data["establecimientos"]
            )
            st.success(
                f"Archivo validado: {len(rows)} establecimientos · "
                f"{counts['Rojo']} rojos · {counts['Amarillo']} amarillos · "
                f"{counts['Verde']} verdes."
            )
            if unmatched:
                st.warning("No se reconocieron: " + ", ".join(unmatched))
        except Exception as exc:
            st.error(f"No fue posible procesar el Anexo: {exc}")

    publish = st.button(
        "☁️ Publicar plan oficial en Google Sheets",
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
            existing = db.table("plan_trabajo").select("id").execute().data or []
            for record in existing:
                if record.get("id") is not None:
                    db.table("plan_trabajo").delete().eq(
                        "id", record["id"]
                    ).execute()
            db.table("plan_trabajo").insert(rows).execute()
            db.table("planes").insert(metadata).execute()
            st.success(
                f"Plan publicado: {len(rows)} establecimientos guardados en Google Sheets."
            )
            st.rerun()
        except Exception as exc:
            st.error(f"No fue posible publicar el plan: {exc}")

    st.caption(
        f"Registros actualmente disponibles en plan_trabajo: {len(data['plan_trabajo'])}."
    )


def render_admin(data: dict[str, list[dict[str, Any]]]) -> None:
    if not admin_login():
        return
    db = service_client()
    if db is None:
        st.error("Falta configurar gcp_service_account / GSHEET_ID en Streamlit Secrets.")
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
# HTML: INTEGRACIÓN NATIVA, SIN OBSERVADORES NI TEMPORIZADORES
# -----------------------------------------------------------------------------
def load_html() -> str:
    for path in HTML_FILES:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("No se encontró index.html junto a app.py.")


def replace_native_loader(html: str, function_name: str, replacement: str) -> str:
    if function_name == "loadPlan":
        pattern = re.compile(
            r"function\s+loadPlan\(\)\s*\{\s*"
            r"try\s*\{\s*PLAN\s*=\s*JSON\.parse\(localStorage\.getItem\(PLAN_KEY\)\)"
            r"\s*\|\|\s*\{meta:null,items:\[\]\};\s*\}\s*"
            r"catch\(e\)\s*\{\s*PLAN\s*=\s*\{meta:null,items:\[\]\};\s*\}\s*\}",
            flags=re.DOTALL,
        )
    else:
        pattern = re.compile(
            r"function\s+loadLic\(\)\s*\{\s*"
            r"try\s*\{\s*LIC\s*=\s*JSON\.parse\(localStorage\.getItem\(LIC_KEY\)\s*\|\|\s*'\{\}'\);\s*\}"
            r"\s*catch\(e\)\s*\{\s*LIC\s*=\s*\{\};\s*\}\s*\}",
            flags=re.DOTALL,
        )
    return pattern.sub(replacement, html, count=1)


def replace_admin_button(html: str) -> str:
    pattern = re.compile(
        r"<button(?P<attrs>[^>]*)>(?P<body>(?:(?!</button>).)*?Administrador(?:(?!</button>).)*?)</button>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def replacement(match: re.Match[str]) -> str:
        attrs = re.sub(
            r"\s+onclick\s*=\s*(['\"]).*?\1",
            "",
            match.group("attrs"),
            flags=re.IGNORECASE | re.DOTALL,
        )
        return (
            f'<a{attrs} href="https://td-ssmocc.streamlit.app/?admin=1" '
            f'target="_top">{match.group("body")}</a>'
        )

    return pattern.sub(replacement, html, count=1)


def inject_native_data(
    html: str,
    contract_payload: dict[str, dict[str, Any]],
    plan_payload: dict[str, Any],
) -> str:
    contracts_json = json.dumps(
        contract_payload, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")
    plan_json = json.dumps(
        plan_payload, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")

    preload = f"""
    <script>
      window.__SHEETS_CONTRACTS__ = {contracts_json};
      window.__SHEETS_PLAN__ = {plan_json};
    </script>
    """
    html = html.replace("</head>", preload + "\n</head>", 1)

    html = replace_native_loader(
        html,
        "loadLic",
        "function loadLic(){try{LIC=window.__SHEETS_CONTRACTS__||{};}catch(e){LIC={};}}",
    )
    html = replace_native_loader(
        html,
        "loadPlan",
        "function loadPlan(){try{PLAN=window.__SHEETS_PLAN__||{meta:null,items:[]};}catch(e){PLAN={meta:null,items:[]};}}",
    )

    # Respaldo: inicializa PLAN desde Google Sheets incluso si cambia el formato del loader.
    html = re.sub(
        r"let\s+PLAN\s*=\s*\{meta:null,items:\[\]\};",
        "let PLAN=window.__SHEETS_PLAN__||{meta:null,items:[]};",
        html,
        count=1,
    )

    html = replace_admin_button(html)
    html = html.replace(
        "Ordenado por % TD. Seleccione una fila para ver el detalle.",
        "Ordenado por % TD (nivel calculado). El nivel oficial del Anexo N°1 se muestra en el Plan de trabajo.",
        1,
    )
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
            data["planes"], data["plan_trabajo"], data["establecimientos"]
        ),
    )
    html = apply_layout_patch(html)
    components.html(html, height=4300, scrolling=False)


if __name__ == "__main__":
    main()
