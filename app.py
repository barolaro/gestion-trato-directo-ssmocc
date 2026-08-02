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
      [data-testid="stAppViewContainer"], [data-testid="stMain"],
      [data-testid="stMainBlockContainer"], .block-container {
        width:100%!important; max-width:100vw!important;
        padding:0!important; margin:0!important;
      }
      [data-testid="stVerticalBlock"] { gap:0!important; }
      iframe[title="streamlit.components.v1.html"] {
        width:100%!important; max-width:100%!important;
        border:0!important; display:block!important;
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


def read_rows(table: str, columns: str = "*") -> list[dict[str, Any]]:
    result = public_client().table(table).select(columns).execute()
    return list(result.data or [])


def safe_read(table: str, columns: str = "*") -> list[dict[str, Any]]:
    try:
        return read_rows(table, columns)
    except Exception as exc:
        st.warning(f"No fue posible leer {table}: {exc}")
        return []


def load_data() -> dict[str, list[dict[str, Any]]]:
    try:
        public_client().table("establecimientos").select("id").limit(1).execute()
    except Exception as exc:
        st.error(f"No fue posible conectar con Supabase: {exc}")
        return {"establecimientos": [], "contratos": [], "planes": [], "plan_trabajo": []}

    establishments = safe_read("establecimientos", "id,nombre,codigo,activo")
    return {
        "establecimientos": [r for r in establishments if r.get("activo", True)],
        "contratos": safe_read("contratos"),
        "planes": safe_read("planes"),
        "plan_trabajo": safe_read("plan_trabajo"),
    }


def normalize(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        char for char in unicodedata.normalize("NFD", text)
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


def detect_column(columns: list[str], candidates: list[str]) -> str | None:
    exact = {normalize(column): column for column in columns}
    for candidate in candidates:
        if normalize(candidate) in exact:
            return exact[normalize(candidate)]
    for column in columns:
        normalized = normalize(column)
        if any(normalize(candidate) in normalized for candidate in candidates):
            return column
    return None


def uploaded_dataframe(uploaded_file) -> pd.DataFrame:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".csv":
        try:
            return pd.read_csv(uploaded_file, sep=None, engine="python")
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, sep=None, engine="python", encoding="latin-1")
    return pd.read_excel(uploaded_file)


def contracts_for_html(
    contracts: list[dict[str, Any]],
    establishments: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    names = {row.get("id"): row.get("nombre", "") for row in establishments}
    payload: dict[str, dict[str, Any]] = {}
    for row in contracts:
        establishment = row.get("establecimiento") or names.get(row.get("establecimiento_id"), "")
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


def plans_for_html(
    plan_rows: list[dict[str, Any]],
    establishments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names = {row.get("id"): row.get("nombre", "") for row in establishments}
    output: list[dict[str, Any]] = []
    for row in plan_rows:
        establishment = row.get("establecimiento") or names.get(row.get("establecimiento_id"), "")
        if not establishment:
            continue
        output.append(
            {
                "establecimiento": establishment,
                "key": normalize(establishment),
                "nivel": level_name(row.get("nivel")),
                "acciones": str(row.get("acciones") or "").strip(),
                "responsable": str(row.get("responsable") or "").strip(),
                "fecha": str(row.get("fecha_compromiso") or "").strip(),
                "estado": str(row.get("estado") or "Publicado").strip(),
                "observaciones": str(row.get("observaciones") or "").strip(),
            }
        )
    return output


def latest_plan_metadata(planes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not planes:
        return None
    return sorted(
        planes,
        key=lambda row: (str(row.get("fecha_publicacion") or ""), int(row.get("id") or 0)),
        reverse=True,
    )[0]


def admin_login() -> bool:
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


def render_contract_admin(data: dict[str, list[dict[str, Any]]], db: Client) -> None:
    establishments = data["establecimientos"]
    contracts = data["contratos"]
    options = {
        row["nombre"]: row["id"]
        for row in establishments
        if row.get("nombre") and row.get("id") is not None
    }
    if not options:
        st.error("No existen establecimientos disponibles.")
        return

    id_to_name = {value: key for key, value in options.items()}
    contract_options: dict[str, dict[str, Any]] = {"Crear nuevo contrato": {}}
    for contract in contracts:
        label = (
            f"{contract.get('licitacion', 'Sin código')} · "
            f"{id_to_name.get(contract.get('establecimiento_id'), 'Sin establecimiento')}"
        )
        contract_options[label] = contract

    selected_label = st.selectbox("Contrato a gestionar", list(contract_options))
    selected = contract_options[selected_label]
    establishment_names = list(options)
    current_name = id_to_name.get(selected.get("establecimiento_id"), establishment_names[0])

    with st.form("contract_form"):
        establishment = st.selectbox(
            "Establecimiento",
            establishment_names,
            index=establishment_names.index(current_name),
        )
        tender = st.text_input("Licitación / instrumento", value=str(selected.get("licitacion") or ""))
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
        duration = col1.number_input("Duración (meses)", 1, 240, int(selected.get("duracion_meses") or 12))
        renewal = col2.number_input(
            "Anticipación de renovación (meses)", 0, 36,
            int(selected.get("anticipacion_renovacion") or 6),
        )
        statuses = ["Vigente", "En renovación", "Prorrogado", "Finalizado", "Suspendido"]
        current_status = str(selected.get("estado") or "Vigente")
        status = st.selectbox(
            "Estado administrativo",
            statuses,
            index=statuses.index(current_status) if current_status in statuses else 0,
        )
        manager = st.text_input("Responsable", value=str(selected.get("responsable") or ""))
        observations = st.text_area("Observaciones", value=str(selected.get("observaciones") or ""))
        save = st.form_submit_button("💾 Guardar gestión contractual", use_container_width=True)

    if save:
        if not tender.strip():
            st.error("Debes ingresar la licitación o instrumento.")
            return
        payload = {
            "establecimiento_id": options[establishment],
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
    dataframe = dataframe.copy()
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    columns = list(dataframe.columns)

    establishment_col = detect_column(columns, ["establecimiento", "hospital", "centro"])
    level_col = detect_column(columns, ["nivel", "clasificacion", "riesgo", "semaforo", "color"])
    action_col = detect_column(columns, ["acciones", "medidas", "plan comprometido", "plan de accion"])
    responsible_col = detect_column(columns, ["responsable"])
    date_col = detect_column(columns, ["fecha compromiso", "plazo", "fecha"])
    observation_col = detect_column(columns, ["observaciones", "compromisos", "causas", "justificacion"])

    if not establishment_col or not level_col:
        raise ValueError("El archivo debe incluir columnas de establecimiento y nivel/clasificación.")

    establishment_map = {
        normalize(row.get("nombre")): row.get("id")
        for row in establishments if row.get("id") is not None
    }
    aliases = {
        "felix bulnes": "hospital dr felix bulnes cerda",
        "hospital felix bulnes": "hospital dr felix bulnes cerda",
        "san juan de dios": "hospital san juan de dios",
        "talagante": "hospital de talagante",
        "melipilla": "hospital de melipilla",
        "penaflor": "hospital de penaflor",
        "crs s allende": "crs salvador allende",
        "inst traumatologico": "instituto traumatologico",
        "ssmocc direccion": "ssmocc direccion",
    }

    rows: list[dict[str, Any]] = []
    unmatched: list[str] = []
    counts = {"Rojo": 0, "Amarillo": 0, "Verde": 0}

    for _, record in dataframe.iterrows():
        establishment_name = str(record.get(establishment_col) or "").strip()
        if not establishment_name or establishment_name.lower() == "nan":
            continue
        key = normalize(establishment_name)
        key = aliases.get(key, key)
        establishment_id = establishment_map.get(key)
        if establishment_id is None:
            unmatched.append(establishment_name)
            continue

        level = level_name(record.get(level_col))
        if level in counts:
            counts[level] += 1

        def cell(column: str | None) -> str:
            if not column:
                return ""
            value = record.get(column)
            return "" if pd.isna(value) else str(value).strip()

        row: dict[str, Any] = {
            "establecimiento_id": establishment_id,
            "nivel": level,
            "acciones": cell(action_col),
            "responsable": cell(responsible_col),
            "estado": "Publicado",
            "observaciones": cell(observation_col),
        }
        if date_col:
            value = record.get(date_col)
            if pd.notna(value):
                try:
                    row["fecha_compromiso"] = pd.to_datetime(value).date().isoformat()
                except Exception:
                    pass
        rows.append(row)

    return rows, counts, sorted(set(unmatched))


def render_plan_admin(data: dict[str, list[dict[str, Any]]], db: Client) -> None:
    st.subheader("☁️ Plan de trabajo oficial · Anexo N°1")
    st.info(
        "Publique el archivo desde este módulo para guardarlo realmente en Supabase."
    )

    uploaded = st.file_uploader("Seleccionar Anexo N°1", type=["xlsx", "xls", "csv"])
    col1, col2 = st.columns(2)
    reporte = col1.text_input("Reporte", value="Reporte 1")
    periodo = col2.text_input("Período", value="Enero–Marzo 2026")
    publication_date = st.date_input("Fecha de publicación", value=date.today())

    rows: list[dict[str, Any]] = []
    counts = {"Rojo": 0, "Amarillo": 0, "Verde": 0}
    unmatched: list[str] = []

    if uploaded is not None:
        try:
            dataframe = uploaded_dataframe(uploaded)
            rows, counts, unmatched = build_plan_rows(dataframe, data["establecimientos"])
            st.success(
                f"Archivo leído: {len(rows)} establecimientos válidos · "
                f"{counts['Rojo']} rojos · {counts['Amarillo']} amarillos · {counts['Verde']} verdes."
            )
            if unmatched:
                st.warning("No se reconocieron: " + ", ".join(unmatched))
            st.dataframe(dataframe.head(20), use_container_width=True)
        except Exception as exc:
            st.error(f"No fue posible leer el archivo: {exc}")

    publish = st.button(
        "☁️ Publicar plan oficial en Supabase",
        type="primary",
        use_container_width=True,
        disabled=uploaded is None or not rows,
    )

    if publish and uploaded is not None:
        metadata = {
            "nombre_archivo": uploaded.name,
            "reporte": reporte.strip(),
            "periodo": periodo.strip(),
            "fecha_publicacion": publication_date.isoformat(),
            "establecimientos": len(rows),
            "rojos": counts["Rojo"],
            "amarillos": counts["Amarillo"],
            "verdes": counts["Verde"],
            "url_archivo": "",
        }
        try:
            db.table("plan_trabajo").delete().neq("id", 0).execute()
            db.table("plan_trabajo").insert(rows).execute()
            db.table("planes").insert(metadata).execute()
            st.success(f"Plan publicado en Supabase con {len(rows)} establecimientos.")
            st.rerun()
        except Exception as exc:
            st.error(f"No fue posible publicar el plan: {exc}")

    current = latest_plan_metadata(data["planes"])
    if current:
        st.divider()
        st.write(
            f"**Plan registrado en Supabase:** {current.get('nombre_archivo') or 'Sin nombre'} · "
            f"{current.get('establecimientos') or 0} establecimientos · "
            f"publicado {current.get('fecha_publicacion') or ''}."
        )
        st.write(f"Filas de detalle disponibles: **{len(data['plan_trabajo'])}**")


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

    tab_contracts, tab_plan = st.tabs(["📄 Gestión contractual", "☁️ Plan oficial"])
    with tab_contracts:
        render_contract_admin(data, db)
    with tab_plan:
        render_plan_admin(data, db)

    if st.button("← Volver al dashboard"):
        st.query_params.clear()
        st.rerun()


def load_html() -> str:
    for path in HTML_FILES:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("No se encontró index.html junto a app.py.")


def inject_data(
    html: str,
    contracts: dict[str, dict[str, Any]],
    plan_rows: list[dict[str, Any]],
    plan_meta: dict[str, Any] | None,
) -> str:
    contracts_json = json.dumps(contracts, ensure_ascii=False).replace("</", "<\\/")
    rows_json = json.dumps(plan_rows, ensure_ascii=False).replace("</", "<\\/")
    meta_json = json.dumps(plan_meta, ensure_ascii=False).replace("</", "<\\/")

    script = f"""
    <script>
      window.__SUPABASE_CONTRACTS__ = {contracts_json};
      window.__SUPABASE_PLAN_ROWS__ = {rows_json};
      window.__SUPABASE_PLAN_META__ = {meta_json};

      function ssmoccNorm(v) {{
        return String(v || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
          .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
      }}

      function ssmoccVisible(el) {{
        if (!el) return false;
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
      }}

      function ssmoccCurrentPlan() {{
        const rows = window.__SUPABASE_PLAN_ROWS__ || [];
        if (!rows.length) return null;
        const selected = [...document.querySelectorAll('select')]
          .map(el => el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex].textContent : '')
          .filter(Boolean).join(' ');
        const pageText = document.body ? document.body.innerText : '';
        const source = ssmoccNorm(selected + ' ' + pageText);
        for (const row of rows) {{
          const candidate = ssmoccNorm(row.establecimiento);
          if (candidate && source.includes(candidate)) return row;
        }}
        return rows[0];
      }}

      function ssmoccRenderPlan() {{
        const row = ssmoccCurrentPlan();
        if (!row) return;
        const pending = [...document.querySelectorAll('div,p,span')].find(el =>
          ssmoccVisible(el) && ssmoccNorm(el.textContent).includes('plan comprometido pendiente')
        );
        if (!pending) return;
        let target = pending;
        while (target.parentElement && target.parentElement.textContent.trim() === pending.textContent.trim()) {{
          target = target.parentElement;
        }}
        const actions = row.acciones
          ? row.acciones.split(/\\n|•|;/).map(x => x.trim()).filter(Boolean)
          : [];
        const actionHtml = actions.length
          ? '<ul style="margin:8px 0 0 20px">' + actions.map(x => '<li style="margin:5px 0">' + x + '</li>').join('') + '</ul>'
          : '<p style="margin:8px 0 0">Sin acciones informadas.</p>';
        target.innerHTML = `
          <div style="padding:16px 18px;border:1px solid #b9d7f2;border-radius:12px;background:#f7fbff;color:#334155">
            <div style="font-weight:800;color:#0b4f87;margin-bottom:6px">✅ Plan comprometido oficial</div>
            ${{actionHtml}}
            ${{row.observaciones ? `<div style="margin-top:12px"><b>Observaciones:</b> ${{row.observaciones}}</div>` : ''}}
            ${{row.responsable ? `<div style="margin-top:8px"><b>Responsable:</b> ${{row.responsable}}</div>` : ''}}
            ${{row.fecha ? `<div style="margin-top:8px"><b>Fecha compromiso:</b> ${{row.fecha}}</div>` : ''}}
          </div>`;
      }}

      document.addEventListener('click', function(event) {{
        const control = event.target.closest('button,a');
        if (!control) return;
        if (ssmoccNorm(control.textContent).includes('administrador')) {{
          event.preventDefault();
          event.stopImmediatePropagation();
          window.top.location.href = 'https://td-ssmocc.streamlit.app/?admin=1';
        }}
      }}, true);

      document.addEventListener('DOMContentLoaded', function() {{
        ssmoccRenderPlan();
        const observer = new MutationObserver(() => ssmoccRenderPlan());
        observer.observe(document.body, {{childList:true, subtree:true, characterData:true}});
        setInterval(ssmoccRenderPlan, 1200);
      }});
    </script>
    """
    html = html.replace("</body>", script + "\n</body>", 1)

    old_load = (
        "function loadLic(){ try{LIC=JSON.parse("
        "localStorage.getItem(LIC_KEY)||'{}');}catch(e){LIC={};} }"
    )
    new_load = "function loadLic(){try{LIC=window.__SUPABASE_CONTRACTS__||{};}catch(e){LIC={};}}"
    html = html.replace(old_load, new_load, 1)

    patch = """
    <style>
      html,body{width:100%!important;max-width:100%!important;overflow-x:hidden!important}
      [class~="max-w-[1600px]"]{max-width:100%!important}
      @media(min-width:1024px){#sidebar{position:static!important;inset:auto!important;
      transform:none!important;max-height:none!important;height:auto!important;
      overflow:visible!important;align-self:flex-start!important}}
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

    html = inject_data(
        html,
        contracts_for_html(data["contratos"], data["establecimientos"]),
        plans_for_html(data["plan_trabajo"], data["establecimientos"]),
        latest_plan_metadata(data["planes"]),
    )
    components.html(html, height=4300, scrolling=False)


if __name__ == "__main__":
    main()
