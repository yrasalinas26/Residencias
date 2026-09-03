import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
import io
import urllib.parse
import math
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -----------------------------------------------------------------------------
# REGLA DE REDONDEO PERSONALIZADA (SOLO PARA TOTALES FINALES)
# (> 0.5 sube al siguiente entero; <= 0.5 mantiene el entero actual)
# -----------------------------------------------------------------------------
def redondear_custom(val):
    if val is None:
        return 0
    val = float(val)
    entero = math.floor(val)
    decimal = val - entero
    if decimal > 0.5:
        return entero + 1
    else:
        return entero

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
# FUNCIONES AUXILIARES DE FECHA
# -----------------------------------------------------------------------------
def obtener_mes_anterior():
    hoy = datetime.now()
    if hoy.month == 1:
        return f"{hoy.year - 1}-12"
    else:
        return f"{hoy.year}-{hoy.month - 1:02d}"

def obtener_mes_actual():
    return datetime.now().strftime("%Y-%m")

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
# FUNCIONES AUXILIARES, DE PDF Y WHATSAPP
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

def generar_enlace_whatsapp(telefono, mensaje):
    num_limpio = "".join(filter(str.isdigit, str(telefono or "")))
    msg_enc = urllib.parse.quote(mensaje)
    if num_limpio:
        return f"https://wa.me/{num_limpio}?text={msg_enc}"
    return f"https://wa.me/?text={msg_enc}"

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
        m_base = float(item['base'])
        m_cuota = float(item['monto'])
        tabla_datos.append([item['concepto'], f"${m_base:,.2f}", f"${m_cuota:,.2f}"])
    
    tot_red = redondear_custom(total_cuota)
    tabla_datos.append(["TOTAL A PAGAR (REDONDEADO)", "", f"${tot_red:,.0f}"])

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
    prop_tel = row_u['telefono'].values[0] if not row_u.empty else ""
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
        
        mes_vencido_defecto = obtener_mes_anterior()
        mes_actual = st.text_input("Periodo a Consultar (AAAA-MM):", value=mes_vencido_defecto, key="prop_consulta_mes")
        
        try:
            with engine.connect() as conn:
                gastos_aprob = conn.execute(
                    text("SELECT SUM(monto) FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    {"m": mes_actual}
                ).scalar() or 0.0
                
                cargos_ind = conn.execute(
                    text("SELECT SUM(monto) FROM cargos_individuales WHERE apartamento = :u AND mes_anio = :m"),
                    {"u": user_actual, "m": mes_actual}
                ).scalar() or 0.0

            cuota_comun_raw = float(gastos_aprob) * (pct_user / 100.0)
            cargos_ind_raw = float(cargos_ind)
            
            total_mes_raw = cuota_comun_raw + cargos_ind_raw
            total_mes_red = redondear_custom(total_mes_raw)

            c1, c2, c3 = st.columns(3)
            c1.metric("Cuota Común Estimada", f"${cuota_comun_raw:,.2f}")
            c2.metric("Cargos No Comunes / Extra", f"${cargos_ind_raw:,.2f}")
            c3.metric(f"Total a Pagar Periodo ({mes_actual})", f"${total_mes_red:,.0f}")

            st.write("---")
            st.subheader("📥 Descargar Recibo / Compartir por WhatsApp")
            
            detalles = [
                {"concepto": "Gastos Comunes del Edificio", "base": float(gastos_aprob), "monto": cuota_comun_raw},
                {"concepto": "Cargos Indiv. No Comunes / Cuotas Extras", "base": cargos_ind_raw, "monto": cargos_ind_raw}
            ]
            pdf_bytes = generar_pdf_recibo(user_actual, mes_actual, total_mes_raw, detalles, pct_user)

            msg_ws = f"🏢 *{datos_ed['nombre']}*\n📄 *AVISO DE COBRO ({mes_actual})*\nUnidad: {user_actual}\nTotal a Pagar: ${total_mes_red:,.0f}\n\nPor favor reportar el pago a través de la app."
            link_ws = generar_enlace_whatsapp(prop_tel, msg_ws)

            col_pdf, col_ws = st.columns(2)
            with col_pdf:
                st.download_button(
                    f"📄 Descargar Recibo PDF ({mes_actual})",
                    data=pdf_bytes,
                    file_name=f"recibo_{user_actual}_{mes_actual}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            with col_ws:
                st.link_button("📲 Compartir por WhatsApp", link_ws, use_container_width=True)

        except Exception as e:
            st.error(f"Error consultando estado de cuenta: {e}")

    with t_p2:
        st.subheader("📝 Formulario de Reporte de Pago")
        with st.form("form_reportar_pago"):
            tipo_p = st.selectbox("Tipo de Pago", ["Mensualidad", "Cuota Extraordinaria"])
            mes_p = st.text_input("Periodo / Mes-Año a Pagar (AAAA-MM)", value=obtener_mes_anterior())
            monto_p = st.number_input("Monto Pagado ($)", min_value=1.0, step=0.01)
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
                                {"u": user_actual, "tp": tipo_p, "m": mes_p, "mo": float(monto_p), "met": metodo, "ref": ref, "f": fecha_p}
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
                df_mis_pagos['monto'] = df_mis_pagos['monto'].apply(lambda x: f"${float(x):,.2f}")
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
        "📲 Notificar Recibos", 
        "⚙️ Datos Edificio"
    ])

    # TAB 1: GASTOS COMUNES
    with t1:
        st.subheader("➕ Cargar Nuevo Gasto Común")
        
        with st.form("form_gasto"):
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                mes = st.text_input("Mes / Año del Gasto (AAAA-MM)", value=obtener_mes_anterior())
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
                            {"m": mes, "c": concepto, "mo": float(monto), "p": proveedor if proveedor.strip() else "N/A"}
                        )
                        conn.commit()
                    st.success("Gasto guardado en estado pendiente de aprobación.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error registrando gasto: {e}")

        st.write("---")
        st.subheader("🔍 Previsualizar y Aprobar Gastos Comunes")
        
        mes_filtro = st.text_input("Filtrar gastos por periodo (AAAA-MM):", value=obtener_mes_anterior(), key="filtro_gastos_admin")
        
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
                        m_gasto_val = float(r_gasto['monto'])
                        st.markdown(f"**Concepto:** {r_gasto['concepto']} | **Monto:** ${m_gasto_val:,.2f} | **Estatus:** {badge_estatus}")
                    
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

    # TAB 2: GASTOS NO COMUNES
    with t2:
        st.subheader("🛠️ Cargar Gasto No Común (Cargo Individual)")
        df_unidades_list = obtener_unidades_df()
        
        with st.form("form_cargo_ind"):
            c_nc1, c_nc2 = st.columns(2)
            with c_nc1:
                apt_destino = st.selectbox("Apartamento / Unidad Destino", df_unidades_list['unidad'].tolist())
                mes_nc = st.text_input("Periodo de Facturación (AAAA-MM)", value=obtener_mes_anterior(), key="nc_mes")
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
                            {"a": apt_destino, "m": mes_nc, "c": concepto_nc, "mo": float(monto_nc)}
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
                df_cargos_nc['monto'] = df_cargos_nc['monto'].apply(lambda x: f"${float(x):,.2f}")
                st.dataframe(df_cargos_nc, use_container_width=True)
        except Exception as e:
            st.error(f"Error listando cargos: {e}")

    # TAB 3: CUOTAS EXTRAORDINARIAS
    with t3:
        st.subheader("⭐ Cargar Nueva Cuota Extraordinaria")
        with st.form("form_cuota_extra"):
            col_ce1, col_ce2 = st.columns(2)
            with col_ce1:
                concepto_ce = st.text_input("Proyecto / Concepto (ej. Pintura Fachada, Reparación Ascensor)")
            with col_ce2:
                monto_ce = st.number_input("Monto Total del Proyecto ($)", min_value=0.01, step=0.01)

            btn_ce = st.form_submit_button("Crear Cuota Extraordinaria (Pendiente)", type="primary")

            if btn_ce and concepto_ce:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                                INSERT INTO cuotas_extraordinarias (concepto, monto_total, fecha_emision, estatus)
                                VALUES (:c, :m, CURRENT_DATE, 'Pendiente')
                            """),
                            {"c": concepto_ce, "m": float(monto_ce)}
                        )
                        conn.commit()
                    st.success("Cuota extraordinaria creada en estado Pendiente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar cuota extra: {e}")

        st.write("---")
        st.subheader("🔍 Previsualizar, Aprobar, Distribuir y Notificar")
        try:
            with engine.connect() as conn:
                df_ce = pd.read_sql(
                    text("SELECT id, concepto, monto_total, fecha_emision, estatus FROM cuotas_extraordinarias ORDER BY id DESC"),
                    conn
                )

            if df_ce.empty:
                st.info("No hay cuotas extraordinarias registradas.")
            else:
                mes_dist = st.text_input("Periodo en el que se cobrará al aprobar (AAAA-MM):", value=obtener_mes_anterior(), key="ce_mes_dist")

                for _, r_ce in df_ce.iterrows():
                    c_det, c_act = st.columns([3, 2])
                    with c_det:
                        badge_st = "🟡 Pendiente" if r_ce['estatus'] == 'Pendiente' else "🟢 Aprobada y Distribuida"
                        m_ce_tot = float(r_ce['monto_total'])
                        st.markdown(f"**PROYECTO #{r_ce['id']}:** {r_ce['concepto']} | **Monto Total:** ${m_ce_tot:,.2f}")
                        st.caption(f"Fecha Emisión: {r_ce['fecha_emision']} | **Estatus:** {badge_st}")

                    with c_act:
                        b_col1, b_col2 = st.columns(2)
                        with b_col1:
                            if r_ce['estatus'] == 'Pendiente':
                                if st.button("✅ Aprobar y Distribuir", key=f"app_ce_{r_ce['id']}", type="primary"):
                                    try:
                                        with engine.connect() as conn:
                                            unidades_res = conn.execute(text("SELECT unidad, alicuota FROM unidades")).fetchall()
                                            monto_tot = float(r_ce['monto_total'])
                                            for u_row in unidades_res:
                                                u_cod = u_row[0]
                                                u_alic = float(u_row[1])
                                                monto_apto_raw = monto_tot * (u_alic / 100.0)

                                                conn.execute(
                                                    text("""
                                                        INSERT INTO cargos_individuales (apartamento, mes_anio, concepto, monto, fecha)
                                                        VALUES (:a, :m, :c, :mo, CURRENT_DATE)
                                                    """),
                                                    {"a": u_cod, "m": mes_dist, "c": f"Cuota Extra: {r_ce['concepto']}", "mo": monto_apto_raw}
                                                )

                                            conn.execute(
                                                text("UPDATE cuotas_extraordinarias SET estatus = 'Aprobada' WHERE id = :id"),
                                                {"id": r_ce['id']}
                                            )
                                            conn.commit()
                                        st.success("Cuota aprobada y cargada a todas las unidades.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error al procesar: {e}")
                        with b_col2:
                            if st.button("❌ Eliminar", key=f"del_ce_{r_ce['id']}", type="secondary"):
                                try:
                                    with engine.connect() as conn:
                                        conn.execute(
                                            text("DELETE FROM cuotas_extraordinarias WHERE id = :id"),
                                            {"id": r_ce['id']}
                                        )
                                        conn.commit()
                                    st.success("Cuota extraordinaria eliminada.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al eliminar: {e}")
                    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error consultando cuotas extras: {e}")

    # TAB 4: VALIDAR PAGOS
    with t4:
        st.subheader("✅ Verificación de Pagos Reportados por Propietarios")
        try:
            with engine.connect() as conn:
                df_pagos_rep = pd.read_sql(
                    text("SELECT id, apartamento, tipo_pago, mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus FROM pagos_reportados ORDER BY id DESC"),
                    conn
                )

            if df_pagos_rep.empty:
                st.info("No hay pagos reportados en la plataforma.")
            else:
                for _, r_pago in df_pagos_rep.iterrows():
                    col_p1, col_p2 = st.columns([3, 2])
                    with col_p1:
                        st.markdown(f"**Unidad {r_pago['apartamento']}** | {r_pago['tipo_pago']} ({r_pago['mes_anio']})")
                        st.write(f"Monto: **${float(r_pago['monto']):,.2f}** | Método: {r_pago['metodo_pago']} | Ref: `{r_pago['referencia']}`")
                        st.caption(f"Fecha Pago: {r_pago['fecha_pago']} | Estatus: **{r_pago['estatus']}**")
                    with col_p2:
                        btn_val1, btn_val2 = st.columns(2)
                        with btn_val1:
                            if r_pago['estatus'] == 'Pendiente':
                                if st.button("Aprobar", key=f"app_pago_{r_pago['id']}", type="primary"):
                                    with engine.connect() as conn:
                                        conn.execute(
                                            text("UPDATE pagos_reportados SET estatus = 'Aprobado' WHERE id = :id"),
                                            {"id": r_pago['id']}
                                        )
                                        conn.commit()
                                    st.success("Pago aprobado.")
                                    st.rerun()
                        with btn_val2:
                            if r_pago['estatus'] == 'Pendiente':
                                if st.button("Rechazar", key=f"rech_pago_{r_pago['id']}", type="secondary"):
                                    with engine.connect() as conn:
                                        conn.execute(
                                            text("UPDATE pagos_reportados SET estatus = 'Rechazado' WHERE id = :id"),
                                            {"id": r_pago['id']}
                                        )
                                        conn.commit()
                                    st.warning("Pago rechazado.")
                                    st.rerun()
                    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error gestionando pagos: {e}")

    # TAB 5: ALÍCUOTAS Y UNIDADES
    with t5:
        st.subheader("🏢 Gestión de Unidades y Alícuotas")
        df_unidades = obtener_unidades_df()

        edited_df = st.data_editor(
            df_unidades,
            column_config={
                "unidad": st.column_config.TextColumn("Unidad", disabled=True),
                "alicuota": st.column_config.NumberColumn("Alícuota (%)", format="%.2f%%"),
                "propietario": st.column_config.TextColumn("Propietario"),
                "telefono": st.column_config.TextColumn("Teléfono")
            },
            hide_index=True,
            use_container_width=True
        )

        if st.button("💾 Guardar Cambios de Unidades", type="primary"):
            try:
                with engine.connect() as conn:
                    for _, row in edited_df.iterrows():
                        conn.execute(
                            text("""
                                UPDATE unidades 
                                SET alicuota = :a, propietario = :p, telefono = :t 
                                WHERE unidad = :u
                            """),
                            {"a": float(row['alicuota']), "p": row['propietario'], "t": row['telefono'], "u": row['unidad']}
                        )
                    conn.commit()
                st.success("Configuración de unidades actualizada correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar cambios: {e}")

    # TAB 6: NOTIFICAR RECIBOS
    with t6:
        st.subheader("📲 Envío Masivo / Notificación de Recibos por WhatsApp")
        mes_notif = st.text_input("Periodo a Notificar (AAAA-MM):", value=obtener_mes_anterior(), key="notif_mes")
        
        df_u_notif = obtener_unidades_df()
        
        if st.button("🔄 Generar Enlaces de Envío"):
            st.success(f"Enlaces generados para el periodo {mes_notif}")

        for _, u_row in df_u_notif.iterrows():
            apt = u_row['unidad']
            tel = u_row['telefono']
            prop = u_row['propietario']
            alic = float(u_row['alicuota'])

            try:
                with engine.connect() as conn:
                    gastos_tot = conn.execute(
                        text("SELECT SUM(monto) FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                        {"m": mes_notif}
                    ).scalar() or 0.0
                    
                    cargos_ind_tot = conn.execute(
                        text("SELECT SUM(monto) FROM cargos_individuales WHERE apartamento = :u AND mes_anio = :m"),
                        {"u": apt, "m": mes_notif}
                    ).scalar() or 0.0

                c_comun = float(gastos_tot) * (alic / 100.0)
                tot_raw = c_comun + float(cargos_ind_tot)
                tot_red = redondear_custom(tot_raw)

                msg = f"Estimado(a) {prop} ({apt}), se ha generado su aviso de cobro del periodo {mes_notif}.\nTotal a pagar: ${tot_red:,.0f}."
                link = generar_enlace_whatsapp(tel, msg)

                col_n1, col_n2 = st.columns([3, 1])
                with col_n1:
                    st.write(f"**Unidad {apt}** - {prop} | Total: **${tot_red:,.0f}**")
                with col_n2:
                    st.link_button("📲 Enviar WhatsApp", link, use_container_width=True)
            except Exception as e:
                st.error(f"Error con la unidad {apt}: {e}")

    # TAB 7: DATOS EDIFICIO
    with t7:
        st.subheader("⚙️ Configuración del Edificio")
        datos_actuales = obtener_datos_edificio()

        with st.form("form_edificio"):
            nombre_ed = st.text_input("Nombre del Edificio / Condominio", value=datos_actuales['nombre'])
            rif_ed = st.text_input("RIF", value=datos_actuales['rif'])
            dir_ed = st.text_area("Dirección", value=datos_actuales['direccion'])

            btn_ed = st.form_submit_button("Guardar Configuración", type="primary")

            if btn_ed:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                                UPDATE configuracion_edificio 
                                SET nombre = :n, rif = :r, direccion = :d 
                                WHERE id = 1
                            """),
                            {"n": nombre_ed, "r": rif_ed, "d": dir_ed}
                        )
                        conn.commit()
                    st.success("Datos del edificio actualizados con éxito.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error actualizando datos: {e}")
