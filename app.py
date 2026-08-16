import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
import io
import urllib.parse
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
                    mes_anio VARCHAR(7) NOT NULL,
                    concepto VARCHAR(200) NOT NULL,
                    monto NUMERIC(12,2) NOT NULL,
                    estatus VARCHAR(20) DEFAULT 'Aprobado',
                    fecha DATE DEFAULT CURRENT_DATE
                );
            """))

            # NUEVA TABLA: CARGOS INDIVIDUALES / GASTOS NO COMUNES
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
                    estatus VARCHAR(20) DEFAULT 'Activa'
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
# FUNCIONES AUXILIARES
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

def calcular_estado_cuenta(apartamento, mes_hasta):
    df_u = obtener_unidades_df()
    row_u = df_u[df_u['unidad'] == apartamento]
    pct = float(row_u['alicuota'].values[0]) / 100.0 if not row_u.empty else 0.06

    if not engine:
        return {"mes_actual": 0.0, "cargos_ind": 0.0, "deuda_anterior": 0.0, "pagos_mes": 0.0, "total_deber": 0.0, "gastos_totales": 0.0}

    try:
        with engine.connect() as conn:
            df_gastos = pd.read_sql(
                text("SELECT mes_anio, COALESCE(SUM(monto), 0) as total_gasto FROM gastos WHERE estatus = 'Aprobado' AND mes_anio <= :m GROUP BY mes_anio ORDER BY mes_anio ASC"),
                conn, params={"m": mes_hasta}
            )
            df_cargos_ind = pd.read_sql(
                text("SELECT mes_anio, COALESCE(SUM(monto), 0) as total_ind FROM cargos_individuales WHERE apartamento = :ap AND mes_anio <= :m GROUP BY mes_anio"),
                conn, params={"ap": apartamento, "m": mes_hasta}
            )
            df_pagos = pd.read_sql(
                text("SELECT mes_anio, COALESCE(SUM(monto), 0) as total_pago FROM pagos_reportados WHERE apartamento = :ap AND tipo_pago = 'Mensualidad' AND estatus = 'Aprobado' AND mes_anio <= :m GROUP BY mes_anio"),
                conn, params={"ap": apartamento, "m": mes_hasta}
            )

        pagos_dict = dict(zip(df_pagos['mes_anio'], df_pagos['total_pago'])) if not df_pagos.empty else {}
        cargos_ind_dict = dict(zip(df_cargos_ind['mes_anio'], df_cargos_ind['total_ind'])) if not df_cargos_ind.empty else {}

        deuda_anterior, cuota_mes_actual, cargos_ind_actual, pagos_mes_actual, gastos_mes_totales = 0.0, 0.0, 0.0, 0.0, 0.0

        # Obtener todos los meses involucrados
        meses_unicos = sorted(list(set(df_gastos['mes_anio'].tolist() + list(cargos_ind_dict.keys()) + list(pagos_dict.keys()))))

        for m in meses_unicos:
            if m <= mes_hasta:
                g_monto = float(df_gastos[df_gastos['mes_anio'] == m]['total_gasto'].sum()) if not df_gastos.empty else 0.0
                cuota_comun = round(g_monto * pct, 2)
                cargo_ind = float(cargos_ind_dict.get(m, 0.0))
                pago = float(pagos_dict.get(m, 0.0))
                total_mes = cuota_comun + cargo_ind

                if m == mes_hasta:
                    cuota_mes_actual = cuota_comun
                    cargos_ind_actual = cargo_ind
                    pagos_mes_actual = pago
                    gastos_mes_totales = g_monto
                else:
                    deuda_anterior += (total_mes - pago)

        total_adeudado = round(deuda_anterior + cuota_mes_actual + cargos_ind_actual - pagos_mes_actual, 2)
        return {
            "mes_actual": cuota_mes_actual,
            "cargos_ind": cargos_ind_actual,
            "deuda_anterior": round(deuda_anterior, 2),
            "pagos_mes": pagos_mes_actual,
            "total_deber": total_adeudado,
            "gastos_totales": gastos_mes_totales
        }
    except Exception:
        return {"mes_actual": 0.0, "cargos_ind": 0.0, "deuda_anterior": 0.0, "pagos_mes": 0.0, "total_deber": 0.0, "gastos_totales": 0.0}

def generar_pdf_recibo(apartamento, mes_anio, datos_cuenta):
    datos_ed = obtener_datos_edificio()
    df_u = obtener_unidades_df()
    row_u = df_u[df_u['unidad'] == apartamento]
    prop = row_u['propietario'].values[0] if not row_u.empty else "Propietario"
    alic = row_u['alicuota'].values[0] if not row_u.empty else 6.0

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"<b>{datos_ed['nombre'].upper()}</b>", styles['Heading1']))
    story.append(Paragraph(f"<b>RIF:</b> {datos_ed['rif']} | <b>Dirección:</b> {datos_ed['direccion']}", styles['Normal']))
    story.append(Spacer(1, 15))

    title_style = ParagraphStyle('DocTitle', parent=styles['Heading2'], alignment=1, spaceAfter=15)
    story.append(Paragraph(f"RECIBO DE CONDOMINIO - PERIODO {mes_anio}", title_style))
    story.append(Paragraph(f"<b>Unidad / Inmueble:</b> {apartamento} (Alícuota: {alic}%)", styles['Normal']))
    story.append(Paragraph(f"<b>Propietario:</b> {prop}", styles['Normal']))
    story.append(Paragraph(f"<b>Fecha de Emisión:</b> {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
    story.append(Spacer(1, 15))

    data_resumen = [
        ["Concepto", "Monto ($)"],
        ["Gastos Comunes Totales del Condominio", f"${datos_cuenta['gastos_totales']:,.2f}"],
        ["Deuda Acumulada (Meses Anteriores)", f"${datos_cuenta['deuda_anterior']:,.2f}"],
        [f"Cuota Común del Mes ({mes_anio})", f"${datos_cuenta['mes_actual']:,.2f}"],
        ["Gastos No Comunes / Cargos Individuales", f"${datos_cuenta['cargos_ind']:,.2f}"],
        ["Pagos Aprobados / Abonados", f"-${datos_cuenta['pagos_mes']:,.2f}"],
        ["TOTAL A CANCELAR", f"${datos_cuenta['total_deber']:,.2f}"]
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

def generar_link_whatsapp(telefono, mensaje):
    msg_enc = urllib.parse.quote(mensaje)
    tel_limpio = "".join(filter(str.isdigit, str(telefono)))
    if tel_limpio:
        return f"https://wa.me/{tel_limpio}?text={msg_enc}"
    return f"https://wa.me/?text={msg_enc}"

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
# 1. PORTAL DE ACCESO NEUTRO
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
        st.title(f"🏢 {datos_ed['nombre']} - {user_actual}")
        st.caption(f"Propietario: {prop_nombre} | Alícuota: {pct_user}%")
    with col_out:
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            cerrar_sesion()

    st.write("---")

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Recibo del Mes", "⭐ Cuotas Extraordinarias", "📥 Reportar Pago", "📋 Mis Pagos"])

    with tab1:
        mes_filtro = st.text_input("Consulta de mes (AAAA-MM):", value=datetime.now().strftime("%Y-%m"))
        datos = calcular_estado_cuenta(user_actual, mes_filtro)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Morosidad Anterior", f"${datos['deuda_anterior']:,.2f}")
        c2.metric("Cuota Común Mes", f"${datos['mes_actual']:,.2f}")
        c3.metric("Gastos No Comunes", f"${datos['cargos_ind']:,.2f}")
        c4.metric("Pagos Validados", f"${datos['pagos_mes']:,.2f}")
        c5.metric("TOTAL A PAGAR", f"${datos['total_deber']:,.2f}", delta=-datos['total_deber'] if datos['total_deber'] > 0 else 0)

        # Mostrar desglose de gastos no comunes si existen
        if datos['cargos_ind'] > 0:
            st.info("📌 **Desglose de Gastos No Comunes / Cargos Individuales del Mes:**")
            try:
                with engine.connect() as conn:
                    df_ind_det = pd.read_sql(
                        text("SELECT concepto, monto, fecha FROM cargos_individuales WHERE apartamento = :ap AND mes_anio = :m"),
                        conn, params={"ap": user_actual, "m": mes_filtro}
                    )
                st.dataframe(df_ind_det, use_container_width=True)
            except Exception:
                pass

        st.write("---")
        c_pdf, c_wa = st.columns(2)
        with c_pdf:
            pdf_bytes = generar_pdf_recibo(user_actual, mes_filtro, datos)
            st.download_button(
                label="📄 Descargar Recibo Digital (PDF)",
                data=pdf_bytes,
                file_name=f"Recibo_{user_actual}_{mes_filtro}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        with c_wa:
            msg_p = f"🏢 *{datos_ed['nombre']}*\nRIF: {datos_ed['rif']}\n\nEstimado(a) {prop_nombre} ({user_actual}):\nResumen Estado de Cuenta ({mes_filtro}):\n- Cuota Común del Mes: ${datos['mes_actual']:,.2f}\n- Gastos No Comunes: ${datos['cargos_ind']:,.2f}\n- Deuda Anterior: ${datos['deuda_anterior']:,.2f}\n- Abonado: ${datos['pagos_mes']:,.2f}\n*TOTAL PENDIENTE: ${datos['total_deber']:,.2f}*"
            link_w = generar_link_whatsapp("", msg_p)
            st.link_button("📱 Compartir Recibo por WhatsApp", link_w, use_container_width=True)

    with tab2:
        st.subheader("Cuotas Extraordinarias Asignadas")
        try:
            with engine.connect() as conn:
                df_ce = pd.read_sql(text("SELECT id, concepto, monto_total, fecha_emision, estatus FROM cuotas_extraordinarias WHERE estatus = 'Activa' ORDER BY id DESC"), conn)

            if df_ce.empty:
                st.info("No hay cuotas extraordinarias activas.")
            else:
                filas_ce = []
                for _, r in df_ce.iterrows():
                    m_total = float(r['monto_total'])
                    m_corresponde = round(m_total * (pct_user / 100.0), 2)
                    with engine.connect() as conn:
                        pagado = conn.execute(
                            text("SELECT COALESCE(SUM(monto),0) FROM pagos_reportados WHERE apartamento = :a AND id_cuota_extra = :id AND estatus = 'Aprobado'"),
                            {"a": user_actual, "id": r['id']}
                        ).scalar()
                    saldo_ce = round(m_corresponde - float(pagado), 2)
                    filas_ce.append({
                        "ID": r['id'], "Concepto": r['concepto'], "Monto Total Fondo ($)": f"${m_total:,.2f}",
                        "Mi Cuota ($)": f"${m_corresponde:,.2f}", "Abonado ($)": f"${float(pagado):,.2f}",
                        "Pendiente ($)": f"${saldo_ce:,.2f}", "Estatus": "🟢 Pagado" if saldo_ce <= 0 else "🔴 Pendiente"
                    })
                st.dataframe(pd.DataFrame(filas_ce), use_container_width=True)
        except Exception as e:
            st.error(f"Error cargando cuotas: {e}")

    with tab3:
        st.subheader("Reportar Comprobante de Pago")
        tipo_p = st.radio("Tipo de Cobro a Cancelar:", ["Mensualidad de Condominio", "Cuota Extraordinaria"])
        id_ce_sel = None
        if tipo_p == "Cuota Extraordinaria":
            try:
                with engine.connect() as conn:
                    df_ce_opts = pd.read_sql(text("SELECT id, concepto FROM cuotas_extraordinarias WHERE estatus = 'Activa'"), conn)
                if not df_ce_opts.empty:
                    opcion = st.selectbox("Selecciona la Cuota Extraordinaria:", df_ce_opts.apply(lambda x: f"#{x['id']} - {x['concepto']}", axis=1))
                    id_ce_sel = int(opcion.split(" - ")[0].replace("#", ""))
            except Exception as e:
                st.error(f"Error al cargar lista: {e}")

        with st.form("form_pago", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("Apartamento", value=user_actual, disabled=True)
                mes_pago = st.text_input("Mes Relacionado (AAAA-MM)", value=datetime.now().strftime("%Y-%m"))
                monto = st.number_input("Monto Pagado ($)", min_value=0.01, step=0.01)
            with c2:
                metodo = st.selectbox("Método de Pago", ["Transferencia Bancaria", "Pago Móvil", "Zelle", "Efectivo $"])
                referencia = st.text_input("Número de Referencia")
                fecha_pago = st.date_input("Fecha de Pago", value=datetime.now().date())

            comprobante = st.file_uploader("Adjuntar Comprobante", type=["png", "jpg", "jpeg", "pdf"])
            btn_subir = st.form_submit_button("🚀 Registrar Pago", type="primary")

            if btn_subir:
                if not referencia.strip():
                    st.error("Por favor ingresa la referencia de pago.")
                else:
                    nombre_file = comprobante.name if comprobante else "Sin comprobante"
                    tipo_str = "Extraordinaria" if tipo_p == "Cuota Extraordinaria" else "Mensualidad"
                    try:
                        with engine.connect() as conn:
                            conn.execute(text("""
                                INSERT INTO pagos_reportados (apartamento, tipo_pago, mes_anio, id_cuota_extra, monto, metodo_pago, referencia, fecha_pago, comprobante_nombre, estatus)
                                VALUES (:apto, :tipo, :mes, :id_ce, :monto, :metodo, :ref, :fecha, :comp, 'Pendiente')
                            """), {
                                "apto": user_actual, "tipo": tipo_str, "mes": mes_pago, "id_ce": id_ce_sel,
                                "monto": monto, "metodo": metodo, "ref": referencia, "fecha": fecha_pago, "comp": nombre_file
                            })
                            conn.commit()
                        st.success("✅ Pago registrado correctamente.")
                    except Exception as e:
                        st.error(f"Error registrando el pago: {e}")

    with tab4:
        try:
            with engine.connect() as conn:
                df_mis_p = pd.read_sql(
                    text("SELECT tipo_pago, mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus FROM pagos_reportados WHERE apartamento = :a ORDER BY id DESC"),
                    conn, params={"a": user_actual}
                )
            if df_mis_p.empty:
                st.info("Sin pagos registrados.")
            else:
                st.dataframe(df_mis_p, use_container_width=True)
        except Exception as e:
            st.error(f"Error consultando historial: {e}")

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

    t1, t2, t3, t4, t5, t6, t7 = st.tabs(["📊 Gastos Comunes", "🛠️ Gastos No Comunes", "⭐ Cuotas Extras", "✅ Validar Pagos", "🏢 Alícuotas y Unidades", "🚨 Morosidad y Recibos", "⚙️ Datos Edificio"])

    # GASTOS COMUNES Y WHATSAPP
    with t1:
        st.subheader("Cargar Gasto Común (Se distribuye por alícuota a todos)")
        with st.form("form_gasto"):
            mes = st.text_input("Mes / Año (AAAA-MM)", value=datetime.now().strftime("%Y-%m"))
            concepto = st.text_input("Descripción del Gasto Común")
            monto = st.number_input("Monto Total ($)", min_value=0.01, step=0.01)
            btn = st.form_submit_button("Guardar Gasto Común", type="primary")

            if btn and concepto:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("INSERT INTO gastos (mes_anio, concepto, monto, estatus) VALUES (:m, :c, :mo, 'Aprobado')"),
                            {"m": mes, "c": concepto, "mo": monto}
                        )
                        conn.commit()
                    st.success("Gasto común registrado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error registrando gasto: {e}")

        st.write("---")
        st.subheader("🗑️ Historial de Gastos Comunes")
        mes_eliminar = st.text_input("Filtrar gastos por mes (AAAA-MM):", value=datetime.now().strftime("%Y-%m"), key="filtro_elim")
        
        try:
            with engine.connect() as conn:
                df_gastos_lista = pd.read_sql(
                    text("SELECT id, mes_anio, concepto, monto, fecha FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado' ORDER BY id DESC"),
                    conn, params={"m": mes_eliminar}
                )

            if df_gastos_lista.empty:
                st.info(f"No hay gastos comunes registrados en {mes_eliminar}.")
            else:
                for _, g in df_gastos_lista.iterrows():
                    col_info, col_btn = st.columns([4, 1])
                    with col_info:
                        st.markdown(f"**ID:** {g['id']} | **Concepto:** {g['concepto']} | **Monto:** ${float(g['monto']):,.2f}")
                    with col_btn:
                        if st.button("❌ Eliminar", key=f"del_gasto_{g['id']}", type="secondary"):
                            with engine.connect() as conn:
                                conn.execute(text("DELETE FROM gastos WHERE id = :id"), {"id": g['id']})
                                conn.commit()
                            st.success(f"Gasto #{g['id']} eliminado.")
                            st.rerun()
                    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error consultando gastos: {e}")

        st.write("---")
        st.subheader("📢 Reporte General de Gastos para WhatsApp")
        mes_rep = st.text_input("Mes del Reporte (AAAA-MM):", value=datetime.now().strftime("%Y-%m"), key="rep_g")

        try:
            with engine.connect() as conn:
                df_g = pd.read_sql(text("SELECT concepto, monto FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"), conn, params={"m": mes_rep})

            total_g = df_g["monto"].sum() if not df_g.empty else 0.0
            df_u = obtener_unidades_df()

            txt_wa = f"🏢 *{datos_ed['nombre'].upper()}*\nRIF: {datos_ed['rif']}\n📍 {datos_ed['direccion']}\n\n"
            txt_wa += f"📊 *REPORTE GENERAL DE GASTOS - PERIODO {mes_rep}*\n"
            txt_wa += f"-----------------------------------\n"
            txt_wa += f"💰 *Monto Total Gastos Comunes:* ${total_g:,.2f}\n\n"
            txt_wa += f"*DISTRIBUCIÓN POR ALÍCUOTA:*\n"

            for _, r in df_u.iterrows():
                cuota_apt = round(total_g * (float(r['alicuota']) / 100.0), 2)
                txt_wa += f"• *{r['unidad']}* ({r['alicuota']}%): ${cuota_apt:,.2f}\n"

            txt_wa += f"\nPor favor realizar sus pagos y reportarlos a través del portal del condominio."

            st.text_area("Previsualización del Mensaje para el Grupo:", value=txt_wa, height=220)
            st.link_button("📲 Compartir Reporte General al Grupo de WhatsApp", generar_link_whatsapp("", txt_wa), type="primary")
        except Exception as e:
            st.error(f"Error generando reporte: {e}")

    # GASTOS NO COMUNES / CARGOS INDIVIDUALES
    with t2:
        st.subheader("🛠️ Cargar Gasto No Común (Exclusivo a un Solo Apartamento)")
        df_u = obtener_unidades_df()
        
        with st.form("form_gasto_individual"):
            col1, col2 = st.columns(2)
            with col1:
                apto_ind = st.selectbox("Seleccionar Apartamento:", df_u["unidad"].tolist())
                mes_ind = st.text_input("Mes / Año (AAAA-MM)", value=datetime.now().strftime("%Y-%m"), key="mes_ind_input")
            with col2:
                concepto_ind = st.text_input("Descripción (ej. Reparación de tubería privada, Llave de acceso)")
                monto_ind = st.number_input("Monto del Cargo ($)", min_value=0.01, step=0.01, key="monto_ind_input")
            
            btn_ind = st.form_submit_button("Cargar Gasto a Apartamento", type="primary")

            if btn_ind and concepto_ind:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("INSERT INTO cargos_individuales (apartamento, mes_anio, concepto, monto) VALUES (:ap, :m, :c, :mo)"),
                            {"ap": apto_ind, "m": mes_ind, "c": concepto_ind, "mo": monto_ind}
                        )
                        conn.commit()
                    st.success(f"Cargo de ${monto_ind:,.2f} aplicado exitosamente al departamento {apto_ind}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error registrando cargo individual: {e}")

        st.write("---")
        st.subheader("📋 Consultar y Eliminar Gastos No Comunes Registrados")
        mes_filtro_ind = st.text_input("Filtrar por mes (AAAA-MM):", value=datetime.now().strftime("%Y-%m"), key="filtro_ind_mes")

        try:
            with engine.connect() as conn:
                df_cargos_registrados = pd.read_sql(
                    text("SELECT id, apartamento, mes_anio, concepto, monto, fecha FROM cargos_individuales WHERE mes_anio = :m ORDER BY id DESC"),
                    conn, params={"m": mes_filtro_ind}
                )

            if df_cargos_registrados.empty:
                st.info(f"No hay cargos individuales o gastos no comunes en el periodo {mes_filtro_ind}.")
            else:
                for _, ci in df_cargos_registrados.iterrows():
                    col_info, col_del = st.columns([4, 1])
                    with col_info:
                        st.markdown(f"**Apto {ci['apartamento']}** | **Concepto:** {ci['concepto']} | **Monto:** ${float(ci['monto']):,.2f} | **Fecha:** {ci['fecha']}")
                    with col_del:
                        if st.button("❌ Eliminar", key=f"del_ind_{ci['id']}", type="secondary"):
                            with engine.connect() as conn:
                                conn.execute(text("DELETE FROM cargos_individuales WHERE id = :id"), {"id": ci['id']})
                                conn.commit()
                            st.success(f"Cargo #{ci['id']} eliminado.")
                            st.rerun()
                    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error consultando cargos individuales: {e}")

    # CUOTAS EXTRAS
    with t3:
        st.subheader("1️⃣ Crear Nueva Cuota Extraordinaria")
        with st.form("form_ce"):
            concepto_ce = st.text_input("Concepto (ej. Reparación de Ascensor)")
            monto_ce = st.number_input("Monto Total del Fondo ($)", min_value=0.01, step=0.01)
            btn_ce = st.form_submit_button("Guardar Cuota Extraordinaria", type="primary")

            if btn_ce and concepto_ce:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("INSERT INTO cuotas_extraordinarias (concepto, monto_total) VALUES (:c, :m)"),
                            {"c": concepto_ce, "m": monto_ce}
                        )
                        conn.commit()
                    st.success("Cuota extraordinaria creada exitosamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error creando cuota: {e}")

        st.write("---")
        st.subheader("2️⃣ Previsualizar Distribución y Notificar por WhatsApp")

        try:
            with engine.connect() as conn:
                df_cuotas = pd.read_sql(text("SELECT id, concepto, monto_total FROM cuotas_extraordinarias WHERE estatus = 'Activa' ORDER BY id DESC"), conn)

            if df_cuotas.empty:
                st.info("No hay cuotas extraordinarias creadas.")
            else:
                opciones_ce = df_cuotas.apply(lambda x: f"#{x['id']} - {x['concepto']} (${x['monto_total']:,.2f})", axis=1).tolist()
                ce_seleccionada = st.selectbox("Selecciona la Cuota Extraordinaria:", opciones_ce)
                
                id_ce_actual = int(ce_seleccionada.split(" - ")[0].replace("#", ""))
                row_ce = df_cuotas[df_cuotas['id'] == id_ce_actual].iloc[0]
                
                monto_ce_total = float(row_ce['monto_total'])
                concepto_ce_txt = row_ce['concepto']

                df_u = obtener_unidades_df()

                filas_distribucion = []
                txt_ce_grupo = f"🏢 *{datos_ed['nombre'].upper()}*\nRIF: {datos_ed['rif']}\n\n"
                txt_ce_grupo += f"⭐ *COBRO DE CUOTA EXTRAORDINARIA*\n"
                txt_ce_grupo += f"📌 *Concepto:* {concepto_ce_txt}\n"
                txt_ce_grupo += f"💰 *Monto Total del Fondo:* ${monto_ce_total:,.2f}\n"
                txt_ce_grupo += f"-----------------------------------\n"
                txt_ce_grupo += f"*DISTRIBUCIÓN POR ALÍCUOTA:*\n"

                for _, r in df_u.iterrows():
                    monto_corresponde = round(monto_ce_total * (float(r['alicuota']) / 100.0), 2)
                    txt_ce_grupo += f"• *{r['unidad']}* ({r['alicuota']}%): ${monto_corresponde:,.2f}\n"
                    
                    msg_ce_ind = f"🏢 *{datos_ed['nombre']}*\nRIF: {datos_ed['rif']}\n\nEstimado(a) {r['propietario']} ({r['unidad']}):\nSe ha emitido la siguiente *Cuota Extraordinaria*:\n📌 *Concepto:* {concepto_ce_txt}\n💰 *Monto Total del Fondo:* ${monto_ce_total:,.2f}\n📊 *Su Alícuota ({r['alicuota']}%):* ${monto_corresponde:,.2f}\n\nPor favor reportar su pago a través del sistema."
                    
                    filas_distribucion.append({
                        "Unidad": r['unidad'],
                        "Propietario": r['propietario'],
                        "Alícuota": f"{r['alicuota']}%",
                        "Monto a Pagar ($)": f"${monto_corresponde:,.2f}",
                        "WhatsApp Link": generar_link_whatsapp(r['telefono'], msg_ce_ind)
                    })

                txt_ce_grupo += f"\nPor favor reportar sus pagos mediante el portal de la residencia."

                df_dist = pd.DataFrame(filas_distribucion)
                st.dataframe(df_dist.drop(columns=["WhatsApp Link"]), use_container_width=True)

                st.write("---")
                c_grp, c_ind = st.columns(2)

                with c_grp:
                    st.markdown("#### 📢 Notificar al Grupo General")
                    st.text_area("Previsualización Mensaje de Grupo:", value=txt_ce_grupo, height=200)
                    st.link_button("📲 Enviar Cuota Extra al Grupo de WhatsApp", generar_link_whatsapp("", txt_ce_grupo), type="primary", use_container_width=True)

                with c_ind:
                    st.markdown("#### 📱 Notificar a Propietario Individual")
                    u_ce_ind = st.selectbox("Seleccionar Propietario para Enviar:", df_dist["Unidad"].tolist())
                    row_ce_ind = df_dist[df_dist["Unidad"] == u_ce_ind].iloc[0]
                    
                    m_ind_val = round(monto_ce_total * (float(df_u[df_u['unidad'] == u_ce_ind]['alicuota'].values[0]) / 100.0), 2)
                    msg_prev_ind = f"🏢 *{datos_ed['nombre']}*\nRIF: {datos_ed['rif']}\n\nEstimado(a) {row_ce_ind['Propietario']} ({u_ce_ind}):\nSe ha emitido la siguiente *Cuota Extraordinaria*:\n📌 *Concepto:* {concepto_ce_txt}\n💰 *Monto Total del Fondo:* ${monto_ce_total:,.2f}\n📊 *Su Alícuota:* ${m_ind_val:,.2f}\n\nPor favor reportar su pago a través del sistema."
                    
                    st.text_area("Previsualización Mensaje Individual:", value=msg_prev_ind, height=140)
                    st.link_button(f"📱 Enviar a {row_ce_ind['Propietario']} ({u_ce_ind})", row_ce_ind["WhatsApp Link"], type="primary", use_container_width=True)

        except Exception as e:
            st.error(f"Error distribuyendo cuota extraordinaria: {e}")

        st.write("---")
        st.subheader("3️⃣ Gestionar / Eliminar Cuotas Extraordinarias")
        try:
            with engine.connect() as conn:
                df_todas_ce = pd.read_sql(text("SELECT id, concepto, monto_total, fecha_emision, estatus FROM cuotas_extraordinarias ORDER BY id DESC"), conn)

            if df_todas_ce.empty:
                st.info("No hay cuotas registradas.")
            else:
                for _, rce in df_todas_ce.iterrows():
                    col_info, col_del = st.columns([4, 1])
                    with col_info:
                        st.markdown(f"**ID:** #{rce['id']} | **Concepto:** {rce['concepto']} | **Monto Total:** ${float(rce['monto_total']):,.2f} | **Estatus:** {rce['estatus']}")
                    with col_del:
                        if st.button("❌ Eliminar", key=f"del_ce_{rce['id']}", type="secondary"):
                            with engine.connect() as conn:
                                conn.execute(text("DELETE FROM cuotas_extraordinarias WHERE id = :id"), {"id": rce['id']})
                                conn.commit()
                            st.success(f"Cuota extraordinario #{rce['id']} eliminada.")
                            st.rerun()
                    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error al eliminar cuota extraordinaria: {e}")

    # VALIDAR PAGOS
    with t4:
        st.subheader("Pagos Pendientes por Validar")
        try:
            with engine.connect() as conn:
                df_p = pd.read_sql(
                    text("SELECT id, apartamento, tipo_pago, mes_anio, monto, metodo_pago, referencia, fecha_pago FROM pagos_reportados WHERE estatus = 'Pendiente' ORDER BY id ASC"),
                    conn
                )
            if df_p.empty:
                st.info("No hay pagos pendientes.")
            else:
                st.dataframe(df_p, use_container_width=True)
                for _, r in df_p.iterrows():
                    c1, c2, c3 = st.columns([3, 1, 1])
                    with c1:
                        st.write(f"**Pago #{r['id']}** | {r['apartamento']} | {r['tipo_pago']} ({r['mes_anio']}) | ${r['monto']} | Ref: {r['referencia']}")
                    with c2:
                        if st.button("✅ Aprobar", key=f"ap_{r['id']}"):
                            with engine.connect() as conn:
                                conn.execute(text("UPDATE pagos_reportados SET estatus = 'Aprobado' WHERE id = :id"), {"id": r['id']})
                                conn.commit()
                            st.rerun()
                    with c3:
                        if st.button("❌ Rechazar", key=f"rec_{r['id']}"):
                            with engine.connect() as conn:
                                conn.execute(text("UPDATE pagos_reportados SET estatus = 'Rechazado' WHERE id = :id"), {"id": r['id']})
                                conn.commit()
                            st.rerun()
        except Exception as e:
            st.error(f"Error al consultar pagos: {e}")

    # ALÍCUOTAS Y PROPIETARIOS
    with t5:
        st.subheader("Gestión de Unidades y Propietarios")
        df_unid = obtener_unidades_df()
        st.dataframe(df_unid, use_container_width=True)

        with st.form("form_editar_unidad"):
            u_sel = st.selectbox("Unidad a editar:", df_unid["unidad"].tolist())
            p_nom = st.text_input("Nombre del Propietario")
            p_tel = st.text_input("Teléfono (formato internacional ej: 584121234567)")
            btn_u = st.form_submit_button("Guardar Cambios", type="primary")

            if btn_u:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("UPDATE unidades SET propietario = :p, telefono = :t WHERE unidad = :u"),
                            {"p": p_nom, "t": p_tel, "u": u_sel}
                        )
                        conn.commit()
                    st.success("Unidad actualizada.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error actualizando unidad: {e}")

    # MOROSIDAD Y RECIBOS
    with t6:
        st.subheader("Estado de Cuenta de las Unidades")
        mes_mor = st.text_input("Mes de Consulta (AAAA-MM):", value=datetime.now().strftime("%Y-%m"), key="mes_mor")
        df_u = obtener_unidades_df()
        
        datos_mor = []
        for _, r in df_u.iterrows():
            st_cta = calcular_estado_cuenta(r['unidad'], mes_mor)
            datos_mor.append({
                "Unidad": r['unidad'],
                "Propietario": r['propietario'],
                "Alícuota": f"{r['alicuota']}%",
                "Cuota Común ($)": f"${st_cta['mes_actual']:,.2f}",
                "Gasto No Común ($)": f"${st_cta['cargos_ind']:,.2f}",
                "Deuda Anterior ($)": f"${st_cta['deuda_anterior']:,.2f}",
                "Pagos Mes ($)": f"${st_cta['pagos_mes']:,.2f}",
                "Total Pendiente ($)": f"${st_cta['total_deber']:,.2f}"
            })
        st.dataframe(pd.DataFrame(datos_mor), use_container_width=True)

    # DATOS EDIFICIO
    with t7:
        st.subheader("Configuración de la Edificación")
        ed = obtener_datos_edificio()

        with st.form("form_edificio"):
            n_nombre = st.text_input("Nombre de la Residencia / Condominio", value=ed['nombre'])
            n_rif = st.text_input("RIF", value=ed['rif'])
            n_dir = st.text_area("Dirección Física", value=ed['direccion'])
            btn_ed = st.form_submit_button("Guardar Configuración", type="primary")

            if btn_ed:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("UPDATE configuracion_edificio SET nombre = :n, rif = :r, direccion = :d WHERE id = 1"),
                            {"n": n_nombre, "r": n_rif, "d": n_dir}
                        )
                        conn.commit()
                    st.success("Datos del edificio actualizados.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error actualizando configuración: {e}")
