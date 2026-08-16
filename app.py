import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Gestión de Condominio",
    page_icon="🏢",
    layout="wide"
)

# ---------------------------------------------------------
# CONEXIÓN A LA BASE DE DATOS (POSTGRESQL / SUPABASE)
# ---------------------------------------------------------
@st.cache_resource
def obtener_conexion():
    try:
        db_url = st.secrets["postgres"]["url"]
        engine = create_engine(db_url, pool_pre_ping=True)
        return engine
    except Exception as e:
        st.error(f"Error conectando a la base de datos: {e}")
        return None

engine = obtener_conexion()

UNIDADES_DEFECTO = [
    ("1A", 6.0), ("1B", 6.0), ("2", 12.0),
    ("3A", 6.0), ("3B", 6.0), ("4A", 6.0), ("4B", 6.0),
    ("5A", 6.0), ("5B", 6.0), ("6A", 6.0), ("6B", 6.0),
    ("7", 12.0), ("PH", 16.0)
]

# ---------------------------------------------------------
# INICIALIZACIÓN Y MIGRACIONES DE TABLAS
# ---------------------------------------------------------
def inicializar_tablas():
    if not engine:
        return
    try:
        with engine.connect() as conn:
            # 1. Configuración Edificio
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

            # 2. Unidades
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

            if conn.execute(text("SELECT COUNT(*) FROM unidades")).scalar() == 0:
                for u, a in UNIDADES_DEFECTO:
                    conn.execute(text("""
                        INSERT INTO unidades (unidad, alicuota, propietario, telefono) 
                        VALUES (:u, :a, 'Propietario', '')
                    """), {"u": u, "a": a})

            # 3. Usuarios
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

            # 4. Gastos
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

            # 5. Cuotas Extraordinarias
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cuotas_extraordinarias (
                    id SERIAL PRIMARY KEY,
                    concepto VARCHAR(200) NOT NULL,
                    monto_total NUMERIC(12,2) NOT NULL,
                    fecha_emision DATE DEFAULT CURRENT_DATE,
                    estatus VARCHAR(20) DEFAULT 'Activa'
                );
            """))

            # 6. Pagos Reportados
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

            # Migraciones automáticas para columnas faltantes en tablas existentes
            try:
                conn.execute(text("ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS tipo_pago VARCHAR(30) DEFAULT 'Mensualidad'"))
                conn.execute(text("ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS id_cuota_extra INT"))
            except Exception:
                pass

            conn.commit()
    except Exception as e:
        st.error(f"Error al inicializar la base de datos: {e}")

inicializar_tablas()

# ---------------------------------------------------------
# FUNCIONES AUXILIARES DE NAVEGACIÓN Y DATOS
# ---------------------------------------------------------
def obtener_config_edificio():
    with engine.connect() as conn:
        res = conn.execute(text("SELECT nombre, rif, direccion FROM configuracion_edificio WHERE id = 1")).fetchone()
        if res:
            return {"nombre": res[0], "rif": res[1], "direccion": res[2]}
        return {"nombre": "Residencias El Condominio", "rif": "J-12345678-0", "direccion": "Calle Principal"}

def obtener_unidades():
    with engine.connect() as conn:
        df = pd.read_sql("SELECT unidad, alicuota, propietario, telefono FROM unidades ORDER BY unidad ASC", conn)
        return df

def obtener_gastos_mes(mes_anio):
    with engine.connect() as conn:
        df = pd.read_sql("SELECT id, concepto, monto FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'", conn, params={"m": mes_anio})
        return df

def obtener_cuotas_extra():
    with engine.connect() as conn:
        df = pd.read_sql("SELECT id, concepto, monto_total, fecha_emision FROM cuotas_extraordinarias WHERE estatus = 'Activa' ORDER BY id DESC", conn)
        return df

def calcular_balance_unidad(unidad, alicuota, mes_actual):
    with engine.connect() as conn:
        # Gastos comunes acumulados para el mes
        df_gastos = pd.read_sql("SELECT SUM(monto) as total FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'", conn, params={"m": mes_actual})
        total_gastos = df_gastos['total'].iloc[0] if not df_gastos.empty and df_gastos['total'].iloc[0] is not None else 0.0
        monto_cuota_mes = float(total_gastos) * (float(alicuota) / 100.0)

        # Total abonado por mensualidad aprobada
        df_pagos_m = pd.read_sql("""
            SELECT SUM(monto) as total FROM pagos_reportados 
            WHERE apartamento = :u AND mes_anio = :m AND tipo_pago = 'Mensualidad' AND estatus = 'Aprobado'
        """, conn, params={"u": unidad, "m": mes_actual})
        total_pagado_mes = df_pagos_m['total'].iloc[0] if not df_pagos_m.empty and df_pagos_m['total'].iloc[0] is not None else 0.0

        saldo_mes = monto_cuota_mes - float(total_pagado_mes)

        return {
            "total_gastos_edificio": total_gastos,
            "monto_cuota_mes": monto_cuota_mes,
            "total_pagado_mes": total_pagado_mes,
            "saldo_mes": saldo_mes
        }

# ---------------------------------------------------------
# GENERACIÓN DE PDF (REPORTLAB)
# ---------------------------------------------------------
def generar_pdf_recibo(unidad, mes_anio, concepto, monto, referencia, fecha_pago):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()

    config = obtener_config_edificio()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor("#1E3A8A"), alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.gray, alignment=1)
    body_bold = ParagraphStyle('BodyBold', parent=styles['Normal'], fontSize=10, leading=14, fontName="Helvetica-Bold")

    story.append(Paragraph(config["nombre"].upper(), title_style))
    story.append(Paragraph(f"RIF: {config['rif']} | {config['direccion']}", subtitle_style))
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=15))

    story.append(Paragraph("<b>COMPROBANTE OFICIAL DE PAGO / RECIBO</b>", ParagraphStyle('Header', parent=styles['Heading2'], alignment=1, textColor=colors.HexColor("#065F46"))))
    story.append(Spacer(1, 15))

    datos_tabla = [
        [Paragraph("<b>Apartamento / Unidad:</b>", styles['Normal']), Paragraph(str(unidad), body_bold)],
        [Paragraph("<b>Período / Concepto:</b>", styles['Normal']), Paragraph(f"{mes_anio} - {concepto}", styles['Normal'])],
        [Paragraph("<b>Monto Pagado:</b>", styles['Normal']), Paragraph(f"${monto:,.2f}", body_bold)],
        [Paragraph("<b>Método / Referencia:</b>", styles['Normal']), Paragraph(str(referencia), styles['Normal'])],
        [Paragraph("<b>Fecha de Pago:</b>", styles['Normal']), Paragraph(str(fecha_pago), styles['Normal'])],
        [Paragraph("<b>Estatus:</b>", styles['Normal']), Paragraph("<font color='#065F46'><b>PROCESADO Y APROBADO</b></font>", styles['Normal'])],
    ]

    t = Table(datos_tabla, colWidths=[160, 340])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F9FAFB")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t)

    story.append(Spacer(1, 30))
    story.append(Paragraph("<i>Este documento sirve como comprobante oficial de pago para los registros del condominio.</i>", ParagraphStyle('Foot', parent=styles['Italic'], fontSize=8, alignment=1, textColor=colors.gray)))

    doc.build(story)
    buffer.seek(0)
    return buffer

# ---------------------------------------------------------
# AUTENTICACIÓN / AUTORIZACIÓN
# ---------------------------------------------------------
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario"] = ""
    st.session_state["rol"] = ""

def login():
    st.title("🏢 Portal de Administración de Condominio")
    st.subheader("Inicio de Sesión")

    col1, col2 = st.columns([1, 1])
    with col1:
        usuario_in = st.text_input("Usuario (Ej: admin o 1A, 2, PH...):").strip()
        clave_in = st.text_input("Contraseña:", type="password").strip()
        btn_login = st.button("Ingresar")

    if btn_login:
        if engine:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT usuario, rol FROM usuarios WHERE LOWER(usuario) = LOWER(:u) AND clave = :p"), {"u": usuario_in, "p": clave_in}).fetchone()
                if res:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario"] = res[0]
                    st.session_state["rol"] = res[1]
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")

if not st.session_state["autenticado"]:
    login()
    st.stop()

# ---------------------------------------------------------
# BARRA LATERAL (LOGOUT Y DATOS EDIFICIO)
# ---------------------------------------------------------
config_ed = obtener_config_edificio()
st.sidebar.title(f"🏢 {config_ed['nombre']}")
st.sidebar.caption(f"RIF: {config_ed['rif']}")
st.sidebar.write(f"**Usuario:** {st.session_state['usuario']} ({st.session_state['rol'].capitalize()})")

if st.sidebar.button("Cerrar Sesión"):
    st.session_state["autenticado"] = False
    st.session_state["usuario"] = ""
    st.session_state["rol"] = ""
    st.rerun()

# =========================================================
# VISTA: PROPIETARIO
# =========================================================
if st.session_state["rol"] == "propietario":
    unidad_usr = st.session_state["usuario"].upper()
    st.title(f"🏠 Panel Propietario - Unidad {unidad_usr}")

    tab_estado, tab_reportar = st.tabs(["📊 Estado de Cuenta", "💸 Reportar Pago"])

    with tab_estado:
        mes_sel = st.text_input("Consultar Mes/Año (MM-YYYY):", value=datetime.now().strftime("%m-%Y"))
        
        df_unidades = obtener_unidades()
        u_info = df_unidades[df_unidades['unidad'] == unidad_usr]
        alicuota = u_info['alicuota'].iloc[0] if not u_info.empty else 6.0

        bal = calcular_balance_unidad(unidad_usr, alicuota, mes_sel)

        c1, c2, c3 = st.columns(3)
        c1.metric("Gastos Totales Edificio", f"${bal['total_gastos_edificio']:,.2f}")
        c2.metric(f"Tu Cuota ({alicuota}%)", f"${bal['monto_cuota_mes']:,.2f}")
        c3.metric("Saldo Pendiente Mes", f"${bal['saldo_mes']:,.2f}", delta_color="inverse")

        st.markdown("---")
        st.subheader(f"📋 Gastos Comunes de {mes_sel}")
        df_g = obtener_gastos_mes(mes_sel)
        if not df_g.empty:
            st.dataframe(df_g[['concepto', 'monto']], use_container_width=True)
        else:
            st.info("No hay gastos registrados para este mes.")

        st.markdown("---")
        st.subheader("📜 Tus Pagos Reportados")
        with engine.connect() as conn:
            df_mis_pagos = pd.read_sql("""
                SELECT id, tipo_pago, mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus 
                FROM pagos_reportados WHERE apartamento = :u ORDER BY id DESC
            """, conn, params={"u": unidad_usr})
            st.dataframe(df_mis_pagos, use_container_width=True)

    with tab_reportar:
        st.subheader("Formulario de Reporte de Pago")
        with st.form("form_pago_prop"):
            tipo_p = st.selectbox("Tipo de Pago", ["Mensualidad", "Cuota Extraordinaria"])
            mes_p = st.text_input("Mes/Año del Pago (Ej: 08-2026)", value=datetime.now().strftime("%m-%Y"))
            monto_p = st.number_input("Monto Pagado ($)", min_value=0.01, step=5.0)
            metodo_p = st.selectbox("Método de Pago", ["Transferencia", "Pago Móvil", "Zelle", "Efectivo", "Otro"])
            ref_p = st.text_input("Número de Referencia:")
            fecha_p = st.date_input("Fecha de Pago")
            btn_rep = st.form_submit_button("Enviar Reporte de Pago")

        if btn_rep:
            if ref_p and monto_p > 0:
                with engine.connect() as conn:
                    conn.execute(text("""
                        INSERT INTO pagos_reportados (apartamento, tipo_pago, mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus)
                        VALUES (:u, :tp, :m, :mo, :mp, :r, :f, 'Pendiente')
                    """), {"u": unidad_usr, "tp": tipo_p, "m": mes_p, "mo": monto_p, "mp": metodo_p, "r": ref_p, "f": fecha_p})
                    conn.commit()
                st.success("✅ Pago reportado con éxito. El administrador lo validará a la brevedad.")
            else:
                st.error("Por favor ingresa la referencia y un monto válido.")

# =========================================================
# VISTA: ADMINISTRADOR
# =========================================================
elif st.session_state["rol"] == "admin":
    st.title("⚙️ Panel de Administración")

    tab_val, tab_gastos, tab_cuotas, tab_config, tab_rep = st.tabs([
        "✅ Validar Pagos", 
        "💸 Gastos Comunes", 
        "🏗️ Cuotas Extras", 
        "🏢 Edificio y Unidades", 
        "📲 Reportes WhatsApp"
    ])

    # -----------------------------------------------------
    # TAB 1: VALIDAR PAGOS (+ PREVISUALIZACIÓN Y WHATSAPP)
    # -----------------------------------------------------
    with tab_val:
        st.subheader("Pagos Pendientes por Validación")
        with engine.connect() as conn:
            df_pend = pd.read_sql("""
                SELECT id, apartamento, tipo_pago, mes_anio, monto, metodo_pago, referencia, fecha_pago 
                FROM pagos_reportados WHERE estatus = 'Pendiente' ORDER BY id ASC
            """, conn)

        if not df_pend.empty:
            for idx, row in df_pend.iterrows():
                with st.expander(f"📌 Pago #{row['id']} - Apto {row['apartamento']} | ${row['monto']:,.2f} ({row['tipo_pago']})"):
                    st.write(f"**Mes/Año:** {row['mes_anio']} | **Método:** {row['metodo_pago']} | **Ref:** {row['referencia']} | **Fecha:** {row['fecha_pago']}")
                    
                    c_app, c_rej = st.columns(2)
                    if c_app.button(f"Aprobar Pago #{row['id']}", key=f"app_{row['id']}"):
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE pagos_reportados SET estatus = 'Aprobado' WHERE id = :i"), {"i": row['id']})
                            conn.commit()
                        st.success(f"✅ Pago #{row['id']} aprobado exitosamente.")

                        # Buscar teléfono del propietario
                        df_u = obtener_unidades()
                        tlf = df_u[df_u['unidad'] == row['apartamento']]['telefono'].values
                        num_tlf = str(tlf[0]).strip().replace("+", "").replace(" ", "") if len(tlf) > 0 and str(tlf[0]).strip() else ""

                        # Previsualización Recibo Aprobado
                        st.markdown("---")
                        st.markdown("### 📄 Previsualización del Recibo de Confirmación")
                        st.info(f"""
                        **{config_ed['nombre']} - Recibo de Pago Aprobado**
                        - **Unidad:** Apt {row['apartamento']}
                        - **Concepto:** {row['tipo_pago']} ({row['mes_anio']})
                        - **Monto Recibido:** ${row['monto']:,.2f}
                        - **Referencia:** {row['referencia']}
                        - **Estatus:** APROBADO Y REGISTRADO
                        """)

                        # Generar PDF para descarga directa
                        pdf_data = generar_pdf_recibo(row['apartamento'], row['mes_anio'], row['tipo_pago'], float(row['monto']), row['referencia'], row['fecha_pago'])
                        st.download_button(
                            label="📥 Descargar Recibo PDF Oficial",
                            data=pdf_data,
                            file_name=f"Recibo_{row['apartamento']}_{row['mes_anio']}.pdf",
                            mime="application/pdf"
                        )

                        # Enlace de WhatsApp directo al propietario
                        msg_pago = f"🏢 *{config_ed['nombre']}*\n\nHola, estimado propietario del Apt *{row['apartamento']}*.\n\nSu pago ha sido *VALIDADO Y APROBADO* exitosamente:\n📌 *Concepto:* {row['tipo_pago']} ({row['mes_anio']})\n💵 *Monto:* ${row['monto']:,.2f}\n🔢 *Referencia:* {row['referencia']}\n\n¡Gracias por su puntualidad!"
                        msg_pago_enc = urllib.parse.quote(msg_pago)
                        ws_pago_url = f"https://api.whatsapp.com/send?phone={num_tlf}&text={msg_pago_enc}" if num_tlf else f"https://api.whatsapp.com/send?text={msg_pago_enc}"

                        st.markdown(f'<a href="{ws_pago_url}" target="_blank" style="text-decoration:none;"><button style="background-color:#25D366;color:white;border:none;padding:10px 20px;border-radius:5px;font-weight:bold;cursor:pointer;">📲 Notificar Recibo por WhatsApp al Propietario</button></a>', unsafe_allow_html=True)

                    if c_rej.button(f"Rechazar Pago #{row['id']}", key=f"rej_{row['id']}"):
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE pagos_reportados SET estatus = 'Rechazado' WHERE id = :i"), {"i": row['id']})
                            conn.commit()
                        st.warning(f"❌ Pago #{row['id']} rechazado.")
                        st.rerun()
        else:
            st.info("No hay pagos pendientes de aprobación.")

    # -----------------------------------------------------
    # TAB 2: GASTOS COMUNES (+ PREVISUALIZACIÓN Y WHATSAPP)
    # -----------------------------------------------------
    with tab_gastos:
        st.subheader("➕ Registrar Nuevo Gasto Común")
        with st.form("form_nuevo_gasto"):
            mes_gasto = st.text_input("Mes/Año del Gasto (Ej: 08-2026)", value=datetime.now().strftime("%m-%Y"))
            concepto_gasto = st.text_input("Concepto o Descripción del Gasto")
            monto_gasto = st.number_input("Monto Total ($)", min_value=0.01, step=10.0)
            btn_save_gasto = st.form_submit_button("Guardar Gasto")

        if btn_save_gasto:
            if concepto_gasto and monto_gasto > 0:
                with engine.connect() as conn:
                    conn.execute(text("""
                        INSERT INTO gastos (mes_anio, concepto, monto, estatus)
                        VALUES (:m, :c, :mo, 'Aprobado')
                    """), {"m": mes_gasto, "c": concepto_gasto, "mo": monto_gasto})
                    conn.commit()
                st.success("✅ Gasto registrado y procesado correctamente.")

                # Previsualización del Recibo / Notificación
                st.markdown("---")
                st.markdown("### 📄 Previsualización de Notificación de Gasto")
                st.info(f"""
                **{config_ed['nombre']} - Nuevo Gasto Común Cargado**
                - **Período:** {mes_gasto}
                - **Concepto:** {concepto_gasto}
                - **Monto Total:** ${monto_gasto:,.2f}
                """)

                # WhatsApp directo
                msg_g = f"🏢 *{config_ed['nombre']} - NOTIFICACIÓN DE GASTO*\n\nSe ha registrado un nuevo gasto común:\n📌 *Concepto:* {concepto_gasto}\n📅 *Período:* {mes_gasto}\n💵 *Monto Total:* ${monto_gasto:,.2f}\n\nYa se encuentra reflejado en las alícuotas del sistema."
                msg_g_enc = urllib.parse.quote(msg_g)
                ws_g_url = f"https://api.whatsapp.com/send?text={msg_g_enc}"

                st.markdown(f'<a href="{ws_g_url}" target="_blank" style="text-decoration:none;"><button style="background-color:#25D366;color:white;border:none;padding:10px 20px;border-radius:5px;font-weight:bold;cursor:pointer;">📲 Compartir Recibo/Gasto por WhatsApp</button></a>', unsafe_allow_html=True)
            else:
                st.error("Ingresa un concepto y un monto mayor a 0.")

        st.markdown("---")
        st.subheader("📋 Historial de Gastos Registrados")
        mes_filtro_g = st.text_input("Filtrar Gastos por Mes/Año:", value=datetime.now().strftime("%m-%Y"))
        df_g_list = obtener_gastos_mes(mes_filtro_g)
        st.dataframe(df_g_list, use_container_width=True)

    # -----------------------------------------------------
    # TAB 3: CUOTAS EXTRAS (+ PREVISUALIZACIÓN Y WHATSAPP)
    # -----------------------------------------------------
    with tab_cuotas:
        st.subheader("➕ Crear Nueva Cuota Extraordinaria")
        with st.form("form_cuota_extra"):
            concepto_ce = st.text_input("Concepto de la Cuota Extra (Ej: Reparación de Portón/Bomba)")
            monto_ce = st.number_input("Monto Total Requerido ($)", min_value=0.01, step=50.0)
            btn_save_ce = st.form_submit_button("Crear Cuota Extraordinaria")

        if btn_save_ce:
            if concepto_ce and monto_ce > 0:
                with engine.connect() as conn:
                    conn.execute(text("""
                        INSERT INTO cuotas_extraordinarias (concepto, monto_total, estatus)
                        VALUES (:c, :m, 'Activa')
                    """), {"c": concepto_ce, "m": monto_ce})
                    conn.commit()
                st.success("✅ Cuota Extraordinaria creada correctamente.")

                # Previsualización
                st.markdown("---")
                st.markdown("### 📄 Previsualización de Cuota Extraordinaria")
                st.info(f"""
                **{config_ed['nombre']} - Nueva Cuota Extraordinaria**
                - **Proyecto / Concepto:** {concepto_ce}
                - **Monto Total Edificio:** ${monto_ce:,.2f}
                - **Distribución:** Según alícuota correspondiente por apartamento.
                """)

                # WhatsApp directo
                msg_ce = f"🚨 *{config_ed['nombre']} - CUOTA EXTRAORDINARIA*\n\nEstimados propietarios, se aprueba el cobro de cuota extraordinaria:\n📌 *Concepto:* {concepto_ce}\n💵 *Monto Total:* ${monto_ce:,.2f}\n\nCada unidad aportará según su porcentaje de alícuota."
                msg_ce_enc = urllib.parse.quote(msg_ce)
                ws_ce_url = f"https://api.whatsapp.com/send?text={msg_ce_enc}"

                st.markdown(f'<a href="{ws_ce_url}" target="_blank" style="text-decoration:none;"><button style="background-color:#25D366;color:white;border:none;padding:10px 20px;border-radius:5px;font-weight:bold;cursor:pointer;">📲 Anunciar Cuota Extraordinaria por WhatsApp</button></a>', unsafe_allow_html=True)
            else:
                st.error("Ingresa un concepto y un monto válido.")

        st.markdown("---")
        st.subheader("📜 Cuotas Extraordinarias Activas")
        st.dataframe(obtener_cuotas_extra(), use_container_width=True)

    # -----------------------------------------------------
    # TAB 4: CONFIGURACIÓN Y UNIDADES
    # -----------------------------------------------------
    with tab_config:
        st.subheader("⚙️ Configuración del Edificio")
        with st.form("form_cfg_ed"):
            nom_ed = st.text_input("Nombre del Edificio:", value=config_ed['nombre'])
            rif_ed = st.text_input("RIF:", value=config_ed['rif'])
            dir_ed = st.text_area("Dirección:", value=config_ed['direccion'])
            btn_cfg = st.form_submit_button("Actualizar Datos del Edificio")

        if btn_cfg:
            with engine.connect() as conn:
                conn.execute(text("UPDATE configuracion_edificio SET nombre = :n, rif = :r, direccion = :d WHERE id = 1"), {"n": nom_ed, "r": rif_ed, "d": dir_ed})
                conn.commit()
            st.success("✅ Configuración actualizada.")
            st.rerun()

        st.markdown("---")
        st.subheader("👥 Registro de Unidades, Propietarios y Teléfonos")
        df_u_edit = obtener_unidades()

        edited_df = st.data_editor(
            df_u_edit,
            column_config={
                "unidad": st.column_config.TextColumn("Unidad", disabled=True),
                "alicuota": st.column_config.NumberColumn("Alícuota (%)", format="%.2f%%"),
                "propietario": st.column_config.TextColumn("Propietario"),
                "telefono": st.column_config.TextColumn("Teléfono (Ej: 584121234567)")
            },
            hide_index=True,
            use_container_width=True
        )

        if st.button("Guardar Cambios en Unidades"):
            with engine.connect() as conn:
                for idx, r in edited_df.iterrows():
                    conn.execute(text("""
                        UPDATE unidades SET alicuota = :a, propietario = :p, telefono = :t WHERE unidad = :u
                    """), {"a": r['alicuota'], "p": r['propietario'], "t": r['telefono'], "u": r['unidad']})
                conn.commit()
            st.success("✅ Información de unidades guardada correctamente.")

    # -----------------------------------------------------
    # TAB 5: REPORTES GENERALES DE WHATSAPP
    # -----------------------------------------------------
    with tab_rep:
        st.subheader("📲 Reporte de Cobranza Mensual por WhatsApp")
        mes_rep = st.text_input("Generar Reporte para Mes/Año:", value=datetime.now().strftime("%m-%Y"))

        if st.button("Generar Resumen General"):
            df_unids = obtener_unidades()
            resumen_txt = f"🏢 *{config_ed['nombre']}*\n📊 *RESUMEN COBRANZA CONDOMINIO ({mes_rep})*\n\n"

            for idx, r in df_unids.iterrows():
                u = r['unidad']
                ali = r['alicuota']
                b = calcular_balance_unidad(u, ali, mes_rep)
                est_pago = "✅ AL DÍA" if b['saldo_mes'] <= 0 else f"⚠️ DEBE: ${b['saldo_mes']:,.2f}"
                resumen_txt += f"• *Apto {u}*: {est_pago}\n"

            resumen_txt += "\n*Por favor recuerde enviar su comprobante al realizar su pago.*"
            st.text_area("Vista previa del mensaje:", value=resumen_txt, height=250)

            msg_enc_gen = urllib.parse.quote(resumen_txt)
            ws_gen_url = f"https://api.whatsapp.com/send?text={msg_enc_gen}"

            st.markdown(f'<a href="{ws_gen_url}" target="_blank" style="text-decoration:none;"><button style="background-color:#25D366;color:white;border:none;padding:10px 20px;border-radius:5px;font-weight:bold;cursor:pointer;">📲 Enviar Resumen General al Grupo de WhatsApp</button></a>', unsafe_allow_html=True)
