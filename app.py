import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# ---------------------------------------------------------
# 1. CONFIGURACIÓN DE CONEXIÓN A SUPABASE
# ---------------------------------------------------------
st.set_page_config(page_title="Administración de Condominio", layout="wide")

@st.cache_resource
def get_db_engine():
    try:
        db_url = st.secrets["postgres"]["url"]
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return create_engine(db_url, pool_pre_ping=True, pool_recycle=300)
    except Exception as e:
        st.error(f"Error cargando st.secrets: {e}")
        return None

engine = get_db_engine()

# Inicialización de tablas en la BD
def init_db():
    if engine:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS gastos (
                    id SERIAL PRIMARY KEY,
                    descripcion TEXT NOT NULL,
                    monto NUMERIC(10,2) NOT NULL,
                    fecha DATE DEFAULT CURRENT_DATE
                );
                CREATE TABLE IF NOT EXISTS pagos (
                    id SERIAL PRIMARY KEY,
                    apartamento VARCHAR(10) NOT NULL,
                    monto NUMERIC(10,2) NOT NULL,
                    referencia TEXT,
                    estatus VARCHAR(20) DEFAULT 'Pendiente',
                    fecha DATE DEFAULT CURRENT_DATE
                );
            """))

if engine:
    init_db()

# ---------------------------------------------------------
# 2. ESTRUCTURA Y ALÍCUOTAS DEL CONDOMINIO (13 APARTAMENTOS)
# ---------------------------------------------------------
ALICUOTAS = {
    '1A': 0.06, '1B': 0.06,
    '2':  0.12,
    '3A': 0.06, '3B': 0.06,
    '4A': 0.06, '4B': 0.06,
    '5A': 0.06, '5B': 0.06,
    '6A': 0.06, '6B': 0.06,
    '7':  0.12,
    'PH': 0.16
}

# ---------------------------------------------------------
# 3. FUNCIONES AUXILIARES (PDF Y WHATSAPP)
# ---------------------------------------------------------
def generar_pdf_recibo(apto, monto, referencia):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 750, "RECIBO DE PAGO DE CONDOMINIO")
    c.setFont("Helvetica", 12)
    c.drawString(100, 710, f"Apartamento: {apto}")
    c.drawString(100, 690, f"Monto Registrado: ${monto:.2f}")
    c.drawString(100, 670, f"Referencia / Confirmación: {referencia}")
    c.drawString(100, 650, "Estatus: Confirmado / Validado")
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def crear_link_whatsapp(mensaje):
    texto_encoded = urllib.parse.quote(mensaje)
    return f"https://wa.me/?text={texto_encoded}"

# ---------------------------------------------------------
# 4. INTERFAZ DE USUARIO (STREAMLIT)
# ---------------------------------------------------------
st.title("🏢 Gestión de Condominio")

tab1, tab2, tab3 = st.tabs(["📊 Distribución de Gastos", "💳 Reportar/Validar Pagos", "🔐 Administración"])

# --- TAB 1: GASTOS ---
with tab1:
    st.header("Cálculo de Cuotas Comunes")
    monto_total_gasto = st.number_input("Monto Total del Gasto ($)", min_value=0.0, step=10.0)
    
    if monto_total_gasto > 0:
        st.subheader("Cuota por Apartamento")
        tabla_calculos = []
        for apto, pct in ALICUOTAS.items():
            tabla_calculos.append({
                "Apartamento": apto,
                "Alícuota (%)": f"{int(pct * 100)}%",
                "Monto a Pagar ($)": round(monto_total_gasto * pct, 2)
            })
        df_gastos = pd.DataFrame(tabla_calculos)
        st.dataframe(df_gastos, use_container_width=True)

# --- TAB 2: PAGOS ---
with tab2:
    st.header("Registro de Pagos por Propietario")
    with st.form("form_pago"):
        apto_sel = st.selectbox("Selecciona tu Apartamento", list(ALICUOTAS.keys()))
        monto_pago = st.number_input("Monto Pagado ($)", min_value=0.0, step=1.0)
        ref_pago = st.text_input("Número de Referencia / Comprobante")
        submit_pago = st.form_submit_button("Registrar Pago")

        if submit_pago and engine:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO pagos (apartamento, monto, referencia, estatus)
                    VALUES (:apto, :monto, :ref, 'Pendiente')
                """), {"apto": apto_sel, "monto": monto_pago, "ref": ref_pago})
            st.success(f"¡Pago del Apto {apto_sel} registrado con éxito!")
            
            # Notificación por WhatsApp
            msg_ws = f"Hola Admin, he registrado un pago de ${monto_pago:.2f} para el Apto {apto_sel}. Ref: {ref_pago}"
            st.markdown(f"[📲 Notificar Pago por WhatsApp]({crear_link_whatsapp(msg_ws)})")

# --- TAB 3: ADMIN ---
with tab3:
    st.header("Panel Administrativo")
    admin_pass = st.text_input("Clave de Administrador", type="password")
    
    if admin_pass == st.secrets.get("ADMIN_PASSWORD", "admin"):
        st.success("Acceso concedido")
        if engine:
            df_pagos = pd.read_sql("SELECT * FROM pagos ORDER BY id DESC", engine)
            st.dataframe(df_pagos, use_container_width=True)
            
            st.subheader("Generar Recibo de Pago")
            if not df_pagos.empty:
                id_pago = st.selectbox("Seleccionar Pago Registrado", df_pagos['id'].tolist())
                row = df_pagos[df_pagos['id'] == id_pago].iloc[0]
                
                pdf_data = generar_pdf_recibo(row['apartamento'], row['monto'], row['referencia'])
                st.download_button(
                    label="📄 Descargar Recibo PDF",
                    data=pdf_data,
                    file_name=f"recibo_apto_{row['apartamento']}.pdf",
                    mime="application/pdf"
                )
    elif admin_pass:
        st.error("Contraseña incorrecta")
