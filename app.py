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
# CONFIGURACIÓN DE PÁGINA Y ALÍCUOTAS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema de Administración de Condominio",
    page_icon="🏢",
    layout="wide"
)

ALICUOTAS = {
    f"Apto {i}": round(100.0 / 13, 2) for i in range(1, 14)
}

# -----------------------------------------------------------------------------
# CONEXIÓN Y SECRETS
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
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    usuario VARCHAR(20) PRIMARY KEY,
                    clave VARCHAR(100) NOT NULL,
                    rol VARCHAR(20) NOT NULL
                );
            """))

            admin_pwd = st.secrets.get("ADMIN_PASSWORD", "admin123")
            res_admin = conn.execute(text("SELECT usuario FROM usuarios WHERE usuario = 'admin'")).fetchone()
            if not res_admin:
                conn.execute(text("INSERT INTO usuarios (usuario, clave, rol) VALUES ('admin', :p, 'admin')"), {"p": admin_pwd})

            for i in range(1, 14):
                apto_name = f"Apto {i}"
                res_apto = conn.execute(text("SELECT usuario FROM usuarios WHERE usuario = :u"), {"u": apto_name}).fetchone()
                if not res_apto:
                    conn.execute(text("INSERT INTO usuarios (usuario, clave, rol) VALUES (:u, '1234', 'propietario')"), {"u": apto_name})

            conn.commit()
    except Exception:
        pass

inicializar_tablas()

# -----------------------------------------------------------------------------
# MOTOR DE CÁLCULO DE MOROSIDAD
# -----------------------------------------------------------------------------
def calcular_estado_cuenta_acumulado(apartamento, mes_hasta):
    """Calcula el estado financiero histórico de un inmueble hasta un mes dado."""
    if not engine:
        return {"mes_actual": 0.0, "deuda_anterior": 0.0, "pagos_mes": 0.0, "total_deber": 0.0}
    
    try:
        with engine.connect() as conn:
            # Obtener todos los meses registrados con gastos
            df_gastos = pd.read_sql(
                text("SELECT mes_anio, COALESCE(SUM(monto), 0) as total_gasto FROM gastos WHERE estatus = 'Aprobado' AND mes_anio <= :m GROUP BY mes_anio ORDER BY mes_anio ASC"),
                conn, params={"m": mes_hasta}
            )
            
            # Obtener todos los pagos aprobados
            df_pagos = pd.read_sql(
                text("SELECT mes_anio, COALESCE(SUM(monto), 0) as total_pago FROM pagos_reportados WHERE apartamento = :ap AND estatus = 'Aprobado' AND mes_anio <= :m GROUP BY mes_anio"),
                conn, params={"ap": apartamento, "m": mes_hasta}
            )

        pct = ALICUOTAS.get(apartamento, 7.69) / 100.0
        
        pagos_dict = dict(zip(df_pagos['mes_anio'], df_pagos['total_pago'])) if not df_pagos.empty else {}
        
        deuda_anterior = 0.0
        cuota_mes_actual = 0.0
        pagos_mes_actual = 0.0

        if not df_gastos.empty:
            for _, row in df_gastos.iterrows():
                m = row['mes_anio']
                gasto = float(row['total_gasto'])
                cuota = round(gasto * pct, 2)
                pago = float(pagos_dict.get(m, 0.0))

                if m == mes_hasta:
                    cuota_mes_actual = cuota
                    pagos_mes_actual = pago
                else:
                    deuda_anterior += (cuota - pago)

        # Si el usuario realizó pagos en el mes actual que cubren deuda anterior
        total_adeudado = round(deuda_anterior + cuota_mes_actual - pagos_mes_actual, 2)

        return {
            "mes_actual": cuota_mes_actual,
            "deuda_anterior": round(deuda_anterior, 2),
            "pagos_mes": pagos_mes_actual,
            "total_deber": total_adeudado
        }
    except Exception as e:
        return {"error": str(e), "mes_actual": 0.0, "deuda_anterior": 0.0, "pagos_mes": 0.0, "total_deber": 0.0}

# -----------------------------------------------------------------------------
# RECIBOS PDF
# -----------------------------------------------------------------------------
def generar_pdf_recibo(apartamento, mes_anio, datos_cuenta):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontSize=18, alignment=1, spaceAfter=15
    )
    story.append(Paragraph(f"ESTADO DE CUENTA - {mes_anio}", title_style))
    story.append(Paragraph(f"<b>Inmueble:</b> {apartamento}", styles['Normal']))
    story.append(Paragraph(f"<b>Fecha de Emisión:</b> {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
    story.append(Spacer(1, 15))

    data_resumen = [
        ["Concepto", "Monto ($)"],
        ["Deuda Acumulada Meses Anteriores", f"${datos_cuenta['deuda_anterior']:,.2f}"],
        [f"Cuota Mes Actual ({mes_anio})", f"${datos_cuenta['mes_actual']:,.2f}"],
        ["Pagos Validados en el Mes", f"-${datos_cuenta['pagos_mes']:,.2f}"],
        ["TOTAL PENDIENTE A LA FECHA", f"${datos_cuenta['total_deber']:,.2f}"]
    ]
    t = Table(data_resumen, colWidths=[300, 200])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FEE2E2')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#991B1B')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    story.append(t)
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# -----------------------------------------------------------------------------
# CONTROL DE SESIÓN
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
# 1. PORTAL DE ACCESO
# -----------------------------------------------------------------------------
if not st.session_state.usuario_logueado:
    st.markdown("<h2 style='text-align: center;'>🔒 Portal de Acceso</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Ingresa tus credenciales para continuar.</p>", unsafe_allow_html=True)
    
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
# 2. VISTA PROPIETARIOS
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

    tab1, tab2, tab3 = st.tabs(["📊 Estado de Cuenta y Morosidad", "📥 Reportar Pago", "📋 Historial de Pagos"])

    with tab1:
        mes_filtro = st.text_input("Consulta de mes (AAAA-MM):", value=datetime.now().strftime("%Y-%m"))
        
        datos = calcular_estado_cuenta_acumulado(user_actual, mes_filtro)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Morosidad Anterior", f"${datos['deuda_anterior']:,.2f}")
        c2.metric("Cuota Mes Actual", f"${datos['mes_actual']:,.2f}")
        c3.metric("Pagos Aprobados", f"${datos['pagos_mes']:,.2f}")
        c4.metric("TOTAL A PAGAR", f"${datos['total_deber']:,.2f}", delta=-datos['total_deber'] if datos['total_deber'] > 0 else 0)

        st.write("---")
        pdf_bytes = generar_pdf_recibo(user_actual, mes_filtro, datos)
        st.download_button(
            label="📄 Descargar Estado de Cuenta en PDF",
            data=pdf_bytes,
            file_name=f"Estado_Cuenta_{user_actual}_{mes_filtro}.pdf",
            mime="application/pdf"
        )

    with tab2:
        st.subheader("Reportar Comprobante de Pago")
        with st.form("form_pago", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("Apartamento", value=user_actual, disabled=True)
                mes_pago = st.text_input("Mes a Abonar (AAAA-MM)", value=datetime.now().strftime("%Y-%m"))
                monto = st.number_input("Monto Pagado ($)", min_value=0.01, step=0.01)
            with c2:
                metodo = st.selectbox("Método de Pago", ["Transferencia Bancaria", "Pago Móvil", "Zelle", "Efectivo $"])
                referencia = st.text_input("Número de Referencia")
                fecha_pago = st.date_input("Fecha de Pago", value=datetime.now().date())

            comprobante = st.file_uploader("Adjuntar Comprobante", type=["png", "jpg", "jpeg", "pdf"])
            btn_subir = st.form_submit_button("🚀 Registrar Pago", type="primary")

            if btn_subir:
                if not referencia.strip():
                    st.error("Ingresa la referencia de pago.")
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
                        st.success("✅ Pago registrado para validación.")
                    except Exception as e:
                        st.error(f"Error registrando pago: {e}")

    with tab3:
        try:
            with engine.connect() as conn:
                df = pd.read_sql(
                    text("SELECT mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus FROM pagos_reportados WHERE apartamento = :a ORDER BY id DESC"),
                    conn, params={"a": user_actual}
                )
            if df.empty:
                st.info("Sin registros de pago.")
            else:
                st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Error cargando pagos: {e}")

# -----------------------------------------------------------------------------
# 3. VISTA ADMINISTRACIÓN
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

    t1, t2, t3, t4 = st.tabs(["📊 Registrar Gastos", "✅ Validar Pagos", "🚨 Reporte de Morosidad", "📋 Gastos del Mes"])

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
                st.info("No hay pagos pendientes por revisar.")
            else:
                st.dataframe(df_p, use_container_width=True)
                pid = st.selectbox("Seleccionar ID de Pago:", df_p["id"].tolist())
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
            st.error(f"Error en validación: {e}")

    with t3:
        st.subheader("Tabla General de Morosidad")
        mes_eval = st.text_input("Evaluar morosidad hasta (AAAA-MM):", value=datetime.now().strftime("%Y-%m"), key="admin_moroso")
        
        filas_m = []
        total_deuda_edificio = 0.0

        for apto in ALICUOTAS.keys():
            res = calcular_estado_cuenta_acumulado(apto, mes_eval)
            deuda = res["total_deber"]
            total_deuda_edificio += deuda
            
            estatus = "🟢 Al día" if deuda <= 0 else ("🟡 Cuota Pendiente" if deuda <= res["mes_actual"] else "🔴 Moroso")

            filas_m.append({
                "Inmueble": apto,
                "Deuda Anterior ($)": f"${res['deuda_anterior']:,.2f}",
                "Mes Actual ($)": f"${res['mes_actual']:,.2f}",
                "Abonado ($)": f"${res['pagos_mes']:,.2f}",
                "Deuda Total ($)": f"${deuda:,.2f}",
                "Estatus": estatus
            })

        st.metric("Deuda Total Acumulada del Condominio", f"${total_deuda_edificio:,.2f}")
        st.dataframe(pd.DataFrame(filas_m), use_container_width=True)

    with t4:
        st.subheader("Consulta de Gastos por Mes")
        mes_g_search = st.text_input("Mes (AAAA-MM):", value=datetime.now().strftime("%Y-%m"), key="g_search")
        try:
            with engine.connect() as conn:
                df_g = pd.read_sql(
                    text("SELECT id, concepto, monto, fecha FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    conn, params={"m": mes_g_search}
                )
            if df_g.empty:
                st.info("Sin gastos registrados para este periodo.")
            else:
                st.dataframe(df_g, use_container_width=True)
                st.metric("Total Gastos del Mes", f"${df_g['monto'].sum():,.2f}")
        except Exception as e:
            st.error(f"Error cargando gastos: {e}")
