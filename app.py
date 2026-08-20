import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
import io
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA E ICONO PERSONALIZADO
# -----------------------------------------------------------------------------
try:
    logo_img = Image.open("logo.jpg")
except Exception:
    logo_img = "🏢"

st.set_page_config(
    page_title="Sistema de Gestión de Condominios YS",
    page_icon=logo_img,
    layout="wide"
)

UNIDADES_DEFECTO = [
    ("1A", 6.00), ("1B", 6.00),
    ("2", 12.00),
    ("3A", 6.00), ("3B", 6.00),
    ("4A", 6.00), ("4B", 6.00),
    ("5A", 6.00), ("5B", 6.00),
    ("6A", 6.00), ("6B", 6.00),
    ("7", 12.00),
    ("PH", 16.00)
]

# -----------------------------------------------------------------------------
# CONEXIÓN Y BASE DE DATOS
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
                CREATE TABLE IF NOT EXISTS configuracion_edificio (
                    id INT PRIMARY KEY DEFAULT 1,
                    nombre VARCHAR(150) NOT NULL,
                    rif VARCHAR(30) NOT NULL,
                    direccion TEXT NOT NULL
                );
            """))

            res_ed = conn.execute(text("SELECT COUNT(*) FROM configuracion_edificio")).scalar()
            if res_ed == 0:
                conn.execute(text("""
                    INSERT INTO configuracion_edificio (id, nombre, rif, direccion)
                    VALUES (1, 'Residencias El Condominio', 'J-12345678-0', 'Calle Principal, Edificio Central')
                """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS unidades (
                    unidad VARCHAR(10) PRIMARY KEY,
                    alicuota NUMERIC(5,2) NOT NULL,
                    propietario VARCHAR(100) DEFAULT 'Sin Asignar',
                    telefono VARCHAR(30) DEFAULT ''
                );
            """))

            try:
                conn.execute(text("ALTER TABLE unidades ADD COLUMN IF NOT EXISTS propietario VARCHAR(100) DEFAULT 'Sin Asignar'"))
                conn.execute(text("ALTER TABLE unidades ADD COLUMN IF NOT EXISTS telefono VARCHAR(30) DEFAULT ''"))
            except Exception:
                pass

            res_u = conn.execute(text("SELECT COUNT(*) FROM unidades")).scalar()
            if res_u == 0:
                for u, a in UNIDADES_DEFECTO:
                    conn.execute(text("INSERT INTO unidades (unidad, alicuota, propietario, telefono) VALUES (:u, :a, 'Propietario', '')"), {"u": u, "a": a})

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    usuario VARCHAR(20) PRIMARY KEY,
                    clave VARCHAR(100) NOT NULL,
                    rol VARCHAR(20) NOT NULL
                );
            """))

            admin_pwd = st.secrets.get("ADMIN_PASSWORD", "admin123")
            if not conn.execute(text("SELECT usuario FROM usuarios WHERE usuario = 'admin'")).fetchone():
                conn.execute(text("INSERT INTO usuarios (usuario, clave, rol) VALUES ('admin', :p, 'admin')"), {"p": admin_pwd})

            for u, _ in UNIDADES_DEFECTO:
                if not conn.execute(text("SELECT usuario FROM usuarios WHERE usuario = :u"), {"u": u}).fetchone():
                    conn.execute(text("INSERT INTO usuarios (usuario, clave, rol) VALUES (:u, '1234', 'propietario')"), {"u": u})

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS gastos (
                    id SERIAL PRIMARY KEY,
                    periodo VARCHAR(7),
                    mes_anio VARCHAR(7) NOT NULL,
                    concepto VARCHAR(200) NOT NULL,
                    monto NUMERIC(12,2) NOT NULL,
                    estatus VARCHAR(20) DEFAULT 'Pendiente',
                    fecha DATE DEFAULT CURRENT_DATE,
                    tipo VARCHAR(50) DEFAULT 'Comun',
                    proveedor VARCHAR(100) DEFAULT 'N/A'
                );
            """))

            try:
                conn.execute(text("ALTER TABLE gastos ADD COLUMN IF NOT EXISTS tipo VARCHAR(50) DEFAULT 'Comun'"))
                conn.execute(text("ALTER TABLE gastos ADD COLUMN IF NOT EXISTS proveedor VARCHAR(100) DEFAULT 'N/A'"))
                conn.execute(text("ALTER TABLE gastos ADD COLUMN IF NOT EXISTS fecha DATE DEFAULT CURRENT_DATE"))
            except Exception:
                pass

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cargos_individuales (
                    id SERIAL PRIMARY KEY,
                    apartamento VARCHAR(10) NOT NULL,
                    mes_anio VARCHAR(7) NOT NULL,
                    concepto VARCHAR(200) NOT NULL,
                    monto NUMERIC(12,2) NOT NULL,
                    fecha DATE DEFAULT CURRENT_DATE
                );
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cuotas_extraordinarias (
                    id SERIAL PRIMARY KEY,
                    concepto VARCHAR(200) NOT NULL,
                    monto_total NUMERIC(12,2) NOT NULL,
                    fecha_emision DATE DEFAULT CURRENT_DATE,
                    estatus VARCHAR(20) DEFAULT 'Pendiente'
                );
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS pagos_reportados (
                    id SERIAL PRIMARY KEY,
                    apartamento VARCHAR(10) NOT NULL,
                    tipo_pago VARCHAR(30) DEFAULT 'Mensualidad',
                    mes_anio VARCHAR(7),
                    id_cuota_extra INT,
                    monto NUMERIC(12, 2) NOT NULL,
                    metodo_pago VARCHAR(50) NOT NULL,
                    referencia VARCHAR(100) NOT NULL,
                    fecha_pago DATE NOT NULL,
                    comprobante_nombre VARCHAR(255),
                    estatus VARCHAR(20) DEFAULT 'Pendiente',
                    fecha_reporte TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            conn.commit()
    except Exception:
        pass

inicializar_tablas()

# -----------------------------------------------------------------------------
# FUNCIONES AUXILIARES Y DE PDF
# -----------------------------------------------------------------------------
def obtener_datos_edificio():
    if not engine:
        return {"nombre": "Residencias Condominio", "rif": "J-00000000-0", "direccion": "Ciudad"}
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT nombre, rif, direccion FROM configuracion_edificio WHERE id = 1")).fetchone()
            if row:
                return {"nombre": row[0], "rif": row[1], "direccion": row[2]}
    except Exception:
        pass
    return {"nombre": "Residencias Condominio", "rif": "J-00000000-0", "direccion": "Ciudad"}

def obtener_unidades_df():
    if not engine:
        return pd.DataFrame(UNIDADES_DEFECTO, columns=["unidad", "alicuota"])
    try:
        with engine.connect() as conn:
            return pd.read_sql(text("SELECT unidad, alicuota, propietario, telefono FROM unidades ORDER BY unidad ASC"), conn)
    except Exception:
        return pd.DataFrame(UNIDADES_DEFECTO, columns=["unidad", "alicuota"])

def generar_pdf_recibo(apt, periodo, total_cuota, detalles_gastos, alicuota):
    datos_ed = obtener_datos_edificio()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    story = []
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=16,
        leading=20,
        alignment=1,
        textColor=colors.HexColor("#1E3A8A")
    )
    
    story.append(Paragraph(f"<b>{datos_ed['nombre']}</b>", title_style))
    story.append(Paragraph(f"RIF: {datos_ed['rif']} | {datos_ed['direccion']}", styles['Normal']))
    story.append(Spacer(1, 15))
    
    story.append(Paragraph(f"<b>AVISO DE COBRO - PERIODO: {periodo}</b>", styles['Heading2']))
    story.append(Paragraph(f"<b>Unidad:</b> {apt} | <b>Alícuota Aplicada:</b> {alicuota}%", styles['Normal']))
    story.append(Spacer(1, 15))

    tabla_datos = [["Concepto / Descripción", "Monto Base ($)", "Cuota Parte ($)"]]
    for item in detalles_gastos:
        tabla_datos.append([item['concepto'], f"${item['base']:,.2f}", f"${item['monto']:,.2f}"])
    
    tabla_datos.append(["TOTAL A PAGAR", "", f"${total_cuota:,.2f}"])

    t = Table(tabla_datos, colWidths=[280, 110, 110])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#E2E8F0")),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
    ]))
    
    story.append(t)
    story.append(Spacer(1, 20))
    story.append(Paragraph("Por favor realice su pago y repórtelo en la plataforma.", styles['Italic']))

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
        usuario_input = st.text_input("Usuario (ej. 1A, PH o admin)").strip()
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
# 2. VISTA DE PROPIETARIOS
# -----------------------------------------------------------------------------
elif st.session_state.rol_logueado == "propietario":
    user_actual = st.session_state.usuario_logueado
    datos_ed = obtener_datos_edificio()
    df_u = obtener_unidades_df()
    row_u = df_u[df_u['unidad'] == user_actual]
    prop_nombre = row_u['propietario'].values[0] if not row_u.empty else "Propietario"
    pct_user = float(row_u['alicuota'].values[0]) if not row_u.empty else 6.0

    col_head, col_out = st.columns([3, 1])
    with col_head:
        st.title(f"🏢 {datos_ed['nombre']} - Unidad {user_actual}")
        st.caption(f"Propietario: {prop_nombre} | Alícuota: {pct_user}%")
    with col_out:
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            cerrar_sesion()

    st.write("---")

    t_p1, t_p2, t_p3 = st.tabs(["📄 Estado de Cuenta", "💳 Reportar Pago", "📋 Mis Pagos Reportados"])

    with t_p1:
        st.subheader("📊 Mis Deudas y Recibos")
        mes_actual = datetime.now().strftime("%Y-%m")
        
        try:
            with engine.connect() as conn:
                gastos_aprob = conn.execute(
                    text("SELECT SUM(monto) FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    {"m": mes_actual}
                ).scalar() or 0
                
                cargos_ind = conn.execute(
                    text("SELECT SUM(monto) FROM cargos_individuales WHERE apartamento = :u AND mes_anio = :m"),
                    {"u": user_actual, "m": mes_actual}
                ).scalar() or 0

            cuota_comun = float(gastos_aprob) * (pct_user / 100.0)
            total_mes = cuota_comun + float(cargos_ind)

            c1, c2, c3 = st.columns(3)
            c1.metric("Cuota Común Estimada", f"${cuota_comun:,.2f}")
            c2.metric("Cargos No Comunes", f"${float(cargos_ind):,.2f}")
            c3.metric(f"Total Periodo ({mes_actual})", f"${total_mes:,.2f}")

            st.write("---")
            st.subheader("📥 Descargar Recibo del Mes")
            
            detalles = [
                {"concepto": "Gastos Comunes del Edificio", "base": float(gastos_aprob), "monto": cuota_comun},
                {"concepto": "Cargos Indiv. No Comunes", "base": float(cargos_ind), "monto": float(cargos_ind)}
            ]
            pdf_bytes = generar_pdf_recibo(user_actual, mes_actual, total_mes, detalles, pct_user)

            st.download_button(
                f"📄 Descargar Recibo PDF ({mes_actual})",
                data=pdf_bytes,
                file_name=f"recibo_{user_actual}_{mes_actual}.pdf",
                mime="application/pdf"
            )

        except Exception as e:
            st.error(f"Error consultando estado de cuenta: {e}")

    with t_p2:
        st.subheader("📝 Formulario de Reporte de Pago")
        with st.form("form_reportar_pago"):
            tipo_p = st.selectbox("Tipo de Pago", ["Mensualidad", "Cuota Extraordinaria"])
            mes_p = st.text_input("Periodo / Mes-Año", value=datetime.now().strftime("%Y-%m"))
            monto_p = st.number_input("Monto Pagado ($)", min_value=0.01, step=0.01)
            metodo = st.selectbox("Método de Pago", ["Pago Móvil", "Transferencia", "Efectivo USD", "Zelle"])
            ref = st.text_input("Número de Referencia")
            fecha_p = st.date_input("Fecha de Realización del Pago", datetime.now())

            btn_pago = st.form_submit_button("Enviar Reporte de Pago", type="primary")

            if btn_pago:
                if not ref:
                    st.error("Debes ingresar el número de referencia.")
                else:
                    try:
                        with engine.connect() as conn:
                            conn.execute(
                                text("""
                                    INSERT INTO pagos_reportados (apartamento, tipo_pago, mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus)
                                    VALUES (:u, :tp, :m, :mo, :met, :ref, :f, 'Pendiente')
                                """),
                                {"u": user_actual, "tp": tipo_p, "m": mes_p, "mo": monto_p, "met": metodo, "ref": ref, "f": fecha_p}
                            )
                            conn.commit()
                        st.success("✅ Pago reportado con éxito. Queda en espera de verificación por administración.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al registrar pago: {e}")

    with t_p3:
        st.subheader("📋 Historial de Mis Reportes")
        try:
            with engine.connect() as conn:
                df_mis_pagos = pd.read_sql(
                    text("SELECT fecha_pago, tipo_pago, mes_anio, monto, metodo_pago, referencia, estatus FROM pagos_reportados WHERE apartamento = :u ORDER BY id DESC"),
                    conn, params={"u": user_actual}
                )

            if df_mis_pagos.empty:
                st.info("No has registrado ningún pago hasta el momento.")
            else:
                st.dataframe(df_mis_pagos, use_container_width=True)
        except Exception as e:
            st.error(f"Error cargando el historial: {e}")

# -----------------------------------------------------------------------------
# 3. VISTA DE ADMINISTRACIÓN
# -----------------------------------------------------------------------------
elif st.session_state.rol_logueado == "admin":
    datos_ed = obtener_datos_edificio()

    col_head, col_out = st.columns([3, 1])
    with col_head:
        st.title("⚙️ Módulo de Administración")
        st.caption(f"{datos_ed['nombre']} | RIF: {datos_ed['rif']}")
    with col_out:
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            cerrar_sesion()

    st.write("---")

    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "📊 Gastos Comunes", 
        "🛠️ Gastos No Comunes", 
        "⭐ Cuotas Extras", 
        "✅ Validar Pagos", 
        "🏢 Alícuotas y Unidades", 
        "🚨 Morosidad y Recibos", 
        "⚙️ Datos Edificio"
    ])

    # TABS 1: GASTOS COMUNES
    with t1:
        st.subheader("➕ Cargar Nuevo Gasto Común")
        with st.form("form_gasto"):
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                mes = st.text_input("Mes / Año (AAAA-MM)", value=datetime.now().strftime("%Y-%m"))
                concepto = st.text_input("Descripción del Gasto Común")
            with col_g2:
                proveedor = st.text_input("Proveedor", value="N/A")
                monto = st.number_input("Monto Total ($)", min_value=0.01, step=0.01)

            btn = st.form_submit_button("Cargar para Previsualizar/Aprobar", type="primary")

            if btn and concepto:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                                INSERT INTO gastos (periodo, mes_anio, concepto, monto, estatus, fecha, tipo, proveedor) 
                                VALUES (:m, :m, :c, :mo, 'Pendiente', CURRENT_DATE, 'Comun', :p)
                            """),
                            {"m": mes, "c": concepto, "mo": monto, "p": proveedor if proveedor.strip() else "N/A"}
                        )
                        conn.commit()
                    st.success("Gasto guardado en estado pendiente de aprobación.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error registrando gasto: {e}")

        st.write("---")
        st.subheader("🔍 Previsualizar y Aprobar Gastos Comunes")
        
        mes_filtro = st.text_input("Filtrar gastos por periodo (AAAA-MM):", value=datetime.now().strftime("%Y-%m"), key="filtro_gastos_admin")
        
        try:
            with engine.connect() as conn:
                df_gastos_pendientes = pd.read_sql(
                    text("SELECT id, concepto, monto, estatus, mes_anio FROM gastos WHERE mes_anio = :m ORDER BY id DESC"),
                    conn, params={"m": mes_filtro}
                )

            if df_gastos_pendientes.empty:
                st.info(f"No hay gastos registrados para el periodo {mes_filtro}.")
            else:
                for _, r_gasto in df_gastos_pendientes.iterrows():
                    c_detalles, c_acciones = st.columns([3, 2])
                    with c_detalles:
                        badge_estatus = "🟡 Pendiente" if r_gasto['estatus'] == 'Pendiente' else "🟢 Aprobado"
                        st.markdown(f"**Concepto:** {r_gasto['concepto']} | **Monto:** ${float(r_gasto['monto']):,.2f} | **Estatus:** {badge_estatus}")
                    
                    with c_acciones:
                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            if r_gasto['estatus'] == 'Pendiente':
                                if st.button("✅ Aprobar", key=f"app_gasto_{r_gasto['id']}", type="primary"):
                                    with engine.connect() as conn:
                                        conn.execute(
                                            text("UPDATE gastos SET estatus = 'Aprobado' WHERE id = :id"),
                                            {"id": r_gasto['id']}
                                        )
                                        conn.commit()
                                    st.success("Gasto aprobado.")
                                    st.rerun()
                        with btn_col2:
                            if st.button("❌ Eliminar", key=f"del_gasto_{r_gasto['id']}", type="secondary"):
                                with engine.connect() as conn:
                                    conn.execute(
                                        text("DELETE FROM gastos WHERE id = :id"),
                                        {"id": r_gasto['id']}
                                    )
                                    conn.commit()
                                st.success("Gasto eliminado.")
                                st.rerun()
                    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)

        except Exception as e:
            st.error(f"Error consultando gastos: {e}")

    # TABS 2: GASTOS NO COMUNES (CARGOS INDIVIDUALES)
    with t2:
        st.subheader("🛠️ Cargar Gasto No Común (Cargo Individual)")
        df_unidades_list = obtener_unidades_df()
        
        with st.form("form_cargo_ind"):
            c_nc1, c_nc2 = st.columns(2)
            with c_nc1:
                apt_destino = st.selectbox("Apartamento / Unidad Destino", df_unidades_list['unidad'].tolist())
                mes_nc = st.text_input("Periodo (AAAA-MM)", value=datetime.now().strftime("%Y-%m"), key="nc_mes")
            with c_nc2:
                concepto_nc = st.text_input("Concepto (ej. Llave de portón, Reparación tubería)")
                monto_nc = st.number_input("Monto ($)", min_value=0.01, step=0.01, key="nc_monto")

            btn_nc = st.form_submit_button("Asignar Cargo Individual", type="primary")

            if btn_nc and concepto_nc:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                                INSERT INTO cargos_individuales (apartamento, mes_anio, concepto, monto, fecha)
                                VALUES (:a, :m, :c, :mo, CURRENT_DATE)
                            """),
                            {"a": apt_destino, "m": mes_nc, "c": concepto_nc, "mo": monto_nc}
                        )
                        conn.commit()
                    st.success(f"Cargo no común cargado exitosamente a la unidad {apt_destino}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error registrando cargo individual: {e}")

        st.write("---")
        st.subheader("📋 Cargos No Comunes Registrados")
        try:
            with engine.connect() as conn:
                df_cargos_nc = pd.read_sql(text("SELECT id, apartamento, mes_anio, concepto, monto, fecha FROM cargos_individuales ORDER BY id DESC"), conn)
            if df_cargos_nc.empty:
                st.info("No hay cargos individuales registrados.")
            else:
                st.dataframe(df_cargos_nc, use_container_width=True)
        except Exception as e:
            st.error(f"Error listando cargos: {e}")

    # TABS 3: CUOTAS EXTRAORDINARIAS
    with t3:
        st.subheader("⭐ Cargar Cuota Extraordinaria")
        with st.form("form_cuota_extra"):
            col_ce1, col_ce2 = st.columns(2)
            with col_ce1:
                concepto_ce = st.text_input("Proyecto / Concepto (ej. Pintura Fachada)")
            with col_ce2:
                monto_ce = st.number_input("Monto Total del Proyecto ($)", min_value=0.01, step=0.01)

            btn_ce = st.form_submit_button("Registrar Cuota Extraordinaria", type="primary")

            if btn_ce and concepto_ce:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                                INSERT INTO cuotas_extraordinarias (concepto, monto_total, fecha_emision, estatus)
                                VALUES (:c, :m, CURRENT_DATE, 'Aprobado')
                            """),
                            {"c": concepto_ce, "m": monto_ce}
                        )
                        conn.commit()
                    st.success("Cuota extraordinaria registrada correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar cuota extra: {e}")

        st.write("---")
        st.subheader("⭐ Proyectos y Cuotas Extraordinarias Activas")
        try:
            with engine.connect() as conn:
                df_ce = pd.read_sql(text("SELECT id, concepto, monto_total, fecha_emision, estatus FROM cuotas_extraordinarias ORDER BY id DESC"), conn)
            if df_ce.empty:
                st.info("No hay cuotas extraordinarias registradas.")
            else:
                st.dataframe(df_ce, use_container_width=True)
        except Exception as e:
            st.error(f"Error consultando cuotas extras: {e}")

    # TABS 4: VALIDAR PAGOS
    with t4:
        st.subheader("✅ Verificación y Aprobación de Pagos")
        try:
            with engine.connect() as conn:
                df_pagos_pend = pd.read_sql(
                    text("SELECT id, apartamento, tipo_pago, mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus FROM pagos_reportados WHERE estatus = 'Pendiente' ORDER BY id ASC"),
                    conn
                )

            if df_pagos_pend.empty:
                st.success("🎉 No hay pagos pendientes por verificar.")
            else:
                for _, row_p in df_pagos_pend.iterrows():
                    c_p1, c_p2 = st.columns([3, 2])
                    with c_p1:
                        st.markdown(f"**Apto:** {row_p['apartamento']} | **Tipo:** {row_p['tipo_pago']} | **Monto:** ${float(row_p['monto']):,.2f}")
                        st.caption(f"Método: {row_p['metodo_pago']} | Ref: {row_p['referencia']} | Fecha: {row_p['fecha_pago']}")
                    with c_p2:
                        b_val1, b_val2 = st.columns(2)
                        with b_val1:
                            if st.button("✅ Aprobar", key=f"val_p_{row_p['id']}", type="primary"):
                                with engine.connect() as conn:
                                    conn.execute(text("UPDATE pagos_reportados SET estatus = 'Aprobado' WHERE id = :id"), {"id": row_p['id']})
                                    conn.commit()
                                st.success("Pago Aprobado.")
                                st.rerun()
                        with b_val2:
                            if st.button("❌ Rechazar", key=f"rec_p_{row_p['id']}", type="secondary"):
                                with engine.connect() as conn:
                                    conn.execute(text("UPDATE pagos_reportados SET estatus = 'Rechazado' WHERE id = :id"), {"id": row_p['id']})
                                    conn.commit()
                                st.warning("Pago Rechazado.")
                                st.rerun()
                    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error validando pagos: {e}")

    # TABS 5: ALÍCUOTAS Y UNIDADES
    with t5:
        st.subheader("🏢 Gestión de Unidades y Alícuotas")
        df_unid = obtener_unidades_df()
        
        st.dataframe(df_unid, use_container_width=True)

        st.write("---")
        st.subheader("✏️ Modificar Datos de Unidad")
        with st.form("form_edit_unidad"):
            c_u1, c_u2 = st.columns(2)
            with c_u1:
                u_sel = st.selectbox("Seleccionar Unidad", df_unid['unidad'].tolist())
                prop_in = st.text_input("Nombre del Propietario")
            with c_u2:
                tel_in = st.text_input("Teléfono de Contacto")
                alic_in = st.number_input("Alícuota (%)", min_value=0.01, max_value=100.0, step=0.01, value=6.0)

            btn_u_save = st.form_submit_button("Actualizar Unidad", type="primary")

            if btn_u_save:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("UPDATE unidades SET propietario = :p, telefono = :t, alicuota = :a WHERE unidad = :u"),
                            {"p": prop_in, "t": tel_in, "a": alic_in, "u": u_sel}
                        )
                        conn.commit()
                    st.success(f"Datos de la unidad {u_sel} actualizados correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error editando unidad: {e}")

    # TABS 6: MOROSIDAD Y RECIBOS
    with t6:
        st.subheader("🚨 Control de Deudas por Unidad")
        mes_mor = st.text_input("Periodo a Consultar (AAAA-MM)", value=datetime.now().strftime("%Y-%m"), key="mes_morosidad")

        try:
            with engine.connect() as conn:
                gastos_totales = conn.execute(
                    text("SELECT SUM(monto) FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    {"m": mes_mor}
                ).scalar() or 0

                df_u_mor = pd.read_sql(text("SELECT unidad, alicuota, propietario FROM unidades ORDER BY unidad ASC"), conn)

            res_morosidad = []
            for _, r in df_u_mor.iterrows():
                cuota_c = float(gastos_totales) * (float(r['alicuota']) / 100.0)
                
                try:
                    with engine.connect() as conn:
                        c_ind = conn.execute(
                            text("SELECT SUM(monto) FROM cargos_individuales WHERE apartamento = :u AND mes_anio = :m"),
                            {"u": r['unidad'], "m": mes_mor}
                        ).scalar() or 0

                        p_pagado = conn.execute(
                            text("SELECT SUM(monto) FROM pagos_reportados WHERE apartamento = :u AND mes_anio = :m AND estatus = 'Aprobado'"),
                            {"u": r['unidad'], "m": mes_mor}
                        ).scalar() or 0
                except Exception:
                    c_ind = 0
                    p_pagado = 0

                total_deuda = cuota_c + float(c_ind) - float(p_pagado)
                est_deuda = "🔴 Pendiente / Moroso" if total_deuda > 0 else "🟢 Al Día"

                res_morosidad.append({
                    "Unidad": r['unidad'],
                    "Propietario": r['propietario'],
                    "Alícuota (%)": r['alicuota'],
                    "Monto Mes ($)": cuota_c + float(c_ind),
                    "Abonado ($)": float(p_pagado),
                    "Saldo Pendiente ($)": total_deuda,
                    "Estatus": est_deuda
                })

            st.dataframe(pd.DataFrame(res_morosidad), use_container_width=True)

        except Exception as e:
            st.error(f"Error generando reporte de morosidad: {e}")

    # TABS 7: DATOS EDIFICIO
    with t7:
        st.subheader("⚙️ Configuración del Edificio")
        d_ed = obtener_datos_edificio()

        with st.form("form_edificio_config"):
            ed_nombre = st.text_input("Nombre del Condominio / Edificio", value=d_ed['nombre'])
            ed_rif = st.text_input("RIF / Documento de Identificación", value=d_ed['rif'])
            ed_dir = st.text_area("Dirección Física", value=d_ed['direccion'])

            btn_ed = st.form_submit_button("Guardar Cambios del Edificio", type="primary")

            if btn_ed:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("UPDATE configuracion_edificio SET nombre = :n, rif = :r, direccion = :d WHERE id = 1"),
                            {"n": ed_nombre, "r": ed_rif, "d": ed_dir}
                        )
                        conn.commit()
                    st.success("Configuración actualizada correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error guardando datos: {e}")
