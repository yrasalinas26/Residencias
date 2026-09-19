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

            # <-- CAMBIO AQUÍ: Usamos float(str(...)) para blindar contra Decimal de la BD
            if tasa_existente is not None:
                return float(str(tasa_existente))

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
            
            # <-- Y CAMBIO AQUÍ TAMBIÉN: Blindamos la última tasa de la misma forma
            if ultima_tasa is not None:
                return float(str(ultima_tasa))
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
                                st.error("Gasto eliminado.")
                                st.rerun()

            # ==========================================
            # SECCIÓN NUEVA: RECIBO DE GASTOS COMUNES Y WHATSAPP
            # ==========================================
            st.write("---")
            st.subheader(f"📢 Generar Recibo y Envío por WhatsApp (Periodo: {mes_filtro})")

            with engine.connect() as conn:
                # Traer solo los gastos APROBADOS del mes para calcular el recibo real
                df_gastos_aprobados = pd.read_sql(
                    text("SELECT concepto, monto FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    conn,
                    params={"m": mes_filtro}
                )
                df_unidades_gc = pd.read_sql("SELECT unidad, propietario, alicuota, telefono FROM unidades", conn)

            if df_gastos_aprobados.empty:
                st.warning(f"⚠️ No hay gastos aprobados para el periodo {mes_filtro} para poder generar el recibo.")
            else:
                total_gastos_mes = df_gastos_aprobados['monto'].sum()
                
                # Mostrar desglose en pantalla
                st.markdown(f"**Total de Gastos Comunes Aprobados:** ${total_gastos_mes:,.2f}")
                with st.expander("Ver desglose de los gastos del mes"):
                    for _, g_row in df_gastos_aprobados.iterrows():
                        st.text(f"• {g_row['concepto']}: ${float(g_row['monto']):,.2f}")

                if df_unidades_gc.empty:
                    st.warning("⚠️ No hay unidades configuradas para calcular las alícuotas.")
                else:
                    # Orden oficial estricto de las 13 unidades
                    orden_oficial = ["1A", "1B", "2", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7", "PH"]
                    
                    dict_unidades_gc = {}
                    for _, u in df_unidades_gc.iterrows():
                        dict_unidades_gc[str(u['unidad']).strip().upper()] = {
                            "propietario": u['propietario'],
                            "alicuota": float(u['alicuota']),
                            "telefono": str(u['telefono'])
                        }

                    # Construir el texto del detalle de gastos para el mensaje
                    desglose_gastos_txt = "\n".join([f"• {row['concepto']}: ${float(row['monto']):,.2f}" for _, row in df_gastos_aprobados.iterrows()])

                    # Construir la distribución por apartamento ordenada
                    lineas_distribucion = []
                    for apto_nombre in orden_oficial:
                        if apto_nombre in dict_unidades_gc:
                            alic = dict_unidades_gc[apto_nombre]["alicuota"]
                            monto_parte = total_gastos_mes * (alic / 100.0)
                            lineas_distribucion.append(f"• Apto {apto_nombre} ({alic}%): ${monto_parte:,.2f}")
                    
                    distribucion_str = "\n".join(lineas_distribucion)

                    # 1. Mensaje para el Grupo General
                    msg_grupo_gc = (
                        f"🏢 *RELACIÓN DE GASTOS COMUNES - {mes_filtro}* 🏢\n\n"
                        f"Estimados propietarios, a continuación el detalle de los gastos del mes:\n\n"
                        f"{desglose_gastos_txt}\n\n"
                        f"💵 *Monto Total del Mes:* ${total_gastos_mes:,.2f}\n\n"
                        f"📋 *Distribución por alícuotas:*\n{distribucion_str}\n\n"
                        f"Agradecemos su pronta cancelación. ¡Saludos!"
                    )

                    import urllib.parse
                    msg_grupo_encoded = urllib.parse.quote(msg_grupo_gc)
                    link_grupo_gc = f"https://wa.me/?text={msg_grupo_encoded}"

                    st.markdown("---")
                    st.markdown("**1️⃣ Difusión General del Recibo:**")
                    st.link_button("📲 Enviar Relación de Gastos al Grupo (WhatsApp)", url=link_grupo_gc)

                    st.markdown("---")
                    st.markdown("**2️⃣ Envío de Estado de Cuenta Individual:**")
                    
                    lista_aptos_gc = [apto for apto in orden_oficial if apto in dict_unidades_gc]
                    apto_sel_gc = st.selectbox("Seleccione apartamento para enviar recibo individual:", lista_aptos_gc, key=f"sel_gc_{mes_filtro}")

                    if apto_sel_gc:
                        info_u_gc = dict_unidades_gc[apto_sel_gc]
                        alic_gc = info_u_gc['alicuota']
                        monto_apto_gc = total_gastos_mes * (alic_gc / 100.0)
                        tel_gc = info_u_gc['telefono'].strip()

                        msg_ind_gc = (
                            f"Hola {info_u_gc['propietario']}, le escribimos de la administración de las Residencias.\n\n"
                            f"Le enviamos su estado de cuenta de Gastos Comunes ({mes_filtro}):\n"
                            f"🏠 *Unidad:* {apto_sel_gc} (Alícuota {alic_gc}%)\n\n"
                            f"📌 *Desglose de gastos del periodo:*\n{desglose_gastos_txt}\n\n"
                            f"💵 *Total a pagar:* **${monto_apto_gc:,.2f}**\n\n"
                            f"Por favor reportar su pago al realizarlo. ¡Gracias!"
                        )

                        msg_ind_gc_encoded = urllib.parse.quote(msg_ind_gc)
                        tel_limpio_gc = "".join(filter(str.isdigit, tel_gc))

                        if tel_limpio_gc:
                            link_ind_gc = f"https://wa.me/{tel_limpio_gc}?text={msg_ind_gc_encoded}"
                            st.link_button(f"📲 Enviar Recibo Individual a {info_u_gc['propietario']} ({apto_sel_gc})", url=link_ind_gc)
                            st.caption(f"Teléfono registrado: {tel_gc}")
                        else:
                            st.warning(f"⚠️ El apartamento {apto_sel_gc} no tiene un teléfono válido registrado.")

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
                        with engine.begin() as conn:
                            conn.execute(
                                text("""
                                    INSERT INTO cuotas_extraordinarias (concepto, monto_total, fecha_emision, estatus)
                                    VALUES (:c, :m, CURRENT_DATE, 'Pendiente')
                                """),
                                {"c": concepto_ce, "m": monto_ce}
                            )
                        st.success("✅ Cuota extraordinaria creada exitosamente en estado pendiente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al registrar la cuota extraordinaria: {e}")

        st.write("---")
        st.subheader("📋 Listado y Control de Cuotas Extraordinarias")
        
        import time
        from sqlalchemy.exc import DBAPIError

        def ejecutar_sql_seguro(query_text, params=None, es_lectura=True):
            max_intentos = 3
            for intento in range(max_intentos):
                try:
                    if es_lectura:
                        with engine.connect() as conn:
                            return pd.read_sql(text(query_text), conn, params=params)
                    else:
                        with engine.begin() as conn:
                            conn.execute(text(query_text), params or {})
                            return True
                except DBAPIError as e:
                    if "deadlock detected" in str(e) and intento < max_intentos - 1:
                        time.sleep(0.4 * (intento + 1))
                        continue
                    else:
                        raise e

        try:
            df_cuotas_admin = ejecutar_sql_seguro(
                "SELECT id, concepto, monto_total, fecha_emision, estatus FROM cuotas_extraordinarias ORDER BY id DESC", 
                es_lectura=True
            )
            df_unidades_ce = ejecutar_sql_seguro(
                "SELECT unidad, propietario, alicuota, telefono FROM unidades", 
                es_lectura=True
            )

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

                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if estatus_ce == "Pendiente":
                                if st.button("✅ Aprobar Cuota", key=f"app_ce_{id_ce}", type="primary"):
                                    try:
                                        ejecutar_sql_seguro(
                                            "UPDATE cuotas_extraordinarias SET estatus = 'Aprobada' WHERE id = :id",
                                            {"id": id_ce},
                                            es_lectura=False
                                        )
                                        st.success("Cuota extraordinaria aprobada.")
                                        st.rerun()
                                    except Exception as ex:
                                        st.error(f"Error al aprobar: {ex}")
                        with col_btn2:
                            if st.button("🗑️ Eliminar Cuota", key=f"del_ce_{id_ce}", type="secondary"):
                                try:
                                    ejecutar_sql_seguro(
                                        "DELETE FROM cuotas_extraordinarias WHERE id = :id",
                                        {"id": id_ce},
                                        es_lectura=False
                                    )
                                    st.error("Cuota extraordinaria eliminada correctamente.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al eliminar: {e}")

                        st.markdown("---")
                        st.subheader("📢 Envío Directo por WhatsApp (Distribución por Alícuotas)")
                        
                        if not df_unidades_ce.empty:
                            orden_oficial = ["1A", "1B", "2", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7", "PH"]
                            
                            dict_unidades = {}
                            for _, u in df_unidades_ce.iterrows():
                                dict_unidades[str(u['unidad']).strip().upper()] = {
                                    "propietario": u['propietario'],
                                    "alicuota": float(u['alicuota']),
                                    "telefono": str(u['telefono'])
                                }

                            lineas_detalle = []
                            for apto_nombre in orden_oficial:
                                if apto_nombre in dict_unidades:
                                    alic = dict_unidades[apto_nombre]["alicuota"]
                                    monto_parte = monto_total_ce * (alic / 100.0)
                                    lineas_detalle.append(f"• Apto {apto_nombre} ({alic}%): ${monto_parte:,.2f}")
                            
                            detalle_str = "\n".join(lineas_detalle)
                            
                            msg_grupo = (
                                f"📢 *AVISO DE CUOTA EXTRAORDINARIA* 📢\n\n"
                                f"Estimados propietarios, se ha emitido una cuota extraordinaria con los siguientes detalles:\n\n"
                                f"📌 *Concepto:* {concepto_txt}\n"
                                f"💵 *Monto Total:* ${monto_total_ce:,.2f}\n\n"
                                f"📋 *Distribución por alícuotas:*\n{detalle_str}\n\n"
                                f"Por favor realizar su pago correspondiente y reportarlo por la app. ¡Gracias!"
                            )
                            
                            import urllib.parse
                            msg_grupo_encoded = urllib.parse.quote(msg_grupo)
                            link_grupo = f"https://wa.me/?text={msg_grupo_encoded}"
                            
                            st.markdown("**1️⃣ Difusión General:**")
                            st.link_button("📲 Enviar Aviso al Grupo General (WhatsApp)", url=link_grupo)
                            
                            st.markdown("---")
                            st.markdown("**2️⃣ Envío Individualizado por Propietario:**")
                            
                            lista_aptos_ordenada = [apto for apto in orden_oficial if apto in dict_unidades]
                            apto_w = st.selectbox("Seleccione apartamento:", lista_aptos_ordenada, key=f"sel_w_ce_{id_ce}")
                            
                            if apto_w:
                                info_u = dict_unidades[apto_w]
                                alic_sel = info_u['alicuota']
                                monto_sel = monto_total_ce * (alic_sel / 100.0)
                                tel_prop = info_u['telefono'].strip()
                                
                                msg_individual = (
                                    f"Hola {info_u['propietario']}, le escribimos de la administración de las Residencias.\n\n"
                                    f"Le recordamos su cuota extraordinaria:\n"
                                    f"📌 *Concepto:* {concepto_txt}\n"
                                    f"🏠 *Unidad:* {apto_w} (Alícuota {alic_sel}%)\n"
                                    f"💵 *Monto a pagar:* **${monto_sel:,.2f}**\n\n"
                                    f"Agradecemos reportar su pago a la brevedad. ¡Saludos!"
                                )
                                
                                msg_ind_encoded = urllib.parse.quote(msg_individual)
                                tel_limpio = "".join(filter(str.isdigit, tel_prop))
                                
                                if tel_limpio:
                                    link_individual = f"https://wa.me/{tel_limpio}?text={msg_ind_encoded}"
                                    st.link_button(f"📲 Enviar WhatsApp a {info_u['propietario']} ({apto_w})", url=link_individual)
                                    st.caption(f"Número registrado: {tel_prop}")
                                else:
                                    st.warning(f"⚠️ El apartamento {apto_w} no tiene un teléfono válido registrado en la sección de unidades.")
                        else:
                            st.warning("No hay unidades configuradas para hacer el cálculo.")

        except Exception as e:
            st.error(f"Error de conexión o bloqueo temporal en la base de datos: {e}")
            if st.button("🔄 Reintentar Carga"):
                st.rerun()

        # =========================================================================
        # --- REPORTE GENERAL DE PAGOS (LISTO PARA IMPRIMIR / WHATSAPP) ---
        # =========================================================================
        st.write("---")
        st.subheader("📊 Reporte de Pagos Aprobados - Cuotas Extraordinarias")
        st.info("💡 **Consejo de impresión:** Presiona `Ctrl + P` en tu teclado para imprimir este reporte de manera limpia o guardarlo como PDF. También puedes enviarlo directamente por WhatsApp.")
        
        try:
            query_reporte_ce = """
                SELECT 
                    referencia AS Concepto_Cuota, 
                    apartamento AS Apartamento, 
                    monto_usd AS Monto_Cuota, 
                    referencia AS Referencia_Pago, 
                    fecha_pago AS Fecha_Pago
                FROM pagos_reportados 
                WHERE estatus = 'Aprobado' AND tipo_pago = 'Cuota Extraordinaria'
                ORDER BY fecha_pago DESC
            """
            df_reporte_ce = ejecutar_sql_seguro(query_reporte_ce, es_lectura=True)
                
            if not df_reporte_ce.empty:
                # Mostramos la tabla interactiva de Streamlit
                st.dataframe(df_reporte_ce, use_container_width=True)
                
                # Cálculo rápido de total recaudado para el reporte
                total_recaudado_ce = df_reporte_ce['Monto_Cuota'].sum()
                st.markdown(f"### **Total Recaudado en Cuotas Extraordinarias: ${total_recaudado_ce:,.2f}**")
                
                st.write("")
                st.markdown("#### 🚀 Acciones de Compartir Reporte")
                
                # Generador de mensaje formateado para WhatsApp con el reporte
                detalle_pagos_txt = ""
                for _, row in df_reporte_ce.iterrows():
                    detalle_pagos_txt += f"• Apto {row['Apartamento']} - ${row['Monto_Cuota']:,.2f} (Ref: {row['Referencia_Pago']})\n"
                
                msg_reporte_wa = (
                    f"📊 *REPORTE DE PAGOS: CUOTAS EXTRAORDINARIAS* 📊\n\n"
                    f"*Detalle de pagos aprobados:*\n{detalle_pagos_txt}\n"
                    f"💵 *Total Recaudado:* ${total_recaudado_ce:,.2f}\n\n"
                    f"Reporte emitido por la administración."
                )
                
                import urllib.parse
                msg_reporte_encoded = urllib.parse.quote(msg_reporte_wa)
                link_reporte_wa = f"https://wa.me/?text={msg_reporte_encoded}"
                
                col_wa1, col_wa2 = st.columns(2)
                with col_wa1:
                    st.link_button("📲 Enviar Reporte por WhatsApp (General)", url=link_reporte_wa, type="primary")
                with col_wa2:
                    csv_data = df_reporte_ce.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Descargar CSV",
                        data=csv_data,
                        file_name="reporte_cuotas_extraordinarias.csv",
                        mime="text/csv"
                    )
            else:
                st.info("No se encuentran pagos aprobados de cuotas extraordinarias registrados en el sistema.")
        except Exception as e:
            st.warning(f"Aún no se ha adaptado la columna de tipos de pago o hubo un error al consultar: {e}")
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
        
        # 1. Cargar datos actuales
        df_unidades = obtener_unidades_df()
        
        if not df_unidades.empty:
            # Aseguramos el orden de las columnas esperadas
            cols_mostrar = ['unidad', 'propietario', 'telefono', 'alicuota']
            cols_presentes = [c for c in cols_mostrar if c in df_unidades.columns]
            
            st.markdown("### ✏️ Edición Rápida de Unidades")
            st.caption("Modifica los valores directamente en la tabla y presiona 'Guardar Cambios' abajo.")
            
            # 2. Editor interactivo masivo (tipo Excel)
            df_editado = st.data_editor(
                df_unidades[cols_presentes],
                disabled=["unidad"], # La clave primaria 'unidad' no se debe modificar
                column_config={
                    "unidad": st.column_config.TextColumn("Unidad / Apto", disabled=True),
                    "propietario": st.column_config.TextColumn("Nombre del Propietario"),
                    "telefono": st.column_config.TextColumn("Teléfono"),
                    "alicuota": st.column_config.NumberColumn(
                        "Alícuota (%)",
                        format="%.2f %%",
                        min_value=0.0,
                        max_value=100.0,
                        step=0.01
                    )
                },
                hide_index=True,
                use_container_width=True,
                key="editor_unidades_t6"
            )
            
            # 3. Botón de guardado masivo en la Base de Datos
            if st.button("💾 Guardar Cambios de Unidades", type="primary", key="btn_save_unid_editor"):
                try:
                    with engine.begin() as conn:
                        for _, row in df_editado.iterrows():
                            conn.execute(
                                text("""
                                    UPDATE unidades 
                                    SET propietario = :p, telefono = :t, alicuota = :a
                                    WHERE unidad = :u
                                """),
                                {
                                    "p": str(row["propietario"] or "").strip(),
                                    "t": str(row["telefono"] or "").strip(),
                                    "a": float(row["alicuota"]),
                                    "u": str(row["unidad"])
                                }
                            )
                    st.success("✅ Unidades actualizadas correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error actualizando unidades: {e}")
        else:
            st.warning("No se encontraron unidades registradas en la base de datos.")

        st.markdown("---")
    
        # =====================================================================
        # ⚠️ GESTIÓN DE SALDO INICIAL / DEUDOR ANTERIOR
        # =====================================================================
        with st.expander("⚠️ Configurar Saldo Inicial / Deudor por Unidad (Ej. al 07/2026)"):
            st.info("Permite registrar un saldo de arrastre (deudor o a favor) antes del inicio del sistema o para un periodo específico.")
            df_saldos_units = obtener_unidades_df()
            lista_saldos_units = df_saldos_units['unidad'].tolist() if not df_saldos_units.empty else []
            
            apto_saldo = st.selectbox("Seleccione la Unidad:", lista_saldos_units, key="select_saldo_inicial_unit")
            
            # Consultar si ya tiene saldo inicial registrado
            saldo_actual_db = 0.0
            try:
                with engine.connect() as conn:
                    res_s = conn.execute(text("SELECT saldo_inicial FROM unidades WHERE unidad = :u"), {"u": apto_saldo}).fetchone()
                    if res_s and hasattr(res_s, 'saldo_inicial') and res_s.saldo_inicial is not None:
                        saldo_actual_db = float(res_s.saldo_inicial)
            except Exception:
                try:
                    with engine.begin() as conn_w:
                        conn_w.execute(text("ALTER TABLE unidades ADD COLUMN saldo_inicial FLOAT DEFAULT 0.0"))
                except Exception:
                    pass

            monto_saldo_ingresado = st.number_input(
                "Saldo Inicial en USD (Positivo si es a favor, Negativo si es deudor / deuda previa):", 
                value=saldo_actual_db, 
                step=1.0, 
                format="%.2f",
                key="input_valor_saldo_inicial",
                help="Ejemplo: Si el apartamento 6B debe $150 al 07/2026, ingresa -150.00"
            )
            
            if st.button("Guardar Saldo Inicial", key="btn_guardar_saldo_inicial", type="primary"):
                try:
                    with engine.begin() as conn_w:
                        conn_w.execute(
                            text("UPDATE unidades SET saldo_inicial = :s WHERE unidad = :u"),
                            {"s": monto_saldo_ingresado, "u": apto_saldo}
                        )
                    st.success(f"¡Saldo inicial actualizado exitosamente para la unidad {apto_saldo}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar saldo inicial: {e}")

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
                        res_unid = conn.execute(
                            text("SELECT alicuota, propietario, saldo_inicial FROM unidades WHERE unidad = :u"),
                            {"u": apto_seleccionado}
                        ).fetchone()
                        
                        alicuota_pct = float(res_unid.alicuota) if res_unid and res_unid.alicuota else 0.0
                        nombre_prop = res_unid.propietario if res_unid else "N/D"
                        saldo_inicial_base = float(res_unid.saldo_inicial) if res_unid and hasattr(res_unid, 'saldo_inicial') and res_unid.saldo_inicial else 0.0

                        df_pagos_aprobados = pd.read_sql(
                            text("""
                                SELECT mes_anio, monto_original, moneda, tasa_aplicada, monto_usd, referencia, fecha_pago, metodo_pago 
                                FROM pagos_reportados 
                                WHERE apartamento = :apt AND estatus = 'Aprobado'
                            """),
                            conn,
                            params={"apt": apto_seleccionado}
                        )
                        
                        df_gastos_mes = pd.read_sql(
                            text("SELECT mes_anio, SUM(monto) as total_gastos FROM gastos WHERE estatus = 'Aprobado' GROUP BY mes_anio ORDER BY mes_anio"),
                            conn
                        )

                    st.markdown(f"### 📄 Estado de Cuenta Histórico: Unidad **{apto_seleccionado}** ({nombre_prop})")
                    st.info(f"📌 Alícuota asignada: **{alicuota_pct}%** | 📌 Saldo Inicial de Arrastre: **${saldo_inicial_base:,.2f} USD**")

                    if not df_gastos_mes.empty:
                        reporte_global = []
                        saldo_acumulado = saldo_inicial_base 

                        for _, row_g in df_gastos_mes.iterrows():
                            mes = row_g["mes_anio"]
                            gasto_total = float(row_g["total_gastos"])
                            cuota_a_cobrar = gasto_total * (alicuota_pct / 100.0)

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

        st.markdown("---")

        # =====================================================================
        # 📱 REGISTRAR Y APROBAR PAGO EN NOMBRE DE UN PROPIETARIO (ADMIN)
        # =====================================================================
        with st.expander("📱 Registrar y Aprobar Pago (Admin)"):
            st.info("Permite registrar y aprobar un pago directamente en nombre de un propietario seleccionando la moneda y método correspondiente.")
            
            df_units_pago = obtener_unidades_df()
            lista_units_admin = df_units_pago['unidad'].tolist() if not df_units_pago.empty else []
            
            with st.form("form_pago_admin_unificado"):
                unidad_destino_pm = st.selectbox("Seleccionar Unidad / Apartamento:", lista_units_admin, key="admin_uni_destino")
                
                col_a1, col_a2 = st.columns(2)
                
                with col_a1:
                    tipo_pago_admin = st.selectbox(
                        "Tipo de Pago:", 
                        ["Mensualidad", "Cuota Extraordinaria", "Otro"], 
                        key="admin_tipo_pago"
                    )
                    mes_pago_pm = st.text_input("Periodo a Abonar (AAAA-MM)", value=obtener_mes_anterior(), key="admin_mes_abonar")
                    moneda_pago = st.selectbox("Moneda de Pago:", ["USD", "VES"], key="admin_moneda_pago")
                    monto_pagado = st.number_input("Monto Pagado en Moneda Seleccionada:", min_value=0.01, step=1.00, key="admin_monto_pagado")
                
                with col_a2:
                    fecha_pago_pm = st.date_input("Fecha en que realizó el pago:", value=date.today(), key="admin_fecha_pago")
                    
                    # Buscar tasa sugerida si es VES
                    tasa_sug_admin = 1.0
                    try:
                        with engine.connect() as conn_t:
                            res_t = conn_t.execute(text("SELECT tasa FROM tasa_cambio WHERE fecha = :f LIMIT 1"), {"f": fecha_pago_pm}).scalar()
                            if res_t:
                                tasa_sug_admin = float(res_t)
                    except Exception:
                        pass
                        
                    tasa_aplicada = st.number_input("Tasa Aplicada (si es USD directo, colocar 1 o la tasa BCV):", min_value=0.01, value=tasa_sug_admin, step=0.01, key="admin_tasa_aplicada")
                    metodo_pago = st.selectbox("Método de Pago:", ["Pago Móvil", "Transferencia Bancaria", "Zelle", "Efectivo USD", "Efectivo VES", "Otro"], key="admin_metodo_pago")
                    referencia_pm = st.text_input("Número de Referencia:", placeholder="Ej: 123456 o N/A", key="admin_referencia_pago")

                btn_aprobar_pago_admin = st.form_submit_button("Aprobar Pago", type="primary")
                
                if btn_aprobar_pago_admin:
                    if monto_pagado > 0 and tasa_aplicada > 0:
                        # Forzar la conversión estricta según la moneda elegida
                        if moneda_pago.upper() == "VES":
                            monto_usd_calc = monto_pagado / tasa_aplicada
                        else:
                            monto_usd_calc = monto_pagado  # Si es USD directo
                            
                        try:
                            with engine.begin() as conn_ins:
                                conn_ins.execute(
                                    text("""
                                        INSERT INTO pagos_reportados (apartamento, tipo_pago, mes_anio, monto_original, moneda, tasa_aplicada, monto_usd, metodo_pago, referencia, fecha_pago, estatus)
                                        VALUES (:apt, :tp, :m, :mo, :mon, :ta, :musd, :met, :ref, :f, 'Aprobado')
                                    """),
                                    {
                                        "apt": unidad_destino_pm,
                                        "tp": tipo_pago_admin,
                                        "m": mes_pago_pm,
                                        "mo": monto_pagado,
                                        "mon": moneda_pago.upper(),
                                        "ta": tasa_aplicada,
                                        "musd": round(monto_usd_calc, 2), # Redondeado limpio a 2 decimales
                                        "met": metodo_pago,
                                        "ref": referencia_pm,
                                        "f": fecha_pago_pm
                                    }
                                )
                            st.success(f"✅ ¡Pago de {monto_pagado:,.2f} {moneda_pago} (Equivalente a ${monto_usd_calc:,.2f} USD) aprobado y registrado!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error al registrar el pago: {e}")
                    else:
                        st.warning("⚠️ Por favor ingresa un monto y una tasa válidos.")
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
                # 1. Gastos comunes del mes
                g_comun_sum = conn.execute(
                    text("SELECT SUM(monto) FROM gastos WHERE mes_anio = :m AND estatus = 'Aprobado'"),
                    {"m": mes_concil}
                ).scalar() or 0.0

                # 2. Pagos aprobados separados por tipo
                p_ordinaria_sum = conn.execute(
                    text("SELECT SUM(monto_usd) FROM pagos_reportados WHERE mes_anio = :m AND estatus = 'Aprobado' AND (tipo_pago = 'Cuota Ordinaria' OR tipo_pago IS NULL)"),
                    {"m": mes_concil}
                ).scalar() or 0.0

                p_extra_sum = conn.execute(
                    text("SELECT SUM(monto_usd) FROM pagos_reportados WHERE mes_anio = :m AND estatus = 'Aprobado' AND tipo_pago = 'Cuota Extraordinaria'"),
                    {"m": mes_concil}
                ).scalar() or 0.0

                p_aprob_sum = p_ordinaria_sum + p_extra_sum

            col_c1, col_c2, col_c3, col_c4 = st.columns(4)
            balance_val = float(p_aprob_sum or 0.0) - float(g_comun_sum or 0.0)
            col_c1.metric("Gastos Aprobados", f"${float(g_comun_sum or 0.0):,.2f}")
            col_c2.metric("Ingr. Ordinarios", f"${float(p_ordinaria_sum or 0.0):,.2f}")
            col_c3.metric("Ingr. Extraordinarios", f"${float(p_extra_sum or 0.0):,.2f}")
            col_c4.metric("Balance Total", f"${balance_val:,.2f}")  
            
        except Exception as e:
            st.error(f"Error en conciliación: {e}")

        # -------------------------------------------------------------------------
        # SELECTOR DE TIPO DE REPORTE SEPARADO
        # -------------------------------------------------------------------------
        st.markdown("---")
        st.subheader("📋 Reportes Separados de Morosidad y Saldos")
        
        tipo_reporte_sel = st.selectbox(
            "Seleccione el tipo de reporte a visualizar y descargar:",
            ["Cuotas Ordinarias", "Cuotas Extraordinarias"],
            key="selector_tipo_reporte_separado"
        )

        try:
            with engine.connect() as conn:
                df_unidades = pd.read_sql("SELECT unidad, alicuota FROM unidades", conn)
                gasto_mes_total = float(g_comun_sum if 'g_comun_sum' in locals() and g_comun_sum else 0.0)
                
                # Cargar datos según la selección
                if tipo_reporte_sel == "Cuotas Ordinarias":
                    query_pagos = text("""
                        SELECT apartamento, SUM(monto_usd) as total_pagado 
                        FROM pagos_reportados 
                        WHERE mes_anio = :m AND estatus = 'Aprobado' AND (tipo_pago = 'Cuota Ordinaria' OR tipo_pago IS NULL)
                        GROUP BY apartamento
                    """)
                else:
                    query_pagos = text("""
                        SELECT apartamento, SUM(monto_usd) as total_pagado 
                        FROM pagos_reportados 
                        WHERE mes_anio = :m AND estatus = 'Aprobado' AND tipo_pago = 'Cuota Extraordinaria'
                        GROUP BY apartamento
                    """)
                df_pagos_filtrados = pd.read_sql(query_pagos, conn, params={"m": mes_concil})

            if not df_unidades.empty:
                orden_unidades = ["1A", "1B", "2", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7", "PH"]
                df_unidades['unidad'] = pd.Categorical(df_unidades['unidad'], categories=orden_unidades, ordered=True)
                df_unidades = df_unidades.sort_values('unidad').reset_index(drop=True)

                reporte_datos = []
                for _, u_row in df_unidades.iterrows():
                    apto = str(u_row['unidad'])
                    alic = float(u_row['alicuota'])
                    
                    # Si es ordinaria se calcula por alícuota del gasto; si es extraordinaria, el cargo base depende de si hay un monto global fijado (o se muestra lo pagado vs esperado si aplica)
                    if tipo_reporte_sel == "Cuotas Ordinarias":
                        cargo_esperado = gasto_mes_total * (alic / 100.0)
                    else:
                        # Para extraordinarias, puedes ajustar si manejas cuota fija por unidad o alícuota
                        cargo_esperado = 0.0 # O el monto extraordinario correspondiente a la alícuota
                    
                    pagado = 0.0
                    if not df_pagos_filtrados.empty:
                        m_fil = df_pagos_filtrados[df_pagos_filtrados['apartamento'] == apto]
                        if not m_fil.empty:
                            pagado = float(m_fil['total_pagado'].values[0])
                    
                    if tipo_reporte_sel == "Cuotas Ordinarias":
                        diferencia = pagado - cargo_esperado
                        if diferencia >= -0.01:
                            estatus = f"🟢 Solvente (+${diferencia:,.2f})"
                        else:
                            estatus = f"🔴 Deudor (-${abs(diferencia):,.2f})"
                        
                        reporte_datos.append({
                            "Unidad": apto,
                            "Alícuota (%)": f"{alic}%",
                            "Cuota Esperada ($)": f"${cargo_esperado:,.2f}",
                            "Monto Pagado ($)": f"${pagado:,.2f}",
                            "Estatus / Saldo": estatus
                        })
                    else:
                        reporte_datos.append({
                            "Unidad": apto,
                            "Alícuota (%)": f"{alic}%",
                            "Monto Pagado Extraordinario ($)": f"${pagado:,.2f}",
                            "Estatus": "Registrado" if pagado > 0 else "Sin aporte"
                        })

                df_resultado_final = pd.DataFrame(reporte_datos)
                st.markdown(f"### Mostrando: {tipo_reporte_sel}")
                st.dataframe(df_resultado_final, use_container_width=True)

                # --- GENERADOR DE PDF PARA EL REPORTE SELECCIONADO ---
                import io
                from reportlab.lib.pagesizes import letter
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib import colors

                def generar_pdf_individual(mes, tipo_rep, df_datos, db_engine):
                    nombre_edif = "CONDOMINIO RESIDENCIAS"
                    rif_edif = ""
                    dir_edif = ""
                    try:
                        with db_engine.connect() as c_config:
                            res_config = c_config.execute(text("SELECT nombre, rif, direccion FROM configuracion_edificio WHERE id = 1")).fetchone()
                            if res_config:
                                nombre_edif = res_config[0] or nombre_edif
                                rif_edif = res_config[1] or ""
                                dir_edif = res_config[2] or ""
                    except Exception:
                        pass

                    buffer = io.BytesIO()
                    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
                    elementos = []
                    styles = getSampleStyleSheet()
                    
                    estilo_edificio = ParagraphStyle('Edif', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=14, textColor=colors.HexColor('#1f4e79'), alignment=1, spaceAfter=2)
                    estilo_info = ParagraphStyle('Info', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#595959'), alignment=1, spaceAfter=15)
                    estilo_titulo = ParagraphStyle('Tit', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#333333'), alignment=1, spaceAfter=15)

                    elementos.append(Paragraph(f"<b>{nombre_edif}</b>", estilo_edificio))
                    info_detalles = f"RIF: {rif_edif} | Dirección: {dir_edif}".strip(" |")
                    if info_detalles:
                        elementos.append(Paragraph(info_detalles, estilo_info))
                    
                    elementos.append(Paragraph(f"<b>Reporte de {tipo_rep} — Periodo: {mes}</b>", estilo_titulo))
                    
                    columnas = list(df_datos.columns)
                    tabla_data = [columnas]
                    for _, row in df_datos.iterrows():
                        tabla_data.append([str(row[col]) for col in columnas])
                    
                    t = Table(tabla_data)
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 9),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                        ('TOPPADDING', (0, 0), (-1, 0), 6),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9f9f9')),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d3d3d3')),
                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 1), (-1, -1), 9),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]))
                    
                    elementos.append(t)
                    doc.build(elementos)
                    buffer.seek(0)
                    return buffer.getvalue()

                pdf_bytes = generar_pdf_individual(mes_concil, tipo_reporte_sel, df_resultado_final, engine)
                st.download_button(
                    label=f"📥 Descargar Reporte de {tipo_reporte_sel} en PDF",
                    data=pdf_bytes,
                    file_name=f"Reporte_{tipo_reporte_sel.replace(' ', '_')}_{mes_concil}.pdf",
                    mime="application/pdf",
                    key=f"btn_pdf_{tipo_reporte_sel.replace(' ', '_')}_{mes_concil}"
                )

            else:
                st.warning("No hay unidades registradas en la base de datos.")

        except Exception as e:
            st.error(f"Error generando el reporte: {e}")

        # -------------------------------------------------------------------------
        # GESTIÓN Y VALIDACIÓN DE PAGOS REPORTADOS
        # -------------------------------------------------------------------------
        st.markdown("---")
        st.subheader("🔍 Gestión y Validación de Pagos Reportados")
        # (El resto de la sección de administración de pagos se mantiene igual con los filtros)

    with t10:
        st.subheader("💱 Conciliación de Pagos y Estado Financiero")
        st.info("Resumen consolidado de ingresos por pagos aprobados frente a los gastos totales aprobados del periodo.")

        # Selector de Periodo a Conciliar
        periodo_cifras = st.text_input("Periodo a conciliar (AAAA-MM):", value="2026-07", key="input_periodo_t10")

        if periodo_cifra_btn := st.button("Calcular Conciliación del Periodo", key="btn_calc_conciliacion"):
            try:
                # 1. Ingresos aprobados (Forzando limpieza total con pd.to_numeric)
                q_ingresos = "SELECT monto_usd FROM pagos_reportados WHERE estatus = 'Aprobado' AND mes_anio = :periodo"
                df_ing_c = ejecutar_sql_seguro(q_ingresos, {"periodo": periodo_cifras}, es_lectura=True)
                
                total_ing = 0.0
                if not df_ing_c.empty and 'monto_usd' in df_ing_c.columns:
                    serie_limpia = pd.to_numeric(df_ing_c['monto_usd'], errors='coerce').fillna(0.0)
                    total_ing = float(serie_limpia.sum())

                # 2. Gastos aprobados (Aplicando la misma limpieza)
                q_gastos = "SELECT monto_usd FROM gastos_proveedores WHERE mes_anio = :periodo"
                total_gas = 0.0
                try:
                    df_gas_c = ejecutar_sql_seguro(q_gastos, {"periodo": periodo_cifras}, es_lectura=True)
                    if not df_gas_c.empty and 'monto_usd' in df_gas_c.columns:
                        serie_gas_limpia = pd.to_numeric(df_gas_c['monto_usd'], errors='coerce').fillna(0.0)
                        total_gas = float(serie_gas_limpia.sum())
                except Exception:
                    pass

                col_c1, col_c2, col_c3 = st.columns(3)
                with col_c1:
                    st.metric("Total Ingresos Aprobados", f"${total_ing:,.2f}")
                with col_c2:
                    st.metric("Total Gastos Aprobados", f"${total_gas:,.2f}")
                with col_c3:
                    neto_conciliacion = total_ing - total_gas
                    st.metric("Balance del Periodo", f"${neto_conciliacion:,.2f}", delta=f"${neto_conciliacion:,.2f}")

            except Exception as e:
                st.error(f"Error en conciliación: {e}")
        st.markdown("---")
        st.subheader("📋 Reportes Separados de Morosidad y Saldos")
        tipo_reporte_sel = st.selectbox("Seleccione el tipo de reporte a visualizar y descargar:", ["Cuotas Ordinarias", "Cuotas Extraordinarias", "Proveedores"])
        st.write(f"Mostrando: {tipo_reporte_sel}")

        # Lógica de visualización rápida según el reporte seleccionado
        if tipo_reporte_sel == "Cuotas Ordinarias":
            with engine.connect() as conn:
                df_ord = pd.read_sql(text("SELECT * FROM unidades"), conn)
            if not df_ord.empty:
                st.dataframe(df_ord, use_container_width=True)
        elif tipo_reporte_sel == "Cuotas Extraordinarias":
            try:
                with engine.connect() as conn:
                    df_ext = pd.read_sql(text("SELECT * FROM cuotas_extraordinarias"), conn)
                if not df_ext.empty:
                    st.dataframe(df_ext, use_container_width=True)
                else:
                    st.info("No hay registros de cuotas extraordinarias.")
            except Exception:
                st.info("No se encontró la tabla de cuotas extraordinarias.")
        else:
            try:
                with engine.connect() as conn:
                    df_prov = pd.read_sql(text("SELECT * FROM gastos_proveedores"), conn)
                if not df_prov.empty:
                    st.dataframe(df_prov, use_container_width=True)
                else:
                    st.info("No hay registros de proveedores.")
            except Exception:
                st.info("No se encontró la tabla de proveedores.")

        st.markdown("---")

        # --- SECCIÓN DE GESTIÓN, VALIDACIÓN Y ELIMINACIÓN DE PAGOS REPORTADOS ---
        st.subheader("🔍 Gestión y Validación de Pagos Reportados")
        st.info("Aquí puedes revisar los pagos reportados por los propietarios, aprobarlos o eliminarlos permanentemente si contienen errores.")

        with engine.connect() as conn:
            q_todos_pagos = text("SELECT id, apartamento, tipo_pago, monto_usd, metodo_pago, referencia, estatus, mes_anio FROM pagos_reportados ORDER BY id DESC")
            df_todos_pagos = pd.read_sql(q_todos_pagos, conn)

        if not df_todos_pagos.empty:
            st.dataframe(df_todos_pagos, use_container_width=True)
            
            col_del1, col_del2 = st.columns(2)
            with col_del1:
                pago_id_sel = st.number_input("ID del pago a gestionar (Eliminar/Modificar):", min_value=1, step=1, value=int(df_todos_pagos['id'].iloc[0]) if not df_todos_pagos.empty else 1)
            with col_del2:
                st.write("")
                st.write("")
                btn_eliminar_pago_def = st.button("🗑️ Eliminar este Pago Permanentemente", type="secondary")

            if btn_eliminar_pago_def:
                try:
                    q_del = text("DELETE FROM pagos_reportados WHERE id = :id_pago")
                    with engine.begin() as conn:
                        conn.execute(q_del, {"id_pago": pago_id_sel})
                    st.success(f"¡El pago con ID {pago_id_sel} ha sido eliminado con éxito!")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo eliminar el pago: {e}")
        else:
            st.info("No hay pagos reportados registrados en el sistema.")
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
