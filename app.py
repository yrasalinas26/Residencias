import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Acceso al Sistema",
    page_icon="🔒",
    layout="centered"
)

# -----------------------------------------------------------------------------
# GESTIÓN DE CONEXIÓN A BASE DE DATOS
# -----------------------------------------------------------------------------
@st.cache_resource
def obtener_engine():
    try:
        if "DATABASE_URL" in st.secrets:
            url = st.secrets["DATABASE_URL"]
        elif "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
            pg = st.secrets["connections"]["postgresql"]
            url = f"{pg.get('dialect', 'postgresql')}://{pg['username']}:{pg['password']}@{pg['host']}:{pg.get('port', 5432)}/{pg['database']}"
        elif "username" in st.secrets:
            url = f"postgresql://{st.secrets['username']}:{st.secrets['password']}@{st.secrets['host']}:{st.secrets.get('port', 5432)}/{st.secrets['database']}"
        else:
            return None, "No se encontraron credenciales de base de datos en Secrets."

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
            # Tabla de Usuarios / Credenciales (Propietarios y Admin)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    usuario VARCHAR(20) PRIMARY KEY,
                    clave VARCHAR(100) NOT NULL,
                    rol VARCHAR(20) NOT NULL
                );
            """))
            
            # Crear administrador por defecto si no existe
            res_admin = conn.execute(text("SELECT usuario FROM usuarios WHERE usuario = 'admin'")).fetchone()
            if not res_admin:
                conn.execute(text("INSERT INTO usuarios (usuario, clave, rol) VALUES ('admin', 'admin123', 'admin')"))
            
            # Crear credenciales por defecto para Aptos 1 a 13 (clave inicial '1234')
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
# ESTADO DE SESIÓN NEUTRO
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
# 1. PANTALLA DE ACCESO NEUTRA (LOGIN ÚNICO)
# -----------------------------------------------------------------------------
if not st.session_state.usuario_logueado:
    st.markdown("<h2 style='text-align: center;'>🔒 Inicio de Sesión</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Ingresa tus credenciales para acceder al sistema.</p>", unsafe_allow_html=True)
    
    if error_conexion:
        st.error("⚠️ La base de datos no está disponible. Verifica los Secrets.")

    with st.form("form_login_neutro"):
        usuario_input = st.text_input("Usuario (ej. Apto 1 o admin)").strip()
        clave_input = st.text_input("Contraseña", type="password").strip()
        bot_login = st.form_submit_button("Ingresar", type="primary", use_container_width=True)

        if bot_login:
            if not usuario_input or not clave_input:
                st.error("Por favor completa ambos campos.")
            elif not engine:
                st.error("Sin conexión a la base de datos.")
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
                        st.success("Acceso concedido.")
                        st.rerun()
                    else:
                        st.error("❌ Usuario o contraseña incorrectos.")
                except Exception as e:
                    st.error(f"Error durante el ingreso: {e}")

# -----------------------------------------------------------------------------
# 2. PANEL PRIVADO DEL PROPIETARIO
# -----------------------------------------------------------------------------
elif st.session_state.rol_logueado == "propietario":
    user_actual = st.session_state.usuario_logueado

    col_head, col_out = st.columns([3, 1])
    with col_head:
        st.title(f"🏢 Bienvenido, {user_actual}")
    with col_out:
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            cerrar_sesion()

    st.write("---")

    opcion = st.radio(
        "Selecciona una opción:",
        ["📥 Reportar Pago", "📋 Mis Pagos Registrados"],
        horizontal=True
    )

    METODOS_PAGO = ["Transferencia Bancaria", "Pago Móvil", "Zelle", "Efectivo $"]

    if opcion == "📥 Reportar Pago":
        st.subheader("Formulario de Reporte de Pago")
        with st.form("form_pago_prop", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Unidad", value=user_actual, disabled=True)
                mes_anio = st.text_input("Mes / Año a pagar", value=datetime.now().strftime("%Y-%m"))
                monto = st.number_input("Monto Pagado", min_value=0.01, step=0.01, format="%.2f")

            with col2:
                metodo = st.selectbox("Método de Pago", METODOS_PAGO)
                referencia = st.text_input("Número de Referencia")
                fecha_pago = st.date_input("Fecha del Pago", value=datetime.now().date())

            comprobante = st.file_uploader("Adjuntar Comprobante", type=["png", "jpg", "jpeg", "pdf"])
            btn_guardar = st.form_submit_button("🚀 Registrar Pago", type="primary")

            if btn_guardar:
                if not referencia.strip():
                    st.error("Ingresa la referencia del pago.")
                else:
                    nombre_archivo = comprobante.name if comprobante else "Sin archivo"
                    try:
                        with engine.connect() as conn:
                            conn.execute(text("""
                                INSERT INTO pagos_reportados 
                                (apartamento, mes_anio, monto, metodo_pago, referencia, fecha_pago, comprobante_nombre, estatus)
                                VALUES (:apto, :mes, :monto, :metodo, :ref, :fecha, :comp, 'Pendiente')
                            """), {
                                "apto": user_actual,
                                "mes": mes_anio,
                                "monto": monto,
                                "metodo": metodo,
                                "ref": referencia,
                                "fecha": fecha_pago,
                                "comp": nombre_archivo
                            })
                            conn.commit()
                        st.success("✅ ¡Pago registrado exitosamente!")
                    except Exception as e:
                        st.error(f"Error al registrar: {e}")

    elif opcion == "📋 Mis Pagos Registrados":
        st.subheader("Historial de Pagos de la Unidad")
        try:
            with engine.connect() as conn:
                df_pagos = pd.read_sql(
                    text("SELECT mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus FROM pagos_reportados WHERE apartamento = :apto ORDER BY id DESC"),
                    conn,
                    params={"apto": user_actual}
                )
            if df_pagos.empty:
                st.info("No tienes pagos reportados hasta el momento.")
            else:
                st.dataframe(df_pagos, use_container_width=True)
        except Exception as e:
            st.error(f"Error consultando historial: {e}")

# -----------------------------------------------------------------------------
# 3. PANEL EXCLUSIVO DE ADMINISTRACIÓN
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

    tab1, tab2, tab3 = st.tabs(["📊 Registrar Gasto", "✅ Validar Pagos", "📄 Resumen Gastos"])

    with tab1:
        st.subheader("Registrar Gasto Común del Condominio")
        with st.form("form_gastos"):
            mes = st.text_input("Mes / Año", value=datetime.now().strftime("%Y-%m"))
            concepto = st.text_input("Concepto del Gasto")
            monto_gasto = st.number_input("Monto Total ($)", min_value=0.0, step=0.01)
            btn_gasto = st.form_submit_button("Guardar Gasto", type="primary")

            if btn_gasto and concepto:
                try:
                    with engine.connect() as conn:
                        conn.execute(text("""
                            INSERT INTO gastos (mes_anio, concepto, monto, estatus)
                            VALUES (:mes, :concepto, :monto, 'Aprobado')
                        """), {"mes": mes, "concepto": concepto, "monto": monto_gasto})
                        conn.commit()
                    st.success("Gasto registrado exitosamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al registrar gasto: {e}")

    with tab2:
        st.subheader("Pagos Pendientes por Revisar")
        try:
            with engine.connect() as conn:
                df_pendientes = pd.read_sql(
                    text("SELECT id, apartamento, mes_anio, monto, metodo_pago, referencia, fecha_pago, comprobante_nombre, estatus FROM pagos_reportados WHERE estatus = 'Pendiente' ORDER BY id ASC"),
                    conn
                )

            if df_pendientes.empty:
                st.info("🎉 No hay pagos pendientes por revisar.")
            else:
                st.dataframe(df_pendientes, use_container_width=True)
                pago_id = st.selectbox("Seleccionar ID de Pago a Gestionar:", df_pendientes["id"].tolist())
                col_a, col_r = st.columns(2)
                with col_a:
                    if st.button("✅ Aprobar Pago", use_container_width=True):
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE pagos_reportados SET estatus = 'Aprobado' WHERE id = :id"), {"id": pago_id})
                            conn.commit()
                        st.success(f"Pago #{pago_id} Aprobado.")
                        st.rerun()
                with col_r:
                    if st.button("❌ Rechazar Pago", use_container_width=True):
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE pagos_reportados SET estatus = 'Rechazado' WHERE id = :id"), {"id": pago_id})
                            conn.commit()
                        st.warning(f"Pago #{pago_id} Rechazado.")
                        st.rerun()
        except Exception as e:
            st.error(f"Error al cargar reportes: {e}")

    with tab3:
        st.subheader("Resumen de Gastos Comunes")
        mes_filtro = st.text_input("Filtrar por Mes (AAAA-MM)", value=datetime.now().strftime("%Y-%m"))
        try:
            with engine.connect() as conn:
                df_gastos_mes = pd.read_sql(
                    text("SELECT concepto, monto FROM gastos WHERE mes_anio = :mes AND estatus = 'Aprobado'"),
                    conn,
                    params={"mes": mes_filtro}
                )
            total_gastos = df_gastos_mes["monto"].sum() if not df_gastos_mes.empty else 0.0
            st.metric("Total Gastos del Mes", f"${total_gastos:,.2f}")
            st.dataframe(df_gastos_mes, use_container_width=True)
        except Exception as e:
            st.error(f"Error consultando resumen: {e}")
