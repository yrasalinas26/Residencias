import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

st.set_page_config(page_title="Sistema de Condominio", page_icon="🏢", layout="wide")

# --- CONEXIÓN A BASE DE DATOS (NO DETIENE LA APP SI FALLA) ---
engine = None
try:
    if "DATABASE_URL" in st.secrets:
        DB_URL = st.secrets["DATABASE_URL"]
        engine = create_engine(DB_URL)
    elif "connections" in st.secrets:
        pg = st.secrets["connections"]["postgresql"]
        DB_URL = f"postgresql://{pg['username']}:{pg['password']}@{pg['host']}:{pg.get('port', 5432)}/{pg['database']}"
        engine = create_engine(DB_URL)
except Exception as e:
    st.sidebar.error("⚠️ Base de datos no conectada. Configura tus Secrets.")

# --- INICIALIZACIÓN DE TABLAS (SOLO SI HAY CONEXIÓN) ---
def init_db():
    if engine:
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, mes_anio VARCHAR(7), concepto VARCHAR(200), monto NUMERIC(12,2), estatus VARCHAR(20) DEFAULT 'Aprobado');"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS pagos_reportados (id SERIAL PRIMARY KEY, apartamento VARCHAR(10), mes_anio VARCHAR(7), monto NUMERIC(12,2), metodo_pago VARCHAR(50), referencia VARCHAR(100), fecha_pago DATE, comprobante_nombre VARCHAR(255), estatus VARCHAR(20) DEFAULT 'Pendiente', fecha_reporte TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"))
            conn.commit()
init_db()

# --- ESTADO DE NAVEGACIÓN ---
if "rol_activo" not in st.session_state:
    st.session_state.rol_activo = "Inicio"

# --- VISTAS ---
def vista_inicio_neutro():
    st.markdown("<h1 style='text-align: center;'>🏢 Portal de Administración</h1>", unsafe_allow_html=True)
    st.info("Selecciona tu perfil:")
    col1, col2 = st.columns(2)
    if col1.button("Ingresar como Propietario"):
        st.session_state.rol_activo = "Propietario"
        st.rerun()
    if col2.button("Ingresar como Administrador"):
        st.session_state.rol_activo = "Administrador"
        st.rerun()

# [AQUÍ IRÍAN LAS FUNCIONES vista_propietario Y vista_administrador QUE TENÍAMOS ANTES]
# ... (Mantén el resto del código igual)

# --- NAVEGACIÓN PRINCIPAL ---
if st.session_state.rol_activo == "Inicio":
    vista_inicio_neutro()
elif st.session_state.rol_activo == "Propietario":
    # vista_propietario()
    st.write("Vista Propietario en desarrollo")
elif st.session_state.rol_activo == "Administrador":
    # vista_administrador()
    st.write("Vista Administrador en desarrollo")
