from datetime import date, datetime
import io
import urllib.parse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import pandas as pd
import requests
from sqlalchemy import create_engine, text
import streamlit as st
from PIL import Image

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
    layout="wide",
)

# Actualizado según los requerimientos precisos del edificio:
# 10 apartamentos al 6%, dos al 12%, y el PH al 16% (Total 100%)
UNIDADES_DEFECTO = [
    ("1A", 6.00),
    ("1B", 6.00),
    ("2", 12.00),
    ("3A", 6.00),
    ("3B", 6.00),
    ("4A", 6.00),
    ("4B", 6.00),
    ("5A", 6.00),
    ("5B", 6.00),
    ("6A", 6.00),
    ("6B", 6.00),
    ("7", 12.00),
    ("PH", 16.00),
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
            url, connect_args={"prepare_threshold": None}, pool_pre_ping=True
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
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS configuracion_edificio (
                    id INT PRIMARY KEY DEFAULT 1,
                    nombre VARCHAR(150) NOT NULL,
                    rif VARCHAR(30) NOT NULL,
                    direccion TEXT NOT NULL
                );
            """)
            )

            res_ed = conn.execute(
                text("SELECT COUNT(*) FROM configuracion_edificio")
            ).scalar()
            if res_ed == 0:
                conn.execute(
                    text("""
                        INSERT INTO configuracion_edificio (id, nombre, rif, direccion)
                        VALUES (1, 'Residencias El Condominio', 'J-12345678-0', 'Calle Principal, Edificio Central')
                    """)
                )

            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS unidades (
                    unidad VARCHAR(10) PRIMARY KEY,
                    alicuota NUMERIC(5,2) NOT NULL,
                    propietario VARCHAR(100) DEFAULT 'Sin Asignar',
                    telefono VARCHAR(30) DEFAULT ''
                );
            """)
            )

            try:
                conn.execute(
                    text("ALTER TABLE unidades ADD COLUMN IF NOT EXISTS propietario VARCHAR(100) DEFAULT 'Sin Asignar'")
                )
                conn.execute(
                    text("ALTER TABLE unidades ADD COLUMN IF NOT EXISTS telefono VARCHAR(30) DEFAULT ''")
                )
            except Exception:
                pass

            res_u = conn.execute(text("SELECT COUNT(*) FROM unidades")).scalar()
            if res_u == 0:
                for u, a in UNIDADES_DEFECTO:
                    conn.execute(
                        text(
                            "INSERT INTO unidades (unidad, alicuota, propietario, telefono) VALUES (:u, :a, 'Propietario', '')"
                        ),
                        {"u": u, "a": a},
                    )

            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    usuario VARCHAR(20) PRIMARY KEY,
                    clave VARCHAR(100) NOT NULL,
                    rol VARCHAR(20) NOT NULL
                );
            """)
            )

            admin_pwd = st.secrets.get("ADMIN_PASSWORD", "admin123")
            if not conn.execute(
                text("SELECT usuario FROM usuarios WHERE usuario = 'admin'")
            ).fetchone():
                conn.execute(
                    text(
                        "INSERT INTO usuarios (usuario, clave, rol) VALUES ('admin', :p, 'admin')"
                    ),
                    {"p": admin_pwd},
                )

            for u, _ in UNIDADES_DEFECTO:
                if not conn.execute(
                    text("SELECT usuario FROM usuarios WHERE usuario = :u"), {"u": u}
                ).fetchone():
                    conn.execute(
                        text(
                            "INSERT INTO usuarios (usuario, clave, rol) VALUES (:u, '1234', 'propietario')"
                        ),
                        {"u": u},
                    )

            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS tasa_cambio (
                    fecha DATE PRIMARY KEY,
                    tasa NUMERIC(12, 4) NOT NULL
                );
            """)
            )

            conn.execute(
                text("""
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
            """)
            )

            try:
                conn.execute(
                    text("ALTER TABLE gastos ADD COLUMN IF NOT EXISTS tipo VARCHAR(50) DEFAULT 'Comun'")
                )
                conn.execute(
                    text("ALTER TABLE gastos ADD COLUMN IF NOT EXISTS proveedor VARCHAR(100) DEFAULT 'N/A'")
                )
                conn.execute(
                    text("ALTER TABLE gastos ADD COLUMN IF NOT EXISTS fecha DATE DEFAULT CURRENT_DATE")
                )
            except Exception:
                pass

            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS cargos_individuales (
                    id SERIAL PRIMARY KEY,
                    apartamento VARCHAR(10) NOT NULL,
                    mes_anio VARCHAR(7) NOT NULL,
                    concepto VARCHAR(200) NOT NULL,
                    monto NUMERIC(12,2) NOT NULL,
                    fecha DATE DEFAULT CURRENT_DATE
                );
            """)
            )

            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS cuotas_extraordinarias (
                    id SERIAL PRIMARY KEY,
                    concepto VARCHAR(200) NOT NULL,
                    monto_total NUMERIC(12,2) NOT NULL,
                    fecha_emision DATE DEFAULT CURRENT_DATE,
                    estatus VARCHAR(20) DEFAULT 'Pendiente'
                );
            """)
            )

            # Creación segura de la tabla pagos_reportados sin restricciones nulas conflictivas
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS pagos_reportados (
                    id SERIAL PRIMARY KEY,
                    apartamento VARCHAR(10) NOT NULL,
                    tipo_pago VARCHAR(30) DEFAULT 'Mensualidad',
                    mes_anio VARCHAR(7),
                    monto_original NUMERIC(12, 2) NOT NULL,
                    moneda VARCHAR(10) DEFAULT 'USD',
                    tasa_aplicada NUMERIC(12, 4) DEFAULT 1.0,
                    monto_usd NUMERIC(12, 2) NOT NULL,
                    metodo_pago VARCHAR(50) NOT NULL,
                    referencia VARCHAR(100) NOT NULL,
                    fecha_pago DATE NOT NULL,
                    estatus VARCHAR(20) DEFAULT 'Pendiente',
                    fecha_reporte TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            )

            try:
                # Si la tabla ya existía con la columna antigua 'monto' obligatoria, se la quitamos para evitar el NotNullViolation
                conn.execute(
                    text("ALTER TABLE pagos_reportados ALTER COLUMN monto DROP NOT NULL;")
                )
            except Exception:
                pass

            try:
                conn.execute(
                    text("ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS monto_original NUMERIC(12,2) DEFAULT 0")
                )
                conn.execute(
                    text("ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS moneda VARCHAR(10) DEFAULT 'USD'")
                )
                conn.execute(
                    text("ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS tasa_aplicada NUMERIC(12,4) DEFAULT 1.0")
                )
                conn.execute(
                    text("ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS monto_usd NUMERIC(12,2) DEFAULT 0")
                )
            except Exception:
                pass

            conn.commit()
    except Exception as e:
        print(f"Error inicializando tablas: {e}")
        pass


inicializar_tablas()

# -----------------------------------------------------------------------------
# FUNCIONES AUTOMÁTICAS DE TASA Y AUXILIARES
# -----------------------------------------------------------------------------
def verificar_y_actualizar_tasa_hoy(eng):
    hoy = date.today()
    if not eng:
        return 36.00
    try:
        with eng.connect() as conn:
            tasa_existente = conn.execute(
                text("SELECT tasa FROM tasa_cambio WHERE fecha = :f"), {"f": hoy}
            ).scalar()

            if tasa_existente:
                return float(tasa_existente)

            response = requests.get(
                "https://pydolarvenezuela-api.vercel.app/api/v1/dollar/bcv",
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                tasa_bcv = float(
                    data.get("price", data.get("sources", {}).get("bcv", {}).get("price", 0.0))
                )

                if tasa_bcv > 0:
                    conn.execute(
                        text("""
                            INSERT INTO tasa_cambio (fecha, tasa)
                            VALUES (:f, :t)
                            ON CONFLICT (fecha) DO UPDATE SET tasa = EXCLUDED.tasa
                        """),
                        {"f": hoy, "t": tasa_bcv},
                    )
                    conn.commit()
                    return tasa_bcv

    except Exception:
        pass

    try:
        with eng.connect() as conn:
            ultima_tasa = conn.execute(
                text("SELECT tasa FROM tasa_cambio ORDER BY fecha DESC LIMIT 1")
            ).scalar()
            if ultima_tasa:
                return float(ultima_tasa)
    except Exception:
        pass

    return 36.00


def obtener_datos_edificio():
    if not engine:
        return {
            "nombre": "Residencias Condominio",
            "rif": "J-00000000-0",
            "direccion": "Ciudad",
        }
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT nombre, rif, direccion FROM configuracion_edificio WHERE"
                    " id = 1"
                )
            ).fetchone()
            if row:
                return {"nombre": row[0], "rif": row[1], "direccion": row[2]}
    except Exception:
        pass
    return {
        "nombre": "Residencias Condominio",
        "rif": "J-00000000-0",
        "direccion": "Ciudad",
    }


def obtener_unidades_df():
    if not engine:
        return pd.DataFrame(UNIDADES_DEFECTO, columns=["unidad", "alicuota"])
    try:
        with engine.connect() as conn:
            return pd.read_sql(
                text(
                    "SELECT unidad, alicuota, propietario, telefono FROM unidades"
                    " ORDER BY unidad ASC"
                ),
                conn,
            )
    except Exception:
        return pd.DataFrame(UNIDADES_DEFECTO, columns=["unidad", "alicuota"])


def obtener_tasa_por_fecha(fecha_buscada):
    if not engine:
        return 1.0
    try:
        with engine.connect() as conn:
            res = conn.execute(
                text("SELECT tasa FROM tasa_cambio WHERE fecha = :f"),
                {"f": fecha_buscada},
            ).scalar()
            if res:
                return float(res)

            res_cercana = conn.execute(
                text(
                    "SELECT tasa FROM tasa_cambio WHERE fecha <= :f ORDER BY fecha"
                    " DESC LIMIT 1"
                ),
                {"f": fecha_buscada},
            ).scalar()
            if res_cercana:
                return float(res_cercana)
    except Exception:
        pass
    return 1.0


def generar_enlace_whatsapp(telefono, mensaje):
    num_limpio = "".join(filter(str.isdigit, str(telefono or "")))
    msg_enc = urllib.parse.quote(mensaje)
    if num_limpio:
        return f"https://wa.me/{num_limpio}?text={msg_enc}"
    return f"https://wa.me/?text={msg_enc}"


def generar_pdf_recibo(apt, periodo, total_cuota, detalles_gastos, alicuota):
    datos_ed = obtener_datos_edificio()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    story = []

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        alignment=1,
        textColor=colors.HexColor("#1E3A8A"),
    )

    story.append(Paragraph(f"<b>{datos_ed['nombre']}</b>", title_style))
    story.append(
        Paragraph(
            f"RIF: {datos_ed['rif']} | {datos_ed['direccion']}", styles["Normal"]
        )
    )
    story.append(Spacer(1, 15))

    story.append(
        Paragraph(f"<b>AVISO DE COBRO - PERIODO: {periodo}</b>", styles["Heading2"])
    )
    story.append(
        Paragraph(
            f"<b>Unidad:</b> {apt} | <b>Alícuota Aplicada:</b> {alicuota}%",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 15))

    tabla_datos = [["Concepto / Descripción", "Monto Base ($)", "Cuota Parte ($)"]]
    for item in detalles_gastos:
        tabla_datos.append(
            [item["concepto"], f"${item['base']:,.2f}", f"${item['monto']:,.2f}"]
        )

    tabla_datos.append(["TOTAL A PAGAR", "", f"${total_cuota:,.2f}"])

    t = Table(tabla_datos, colWidths=[280, 110, 110])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2E8F0")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ])
    )

    story.append(t)
    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "Por favor realice su pago y repórtelo en la plataforma indicando su"
            " referencia.",
            styles["Italic"],
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer


def renderizar_recibos():
    datos_ed = obtener_datos_edificio()

    st.subheader("🚨 Recibos y Envíos a WhatsApp")
    
    mes_recibo_gral = st.text_input(
        "Periodo del Recibo (AAAA-MM):",
        value=obtener_mes_anterior(),
        key="periodo_recibo_general_input",
    )

    try:
        with engine.connect() as conn:
            gastos_mes_df = pd.read_sql(
                text(
                    "SELECT concepto, monto FROM gastos WHERE mes_anio = :m AND (estatus = 'Aprobado' OR estatus = 'APROBADO')"
                ),
                conn,
                params={"m": mes_recibo_gral},
            )
            total_gastos_comunes = (
                gastos_mes_df["monto"].sum() if not gastos_mes_df.empty else 0.0
            )

            unidades_df = pd.read_sql(
                text(
                    "SELECT unidad, alicuota, propietario, telefono FROM unidades ORDER BY unidad ASC"
                ),
                conn,
            )

            cargos_df = pd.read_sql(
                text(
                    "SELECT apartamento, SUM(monto) as total_cargos FROM cargos_individuales WHERE mes_anio = :m GROUP BY apartamento"
                ),
                conn,
                params={"m": mes_recibo_gral},
            )

        cargos_dict = (
            dict(zip(cargos_df["apartamento"], cargos_df["total_cargos"]))
            if not cargos_df.empty
            else {}
        )

        if gastos_mes_df.empty:
            st.warning(
                f"⚠️ No se encontraron gastos aprobados para el periodo {mes_recibo_gral}."
            )
        else:
            st.success(
                f"✅ Se cargaron {len(gastos_mes_df)} gastos comunes para el periodo {mes_recibo_gral}."
            )

        st.markdown("### 👤 Recibos Individuales por Propietario (WhatsApp)")
        for _, u_row in unidades_df.iterrows():
            u_cod = u_row["unidad"]
            u_prop = u_row["propietario"]
            u_tel = u_row["telefono"]
            u_alic = float(u_row["alicuota"])
            u_alic_decimal = u_alic / 100.0

            cuota_comun_apt = float(total_gastos_comunes) * u_alic_decimal
            cargos_apt = float(cargos_dict.get(u_cod, 0.0))
            total_apt = cuota_comun_apt + cargos_apt

            with st.expander(
                f"🔹 Apt {u_cod} - {u_prop} (Total: ${total_apt:,.2f})"
            ):
                msg_ind = f"*{datos_ed['nombre']}*\n"
                msg_ind += f"*AVISO DE COBRO - {mes_recibo_gral}*\n"
                msg_ind += f"Estimado(a) *{u_prop}* (Unidad {u_cod})\n"
                msg_ind += f"Alícuota: {u_alic:.1f}%\n"
                msg_ind += f"----------------------------------------\n"
                msg_ind += f"*Desglose de Gastos Comunes:*\n"

                if not gastos_mes_df.empty:
                    for _, g_row in gastos_mes_df.iterrows():
                        g_concepto = g_row["concepto"]
                        g_monto_total = float(g_row["monto"])
                        g_monto_apto = g_monto_total * u_alic_decimal
                        msg_ind += f"• {g_concepto}: ${g_monto_apto:,.2f}\n"
                else:
                    msg_ind += "• (Sin gastos comunes registrados)\n"

                msg_ind += f"----------------------------------------\n"
                msg_ind += f"• Subtotal Cuota Común: ${cuota_comun_apt:,.2f}\n"

                if cargos_apt > 0:
                    msg_ind += f"• Cargos Extras / No Comunes: ${cargos_apt:,.2f}\n"

                msg_ind += f"----------------------------------------\n"
                msg_ind += f"*TOTAL A PAGAR: ${total_apt:,.2f}*\n\n"
                msg_ind += "Por favor realizar su pago y reportarlo en la plataforma. ¡Gracias!"

                st.text_area(
                    f"Mensaje WhatsApp Apt {u_cod}:",
                    msg_ind,
                    height=200,
                    key=f"txt_msg_{u_cod}",
                )
                enlace_wa_apt = generar_enlace_whatsapp(u_tel, msg_ind)
                st.link_button(
                    f"📲 Enviar WhatsApp a Apt {u_cod} ({u_tel or 'Sin teléfono'})",
                    enlace_wa_apt,
                    use_container_width=True,
                )

    except Exception as e:
        st.error(f"Error generando recibos: {e}")


# =============================================================================
# CONTROL DE VISTAS PRINCIPAL (LOGIN)
# =============================================================================

if not st.session_state.get("usuario_logueado"):
    st.markdown("<h2 style='text-align: center;'>🔒 Portal de Acceso</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Ingresa tus credenciales para continuar.</p>", unsafe_allow_html=True)

    if "error_conexion" in locals() and error_conexion:
        st.error(f"⚠️ Error de conexión: {error_conexion}")

    with st.form("form_login"):
        usuario_input = st.text_input("Usuario (ej. 1A, PH o admin)").strip()
        clave_input = st.text_input("Contraseña", type="password").strip()
        bot_login = st.form_submit_button("Ingresar", type="primary", use_container_width=True)

        if bot_login:
            if not usuario_input or not clave_input:
                st.error("Por favor completa los campos.")
            elif "engine" not in locals() or not engine:
                st.error("Base de datos no disponible.")
            else:
                try:
                    with engine.connect() as conn:
                        row = conn.execute(
                            text("SELECT usuario, clave, rol FROM usuarios WHERE LOWER(usuario) = LOWER(:u)"),
                            {"u": usuario_input},
                        ).fetchone()

                    if row and row[1] == clave_input:
                        st.session_state.usuario_logueado = row[0]
                        st.session_state.rol_logueado = row[2]
                        st.rerun()
                    else:
                        st.error("❌ Credenciales incorrectas.")
                except Exception as e:
                    st.error(f"Error al ingresar: {e}")

    st.stop()

# =============================================================================
# ZONA DE USUARIOS AUTENTICADOS (BARRA LATERAL)
# =============================================================================
rol_actual = st.session_state.get("rol_logueado", "propietario")
usuario_actual = st.session_state.get("usuario_logueado", "")

st.sidebar.markdown(f"👤 **Usuario:** {usuario_actual}")
st.sidebar.markdown(f"🔑 **Rol:** {rol_actual.capitalize()}")
st.sidebar.markdown("---")

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state.pop("usuario_logueado", None)
    st.session_state.pop("rol_logueado", None)
    st.rerun()

st.sidebar.markdown("---")

# =============================================================================
# RUTEO SEGÚN EL ROL: ADMINISTRADOR VS. PROPIETARIO
# =============================================================================

if rol_actual == "admin":
    # -------------------------------------------------------------------------
    # PANEL EXCLUSIVO DEL ADMINISTRADOR (9 PESTAÑAS)
    # -------------------------------------------------------------------------
    st.markdown("### 👑 Panel de Control de Administración")

    t1, t2, t3, t4, t5, t6, t7, t8, t9, t10 = st.tabs([
        "📊 Gastos Comunes",
        "🛠️ Gastos No Comunes",
        "⭐ Cuotas Extras",
        "💱 Tasas de Cambio",
        "✅ Validar Pagos",
        "🏢 Alícuotas y Unidades",
        "🚨 Morosidad y Recibos",
        "⚙️ Datos Edificio",
        "💱 Conciliación de Pagos",
        "📊 Reporte y Cierre anual de Gestion", 
    ])
    
    with t1:
        st.subheader("➕ Cargar Nuevo Gasto Común")
        with st.form("form_gasto"):
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                mes = st.text_input(
                    "Mes / Año del Gasto (AAAA-MM)", value=obtener_mes_anterior()
                )
                concepto = st.text_input("Descripción del Gasto Común")
            with col_g2:
                proveedor = st.text_input("Proveedor", value="N/A")
                monto = st.number_input("Monto Total ($)", min_value=0.01, step=0.01)

            btn = st.form_submit_button(
                "Cargar para Previsualizar/Aprobar", type="primary"
            )

            if btn and concepto:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                                INSERT INTO gastos (periodo, mes_anio, concepto, monto, estatus, fecha, tipo, proveedor) 
                                VALUES (:m, :m, :c, :mo, 'Pendiente', CURRENT_DATE, 'Comun', :p)
                            """),
                            {
                                "m": mes,
                                "c": concepto,
                                "mo": monto,
                                "p": proveedor if proveedor.strip() else "N/A",
                            },
                        )
                        conn.commit()
                    st.success("Gasto guardado en estado pendiente de aprobación.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error registrando gasto: {e}")

        st.write("---")
        st.subheader("🔍 Previsualizar y Aprobar Gastos Comunes")
        
        mes_filtro = st.text_input(
            "Filtrar gastos por periodo (AAAA-MM):",
            value=obtener_mes_anterior(),
            key="filtro_gastos_admin",
        )

        try:
            with engine.connect() as conn:
                df_gastos_pendientes = pd.read_sql(
                    text(
                        "SELECT id, concepto, monto, estatus, mes_anio FROM gastos WHERE mes_anio = :m ORDER BY id DESC"
                    ),
                    conn,
                    params={"m": mes_filtro},
                )

            if df_gastos_pendientes.empty:
                st.info(f"No hay gastos registrados para el periodo {mes_filtro}.")
            else:
                for _, r_gasto in df_gastos_pendientes.iterrows():
                    c_detalles, c_acciones = st.columns([3, 2])
                    with c_detalles:
                        badge_estatus = (
                            "🟡 Pendiente"
                            if r_gasto["estatus"] == "Pendiente"
                            else "🟢 Aprobado"
                        )
                        st.markdown(
                            f"**Concepto:** {r_gasto['concepto']} | **Monto:** ${float(r_gasto['monto']):,.2f} | **Estatus:** {badge_estatus}"
                        )

                    with c_acciones:
                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            if r_gasto["estatus"] == "Pendiente":
                                if st.button(
                                    "✅ Aprobar",
                                    key=f"app_gasto_{r_gasto['id']}",
                                    type="primary",
                                ):
                                    with engine.connect() as conn:
                                        conn.execute(
                                            text("UPDATE gastos SET estatus = 'Aprobado' WHERE id = :id"),
                                            {"id": r_gasto["id"]},
                                        )
                                        conn.commit()
                                    st.success("Gasto aprobado.")
                                    st.rerun()
                        with btn_col2:
                            if st.button(
                                "❌ Eliminar",
                                key=f"del_gasto_{r_gasto['id']}",
                                type="secondary",
                            ):
                                with engine.connect() as conn:
                                    conn.execute(
                                        text("DELETE FROM gastos WHERE id = :id"),
                                        {"id": r_gasto["id"]},
                                    )
                                    conn.commit()
                                st.success("Gasto eliminado.")
                                st.rerun()
        except Exception as e:
            st.error(f"Error cargando gastos: {e}")

    with t2:
        st.subheader("🛠️ Gestión de Gastos No Comunes o Individuales")
        with st.form("form_cargo_ind"):
            col_ci1, col_ci2 = st.columns(2)
            with col_ci1:
                mes_ci = st.text_input("Periodo (AAAA-MM)", value=obtener_mes_anterior(), key="mes_ci_in")
                apt_ci = st.selectbox("Apartamento / Unidad", [u[0] for u in UNIDADES_DEFECTO])
            with col_ci2:
                concepto_ci = st.text_input("Concepto (ej. Reparación de tubería específica)")
                monto_ci = st.number_input("Monto ($)", min_value=0.01, step=0.01, key="monto_ci_in")
            
            btn_ci = st.form_submit_button("Registrar Cargo Individual", type="primary")
            if btn_ci:
                if not concepto_ci.strip():
                    st.error("Por favor ingresa un concepto.")
                else:
                    try:
                        with engine.connect() as conn:
                            conn.execute(
                                text("""
                                    INSERT INTO cargos_individuales (apartamento, mes_anio, concepto, monto, fecha)
                                    VALUES (:apt, :m, :c, :mo, CURRENT_DATE)
                                """),
                                {"apt": apt_ci, "m": mes_ci, "c": concepto_ci, "mo": monto_ci},
                            )
                            conn.commit()
                        st.success(f"Cargo registrado exitosamente al apartamento {apt_ci}.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al registrar cargo: {e}")

    with t3:
        st.subheader("⭐ Gestión y Registro de Cuotas Extraordinarias")
        with st.form("form_cuota_extra"):
            col_ce1, col_ce2 = st.columns(2)
            with col_ce1:
                concepto_ce = st.text_input("Concepto de la Cuota Extraordinaria")
            with col_ce2:
                monto_ce = st.number_input("Monto Total ($)", min_value=0.01, step=0.01)
            
            btn_crear_ce = st.form_submit_button("Crear Cuota Extraordinaria", type="primary")
            if btn_crear_ce:
                if not concepto_ce.strip():
                    st.error("Debes ingresar un concepto para la cuota extraordinaria.")
                else:
                    try:
                        with engine.connect() as conn:
                            conn.execute(
                                text("""
                                    INSERT INTO cuotas_extraordinarias (concepto, monto_total, fecha_emision, estatus)
                                    VALUES (:c, :m, CURRENT_DATE, 'Pendiente')
                                """),
                                {"c": concepto_ce, "m": monto_ce}
                            )
                            conn.commit()
                        st.success("✅ Cuota extraordinaria creada exitosamente en estado pendiente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al registrar la cuota extraordinaria: {e}")

        st.write("---")
        st.subheader("📋 Listado y Control de Cuotas Extraordinarias")
        try:
            with engine.connect() as conn:
                df_cuotas_admin = pd.read_sql(
                    text("SELECT id, concepto, monto_total, fecha_emision, estatus FROM cuotas_extraordinarias ORDER BY id DESC"),
                    conn
                )
                df_unidades_ce = pd.read_sql("SELECT unidad, propietario, alicuota FROM unidades", conn)

            if df_cuotas_admin.empty:
                st.info("No hay cuotas extraordinarias registradas.")
            else:
                for _, r_ce in df_cuotas_admin.iterrows():
                    id_ce = r_ce['id']
                    concepto_txt = r_ce['concepto']
                    monto_total_ce = float(r_ce['monto_total'])
                    estatus_ce = r_ce['estatus']
                    
                    badge_ce = "🟡 Pendiente" if estatus_ce == "Pendiente" else "🟢 Aprobada"
                    
                    with st.expander(f"Cuota #{id_ce} | {concepto_txt} - ${monto_total_ce:,.2f} ({badge_ce})"):
                        col_det1, col_det2 = st.columns(2)
                        with col_det1:
                            st.markdown(f"**Concepto:** {concepto_txt}")
                            st.markdown(f"**Monto Total:** ${monto_total_ce:,.2f}")
                            st.markdown(f"**Fecha de Emisión:** {r_ce['fecha_emision']}")
                        with col_det2:
                            st.markdown(f"**Estatus:** {badge_ce}")

                        # Botones de acción (Aprobar / Eliminar)
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if estatus_ce == "Pendiente":
                                if st.button("✅ Aprobar Cuota", key=f"app_ce_{id_ce}", type="primary"):
                                    with engine.connect() as conn:
                                        conn.execute(
                                            text("UPDATE cuotas_extraordinarias SET estatus = 'Aprobada' WHERE id = :id"),
                                            {"id": id_ce}
                                        )
                                        conn.commit()
                                    st.success("Cuota extraordinaria aprobada.")
                                    st.rerun()
                        with col_btn2:
                            if st.button("🗑️ Eliminar Cuota", key=f"del_ce_{id_ce}", type="secondary"):
                                try:
                                    with engine.connect() as conn:
                                        conn.execute(
                                            text("DELETE FROM cuotas_extraordinarias WHERE id = :id"),
                                            {"id": id_ce}
                                        )
                                        conn.commit()
                                    st.error("Cuota extraordinaria eliminada correctamente.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al eliminar: {e}")

                        st.markdown("---")
                        st.subheader("📢 Mensajes para WhatsApp (Distribución por Alícuotas)")
                        
                        # Cálculo automático por alícuotas
                        if not df_unidades_ce.empty:
                            lineas_detalle = []
                            for _, u in df_unidades_ce.iterrows():
                                alic = float(u['alicuota'])
                                monto_parte = monto_total_ce * (alic / 100.0)
                                lineas_detalle.append(f"• Apto {u['unidad']} ({alic}%): ${monto_parte:,.2f}")
                            
                            detalle_str = "\n".join(lineas_detalle)
                            
                            # 1. Mensaje para el Grupo General
                            msg_grupo = (
                                f"📢 *AVISO DE CUOTA EXTRAORDINARIA* 📢\n\n"
                                f"Estimados propietarios, se ha emitido una cuota extraordinaria con los siguientes detalles:\n\n"
                                f"📌 *Concepto:* {concepto_txt}\n"
                                f"💵 *Monto Total:* ${monto_total_ce:,.2f}\n\n"
                                f"📋 *Distribución por alícuotas:*\n{detalle_str}\n\n"
                                f"Por favor realizar su pago correspondiente y reportarlo por la app. ¡Gracias!"
                            )
                            
                            st.markdown("**1️⃣ Mensaje para el Grupo General de WhatsApp:**")
                            st.code(msg_grupo, language="markdown")
                            
                            st.markdown("---")
                            st.markdown("**2️⃣ Mensaje Individualizado por Propietario:**")
                            apto_w = st.selectbox("Seleccione apartamento para copiar su monto:", df_unidades_ce['unidad'].tolist(), key=f"sel_w_ce_{id_ce}")
                            
                            if apto_w:
                                row_sel = df_unidades_ce[df_unidades_ce['unidad'] == apto_w].iloc[0]
                                alic_sel = float(row_sel['alicuota'])
                                monto_sel = monto_total_ce * (alic_sel / 100.0)
                                
                                msg_individual = (
                                    f"Hola {row_sel['propietario']}, le escribimos de la administración de las Residencias.\n\n"
                                    f"Le recordamos su cuota extraordinaria:\n"
    								f"📌 *Concepto:* {concepto_txt}\n"
                                    f"🏠 *Unidad:* {apto_w} (Alícuota {alic_sel}%)\n"
                                    f"💵 *Monto a pagar:* **${monto_sel:,.2f}**\n\n"
                                    f"Agradecemos reportar su pago a la brevedad. ¡Saludos!"
                                )
                                st.code(msg_individual, language="markdown")
                        else:
                            st.warning("No hay unidades configuradas para hacer el cálculo.")

        except Exception as e:
            st.error(f"Error listando cuotas extraordinarias: {e}")

    with t4:
        st.subheader("💱 Tasas de Cambio (BCV)")
        tasa_actual_auto = verificar_y_actualizar_tasa_hoy(engine)
        st.info(f"💡 Tasa BCV actual detectada / registrada para hoy: **{tasa_actual_auto:,.4f} VES/USD**")

        with st.form("form_tasa"):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                fecha_tasa = st.date_input("Fecha de la Tasa", value=date.today())
            with col_t2:
                valor_tasa = st.number_input("Valor Tasa (Bolívares por Dólar)", min_value=0.01, value=float(tasa_actual_auto), step=0.01)
            
            btn_tasa = st.form_submit_button("Guardar / Actualizar Tasa", type="primary")
            if btn_tasa:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                                INSERT INTO tasa_cambio (fecha, tasa) VALUES (:f, :t)
                                ON CONFLICT (fecha) DO UPDATE SET tasa = EXCLUDED.tasa
                            """),
                            {"f": fecha_tasa, "t": valor_tasa},
                        )
                        conn.commit()
                    st.success("Tasa de cambio guardada exitosamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error guardando tasa: {e}")

    with t5:
        st.subheader("✅ Validar Pagos Reportados por Propietarios")
        try:
            with engine.connect() as conn:
                df_pagos_rep = pd.read_sql(
                    text("SELECT id, apartamento, tipo_pago, mes_anio, monto_original, moneda, tasa_aplicada, monto_usd, metodo_pago, referencia, fecha_pago, estatus FROM pagos_reportados ORDER BY id DESC"),
                    conn
                )

            if df_pagos_rep.empty:
                st.info("No hay pagos reportados en la plataforma.")
            else:
                for _, p_row in df_pagos_rep.iterrows():
                    badge_p = "🟡 Pendiente" if p_row["estatus"] == "Pendiente" else ("🟢 Aprobado" if p_row["estatus"] == "Aprobado" else "🔴 Rechazado")
                    with st.expander(f"Pago #{p_row['id']} - Apt {p_row['apartamento']} - ${float(p_row['monto_usd']):,.2f} USD ({badge_p})"):
                        st.markdown(f"""
                        - **Tipo:** {p_row['tipo_pago']} ({p_row['mes_anio']})
                        - **Monto Original:** {float(p_row['monto_original']):,.2f} {p_row['moneda']}
                        - **Método:** {p_row['metodo_pago']} | **Referencia:** {p_row['referencia']}
                        - **Fecha de Pago:** {p_row['fecha_pago']}
                        """)

                        # Si está pendiente, permitimos validar o corregir la tasa si vino mal de antes
                        if p_row["estatus"] == "Pendiente":
                            st.markdown("---")
                            st.write("🔧 **Verificación y Ajuste de Tasa:**")
                            
                            # Inputs para verificar/corregir antes de aprobar
                            tasa_actual_reg = float(p_row['tasa_aplicada'])
                            monto_orig = float(p_row['monto_original'])
                            moneda_pago = p_row['moneda']
                            
                            col_ed1, col_ed2 = st.columns(2)
                            with col_ed1:
                                nueva_tasa_aprob = st.number_input("Tasa a aplicar:", value=tasa_actual_reg, min_value=0.01, step=0.01, key=f"tasa_edit_{p_row['id']}")
                            with col_ed2:
                                # Recalcular USD en vivo según la tasa corregida
                                nuevo_monto_usd = monto_orig / nueva_tasa_aprob if moneda_pago == "VES" else monto_orig
                                st.metric("Monto Final en USD:", f"${nuevo_monto_usd:,.2f}")

                            col_pa1, col_pa2 = st.columns(2)
                            with col_pa1:
                                if st.button("✅ Aprobar con esta Tasa", key=f"app_pago_{p_row['id']}"):
                                    with engine.connect() as conn:
                                        conn.execute(
                                            text("""
                                                UPDATE pagos_reportados 
                                                SET tasa_aplicada = :ta, monto_usd = :musd, estatus = 'Aprobado' 
                                                WHERE id = :id
                                            """),
                                            {
                                                "ta": nueva_tasa_aprob,
                                                "musd": nuevo_monto_usd,
                                                "id": p_row['id']
                                            }
                                        )
                                        conn.commit()
                                    st.success("¡Pago aprobado y actualizado con éxito!")
                                    st.rerun()
                            with col_pa2:
                                if st.button("❌ Rechazar Pago", key=f"rec_pago_{p_row['id']}"):
                                    with engine.connect() as conn:
                                        conn.execute(
                                            text("UPDATE pagos_reportados SET estatus = 'Rechazado' WHERE id = :id"),
                                            {"id": p_row['id']}
                                        )
                                        conn.commit()
                                    st.warning("Pago rechazado.")
                                    st.rerun()
        except Exception as e:
            st.error(f"Error cargando pagos reportados: {e}")

    with t6:
        st.subheader("🏢 Configuración de Alícuotas y Propietarios")
        st.info("Distribución oficial del edificio: 10 unidades al 6%, dos unidades al 12%, y el PH al 16% (Total 100%).")
        
        df_unidades = obtener_unidades_df()
        with st.form("form_editar_unidades"):
            updated_data = []
            for idx, row in df_unidades.iterrows():
                st.markdown(f"**Unidad: {row['unidad']}**")
                col_u1, col_u2, col_u3 = st.columns(3)
                with col_u1:
                    prop_val = st.text_input(f"Propietario {row['unidad']}", value=row['propietario'], key=f"prop_{row['unidad']}")
                with col_u2:
                    tel_val = st.text_input(f"Teléfono {row['unidad']}", value=row['telefono'], key=f"tel_{row['unidad']}")
                with col_u3:
                    alic_val = st.number_input(f"Alícuota % {row['unidad']}", value=float(row['alicuota']), step=0.01, key=f"alic_{row['unidad']}")
                
                updated_data.append({"unidad": row['unidad'], "propietario": prop_val, "telefono": tel_val, "alicuota": alic_val})
                st.markdown("---")

            btn_guardar_unidades = st.form_submit_button("Guardar Cambios de Unidades", type="primary")
            if btn_guardar_unidades:
                try:
                    with engine.connect() as conn:
                        for item in updated_data:
                            conn.execute(
                                text("""
                                    UPDATE unidades SET propietario = :p, telefono = :t, alicuota = :a
                                    WHERE unidad = :u
                                """),
                                {"p": item["propietario"], "t": item["telefono"], "a": item["alicuota"], "u": item["unidad"]}
                            )
                        conn.commit()
                    st.success("Unidades actualizadas correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error actualizando unidades: {e}")

        st.markdown("---")
        
        # =====================================================================
        # 📄 HISTORIAL Y ESTADO DE CUENTA DETALLADO POR PROPIETARIO
        # =====================================================================
        with st.expander("👤 Consultar Historial y Estado de Cuenta Detallado", expanded=True):
            df_lista_units = obtener_unidades_df()
            lista_apartamentos = df_lista_units['unidad'].tolist() if not df_lista_units.empty else []
            
            apto_seleccionado = st.selectbox("Seleccione el Apartamento / Unidad:", lista_apartamentos, key="select_edo_cta_admin")
            
            if st.button("Generar Historial Financiero", key="btn_edo_cuenta", type="primary"):
                try:
                    with engine.connect() as conn:
                        # 1. Obtener la alícuota y propietario de la unidad seleccionada
                        res_unid = conn.execute(
                            text("SELECT alicuota, propietario FROM unidades WHERE unidad = :u"),
                            {"u": apto_seleccionado}
                        ).fetchone()
                        
                        alicuota_pct = float(res_unid.alicuota) if res_unid and res_unid.alicuota else 0.0
                        nombre_prop = res_unid.propietario if res_unid else "N/D"

                        # 2. Obtener todos los pagos aprobados de esta unidad incluyendo moneda, monto original, tasa y detalles
                        df_pagos_aprobados = pd.read_sql(
                            text("""
                                SELECT mes_anio, monto_original, moneda, tasa_aplicada, monto_usd, referencia, fecha_pago, metodo_pago 
                                FROM pagos_reportados 
                                WHERE apartamento = :apt AND estatus = 'Aprobado'
                            """),
                            conn,
                            params={"apt": apto_seleccionado}
                        )
                        
                        # 3. Obtener todos los gastos aprobados ordenados por mes
                        df_gastos_mes = pd.read_sql(
                            text("SELECT mes_anio, SUM(monto) as total_gastos FROM gastos WHERE estatus = 'Aprobado' GROUP BY mes_anio ORDER BY mes_anio"),
                            conn
                        )

                    st.markdown(f"### 📄 Estado de Cuenta Histórico: Unidad **{apto_seleccionado}** ({nombre_prop})")
                    st.info(f"📌 Alícuota asignada: **{alicuota_pct}%**")

                    if not df_gastos_mes.empty:
                        reporte_global = []
                        saldo_acumulado = 0.0

                        for _, row_g in df_gastos_mes.iterrows():
                            mes = row_g["mes_anio"]
                            gasto_total = float(row_g["total_gastos"])
                            cuota_a_cobrar = gasto_total * (alicuota_pct / 100.0)

                            # Buscar pagos aprobados para este mes exacto
                            pago_mes = df_pagos_aprobados[df_pagos_aprobados["mes_anio"] == mes] if not df_pagos_aprobados.empty else pd.DataFrame()
                            
                            monto_pagado_usd = 0.0
                            detalle_pago_str = "Sin pago"
                            tasa_str = "N/A"
                            referencia = "N/A"
                            fecha_pago = "Pendiente"
                            
                            if not pago_mes.empty:
                                monto_pagado_usd = float(pago_mes["monto_usd"].sum())
                                
                                detalles_origen = []
                                tasas_usadas = []
                                refs = []
                                fechas = []
                                
                                for _, p_row in pago_mes.iterrows():
                                    mo = float(p_row["monto_original"])
                                    mon = p_row["moneda"]
                                    ta = float(p_row["tasa_aplicada"])
                                    detalles_origen.append(f"{mo:,.2f} {mon}")
                                    if mon == "VES":
                                        tasas_usadas.append(f"{ta:,.4f}")
                                    refs.append(str(p_row["referencia"]))
                                    fechas.append(str(p_row["fecha_pago"]))
                                
                                detalle_pago_str = " + ".join(detalles_origen)
                                tasa_str = ", ".join(tasas_usadas) if tasas_usadas else "USD Directo"
                                referencia = ", ".join(refs)
                                fecha_pago = ", ".join(fechas)

                            # Cálculo del balance del mes (Pagado en USD menos lo que debía cobrar)
                            diferencia_mes = monto_pagado_usd - cuota_a_cobrar
                            saldo_acumulado += diferencia_mes

                            estatus_saldo = f"🟢 A Favor (+${saldo_acumulado:,.2f})" if saldo_acumulado >= 0 else f"🔴 Deudor (-${abs(saldo_acumulado):,.2f})"

                            reporte_global.append({
                                "Periodo": mes,
                                "A Cobrar ($)": round(cuota_a_cobrar, 2),
                                "Pago Original": detalle_pago_str,
                                "Tasa Aplicada": tasa_str,
                                "Pagado ($)": round(monto_pagado_usd, 2),
                                "Referencia": referencia,
                                "Fecha Pago": fecha_pago,
                                "Saldo / Remanente": estatus_saldo
                            })

                        df_estado = pd.DataFrame(reporte_global)
                        st.dataframe(df_estado, use_container_width=True)
                        
                        st.markdown("---")
                        st.caption("💡 **Tip para imprimir:** Presiona `Ctrl + P` (o `Cmd + P` en Mac) para guardar este historial y compartirlo con el propietario.")
                    else:
                        st.info("No hay registros de gastos aprobados para generar el historial.")

                except Exception as e:
                    st.error(f"Error generando el estado de cuenta histórico: {e}")

        # =====================================================================
        # 🔐 RESTABLECER CONTRASEÑA DE PROPIETARIO
        # =====================================================================
        with st.expander("🔐 Restablecer Contraseña de Propietario"):
            st.info("Asigna una nueva contraseña temporal a la unidad seleccionada en caso de pérdida u olvido.")
            
            df_pass_units = obtener_unidades_df()
            lista_pass_units = df_pass_units['unidad'].tolist() if not df_pass_units.empty else []
            
            apto_pass = st.selectbox("Seleccione la Unidad para resetear clave:", lista_pass_units, key="select_pass_unit")
            nueva_clave = st.text_input("Nueva Contraseña Temporal:", type="password", key="input_nueva_clave")
            
            if st.button("Actualizar Contraseña", key="btn_reset_pass", type="primary"):
                if nueva_clave.strip():
                    try:
                        with engine.connect() as conn:
                            conn.execute(
                                text("UPDATE unidades SET password = :p WHERE unidad = :u"),
                                {"p": nueva_clave.strip(), "u": apto_pass}
                            )
                            conn.commit()
                        st.success(f"¡Contraseña actualizada con éxito para la unidad {apto_pass}!")
                    except Exception as e:
                        st.error(f"Error al actualizar la contraseña: {e}")
                else:
                    st.warning("Por favor ingrese una contraseña válida.")
    with t7:
        renderizar_recibos()

    with t8:
        st.subheader("⚙️ Datos Generales del Edificio")
        datos_actuales = obtener_datos_edificio()
        with st.form("form_edificio"):
            nombre_ed = st.text_input("Nombre del Edificio", value=datos_actuales["nombre"])
            rif_ed = st.text_input("RIF", value=datos_actuales["rif"])
            dir_ed = st.text_area("Dirección", value=datos_actuales["direccion"])

            btn_ed = st.form_submit_button("Actualizar Datos", type="primary")
            if btn_ed:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                                INSERT INTO configuracion_edificio (id, nombre, rif, direccion)
                                VALUES (1, :n, :r, :d)
                                ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre, rif = EXCLUDED.rif, direccion = EXCLUDED.direccion
                            """),
                            {"n": nombre_ed, "r": rif_ed, "d": dir_ed},
                        )
                        conn.commit()
                    st.success("Datos del edificio actualizados.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error actualizando datos: {e}")

    with t9:
        st.subheader("💱 Conciliación de Pagos y Estado Financiero")
        st.info("Resumen consolidado de ingresos por pagos aprobados frente a los gastos totales aprobados del periodo.")
        
        mes_concil = st.text_input("Periodo a conciliar (AAAA-MM):", value=obtener_mes_anterior(), key="mes_conciliacion")
        try:
            with engine.connect() as conn:
                g_comun_sum = conn.execute(
                    text("SELECT SUM(monto) FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    {"m": mes_concil}
                ).scalar() or 0.0

                p_aprob_sum = conn.execute(
                    text("SELECT SUM(monto_usd) FROM pagos_reportados WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    {"m": mes_concil}
                ).scalar() or 0.0

            col_c1, col_c2, col_c3 = st.columns(3)
            balance_val = float(p_aprob_sum or 0.0) - float(g_comun_sum or 0.0)
            col_c1.metric("Gastos Aprobados", f"${float(g_comun_sum or 0.0):,.2f}")
            col_c2.metric("Pagos Validados / Ingresos", f"${float(p_aprob_sum or 0.0):,.2f}")
            col_c3.metric("Balance", f"${balance_val:,.2f}")  
            
        except Exception as e:
            st.error(f"Error en conciliación: {e}")

        # -------------------------------------------------------------------------
        # GESTIÓN Y VALIDACIÓN DE PAGOS REPORTADOS (INMEDIATO ABAJO DE T9)
        # -------------------------------------------------------------------------
        st.markdown("---")
        st.subheader("🔍 Gestión y Validación de Pagos Reportados")
        st.info("Revisa los pagos enviados por los propietarios. Puedes aprobarlos, rechazarlos o eliminarlos si contienen errores para que el propietario pueda volver a reportarlos.")

        try:
            with engine.connect() as conn:
                df_pagos_admin = pd.read_sql(
                    text("""
                        SELECT id, apartamento, tipo_pago, mes_anio, monto_original, 
                               moneda, tasa_aplicada, monto_usd, metodo_pago, 
                               referencia, fecha_pago, estatus, fecha_reporte 
                        FROM pagos_reportados 
                        ORDER BY id DESC
                    """),
                    conn
                )

            if df_pagos_admin.empty:
                st.info("No hay pagos reportados en el sistema.")
            else:
                filtro_estatus = st.selectbox(
                    "Filtrar por estatus:", 
                    ["Todos", "Pendiente", "Aprobado", "Rechazado"],
                    key="filtro_estatus_admin"
                )

                df_filtrado = df_pagos_admin if filtro_estatus == "Todos" else df_pagos_admin[df_pagos_admin["estatus"] == filtro_estatus]

                if df_filtrado.empty:
                    st.warning(f"No hay pagos con el estatus '{filtro_estatus}'.")
                else:
                    for _, p in df_filtrado.iterrows():
                        if p["estatus"] == "Aprobado":
                            badge = "🟢 Aprobado"
                        elif p["estatus"] == "Pendiente":
                            badge = "🟡 Pendiente"
                        else:
                            badge = "🔴 Rechazado"

                        with st.expander(f"ID #{p['id']} | Apto: {p['apartamento']} | Periodo: {p['mes_anio']} | ${float(p['monto_usd']):,.2f} USD ({badge})"):
                            col_info1, col_info2 = st.columns(2)
                            with col_info1:
                                st.markdown(f"""
                                - **Propietario / Apto:** Unidad {p['apartamento']}
                                - **Tipo de Pago:** {p['tipo_pago']}
                                - **Monto Original:** {float(p['monto_original']):,.2f} {p['moneda']}
                                - **Tasa Aplicada:** {float(p['tasa_aplicada']):,.4f}
                                - **Equivalente USD:** **${float(p['monto_usd']):,.2f}**
                                """)
                            with col_info2:
                                st.markdown(f"""
                                - **Método:** {p['metodo_pago']}
                                - **Referencia:** `{p['referencia']}`
                                - **Fecha del Pago:** {p['fecha_pago']}
                                - **Reportado el:** {p['fecha_reporte']}
                                """)

                            col_b1, col_b2, col_b3 = st.columns(3)
                            
                            with col_b1:
                                if p["estatus"] != "Aprobado":
                                    if st.button("✅ Aprobar Pago", key=f"aprobar_{p['id']}"):
                                        with engine.begin() as conn_w:
                                            conn_w.execute(
                                                text("UPDATE pagos_reportados SET estatus = 'Aprobado' WHERE id = :id"),
                                                {"id": p['id']}
                                            )
                                        st.success(f"Pago #{p['id']} aprobado correctamente.")
                                        st.rerun()

                            with col_b2:
                                if p["estatus"] != "Rechazado":
                                    if st.button("❌ Rechazar", key=f"rechazar_{p['id']}"):
                                        with engine.begin() as conn_w:
                                            conn_w.execute(
                                                text("UPDATE pagos_reportados SET estatus = 'Rechazado' WHERE id = :id"),
                                                {"id": p['id']}
                                            )
                                        st.warning(f"Pago #{p['id']} marcado como rechazado.")
                                        st.rerun()

                            with col_b3:
                                if st.button("🗑️ Eliminar Registro", key=f"eliminar_{p['id']}", type="secondary"):
                                    with engine.begin() as conn_w:
                                        conn_w.execute(
                                            text("DELETE FROM pagos_reportados WHERE id = :id"),
                                            {"id": p['id']}
                                        )
                                    st.error(f"Pago #{p['id']} eliminado del sistema. El propietario ya puede reportarlo de nuevo.")
                                    st.rerun()
        except Exception as e:
            st.error(f"Ocurrió un error: {e}")
   
    with t10:
        st.subheader("📊 Cierre y Reporte Anual de Gestión")
        st.info("Genera el balance consolidado del año, el desglose de gastos por proveedor y el estatus de morosidad de las 13 unidades.")
        
        # Selector de año (por defecto el año actual 2026)
        col_y1, col_y2 = st.columns([1, 2])
        with col_y1:
            anio_evaluar = st.text_input("Ingrese el Año a Evaluar (AAAA):", value="2026", key="input_anio_cierre")
        
        with col_y2:
            st.markdown("<br>", unsafe_allow_html=True)
            btn_generar_anual = st.button("🚀 Generar Reporte Anual de Gestión", type="primary", key="btn_generar_reporte_anual")

        if btn_generar_anual:
            if not anio_evaluar.strip() or len(anio_evaluar.strip()) != 4:
                st.warning("Por favor ingrese un año válido en formato AAAA (ej. 2026).")
            else:
                try:
                    with engine.connect() as conn:
                        # 1. Obtener unidades y alícuotas
                        df_unidades = pd.read_sql("SELECT unidad, propietario, alicuota FROM unidades", conn)
                        
                        # 2. Obtener gastos aprobados del año (filtrando por mes que empiece con el año ej. '2026-')
                        query_gastos = text("""
                            SELECT mes_anio, concepto, proveedor, monto, estatus 
                            FROM gastos 
                            WHERE estatus = 'Aprobado' AND mes_anio LIKE :anio
                        """)
                        df_gastos_anual = pd.read_sql(query_gastos, conn, params={"anio": f"{anio_evaluar}%"})

                        # 3. Obtener pagos aprobados del año
                        query_pagos = text("""
                            SELECT mes_anio, apartamento, monto_usd, referencia, fecha_pago, estatus 
                            FROM pagos_reportados 
                            WHERE estatus = 'Aprobado' AND mes_anio LIKE :anio
                        """)
                        df_pagos_anual = pd.read_sql(query_pagos, conn, params={"anio": f"{anio_evaluar}%"})

                    st.markdown("---")
                    st.markdown(f"## 📁 BALANCE Y RENDICIÓN DE CUENTAS - AÑO **{anio_evaluar}**")
                    
                    # --- SECCIÓN 1: RESUMEN FINANCIERO GLOBAL ---
                    total_gastos_anio = float(df_gastos_anual['monto'].sum()) if not df_gastos_anual.empty else 0.0
                    total_ingresos_anio = float(df_pagos_anual['monto_usd'].sum()) if not df_pagos_anual.empty else 0.0
                    balance_anual = total_ingresos_anio - total_gastos_anio

                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("Total Gastos del Año", f"${total_gastos_anio:,.2f}")
                    col_m2.metric("Total Ingresos Recaudados", f"${total_ingresos_anio:,.2f}")
                    
                    if balance_anual >= 0:
                        col_m3.metric("Balance General Anual", f"${balance_anual:,.2f} (Superávit)", delta_color="normal")
                    else:
                        col_m3.metric("Balance General Anual", f"-${abs(balance_anual):,.2f} (Déficit)", delta_color="inverse")

                    st.markdown("---")

                    # --- SECCIÓN 2: GASTOS ACUMULADOS POR PROVEEDOR ---
                    st.subheader("🛠️ Desglose de Gastos por Proveedor")
                    if not df_gastos_anual.empty:
                        # Agrupar por proveedor (si no tiene proveedor especificado, agrupar como 'General / No especificado')
                        df_gastos_anual['proveedor'] = df_gastos_anual['proveedor'].fillna('No especificado')
                        df_proveedores = df_gastos_anual.groupby('proveedor')['monto'].sum().reset_index()
                        df_proveedores.columns = ['Proveedor / Concepto General', 'Total Pagado ($)']
                        df_proveedores = df_proveedores.sort_values(by='Total Pagado ($)', ascending=False)
                        
                        st.dataframe(df_proveedores, use_container_width=True)
                    else:
                        st.info(f"No se registraron gastos aprobados para el año {anio_evaluar}.")

                    st.markdown("---")

                    # --- SECCIÓN 3: ESTADO DE CUENTA Y MOROSIDAD POR UNIDAD AL CIERRE DE AÑO ---
                    st.subheader("👥 Estatus de Saldos y Morosidad por Unidad al Cierre del Año")
                    
                    if not df_unidades.empty and not df_gastos_anual.empty:
                        # Calcular el total de gastos del año para calcular lo que debió aportar cada uno por su alícuota
                        # O mejor aún, calcular mes a mes acumulado para respetar el arrastre exacto de todo el año
                        meses_activos = sorted(df_gastos_anual['mes_anio'].unique())
                        
                        reporte_morosidad = []
                        
                        for _, u_row in df_unidades.iterrows():
                            apto = u_row['unidad']
                            prop = u_row['propietario']
                            alic = float(u_row['alicuota'])
                            
                            saldo_unidad_acumulado = 0.0
                            
                            for m in meses_activos:
                                # Gastos del mes m
                                gasto_mes_val = float(df_gastos_anual[df_gastos_anual['mes_anio'] == m]['monto'].sum())
                                cuota_parte = gasto_mes_val * (alic / 100.0)
                                
                                # Pagos de la unidad en el mes m
                                pagos_unidad_mes = 0.0
                                if not df_pagos_anual.empty:
                                    p_filtrados = df_pagos_anual[(df_pagos_anual['apartamento'] == apto) & (df_pagos_anual['mes_anio'] == m)]
                                    pagos_unidad_mes = float(p_filtrados['monto_usd'].sum())
                                
                                diferencia = pagos_unidad_mes - cuota_parte
                                saldo_unidad_acumulado += diferencia
                            
                            estatus_str = f"🟢 Solvente / A Favor (+${saldo_unidad_acumulado:,.2f})" if saldo_unidad_acumulado >= 0 else f"🔴 Deudor Pendiente (-${abs(saldo_unidad_acumulado):,.2f})"
                            
                            reporte_morosidad.append({
                                "Unidad": apto,
                                "Propietario": prop,
                                "Alícuota (%)": f"{alic}%",
                                "Saldo Final Anual": estatus_str
                            })
                        
                        df_morosidad_final = pd.DataFrame(reporte_morosidad)
                        st.dataframe(df_morosidad_final, use_container_width=True)
                    else:
                        st.info("Faltan datos de unidades o gastos para calcular el estado de cuentas anual.")

                    st.markdown("---")
                    st.caption("💡 Este reporte anual consolida la gestión completa de las unidades para su presentación oficial ante la asamblea de propietarios.")

                except Exception as e:
                    st.error(f"Error generando el reporte anual de gestión: {e}")

else:
    # -------------------------------------------------------------------------
    # PANEL DEL PROPIETARIO (AUTENTICADO CON SU UNIDAD)
    # -------------------------------------------------------------------------
    st.markdown(f"### 🏠 Portal del Propietario - Unidad {usuario_actual}")

    t_p1, t_p2, t_p3, t_p4 = st.tabs([
        "📄 Mis Recibos y Estado de Cuenta",
        "💳 Reportar Pago",
        "📊 Mis Pagos y Conciliación",
        "📞 Contacto y Avisos"
    ])

    with t_p1:
        st.subheader("📑 Tus Avisos de Cobro y Deuda")
        periodo_consulta = st.text_input("Consultar Periodo (AAAA-MM):", value=obtener_mes_anterior(), key="p_periodo_cons")

        try:
            with engine.connect() as conn:
                u_row = conn.execute(
                    text("SELECT alicuota, propietario, telefono FROM unidades WHERE unidad = :u"),
                    {"u": usuario_actual}
                ).fetchone()

                if not u_row:
                    st.error("No se encontró información para tu unidad.")
                else:
                    u_alic = float(u_row[0])
                    u_prop = u_row[1]
                    u_alic_dec = u_alic / 100.0

                    gastos_aprob_df = pd.read_sql(
                        text("SELECT concepto, monto FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                        conn,
                        params={"m": periodo_consulta}
                    )
                    total_gastos = gastos_aprob_df["monto"].sum() if not gastos_aprob_df.empty else 0.0
                    cuota_comun = total_gastos * u_alic_dec

                    cargos_ind_df = pd.read_sql(
                        text("SELECT concepto, monto FROM cargos_individuales WHERE apartamento = :apt AND mes_anio = :m"),
                        conn,
                        params={"apt": usuario_actual, "m": periodo_consulta}
                    )
                    total_cargos_ind = cargos_ind_df["monto"].sum() if not cargos_ind_df.empty else 0.0
                    total_a_pagar = cuota_comun + total_cargos_ind

                    st.markdown(f"""
                    - **Propietario:** {u_prop}
                    - **Alícuota:** {u_alic:.2f}%
                    - **Subtotal Cuota Común:** ${cuota_comun:,.2f}
                    - **Cargos Individuales / Extras:** ${total_cargos_ind:,.2f}
                    - **TOTAL A PAGAR EN EL PERIODO:** **${total_a_pagar:,.2f}**
                    """)

                    detalles_pdf = []
                    for _, g in gastos_aprob_df.iterrows():
                        detalles_pdf.append({
                            "concepto": f"Gasto Común: {g['concepto']}",
                            "base": float(g['monto']),
                            "monto": float(g['monto']) * u_alic_dec
                        })
                    for _, ci in cargos_ind_df.iterrows():
                        detalles_pdf.append({
                            "concepto": f"Cargo Individual: {ci['concepto']}",
                            "base": float(ci['monto']),
                            "monto": float(ci['monto'])
                        })

                    if st.button("📥 Descargar Recibo en PDF", type="primary"):
                        pdf_buffer = generar_pdf_recibo(usuario_actual, periodo_consulta, total_a_pagar, detalles_pdf, u_alic)
                        st.download_button(
                            label="📥 Guardar PDF en Dispositivo",
                            data=pdf_buffer,
                            file_name=f"Recibo_{usuario_actual}_{periodo_consulta}.pdf",
                            mime="application/pdf"
                        )
        except Exception as e:
            st.error(f"Error cargando tu estado de cuenta: {e}")

    with t_p2:
        st.subheader("💳 Registrar / Reportar un Pago")
        tasa_hoy_pago = verificar_y_actualizar_tasa_hoy(engine)
        st.info(f"💡 Tasa de referencia BCV actual: **{tasa_hoy_pago:,.4f} VES/USD**")

        with st.form("form_reportar_pago_prop"):
            col_rp1, col_rp2 = st.columns(2)
            with col_rp1:
                tipo_pago = st.selectbox("Tipo de Pago", ["Mensualidad", "Cuota Extraordinaria", "Otro"])
                mes_pago = st.text_input("Periodo que paga (AAAA-MM)", value=obtener_mes_anterior())
                moneda = st.selectbox("Moneda de Pago", ["USD", "VES"])
                monto_original = st.number_input("Monto Pagado en la Moneda Seleccionada", min_value=0.01, step=0.01)
            
            with col_rp2:
                fecha_pago = st.date_input("Fecha en que realizó el pago", value=date.today())
                
                tasa_sugerida = float(tasa_hoy_pago)
                try:
                    with engine.connect() as conn_tasa:
                        # Corregido de 'tasa_bcv' a 'tasa_cambio'
                        res_tasa_hist = conn_tasa.execute(
                            text("SELECT tasa FROM tasa_cambio WHERE fecha = :f LIMIT 1"),
                            {"f": fecha_pago}
                        ).scalar()
                        if res_tasa_hist:
                            tasa_sugerida = float(res_tasa_hist)
                except Exception:
                    pass

                tasa_aplicada = st.number_input("Tasa aplicada (histórica del día)", min_value=0.01, value=tasa_sugerida, step=0.01)
                metodo_pago = st.selectbox("Método de Pago", ["Transferencia Bancaria", "Pago Móvil", "Zelle", "Efectivo USD", "Otro"])
                referencia = st.text_input("Número de Referencia / Comprobante")

            btn_enviar_pago = st.form_submit_button("Enviar Reporte de Pago", type="primary")
            if btn_enviar_pago:
                if not referencia.strip():
                    st.error("Debes indicar el número de referencia o comprobante.")
                else:
                    try:
                        monto_usd = monto_original / tasa_aplicada if moneda == "VES" else monto_original
                        with engine.connect() as conn:
                            conn.execute(
                                text("""
                                    INSERT INTO pagos_reportados (apartamento, tipo_pago, mes_anio, monto_original, moneda, tasa_aplicada, monto_usd, metodo_pago, referencia, fecha_pago, estatus)
                                    VALUES (:apt, :tp, :m, :mo, :mon, :ta, :musd, :met, :ref, :f, 'Pendiente')
                                """),
                                {
                                    "apt": usuario_actual,
                                    "tp": tipo_pago,
                                    "m": mes_pago,
                                    "mo": monto_original,
                                    "mon": moneda,
                                    "ta": tasa_aplicada,
                                    "musd": monto_usd,
                                    "met": metodo_pago,
                                    "ref": referencia,
                                    "f": fecha_pago
                                }
                            )
                            conn.commit()
                        st.success("✅ Pago reportado exitosamente. El administrador lo validará pronto.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al reportar pago: {e}")
    with t_p3:
        st.subheader("📊 Historial y Conciliación de Mis Pagos")
        st.info("Revisa el estatus de tus reportes de pago y compara el total abonado frente a tus deudas registradas por periodo.")

        periodo_concil_prop = st.text_input("Periodo a conciliar (AAAA-MM):", value=obtener_mes_anterior(), key="periodo_conciliacion_prop")

        try:
            with engine.connect() as conn:
                u_row_c = conn.execute(
                    text("SELECT alicuota FROM unidades WHERE unidad = :u"),
                    {"u": usuario_actual}
                ).fetchone()
                
                u_alic_c = float(u_row_c[0]) / 100.0 if u_row_c and u_row_c[0] is not None else 0.0

                g_tot_c_raw = conn.execute(
                    text("SELECT SUM(monto) FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    {"m": periodo_concil_prop}
                ).scalar()
                g_tot_c = float(g_tot_c_raw) if g_tot_c_raw is not None else 0.0

                c_ind_c_raw = conn.execute(
                    text("SELECT SUM(monto) FROM cargos_individuales WHERE apartamento = :apt AND mes_anio = :m"),
                    {"apt": usuario_actual, "m": periodo_concil_prop}
                ).scalar()
                c_ind_c = float(c_ind_c_raw) if c_ind_c_raw is not None else 0.0

                deuda_total_periodo = (g_tot_c * u_alic_c) + c_ind_c

                p_aprob_raw = conn.execute(
                    text("SELECT SUM(monto_usd) FROM pagos_reportados WHERE apartamento = :apt AND mes_anio = :m AND estatus = 'Aprobado'"),
                    {"apt": usuario_actual, "m": periodo_concil_prop}
                ).scalar()
                pagos_aprobados_sum = float(p_aprob_raw) if p_aprob_raw is not None else 0.0

                balance_pendiente = deuda_total_periodo - pagos_aprobados_sum

                col_mc1, col_mc2, col_mc3 = st.columns(3)
                col_mc1.metric("Deuda del Periodo", f"${deuda_total_periodo:,.2f}")
                col_mc2.metric("Pagos Validados", f"${pagos_aprobados_sum:,.2f}")
                col_mc3.metric("Saldo Pendiente", f"${balance_pendiente:,.2f}", delta_color="inverse" if balance_pendiente > 0 else "off")

                st.markdown("---")
                st.subheader("📋 Historial de Reportes de Pago Realizados")
                
                df_mis_pagos = pd.read_sql(
                    text("SELECT id, tipo_pago, mes_anio, monto_original, moneda, monto_usd, metodo_pago, referencia, fecha_pago, estatus FROM pagos_reportados WHERE apartamento = :apt ORDER BY id DESC"),
                    conn,
                    params={"apt": usuario_actual}
                )

                if df_mis_pagos.empty:
                    st.info("No has registrado reportes de pago en la plataforma.")
                else:
                    for _, mp in df_mis_pagos.iterrows():
                        if mp["estatus"] == "Aprobado":
                            badge_mp = "🟢 Aprobado"
                        elif mp["estatus"] == "Pendiente":
                            badge_mp = "🟡 Pendiente de Validación"
                        else:
                            badge_mp = "🔴 Rechazado"

                        with st.expander(f"Reporte #{mp['id']} - {mp['mes_anio']} - ${float(mp['monto_usd']):,.2f} USD ({badge_mp})"):
                            st.markdown(f"""
                            - **Tipo de Pago:** {mp['tipo_pago']}
                            - **Monto Original:** {float(mp['monto_original']):,.2f} {mp['moneda']}
                            - **Equivalente en USD:** ${float(mp['monto_usd']):,.2f}
                            - **Método:** {mp['metodo_pago']} | **Referencia:** {mp['referencia']}
                            - **Fecha del Pago:** {mp['fecha_pago']}
                            - **Estatus Actual:** **{mp['estatus']}**
                            """)

        except Exception as e:
            st.error(f"Error cargando la conciliación del propietario: {e}")

    with t_p4:
        st.subheader("📞 Información de Contacto y Avisos de la Comunidad")
        datos_ed_p = obtener_datos_edificio()
        st.markdown(f"""
        - **Edificio:** {datos_ed_p['nombre']}
        - **RIF:** {datos_ed_p['rif']}
        - **Dirección:** {datos_ed_p['direccion']}
        """)
        st.info("Ante cualquier duda con tus pagos o reporte de averías en áreas comunes, comunícate directamente con la administración del edificio.")
