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
# REGLA DE REDONDEO PERSONALIZADA (> 0.5 sube al entero; <= 0.5 se mantiene)
# -----------------------------------------------------------------------------
def redondear_custom(val):
    if val is None:
        return 0
    val = float(val)
    entero = math.floor(val)
    decimal = val - entero
    return entero + 1 if decimal > 0.5 else entero

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
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

def obtener_mes_anterior():
    hoy = datetime.now()
    return f"{hoy.year - 1}-12" if hoy.month == 1 else f"{hoy.year}-{hoy.month - 1:02d}"

# -----------------------------------------------------------------------------
# BASE DE DATOS
# -----------------------------------------------------------------------------
@st.cache_resource
def obtener_engine():
    try:
        if "DATABASE_URL" in st.secrets:
            return create_engine(st.secrets["DATABASE_URL"], connect_args={"prepare_threshold": None}, pool_pre_ping=True), None
        return None, "No se encontró DATABASE_URL en Secrets."
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

            if conn.execute(text("SELECT COUNT(*) FROM configuracion_edificio")).scalar() == 0:
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

            if conn.execute(text("SELECT COUNT(*) FROM unidades")).scalar() == 0:
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
# FUNCIONES DE CONSULTA
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
    num = "".join(filter(str.isdigit, str(telefono or "")))
    msg = urllib.parse.quote(mensaje)
    return f"https://wa.me/{num}?text={msg}" if num else f"https://wa.me/?text={msg}"

# -----------------------------------------------------------------------------
# GENERACIÓN PDF: AVISO DE COBRO GENERAL
# -----------------------------------------------------------------------------
def generar_pdf_recibo_general(periodo):
    datos_ed = obtener_datos_edificio()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()

    story = []
    
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=15, leading=18, alignment=1, textColor=colors.HexColor("#1E3A8A"))
    sub_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontSize=9, alignment=1)
    h2_style = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=11, leading=14, textColor=colors.HexColor("#1E3A8A"))

    # Encabezado del Edificio
    story.append(Paragraph(f"<b>{datos_ed['nombre']}</b>", title_style))
    story.append(Paragraph(f"RIF: {datos_ed['rif']} | {datos_ed['direccion']}", sub_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<b>AVISO DE COBRO GENERAL - PERIODO: {periodo}</b>", title_style))
    story.append(Spacer(1, 12))

    # 1. Desglose de Gastos Comunes Aprobados
    story.append(Paragraph("<b>1. DESGLOSE DE GASTOS COMUNES DEL MES</b>", h2_style))
    story.append(Spacer(1, 5))

    gastos_lista = []
    total_gastos = 0.0

    if engine:
        with engine.connect() as conn:
            res_g = conn.execute(
                text("SELECT concepto, proveedor, monto FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                {"m": periodo}
            ).fetchall()
            for r in res_g:
                gastos_lista.append([r[0], r[1], f"${float(r[2]):,.2f}"])
                total_gastos += float(r[2])

    if not gastos_lista:
        tabla_g_data = [["Sin gastos comunes aprobados para este periodo.", "", "$0.00"]]
    else:
        tabla_g_data = [["Concepto", "Proveedor", "Monto ($)"]] + gastos_lista
    
    tabla_g_data.append(["TOTAL GASTOS COMUNES", "", f"${total_gastos:,.2f}"])

    t_gastos = Table(tabla_g_data, colWidths=[280, 140, 110])
    t_gastos.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (2,0), (2,-1), 'RIGHT'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#E2E8F0")),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
    ]))
    story.append(t_gastos)
    story.append(Spacer(1, 15))

    # 2. Distribución y Alícuotas por Apartamento
    story.append(Paragraph("<b>2. DISTRIBUCIÓN DE CUOTAS POR APARTAMENTO</b>", h2_style))
    story.append(Spacer(1, 5))

    df_u = obtener_unidades_df()
    tabla_a_data = [["Unidad", "Propietario", "Alícuota", "Cuota Común ($)", "Detalle Gasto Ind.", "Total a Pagar ($)"]]

    if engine:
        with engine.connect() as conn:
            for _, u_row in df_u.iterrows():
                u_cod = u_row['unidad']
                prop = u_row['propietario']
                alic = float(u_row['alicuota'])

                c_comun = total_gastos * (alic / 100.0)

                # Buscar gastos individuales
                cargos_res = conn.execute(
                    text("SELECT concepto, monto FROM cargos_individuales WHERE apartamento = :u AND mes_anio = :m"),
                    {"u": u_cod, "m": periodo}
                ).fetchall()

                if cargos_res:
                    m_ind = sum(float(c[1]) for c in cargos_res)
                    conceptos_ind = ", ".join([f"{c[0]} (${float(c[1]):,.2f})" for c in cargos_res])
                    total_apto_raw = c_comun + m_ind
                    txt_ind = conceptos_ind
                else:
                    total_apto_raw = c_comun
                    txt_ind = "-"  # No se hace referencia si no posee gastos individuales

                tot_red = redondear_custom(total_apto_raw)

                tabla_a_data.append([
                    u_cod,
                    prop,
                    f"{alic:.2f}%",
                    f"${c_comun:,.2f}",
                    txt_ind,
                    f"${tot_red:,.0f}"
                ])

    t_aptos = Table(tabla_a_data, colWidths=[45, 110, 50, 85, 140, 100])
    t_aptos.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('ALIGN', (2,0), (3,-1), 'RIGHT'),
        ('ALIGN', (5,0), (5,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
    ]))
    story.append(t_aptos)

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
# PORTAL DE ACCESO
# -----------------------------------------------------------------------------
if not st.session_state.usuario_logueado:
    st.markdown("<h2 style='text-align: center;'>🔒 Portal de Acceso</h2>", unsafe_allow_html=True)
    if error_conexion:
        st.error(f"⚠️ Error de conexión: {error_conexion}")

    with st.form("form_login"):
        u_in = st.text_input("Usuario (ej. 1A, PH o admin)").strip()
        p_in = st.text_input("Contraseña", type="password").strip()
        if st.form_submit_button("Ingresar", type="primary", use_container_width=True):
            if engine:
                with engine.connect() as conn:
                    row = conn.execute(text("SELECT usuario, clave, rol FROM usuarios WHERE LOWER(usuario) = LOWER(:u)"), {"u": u_in}).fetchone()
                if row and row[1] == p_in:
                    st.session_state.usuario_logueado = row[0]
                    st.session_state.rol_logueado = row[2]
                    st.rerun()
                else:
                    st.error("❌ Credenciales incorrectas.")

# -----------------------------------------------------------------------------
# VISTA PROPIETARIOS
# -----------------------------------------------------------------------------
elif st.session_state.rol_logueado == "propietario":
    user_actual = st.session_state.usuario_logueado
    datos_ed = obtener_datos_edificio()
    df_u = obtener_unidades_df()
    row_u = df_u[df_u['unidad'] == user_actual]
    prop_nombre = row_u['propietario'].values[0] if not row_u.empty else "Propietario"
    pct_user = float(row_u['alicuota'].values[0]) if not row_u.empty else 6.0

    c_head, c_out = st.columns([3, 1])
    c_head.title(f"🏢 {datos_ed['nombre']} - Unidad {user_actual}")
    if c_out.button("🚪 Cerrar Sesión", use_container_width=True):
        cerrar_sesion()

    t_p1, t_p2 = st.tabs(["📄 Mi Estado de Cuenta", "💳 Reportar Pago"])

    with t_p1:
        mes_consultar = st.text_input("Periodo (AAAA-MM):", value=obtener_mes_anterior())
        if engine:
            with engine.connect() as conn:
                g_aprob = conn.execute(text("SELECT SUM(monto) FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"), {"m": mes_consultar}).scalar() or 0.0
                c_ind = conn.execute(text("SELECT SUM(monto) FROM cargos_individuales WHERE apartamento = :u AND mes_anio = :m"), {"u": user_actual, "m": mes_consultar}).scalar() or 0.0

            cuota_comun = float(g_aprob) * (pct_user / 100.0)
            total_raw = cuota_comun + float(c_ind)
            tot_red = redondear_custom(total_raw)

            c1, c2, c3 = st.columns(3)
            c1.metric("Cuota Común", f"${cuota_comun:,.2f}")
            c2.metric("Cargos Indiv.", f"${c_ind:,.2f}")
            c3.metric("Total a Pagar", f"${tot_red:,.0f}")

    with t_p2:
        with st.form("form_pago_prop"):
            tipo_p = st.selectbox("Tipo de Pago", ["Mensualidad", "Cuota Extraordinaria"])
            mes_p = st.text_input("Periodo (AAAA-MM)", value=obtener_mes_anterior())
            monto_p = st.number_input("Monto ($)", min_value=1.0)
            ref_p = st.text_input("Referencia")
            if st.form_submit_button("Enviar Reporte"):
                with engine.connect() as conn:
                    conn.execute(
                        text("INSERT INTO pagos_reportados (apartamento, tipo_pago, mes_anio, monto, metodo_pago, referencia, fecha_pago) VALUES (:u, :t, :m, :mo, 'Pago Móvil', :r, CURRENT_DATE)"),
                        {"u": user_actual, "t": tipo_p, "m": mes_p, "mo": float(monto_p), "r": ref_p}
                    )
                    conn.commit()
                st.success("Pago reportado exitosamente.")

# -----------------------------------------------------------------------------
# VISTA ADMINISTRACIÓN
# -----------------------------------------------------------------------------
elif st.session_state.rol_logueado == "admin":
    datos_ed = obtener_datos_edificio()

    c_head, c_out = st.columns([3, 1])
    c_head.title("⚙️ Módulo de Administración")
    if c_out.button("🚪 Cerrar Sesión", use_container_width=True):
        cerrar_sesion()

    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "📊 Gastos Comunes", 
        "🛠️ Gastos No Comunes", 
        "⭐ Cuotas Extras", 
        "✅ Validar Pagos", 
        "🏢 Unidades", 
        "📄 Recibo General / Notificar", 
        "⚙️ Datos Edificio"
    ])

    with t1:
        st.subheader("➕ Registrar Gasto Común")
        with st.form("f_gasto"):
            m_g = st.text_input("Mes/Año (AAAA-MM)", value=obtener_mes_anterior())
            c_g = st.text_input("Concepto")
            p_g = st.text_input("Proveedor", value="N/A")
            mo_g = st.number_input("Monto ($)", min_value=0.01)
            if st.form_submit_button("Guardar Gasto") and c_g:
                with engine.connect() as conn:
                    conn.execute(
                        text("INSERT INTO gastos (periodo, mes_anio, concepto, monto, estatus, proveedor) VALUES (:m, :m, :c, :mo, 'Pendiente', :p)"),
                        {"m": m_g, "c": c_g, "mo": float(mo_g), "p": p_g}
                    )
                    conn.commit()
                st.rerun()

        st.subheader("Aprobación de Gastos")
        mes_f = st.text_input("Filtrar Periodo:", value=obtener_mes_anterior())
        with engine.connect() as conn:
            df_g = pd.read_sql(text("SELECT id, concepto, monto, estatus FROM gastos WHERE mes_anio = :m"), conn, params={"m": mes_f})
        for _, r in df_g.iterrows():
            st.write(f"**{r['concepto']}** - ${float(r['monto']):,.2f} ({r['estatus']})")
            if r['estatus'] == 'Pendiente':
                if st.button("Aprobar", key=f"ap_{r['id']}"):
                    with engine.connect() as conn:
                        conn.execute(text("UPDATE gastos SET estatus = 'Aprobado' WHERE id = :id"), {"id": r['id']})
                        conn.commit()
                    st.rerun()

    with t2:
        st.subheader("🛠️ Cargar Gasto No Común")
        df_u = obtener_unidades_df()
        with st.form("f_nc"):
            u_nc = st.selectbox("Unidad", df_u['unidad'].tolist())
            m_nc = st.text_input("Periodo (AAAA-MM)", value=obtener_mes_anterior())
            c_nc = st.text_input("Concepto")
            mo_nc = st.number_input("Monto ($)", min_value=0.01)
            if st.form_submit_button("Asignar Cargo") and c_nc:
                with engine.connect() as conn:
                    conn.execute(
                        text("INSERT INTO cargos_individuales (apartamento, mes_anio, concepto, monto) VALUES (:a, :m, :c, :mo)"),
                        {"a": u_nc, "m": m_nc, "c": c_nc, "mo": float(mo_nc)}
                    )
                    conn.commit()
                st.success("Cargo registrado.")

    with t3:
        st.subheader("⭐ Cuotas Extraordinarias")
        with st.form("f_ce"):
            c_ce = st.text_input("Proyecto")
            mo_ce = st.number_input("Monto Total ($)", min_value=0.01)
            if st.form_submit_button("Crear Cuota Extra") and c_ce:
                with engine.connect() as conn:
                    conn.execute(text("INSERT INTO cuotas_extraordinarias (concepto, monto_total) VALUES (:c, :m)"), {"c": c_ce, "m": float(mo_ce)})
                    conn.commit()
                st.rerun()

    with t4:
        st.subheader("✅ Validar Pagos")
        with engine.connect() as conn:
            df_p = pd.read_sql(text("SELECT id, apartamento, mes_anio, monto, referencia, estatus FROM pagos_reportados WHERE estatus = 'Pendiente'"), conn)
        st.dataframe(df_p, use_container_width=True)

    with t5:
        st.subheader("🏢 Unidades y Alícuotas")
        st.dataframe(obtener_unidades_df(), use_container_width=True)

    with t6:
        st.subheader("📄 Generación de Aviso de Cobro General / Recibo Completo")
        mes_recibo = st.text_input("Seleccionar Periodo (AAAA-MM):", value=obtener_mes_anterior(), key="recibo_gen_mes")

        if st.button("📊 Generar PDF General de Cobro", type="primary"):
            pdf_gen = generar_pdf_recibo_general(mes_recibo)
            st.download_button(
                label=f"📥 Descargar Aviso General PDF ({mes_recibo})",
                data=pdf_gen,
                file_name=f"recibo_general_{mes_recibo}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    with t7:
        st.subheader("⚙️ Datos del Edificio")
        with st.form("f_ed"):
            n_ed = st.text_input("Nombre", value=datos_ed['nombre'])
            r_ed = st.text_input("RIF", value=datos_ed['rif'])
            d_ed = st.text_area("Dirección", value=datos_ed['direccion'])
            if st.form_submit_button("Actualizar"):
                with engine.connect() as conn:
                    conn.execute(text("UPDATE configuracion_edificio SET nombre = :n, rif = :r, direccion = :d WHERE id = 1"), {"n": n_ed, "r": r_ed, "d": d_ed})
                    conn.commit()
                st.success("Datos actualizados.")
            
