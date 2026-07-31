import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Monitoreo Trato Directo SSMOCC",
    layout="wide"
)

with open("index.html", "r", encoding="utf-8") as archivo:
    dashboard = archivo.read()

components.html(dashboard, height=4000, scrolling=True)
