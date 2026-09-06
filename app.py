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
                    text(
                        "ALTER TABLE unidades ADD COLUMN IF NOT EXISTS propietario"
                        " VARCHAR(100) DEFAULT 'Sin Asignar'"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE unidades ADD COLUMN IF NOT EXISTS telefono"
                        " VARCHAR(30) DEFAULT ''"
                    )
                )
            except Exception:
                pass

            res_u = conn.execute(text("SELECT COUNT(*) FROM unidades")).scalar()
            if res_u == 0:
                for u, a in UNIDADES_DEFECTO:
                    conn.execute(
                        text(
                            "INSERT INTO unidades (unidad, alicuota, propietario,"
                            " telefono) VALUES (:u, :a, 'Propietario', '')"
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
                        "INSERT INTO usuarios (usuario, clave, rol) VALUES ('admin',"
                        " :p, 'admin')"
                    ),
                    {"p": admin_pwd},
                )

            for u, _ in UNIDADES_DEFECTO:
                if not conn.execute(
                    text("SELECT usuario FROM usuarios WHERE usuario = :u"), {"u": u}
                ).fetchone():
                    conn.execute(
                        text(
                            "INSERT INTO usuarios (usuario, clave, rol) VALUES (:u,"
                            " '1234', 'propietario')"
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
                    text(
                        "ALTER TABLE gastos ADD COLUMN IF NOT EXISTS tipo VARCHAR(50)"
                        " DEFAULT 'Comun'"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE gastos ADD COLUMN IF NOT EXISTS proveedor"
                        " VARCHAR(100) DEFAULT 'N/A'"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE gastos ADD COLUMN IF NOT EXISTS fecha DATE DEFAULT"
                        " CURRENT_DATE"
                    )
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
                conn.execute(
                    text(
                        "ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS"
                        " monto_original NUMERIC(12,2) DEFAULT 0"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS moneda"
                        " VARCHAR(10) DEFAULT 'USD'"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS"
                        " tasa_aplicada NUMERIC(12,4) DEFAULT 1.0"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS"
                        " monto_usd NUMERIC(12,2) DEFAULT 0"
                    )
                )
            except Exception:
                pass

            conn.commit()
    except Exception:
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

    t1, t2, t3, t4, t5, t6, t7, t8, t9 = st.tabs([
        "📊 Gastos Comunes",
        "🛠️ Gastos No Comunes",
        "⭐ Cuotas Extras",
        "💱 Tasas de Cambio",
        "✅ Validar Pagos",
        "🏢 Alícuotas y Unidades",
        "🚨 Morosidad y Recibos",
        "⚙️ Datos Edificio",
        "💱 Conciliación de Pagos",
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
        st.info("Utiliza esta sección para registrar cargos asignados directamente a apartamentos específicos.")
        
    with t3:
        st.subheader("⭐ Gestión y Registro de Cuotas Extraordinarias")
        
        # Formulario para crear una nueva cuota extraordinaria
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

            if df_cuotas_admin.empty:
                st.info("No hay cuotas extraordinarias registradas.")
            else:
                for _, r_ce in df_cuotas_admin.iterrows():
                    c_det, c_act = st.columns([3, 2])
                    with c_det:
                        badge_ce = "🟡 Pendiente" if r_ce["estatus"] == "Pendiente" else "🟢 Aprobada"
                        st.markdown(
                            f"**Concepto:** {r_ce['concepto']} | **Monto:** ${float(r_ce['monto_total']):,.2f} | **Fecha:** {r_ce['fecha_emision']} | **Estatus:** {badge_ce}"
                        )
                    with c_act:
                        bc1, bc2, bc3 = st.columns(3)
                        with bc1:
                            if r_ce["estatus"] == "Pendiente":
                                if st.button("✅ Aprobar", key=f"aprob_ce_{r_ce['id']}"):
                                    with engine.connect() as conn:
                                        conn.execute(
                                            text("UPDATE cuotas_extraordinarias SET estatus = 'Aprobada' WHERE id = :id"),
                                            {"id": r_ce["id"]}
                                        )
                                        conn.commit()
                                    st.success("Cuota aprobada.")
                                    st.rerun()
                        with bc2:
                            if r_ce["estatus"] == "Aprobada":
                                if st.button("↩️ Pendiente", key=f"pend_ce_{r_ce['id']}"):
                                    with engine.connect() as conn:
                                        conn.execute(
                                            text("UPDATE cuotas_extraordinarias SET estatus = 'Pendiente' WHERE id = :id"),
                                            {"id": r_ce["id"]}
                                        )
                                        conn.commit()
                                    st.success("Cuota marcada como pendiente.")
                                    st.rerun()
                        with bc3:
                            if st.button("❌ Eliminar", key=f"del_ce_{r_ce['id']}"):
                                with engine.connect() as conn:
                                    conn.execute(
                                        text("DELETE FROM cuotas_extraordinarias WHERE id = :id"),
                                        {"id": r_ce["id"]}
                                    )
                                    conn.commit()
                                st.success("Cuota eliminada.")
                                st.rerun()
        except Exception as e:
            st.error(f"Error cargando las cuotas extraordinarias: {e}"

    with t4:
        st.subheader("💱 Gestión de Tasas de Cambio (BCV / Manual)")
        
        # Mostrar tasa de hoy obtenida automáticamente
        tasa_hoy = verificar_y_actualizar_tasa_hoy(engine)
        st.metric("Tasa BCV Automática para Hoy", f"{tasa_hoy:,.4f} VES/USD")

        st.markdown("---")
        st.markdown("### ➕ Registrar o Actualizar Tasa Manualmente")
        
        with st.form("form_registrar_tasa"):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                fecha_tasa = st.date_input("Fecha de la Tasa", value=date.today())
            with col_t2:
                valor_tasa = st.number_input("Valor de la Tasa (VES por 1 USD)", min_value=0.01, value=float(tasa_hoy), step=0.01, format="%.4f")
            
            btn_guardar_tasa = st.form_submit_button("Guardar / Actualizar Tasa", type="primary")

            if btn_guardar_tasa:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                                INSERT INTO tasa_cambio (fecha, tasa)
                                VALUES (:f, :t)
                                ON CONFLICT (fecha) DO UPDATE SET tasa = EXCLUDED.tasa
                            """),
                            {"f": fecha_tasa, "t": valor_tasa}
                        )
                        conn.commit()
                    st.success(f"✅ Tasa de {valor_tasa:,.4f} para la fecha {fecha_tasa} guardada correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar la tasa de cambio: {e}")

        st.markdown("---")
        st.markdown("### 📋 Historial de Tasas Registradas en el Sistema")

        try:
            with engine.connect() as conn:
                df_tasas = pd.read_sql(
                    text("SELECT fecha, tasa FROM tasa_cambio ORDER BY fecha DESC LIMIT 30"),
                    conn
                )
            if df_tasas.empty:
                st.info("No hay tasas de cambio registradas.")
            else:
                st.dataframe(df_tasas, use_container_width=True)
        except Exception as e:
            st.error(f"Error al cargar el historial de tasas: {e}")

    with t5:
        st.subheader("✅ Validación de Pagos Reportados")
        try:
            with engine.connect() as conn:
                df_pagos_pend = pd.read_sql(
                    text("SELECT * FROM pagos_reportados WHERE estatus = 'Pendiente' ORDER BY id DESC"),
                    conn
                )
            if df_pagos_pend.empty:
                st.info("No hay pagos pendientes por validar.")
            else:
                st.dataframe(df_pagos_pend, use_container_width=True)
        except Exception as e:
            st.error(f"Error al cargar pagos reportados: {e}")

    with t6:
        st.subheader("🏢 Configuración de Alícuotas, Unidades y Propietarios")
        st.dataframe(obtener_unidades_df(), use_container_width=True)

        st.markdown("---")
        st.markdown("### 🔑 Restablecer Contraseña de Residente")
        st.info("Si un propietario olvidó su contraseña, puedes restablecerla a su valor por defecto (`1234`) seleccionando su unidad.")

        try:
            with engine.connect() as conn:
                unidades_lista = pd.read_sql(
                    text("SELECT unidad, propietario FROM unidades ORDER BY unidad ASC"),
                    conn
                )
            
            # Crear un diccionario o lista legible para el selectbox
            opciones_unidades = [f"Apt {row['unidad']} - {row['propietario']}" for _, row in unidades_lista.iterrows()]
            dict_unidades = {f"Apt {row['unidad']} - {row['propietario']}": row['unidad'] for _, row in unidades_lista.iterrows()}

            with st.form("form_reset_clave"):
                unidad_seleccionada = st.selectbox("Selecciona la Unidad / Propietario:", opciones_unidades)
                btn_reset = st.form_submit_button("🔄 Restablecer Clave a '1234'", type="primary")

                if btn_reset:
                    apt_codigo = dict_unidades[unidad_seleccionada]
                    try:
                        with engine.connect() as conn:
                            conn.execute(
                                text("UPDATE usuarios SET clave = '1234' WHERE usuario = :u"),
                                {"u": apt_codigo}
                            )
                            conn.commit()
                        st.success(f"✅ La contraseña de la unidad **{apt_codigo}** ha sido restablecida exitosamente a **1234**.")
                    except Exception as e:
                        st.error(f"Error al restablecer la contraseña: {e}")

        except Exception as e:
            st.error(f"Error cargando la lista de unidades para restablecer claves: {e}"

    with t7:
        st.subheader("🚨 Morosidad y Recibos")
        renderizar_recibos()

    with t8:
        st.subheader("⚙️ Datos del Edificio")
        edificio = obtener_datos_edificio()
        st.write(f"**Nombre:** {edificio['nombre']}")
        st.write(f"**RIF:** {edificio['rif']}")
        st.write(f"**Dirección:** {edificio['direccion']}")

    with t9:
        st.subheader("💱 Conciliación de Pagos en Bolívares")
        st.info("Módulo para conciliar pagos calculando la tasa BCV correspondiente al día de la transacción.")

else:
    # -------------------------------------------------------------------------
    # PORTAL RESTRINGIDO DE PROPIETARIOS (4 SECCIONES ESPECÍFICAS)
    # -------------------------------------------------------------------------
    st.markdown(f"### 🏠 Portal de Residente - Unidad {usuario_actual}")
    st.markdown("Bienvenido. Aquí puedes consultar tus recibos, reportar tus pagos, ver cuotas extras y revisar el estado de tu conciliación.")

    # Pestañas exclusivas y restringidas para los propietarios
    p1, p2, p3, p4 = st.tabs([
        "📄 Recibos y Estado de Cuenta",
        "💳 Reportar Pagos",
        "⭐ Cuotas Extras",
        "💱 Conciliación e Historial de Pagos"
    ])

    with p1:
        st.subheader("📄 Consulta de Recibos y Descarga en PDF")
        mes_consulta = st.text_input("Periodo a consultar (AAAA-MM):", value=obtener_mes_anterior(), key="mes_cons_prop")

        try:
            with engine.connect() as conn:
                # Obtener alícuota del apartamento
                row_uni = conn.execute(
                    text("SELECT alicuota FROM unidades WHERE unidad = :u"), {"u": usuario_actual}
                ).fetchone()
                alicuota_apt = float(row_uni[0]) if row_uni else 0.0
                alicuota_dec = alicuota_apt / 100.0

                # Obtener gastos comunes aprobados del mes
                df_gastos_mes = pd.read_sql(
                    text("SELECT concepto, monto FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    conn, params={"m": mes_consulta}
                )

                # Obtener cargos individuales del apartamento
                df_cargos_ind = pd.read_sql(
                    text("SELECT concepto, monto FROM cargos_individuales WHERE mes_anio = :m AND apartamento = :a"),
                    conn, params={"m": mes_consulta, "a": usuario_actual}
                )

            total_comun_edificio = df_gastos_mes["monto"].sum() if not df_gastos_mes.empty else 0.0
            mi_cuota_comun = total_comun_edificio * alicuota_dec
            total_cargos_extras = df_cargos_ind["monto"].sum() if not df_cargos_ind.empty else 0.0
            total_a_pagar = mi_cuota_comun + total_cargos_extras

            st.markdown(f"**Alícuota de tu unidad:** {alicuota_apt:.2f}%")
            st.markdown(f"**Total a Pagar para el periodo {mes_consulta}:** :green[**${total_a_pagar:,.2f}**]")

            st.write("---")
            st.markdown("#### Desglose de Gastos:")
            if not df_gastos_mes.empty:
                detalles_pdf = []
                for _, r in df_gastos_mes.iterrows():
                    monto_parte = float(r["monto"]) * alicuota_dec
                    st.write(f"- {r['concepto']}: Base Total ${float(r['monto']):,.2f} | **Tu parte: ${monto_parte:,.2f}**")
                    detalles_pdf.append({"concepto": r["concepto"], "base": float(r["monto"]), "monto": monto_parte})
                
                # Botón para descargar PDF
                pdf_buffer = generar_pdf_recibo(usuario_actual, mes_consulta, total_a_pagar, detalles_pdf, alicuota_apt)
                st.download_button(
                    label="📥 Descargar Recibo en PDF",
                    data=pdf_buffer,
                    file_name=f"Recibo_{usuario_actual}_{mes_consulta}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            else:
                st.info("No hay gastos comunes aprobados para este periodo todavía.")

        except Exception as e:
            st.error(f"Error al cargar los recibos: {e}")

    with p2:
        st.subheader("💳 Reportar Nuevo Pago")
        tasa_bcv_hoy = verificar_y_actualizar_tasa_hoy(engine)
        st.info(f"💡 Tasa BCV de referencia actual: **{tasa_bcv_hoy:,.4f} VES/USD**")

        with st.form("form_reportar_pago_propietario"):
            col_rp1, col_rp2 = st.columns(2)
            with col_rp1:
                tipo_pago = st.selectbox("Tipo de Pago", ["Mensualidad", "Cuota Extraordinaria", "Otro"])
                mes_pago = st.text_input("Periodo asociado (AAAA-MM)", value=obtener_mes_anterior())
                moneda = st.selectbox("Moneda de Pago", ["USD", "VES", "EUR"])
                monto_original = st.number_input("Monto Pagado en la moneda original", min_value=0.01, step=0.01)
            with col_rp2:
                metodo = st.selectbox("Método de Pago", ["Pago Móvil", "Transferencia Bancaria", "Zelle", "Efectivo USD", "Otro"])
                referencia = st.text_input("Número de Referencia / Comprobante")
                fecha_pago = st.date_input("Fecha en que se realizó el pago", value=date.today())

            btn_enviar_pago = st.form_submit_button("Enviar Reporte de Pago", type="primary", use_container_width=True)

            if btn_enviar_pago:
                if not referencia.strip():
                    st.error("Debes ingresar el número de referencia o comprobante.")
                else:
                    # Calcular monto en USD basado en moneda y tasa
                    if moneda == "USD":
                        tasa_aplicada = 1.0
                        monto_usd = monto_original
                    elif moneda == "EUR":
                        tasa_aplicada = 1.05  # Estimado o referencia
                        monto_usd = monto_original * tasa_aplicada
                    else:  # VES
                        tasa_aplicada = obtener_tasa_por_fecha(fecha_pago)
                        monto_usd = monto_original / tasa_aplicada if tasa_aplicada > 0 else 0.0

                    try:
                        with engine.connect() as conn:
                            conn.execute(
                                text("""
                                    INSERT INTO pagos_reportados 
                                    (apartamento, tipo_pago, mes_anio, monto_original, moneda, tasa_aplicada, monto_usd, metodo_pago, referencia, fecha_pago, estatus)
                                    VALUES (:apt, :tp, :ma, :mo, :mon, :ta, :musd, :met, :ref, :fp, 'Pendiente')
                                """),
                                {
                                    "apt": usuario_actual,
                                    "tp": tipo_pago,
                                    "ma": mes_pago,
                                    "mo": monto_original,
                                    "mon": moneda,
                                    "ta": tasa_aplicada,
                                    "musd": monto_usd,
                                    "met": metodo,
                                    "ref": referencia,
                                    "fp": fecha_pago
                                }
                            )
                            conn.commit()
                        st.success("✅ ¡Pago reportado exitosamente! El administrador lo validará próximamente.")
                    except Exception as e:
                        st.error(f"Error al registrar el pago: {e}")

    with p3:
        st.subheader("⭐ Cuotas Extraordinarias Activas")
        try:
            with engine.connect() as conn:
                df_cuotas = pd.read_sql(
                    text("SELECT concepto, monto_total, fecha_emision, estatus FROM cuotas_extraordinarias ORDER BY id DESC"),
                    conn
                )
            if df_cuotas.empty:
                st.info("No hay cuotas extraordinarias activas registradas en este momento.")
            else:
                st.dataframe(df_cuotas, use_container_width=True)
        except Exception as e:
            st.error(f"Error cargando cuotas extraordinarias: {e}")

    with p4:
        st.subheader("💱 Conciliación e Historial de tus Pagos Reportados")
        try:
            with engine.connect() as conn:
                df_historial = pd.read_sql(
                    text("""
                        SELECT fecha_reporte, tipo_pago, mes_anio, monto_original, moneda, tasa_aplicada, monto_usd, metodo_pago, referencia, estatus 
                        FROM pagos_reportados 
                        WHERE apartamento = :apt 
                        ORDER BY id DESC
                    """),
                    conn,
                    params={"apt": usuario_actual}
                )

            if df_historial.empty:
                st.info("No has reportado ningún pago todavía.")
            else:
                st.dataframe(df_historial, use_container_width=True)
                st.caption("Estatus posibles: 🟡 Pendiente de validación, 🟢 Aprobado / Conciliado, 🔴 Rechazado.")
        except Exception as e:
            st.error(f"Error al consultar el historial de pagos: {e}")
