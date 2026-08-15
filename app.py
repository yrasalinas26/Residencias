import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema de Administración de Condominio",
    page_icon="🏢",
    layout="wide"
)

# Alícuotas por apartamento (porcentaje de participación)
ALICUOTAS = {
    f"Apto {i}": round(100.0 / 13, 2) for i in range(1, 14)
}

# -----------------------------------------------------------------------------
# CONEXIÓN A BASE DE DATOS Y SECRETS
# -----------------------------------------------------------------------------
@st.cache_resource
def obtener_engine():
    try:
        if "DATABASE_URL" in st.secrets:
            url = st.secrets["DATABASE_URL"]
        else:
            return None, "No se encontró DATABASE_URL en Secrets."

        engine = create_engine(
            url,
            connect_args={"prepare_threshold": None},
            pool_pre_ping=True
        )
        return engine, None
    except Exception as e:
        return None, str(e)

engine, error_conexion = obtener_engine()

def inicializar_tablas():
    if not engine:
        return
    try:
        with engine.connect() as conn:
            # Tabla de Gastos
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS gastos (
                    id SERIAL PRIMARY KEY,
                    mes_anio VARCHAR(7) NOT NULL,
                    concepto VARCHAR(200) NOT NULL,
                    monto NUMERIC(12,2) NOT NULL,
                    estatus VARCHAR(20) DEFAULT 'Aprobado',
                    fecha DATE DEFAULT CURRENT_DATE
                );
            """))
            # Tabla de Pagos Reportados
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS pagos_reportados (
                    id SERIAL PRIMARY KEY,
                    apartamento VARCHAR(10) NOT NULL,
                    mes_anio VARCHAR(7) NOT NULL,
                    monto NUMERIC(12, 2) NOT NULL,
                    metodo_pago VARCHAR(50) NOT NULL,
                    referencia VARCHAR(100) NOT NULL,
                    fecha_pago DATE NOT NULL,
                    comprobante_nombre VARCHAR(255),
                    estatus VARCHAR(20) DEFAULT 'Pendiente',
                    fecha_reporte TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            # Tabla de Usuarios / Credenciales
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    usuario VARCHAR(20) PRIMARY KEY,
                    clave VARCHAR(100) NOT NULL,
                    rol VARCHAR(20) NOT NULL
                );
            """))

            # Crear administrador desde Secrets o por defecto
            admin_pwd = st.secrets.get("ADMIN_PASSWORD", "admin123")
            res_admin = conn.execute(text("SELECT usuario FROM usuarios WHERE usuario = 'admin'")).fetchone()
            if not res_admin:
                conn.execute(text("INSERT INTO usuarios (usuario, clave, rol) VALUES ('admin', :p, 'admin')"), {"p": admin_pwd})

            # Crear credenciales para Aptos (1 al 13)
            for i in range(1, 14):
                apto_name = f"Apto {i}"
                res_apto = conn.execute(text("SELECT usuario FROM usuarios WHERE usuario = :u"), {"u": apto_name}).fetchone()
                if not res_apto:
                    conn.execute(text("INSERT INTO usuarios (usuario, clave, rol) VALUES (:u, '1234', 'propietario')"), {"u": apto_name})

            conn.commit()
    except Exception as e:
        pass

inicializar_tablas()

# -----------------------------------------------------------------------------
# FUNCIONALIDAD DE RECIBOS EN PDF
# -----------------------------------------------------------------------------
def generar_pdf_recibo(apartamento, mes_anio, cuota_base, pagos, saldo_deber):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=1,
        spaceAfter=15
    )
    story.append(Paragraph(f"RECIBO DE CONDOMINIO - {mes_anio}", title_style))
    story.append(Paragraph(f"<b>Unidad / Inmueble:</b> {apartamento}", styles['Normal']))
    story.append(Paragraph(f"<b>Fecha de Emisión:</b> {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
    story.append(Spacer(1, 15))

    data_resumen = [
        ["Concepto", "Monto ($)"],
        [f"Cuota de Condominio ({ALICUOTAS.get(apartamento, 7.69)}%)", f"${cuota_base:,.2f}"],
        ["Total Abonado / Validado", f"${pagos:,.2f}"],
        ["Saldo Pendiente a la Fecha", f"${saldo_deber:,.2f}"]
    ]
    t = Table(data_resumen, colWidths=[300, 200])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    story.append(t)
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# -----------------------------------------------------------------------------
# CONTROL DE SESIÓN NEUTRO
# -----------------------------------------------------------------------------
if "usuario_logueado" not in st.session_state:
    st.session_state.usuario_logueado = None

if "rol_logueado" not in st.session_state:
    st.session_state.rol_logueado = None

def cerrar_sesion():
    st.session_state.usuario_logueado = None
    st.session_state.rol_logueado = None
    st.rerun()

# -----------------------------------------------------------------------------
# 1. ACCESO NEUTRO (UNIFICADO)
# -----------------------------------------------------------------------------
if not st.session_state.usuario_logueado:
    st.markdown("<h2 style='text-align: center;'>🔒 Portal de Acceso</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Ingresa tus datos para acceder a tu panel.</p>", unsafe_allow_html=True)
    
    if error_conexion:
        st.error(f"⚠️ Error de conexión: {error_conexion}")

    with st.form("form_login"):
        usuario_input = st.text_input("Usuario (ej. Apto 1 o admin)").strip()
        clave_input = st.text_input("Contraseña", type="password").strip()
        bot_login = st.form_submit_button("Ingresar", type="primary", use_container_width=True)

        if bot_login:
            if not usuario_input or not clave_input:
                st.error("Por favor completa los campos.")
            elif not engine:
                st.error("Base de datos no disponible.")
            else:
                try:
                    with engine.connect() as conn:
                        row = conn.execute(
                            text("SELECT usuario, clave, rol FROM usuarios WHERE LOWER(usuario) = LOWER(:u)"),
                            {"u": usuario_input}
                        ).fetchone()

                    if row and row[1] == clave_input:
                        st.session_state.usuario_logueado = row[0]
                        st.session_state.rol_logueado = row[2]
                        st.rerun()
                    else:
                        st.error("❌ Credenciales incorrectas.")
                except Exception as e:
                    st.error(f"Error al ingresar: {e}")

# -----------------------------------------------------------------------------
# 2. VISTA DE PROPIETARIOS (RESTAURADA)
# -----------------------------------------------------------------------------
elif st.session_state.rol_logueado == "propietario":
    user_actual = st.session_state.usuario_logueado

    col_head, col_out = st.columns([3, 1])
    with col_head:
        st.title(f"🏢 Panel de Control - {user_actual}")
    with col_out:
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            cerrar_sesion()

    st.write("---")

    tab1, tab2, tab3 = st.tabs(["📊 Mi Estado de Cuenta", "📥 Reportar Pago", "📋 Mis Pagos"])

    # --- TAB 1: ESTADO DE CUENTA Y ALÍCUOTA ---
    with tab1:
        mes_filtro = st.text_input("Mes a consultar (AAAA-MM):", value=datetime.now().strftime("%Y-%m"))
        try:
            with engine.connect() as conn:
                # Total Gastos
                res_gastos = conn.execute(
                    text("SELECT COALESCE(SUM(monto), 0) FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    {"m": mes_filtro}
                ).scalar()

                # Pagos aprobados del inmueble
                res_pagos = conn.execute(
                    text("SELECT COALESCE(SUM(monto), 0) FROM pagos_reportados WHERE apartamento = :ap AND mes_anio = :m AND estatus = 'Aprobado'"),
                    {"ap": user_actual, "m": mes_filtro}
                ).scalar()

            alicuota_pct = ALICUOTAS.get(user_actual, 7.69)
            cuota_monto = round(float(res_gastos) * (alicuota_pct / 100.0), 2)
            saldo = round(cuota_monto - float(res_pagos), 2)

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Gastos Comunes Totales", f"${res_gastos:,.2f}")
            col_m2.metric(f"Mi Cuota ({alicuota_pct}%)", f"${cuota_monto:,.2f}")
            col_m3.metric("Saldo Pendiente", f"${saldo:,.2f}", delta=-saldo if saldo > 0 else 0)

            st.write("---")
            # Descargar Recibo
            pdf_bytes = generar_pdf_recibo(user_actual, mes_filtro, cuota_monto, float(res_pagos), saldo)
            st.download_button(
                label="📄 Descargar Recibo Digital (PDF)",
                data=pdf_bytes,
                file_name=f"Recibo_{user_actual}_{mes_filtro}.pdf",
                mime="application/pdf"
            )

        except Exception as e:
            st.error(f"Error consultando saldo: {e}")

    # --- TAB 2: FORMULARIO DE PAGO ---
    with tab2:
        st.subheader("Reportar Comprobante de Pago")
        with st.form("form_pago", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("Apartamento", value=user_actual, disabled=True)
                mes_pago = st.text_input("Mes / Año", value=datetime.now().strftime("%Y-%m"))
                monto = st.number_input("Monto Pagado ($)", min_value=0.01, step=0.01)
            with c2:
                metodo = st.selectbox("Método", ["Transferencia Bancaria", "Pago Móvil", "Zelle", "Efectivo $"])
                referencia = st.text_input("Número de Referencia")
                fecha_pago = st.date_input("Fecha de Operación", value=datetime.now().date())

            comprobante = st.file_uploader("Adjuntar Comprobante", type=["png", "jpg", "jpeg", "pdf"])
            btn_subir = st.form_submit_button("🚀 Registrar Pago", type="primary")

            if btn_subir:
                if not referencia.strip():
                    st.error("Debes ingresar el número de referencia.")
                else:
                    nombre = comprobante.name if comprobante else "Sin comprobante"
                    try:
                        with engine.connect() as conn:
                            conn.execute(text("""
                                INSERT INTO pagos_reportados (apartamento, mes_anio, monto, metodo_pago, referencia, fecha_pago, comprobante_nombre, estatus)
                                VALUES (:apto, :mes, :monto, :metodo, :ref, :fecha, :comp, 'Pendiente')
                            """), {
                                "apto": user_actual, "mes": mes_pago, "monto": monto,
                                "metodo": metodo, "ref": referencia, "fecha": fecha_pago, "comp": nombre
                            })
                            conn.commit()
                        st.success("✅ Pago registrado correctamente.")
                    except Exception as e:
                        st.error(f"Error registrando el pago: {e}")

    # --- TAB 3: CONSULTAR PAGOS ---
    with tab3:
        try:
            with engine.connect() as conn:
                df = pd.read_sql(
                    text("SELECT mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus FROM pagos_reportados WHERE apartamento = :a ORDER BY id DESC"),
                    conn, params={"a": user_actual}
                )
            if df.empty:
                st.info("No se registran pagos previos.")
            else:
                st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Error al cargar historial: {e}")

# -----------------------------------------------------------------------------
# 3. VISTA DE ADMINISTRACIÓN (RESTAURADA)
# -----------------------------------------------------------------------------
elif st.session_state.rol_logueado == "admin":
    col_head, col_out = st.columns([3, 1])
    with col_head:
        st.title("⚙️ Módulo de Administración")
    with col_out:
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            cerrar_sesion()

    st.write("---")

    t1, t2, t3 = st.tabs(["📊 Registrar Gastos", "✅ Validar Pagos", "📋 Distribución por Alícuota"])

    with t1:
        st.subheader("Cargar Nuevo Gasto Común")
        with st.form("form_gasto_admin"):
            mes = st.text_input("Mes / Año (AAAA-MM)", value=datetime.now().strftime("%Y-%m"))
            concepto = st.text_input("Descripción del Gasto")
            monto = st.number_input("Monto Total ($)", min_value=0.01, step=0.01)
            btn = st.form_submit_button("Guardar Gasto", type="primary")

            if btn and concepto:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("INSERT INTO gastos (mes_anio, concepto, monto, estatus) VALUES (:m, :c, :mo, 'Aprobado')"),
                            {"m": mes, "c": concepto, "mo": monto}
                        )
                        conn.commit()
                    st.success("Gasto guardado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error registrando gasto: {e}")

    with t2:
        st.subheader("Pagos Pendientes por Validar")
        try:
            with engine.connect() as conn:
                df_p = pd.read_sql(
                    text("SELECT id, apartamento, mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus FROM pagos_reportados WHERE estatus = 'Pendiente' ORDER BY id ASC"),
                    conn
                )
            if df_p.empty:
                st.info("No hay pagos pendientes.")
            else:
                st.dataframe(df_p, use_container_width=True)
                pid = st.selectbox("Selecciona ID de pago:", df_p["id"].tolist())
                ca, cr = st.columns(2)
                with ca:
                    if st.button("✅ Aprobar Pago", use_container_width=True):
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE pagos_reportados SET estatus = 'Aprobado' WHERE id = :i"), {"i": pid})
                            conn.commit()
                        st.success(f"Pago #{pid} Aprobado.")
                        st.rerun()
                with cr:
                    if st.button("❌ Rechazar Pago", use_container_width=True):
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE pagos_reportados SET estatus = 'Rechazado' WHERE id = :i"), {"i": pid})
                            conn.commit()
                        st.warning(f"Pago #{pid} Rechazado.")
                        st.rerun()
        except Exception as e:
            st.error(f"Error procesando pagos: {e}")

    with t3:
        st.subheader("Distribución de Gastos por Inmueble")
        mes_calculo = st.text_input("Mes a calcular (AAAA-MM)", value=datetime.now().strftime("%Y-%m"), key="calc")
        try:
            with engine.connect() as conn:
                total_g = conn.execute(
                    text("SELECT COALESCE(SUM(monto), 0) FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    {"m": mes_calculo}
                ).scalar()

            st.metric(f"Total Gastos {mes_calculo}", f"${total_g:,.2f}")
            
            filas = []
            for apto, pct in ALICUOTAS.items():
                cuota = round(float(total_g) * (pct / 100.0), 2)
                filas.append({"Inmueble": apto, "Alícuota (%)": f"{pct}%", "Cuota Correspondiente ($)": f"${cuota:,.2f}"})

            st.dataframe(pd.DataFrame(filas), use_container_width=True)
        except Exception as e:
            st.error(f"Error generando distribución: {e}")
