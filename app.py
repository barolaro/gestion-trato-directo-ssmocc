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
      #MainMenu, footer, [data-testid="stHeader"], [data-testid="stToolbar"] {display:none!important}
      [data-testid="stAppViewContainer"], [data-testid="stMain"],
      [data-testid="stMainBlockContainer"], .block-container {
        width:100%!important;max-width:100vw!important;padding:0!important;margin:0!important
      }
      [data-testid="stVerticalBlock"]{gap:0!important}
      iframe[title="streamlit.components.v1.html"]{width:100%!important;max-width:100%!important;border:0!important;display:block!important}
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
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY en Streamlit Secrets.")
    return create_client(url, key)


@st.cache_resource
def service_client() -> Client | None:
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_SERVICE_KEY")
    return create_client(url, key) if url and key else None


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
        return {"establecimientos": [], "contratos": [], "planes": [], "plan_trabajo": []}

    establishments = safe_read("establecimientos", "id,nombre,codigo,activo")
    return {
        "establecimientos": [row for row in establishments if row.get("activo", True)],
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
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def level_name(value: Any) -> str:
    text = normalize(value)
    if "rojo" in text:
        return "Rojo"
    if "amarillo" in text:
        return "Amarillo"
    if "verde" in text:
        return "Verde"
    return str(value or "").strip().title()


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
    rows: list[dict[str, Any]],
    establishments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names = {row.get("id"): row.get("nombre", "") for row in establishments}
    result = []
    for row in rows:
        establishment = row.get("establecimiento") or names.get(row.get("establecimiento_id"), "")
        if not establishment:
            continue
        result.append({
            "establecimiento": establishment,
            "nivel": level_name(row.get("nivel")),
            "compromisos": str(row.get("acciones") or "").strip(),
            "responsable": str(row.get("responsable") or "").strip(),
            "fecha": str(row.get("fecha_compromiso") or "").strip(),
            "observaciones": str(row.get("observaciones") or "").strip(),
        })
    return result


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


def render_contract_admin(data: dict[str, list[dict[str, Any]]], db: Client) -> None:
    establishments, contracts = data["establecimientos"], data["contratos"]
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
        label = f"{contract.get('licitacion', 'Sin código')} · {id_to_name.get(contract.get('establecimiento_id'), 'Sin establecimiento')}"
        contract_options[label] = contract

    selected_label = st.selectbox("Contrato a gestionar", list(contract_options))
    selected = contract_options[selected_label]
    establishment_names = list(options)
    current_name = id_to_name.get(selected.get("establecimiento_id"), establishment_names[0])

    with st.form("contract_form"):
        establishment = st.selectbox("Establecimiento", establishment_names, index=establishment_names.index(current_name))
        tender = st.text_input("Licitación / instrumento", value=str(selected.get("licitacion") or ""))
        amount = st.number_input("Monto adjudicado", min_value=0.0, step=100000.0, value=float(selected.get("monto_adjudicado") or 0), format="%.0f")
        raw_date = selected.get("fecha_adjudicacion")
        try:
            default_date = date.fromisoformat(str(raw_date)) if raw_date else date.today()
        except ValueError:
            default_date = date.today()
        award_date = st.date_input("Fecha de adjudicación", value=default_date)
        col1, col2 = st.columns(2)
        duration = col1.number_input("Duración (meses)", 1, 240, int(selected.get("duracion_meses") or 12))
        renewal = col2.number_input("Anticipación de renovación (meses)", 0, 36, int(selected.get("anticipacion_renovacion") or 6))
        statuses = ["Vigente", "En renovación", "Prorrogado", "Finalizado", "Suspendido"]
        current_status = str(selected.get("estado") or "Vigente")
        status = st.selectbox("Estado administrativo", statuses, index=statuses.index(current_status) if current_status in statuses else 0)
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


def parse_annex(uploaded_file, establishments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    sheet = "Anexo N1 MINSAL"
    frame = pd.read_excel(uploaded_file, sheet_name=sheet, header=5)
    frame.columns = [str(column).strip() for column in frame.columns]
    required = [
        "Establecimiento", "Nivel de Riesgo", "Principales causas",
        "Medidas implementadas", "Compromisos", "Responsable", "Fecha comprometida",
    ]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError("Faltan columnas obligatorias: " + ", ".join(missing))

    establishment_map = {
        normalize(row.get("nombre")): row.get("id")
        for row in establishments if row.get("id") is not None
    }
    aliases = {
        "centro de referencia salud occidente salvador allende": "crs salvador allende",
        "hospital de curacavi": "curacavi",
        "direccion del servicio metropolitano occidente": "ssmocc direccion",
        "instituto traumatologico dr teodoro gebauer": "instituto traumatologico",
        "hospital dr felix bulnes cerda": "hospital dr felix bulnes cerda",
        "hospital san juan de dios": "hospital san juan de dios",
    }

    rows: list[dict[str, Any]] = []
    unmatched: list[str] = []
    counts = {"Rojo": 0, "Amarillo": 0, "Verde": 0}

    for _, record in frame.iterrows():
        establishment_name = str(record.get("Establecimiento") or "").strip()
        if not establishment_name or establishment_name.lower() == "nan":
            continue
        key = normalize(establishment_name)
        target_key = normalize(aliases.get(key, key))
        establishment_id = establishment_map.get(target_key)
        if establishment_id is None:
            for stored_name, stored_id in establishment_map.items():
                if target_key in stored_name or stored_name in target_key:
                    establishment_id = stored_id
                    break
        if establishment_id is None:
            unmatched.append(establishment_name)
            continue

        level = level_name(record.get("Nivel de Riesgo"))
        if level in counts:
            counts[level] += 1

        def clean(column: str) -> str:
            value = record.get(column)
            return "" if pd.isna(value) else str(value).strip()

        date_value = record.get("Fecha comprometida")
        commitment_date = None
        if pd.notna(date_value):
            try:
                commitment_date = pd.to_datetime(date_value).date().isoformat()
            except Exception:
                commitment_date = None

        observations = "\n\n".join(
            part for part in [
                "Principales causas:\n" + clean("Principales causas") if clean("Principales causas") else "",
                "Medidas implementadas:\n" + clean("Medidas implementadas") if clean("Medidas implementadas") else "",
            ] if part
        )
        row = {
            "establecimiento_id": establishment_id,
            "nivel": level,
            "acciones": clean("Compromisos"),
            "responsable": clean("Responsable"),
            "estado": "Publicado",
            "observaciones": observations,
        }
        if commitment_date:
            row["fecha_compromiso"] = commitment_date
        rows.append(row)

    return rows, counts, sorted(set(unmatched))


def render_plan_admin(data: dict[str, list[dict[str, Any]]], db: Client) -> None:
    st.subheader("☁️ Plan de trabajo oficial · Anexo N°1")
    st.caption("El archivo debe corresponder al formato oficial. Los encabezados se leen desde la fila 6.")
    uploaded = st.file_uploader("Seleccionar Anexo N°1", type=["xlsx"])
    col1, col2 = st.columns(2)
    report = col1.text_input("Reporte", value="Reporte 1")
    period = col2.text_input("Período", value="Enero–Marzo 2026")
    publication_date = st.date_input("Fecha de publicación", value=date.today())

    rows: list[dict[str, Any]] = []
    counts = {"Rojo": 0, "Amarillo": 0, "Verde": 0}
    unmatched: list[str] = []

    if uploaded is not None:
        try:
            rows, counts, unmatched = parse_annex(uploaded, data["establecimientos"])
            st.success(
                f"Archivo validado: {len(rows)} establecimientos · "
                f"{counts['Rojo']} rojos · {counts['Amarillo']} amarillos · {counts['Verde']} verdes."
            )
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
            "periodo": period.strip(),
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
            st.success(f"Plan oficial publicado: {len(rows)} establecimientos guardados en Supabase.")
            st.rerun()
        except Exception as exc:
            st.error(f"No fue posible publicar el plan: {exc}")

    st.divider()
    st.write(f"Filas actualmente registradas en `plan_trabajo`: **{len(data['plan_trabajo'])}**")


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

    contracts_tab, plan_tab = st.tabs(["📄 Gestión contractual", "☁️ Plan oficial"])
    with contracts_tab:
        render_contract_admin(data, db)
    with plan_tab:
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
) -> str:
    contracts_json = json.dumps(contracts, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    plans_json = json.dumps(plan_rows, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    preload = f"""
    <script>
      window.__SUPABASE_CONTRACTS__ = {contracts_json};
      window.__SUPABASE_PLAN_ROWS__ = {plans_json};
    </script>
    """
    html = html.replace("</head>", preload + "\n</head>", 1)

    old_load = "function loadLic(){ try{LIC=JSON.parse(localStorage.getItem(LIC_KEY)||'{}');}catch(e){LIC={};} }"
    new_load = "function loadLic(){try{LIC=window.__SUPABASE_CONTRACTS__||{};}catch(e){LIC={};}}"
    html = html.replace(old_load, new_load, 1)

    script = r'''
    <script>
    (() => {
      const norm = value => String(value || '').normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '').toLowerCase()
        .replace(/[^a-z0-9]+/g, ' ').trim();

      const aliases = {
        'crs salvador allende': ['crs s allende','centro de referencia salud occidente salvador allende'],
        'curacavi': ['hospital de curacavi'],
        'ssmocc direccion': ['direccion del servicio metropolitano occidente'],
        'instituto traumatologico': ['instituto traumatologico dr teodoro gebauer','inst traumatologico'],
        'hospital dr felix bulnes cerda': ['felix bulnes'],
        'hospital san juan de dios': ['san juan de dios']
      };

      function currentRow() {
        const rows = window.__SUPABASE_PLAN_ROWS__ || [];
        const selected = [...document.querySelectorAll('select')]
          .map(s => s.options?.[s.selectedIndex]?.textContent || '').join(' ');
        const source = norm(selected);
        for (const row of rows) {
          const base = norm(row.establecimiento);
          const choices = [base, ...(aliases[base] || []).map(norm)];
          if (choices.some(choice => choice && source.includes(choice))) return row;
        }
        return null;
      }

      function renderPlan() {
        const row = currentRow();
        const pending = [...document.querySelectorAll('div,p,span')]
          .find(el => norm(el.textContent).includes('plan comprometido pendiente'));
        if (!pending || !row) return false;
        let target = pending;
        while (target.parentElement && target.parentElement.textContent.trim() === target.textContent.trim()) {
          target = target.parentElement;
        }
        const escaped = text => String(text || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
        const commitments = escaped(row.compromisos).replace(/\n/g, '<br>');
        target.innerHTML = `
          <div style="padding:16px 18px;border:1px solid #b9d7f2;border-radius:12px;background:#f7fbff;color:#334155">
            <div style="font-weight:800;color:#075a9c;margin-bottom:10px">✅ Plan comprometido oficial</div>
            <div style="line-height:1.55">${commitments || 'Sin compromisos informados.'}</div>
            ${row.responsable ? `<div style="margin-top:12px"><b>Responsable:</b> ${escaped(row.responsable)}</div>` : ''}
            ${row.fecha ? `<div style="margin-top:6px"><b>Fecha comprometida:</b> ${escaped(row.fecha)}</div>` : ''}
          </div>`;
        return true;
      }

      function scheduleRender() {
        let attempts = 0;
        const timer = setInterval(() => {
          attempts += 1;
          if (renderPlan() || attempts >= 12) clearInterval(timer);
        }, 350);
      }

      document.addEventListener('DOMContentLoaded', scheduleRender);
      document.addEventListener('change', event => {
        if (event.target.matches('select')) setTimeout(scheduleRender, 50);
      });
      document.addEventListener('click', event => {
        const button = event.target.closest('button,a');
        if (button && norm(button.textContent).includes('administrador')) {
          event.preventDefault();
          window.top.location.href = 'https://td-ssmocc.streamlit.app/?admin=1';
        }
      }, true);
    })();
    </script>
    '''
    html = html.replace("</body>", script + "\n</body>", 1)
    return html


def apply_layout_patch(html: str) -> str:
    patch = """
    <style>
      html,body{width:100%!important;max-width:100%!important;overflow-x:hidden!important}
      [class~="max-w-[1600px]"]{max-width:100%!important}
      @media(min-width:1024px){#sidebar{position:static!important;inset:auto!important;transform:none!important;max-height:none!important;height:auto!important;overflow:visible!important;align-self:flex-start!important}}
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
    )
    html = apply_layout_patch(html)
    components.html(html, height=4300, scrolling=False)


if __name__ == "__main__":
    main()
