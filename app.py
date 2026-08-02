from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client

st.set_page_config(page_title="Inteligencia de Adquisiciones SSMOCC", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
#MainMenu,footer,[data-testid="stHeader"],[data-testid="stToolbar"]{display:none!important}
[data-testid="stAppViewContainer"],[data-testid="stMain"],[data-testid="stMainBlockContainer"],.block-container{width:100%!important;max-width:100vw!important;padding:0!important;margin:0!important}
[data-testid="stVerticalBlock"]{gap:0!important}
iframe[title="streamlit.components.v1.html"]{width:100%!important;max-width:100%!important;border:0!important;display:block!important}
</style>
""", unsafe_allow_html=True)

BASE_DIR = Path(__file__).resolve().parent


def secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


@st.cache_resource
def public_db():
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY en Streamlit Secrets.")
    return create_client(url, key)


@st.cache_resource
def admin_db():
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_SERVICE_KEY")
    return create_client(url, key) if url and key else None


def read_table(name: str, columns: str = "*"):
    return list(public_db().table(name).select(columns).execute().data or [])


def load_data():
    try:
        public_db().table("establecimientos").select("id").limit(1).execute()
        establishments = [r for r in read_table("establecimientos", "id,nombre,codigo,activo") if r.get("activo", True)]
        contracts = read_table("contratos")
        return establishments, contracts
    except Exception as exc:
        st.error(f"No fue posible conectar con Supabase: {exc}")
        return [], []


def dashboard_contracts(establishments, contracts):
    names = {r.get("id"): r.get("nombre", "") for r in establishments}
    result = {}
    for row in contracts:
        establishment = row.get("establecimiento") or names.get(row.get("establecimiento_id"), "")
        tender = str(row.get("licitacion") or "").strip()
        if not establishment or not tender:
            continue
        result[f"{establishment}||{tender}"] = {
            "adj": float(row.get("monto_adjudicado") or 0),
            "awardDate": str(row.get("fecha_adjudicacion") or ""),
            "durationMonths": int(row.get("duracion_meses") or 0),
            "renewalLead": int(row.get("anticipacion_renovacion") or 6),
            "manager": str(row.get("responsable") or ""),
            "contractStatus": str(row.get("estado_administrativo") or row.get("estado") or "Vigente"),
            "notes": str(row.get("observaciones") or ""),
            "updatedAt": str(row.get("actualizado_en") or row.get("ultima_actualizacion") or ""),
        }
    return result


def return_to_dashboard():
    st.session_state["admin_authenticated"] = False
    st.query_params.clear()
    st.rerun()


def admin_panel(establishments, contracts):
    top_left, top_right = st.columns([5, 1])
    with top_left:
        st.markdown("## 🔐 Administración contractual")
    with top_right:
        if st.button("← Volver", use_container_width=True):
            return_to_dashboard()

    password_configured = secret("ADMIN_PASSWORD")
    if not password_configured:
        st.error("Falta configurar ADMIN_PASSWORD en Streamlit Secrets.")
        return

    if not st.session_state.get("admin_authenticated", False):
        with st.form("admin_login"):
            password = st.text_input("Contraseña administrativa", type="password")
            enter = st.form_submit_button("Ingresar")
        if enter:
            if password == password_configured:
                st.session_state["admin_authenticated"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
        return

    col_ok, col_close = st.columns([5, 1])
    col_ok.success("Sesión administrativa activa.")
    if col_close.button("Cerrar sesión"):
        return_to_dashboard()

    db = admin_db()
    if db is None:
        st.warning("Para guardar falta SUPABASE_SERVICE_KEY en Streamlit Secrets.")
        return

    establishment_options = {r["nombre"]: r["id"] for r in establishments if r.get("nombre") and r.get("id") is not None}
    if not establishment_options:
        st.error("No existen establecimientos disponibles en Supabase.")
        return

    existing = {"Crear nuevo contrato": {}}
    id_to_name = {v: k for k, v in establishment_options.items()}
    for contract in contracts:
        label = f"{contract.get('licitacion', 'Sin código')} · {id_to_name.get(contract.get('establecimiento_id'), 'Sin establecimiento')}"
        existing[label] = contract

    selected_label = st.selectbox("Contrato a gestionar", list(existing))
    selected = existing[selected_label]
    establishment_names = list(establishment_options)
    selected_name = id_to_name.get(selected.get("establecimiento_id"), establishment_names[0])

    with st.form("contract_form"):
        establishment = st.selectbox("Establecimiento", establishment_names, index=establishment_names.index(selected_name))
        tender = st.text_input("Licitación / instrumento", value=str(selected.get("licitacion") or ""), placeholder="Ejemplo: 1288-32-LR24")
        amount = st.number_input("Monto adjudicado", min_value=0.0, step=100000.0, value=float(selected.get("monto_adjudicado") or 0), format="%.0f")
        raw_date = selected.get("fecha_adjudicacion")
        try:
            default_date = date.fromisoformat(str(raw_date)) if raw_date else date.today()
        except ValueError:
            default_date = date.today()
        award_date = st.date_input("Fecha de adjudicación", value=default_date)
        c1, c2 = st.columns(2)
        duration = c1.number_input("Duración (meses)", 1, 240, int(selected.get("duracion_meses") or 12))
        renewal = c2.number_input("Anticipación de renovación (meses)", 0, 36, int(selected.get("anticipacion_renovacion") or 6))
        statuses = ["Vigente", "En renovación", "Prorrogado", "Finalizado", "Suspendido"]
        current_status = str(selected.get("estado_administrativo") or selected.get("estado") or "Vigente")
        status = st.selectbox("Estado administrativo", statuses, index=statuses.index(current_status) if current_status in statuses else 0)
        manager = st.text_input("Responsable", value=str(selected.get("responsable") or ""))
        observations = st.text_area("Observaciones", value=str(selected.get("observaciones") or ""), height=100)
        save = st.form_submit_button("💾 Guardar gestión contractual", use_container_width=True)

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
            st.success("Gestión contractual guardada en Supabase.")
            st.rerun()
        except Exception as exc:
            st.error(f"No fue posible guardar: {exc}")


def load_html():
    for name in ("index.html", "index_dashboard_final_corregido_gestion.html"):
        path = BASE_DIR / name
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("No se encontró index.html junto a app.py.")


def prepare_html(html: str, payload: dict):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("</head>", f"<script>window.__SUPABASE_CONTRACTS__={data};</script>\n</head>", 1)
    html = html.replace("function loadLic(){ try{LIC=JSON.parse(localStorage.getItem(LIC_KEY)||'{}');}catch(e){LIC={};} }", "function loadLic(){try{LIC=window.__SUPABASE_CONTRACTS__||{};}catch(e){LIC={};}}", 1)
    html = html.replace("function saveLic(){ try{localStorage.setItem(LIC_KEY,JSON.stringify(LIC));}catch(e){} }", "function saveLic(){try{toast('Use el botón Administrador para guardar en Supabase');}catch(e){}}", 1)
    bridge = r'''
<script>
document.addEventListener('DOMContentLoaded',()=>{
  const btn=[...document.querySelectorAll('button,a')].find(el=>(el.textContent||'').trim().toLowerCase().includes('administrador'));
  if(!btn)return;
  btn.addEventListener('click',e=>{
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
    const origin=(window.location.ancestorOrigins&&window.location.ancestorOrigins[0])?window.location.ancestorOrigins[0]:'https://td-ssmocc.streamlit.app';
    window.top.location.href=origin+'/?admin=1';
  },true);
});
</script>
'''
    html = html.replace("</body>", bridge + "</body>", 1)
    patch = '''<style>html,body{width:100%!important;max-width:100%!important;overflow-x:hidden!important}[class~="max-w-[1600px]"]{max-width:100%!important}@media(min-width:1024px){#sidebar{position:static!important;inset:auto!important;transform:none!important;max-height:none!important;height:auto!important;overflow:visible!important;align-self:flex-start!important}}</style>'''
    return html.replace("</head>", patch + "</head>", 1)


def main():
    establishments, contracts = load_data()
    admin_requested = str(st.query_params.get("admin", "0")) == "1"
    if admin_requested or st.session_state.get("admin_authenticated", False):
        admin_panel(establishments, contracts)
        st.stop()
    try:
        html = prepare_html(load_html(), dashboard_contracts(establishments, contracts))
    except FileNotFoundError as exc:
        st.error(str(exc)); st.stop()
    components.html(html, height=4300, scrolling=False)


if __name__ == "__main__":
    main()
