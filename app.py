import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema de Control de Condominio",
    page_icon="🏢",
    layout="wide"
)

# -----------------------------------------------------------------------------
# 1. GESTIÓN TOLERANTE DE CONEXIÓN A BASE DE DATOS
# -----------------------------------------------------------------------------
@st.cache_resource
def obtener_engine():
    """Intenta crear el motor de base de datos de manera segura."""
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

        # Configuración optimizada para Supabase (evita errores con el pooler PgBouncer)
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
    """Crea las tablas necesarias si el motor de BD está conectado."""
    if not engine:
        return False
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
            conn.commit()
        return True
    except Exception as e:
        st.sidebar.error(f"⚠️ Error al inicializar tablas en Supabase: {e}")
        return False

# Intenta preparar las tablas de forma silenciosa al arrancar
db_lista = inicializar_tablas()

# -----------------------------------------------------------------------------
# CONTROL DE NAVEGACIÓN Y SESIÓN (INGRESO NEUTRO)
# -----------------------------------------------------------------------------
if "rol_activo" not in st.session_state:
    st.session_state.rol_activo = "Inicio"

# -----------------------------------------------------------------------------
# 2. VISTAS DE LA APLICACIÓN
# -----------------------------------------------------------------------------

def vista_inicio_neutro():
    """Pantalla inicial limpia y neutra para elegir rol."""
    st.markdown("<h1 style='text-align: center;'>🏢 Portal de Administración de Condominio</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray; font-size: 18px;'>Bienvenido. Selecciona tu perfil de acceso para continuar.</p>", unsafe_allow_html=True)
    st.write("---")

    if error_conexion:
        st.warning("⚠️ **Atención:** La base de datos no está conectada. Verifica las credenciales en Streamlit Cloud Secrets.")

    col_space1, col1, col2, col_space2 = st.columns([1, 2, 2, 1])

    with col1:
        st.info("### 🔑 Portal de Propietarios")
        st.write("Accede para reportar tus pagos de condominio y consultar el historial de comprobantes.")
        if st.button("Ingresar como Propietario", use_container_width=True, type="primary"):
            st.session_state.rol_activo = "Propietario"
            st.rerun()

    with col2:
        st.warning("### ⚙️ Panel de Administración")
        st.write("Gestión de gastos comunes, validación de pagos reportados y estado financiero del edificio.")
        if st.button("Ingresar como Administrador", use_container_width=True):
            st.session_state.rol_activo = "Administrador"
            st.rerun()


def vista_propietario():
    col_head, col_btn = st.columns([4, 1])
    with col_head:
        st.title("👤 Portal de Propietarios")
    with col_btn:
        st.write("")
        if st.button("🚪 Cambiar Rol"):
            st.session_state.rol_activo = "Inicio"
            st.rerun()

    if not engine:
        st.error("❌ No es posible procesar o consultar pagos porque no hay conexión activa a Supabase.")
        return

    opcion = st.radio(
        "¿Qué deseas realizar?",
        ["📥 Reportar un Pago", "📋 Ver Mis Pagos Reportados"],
        horizontal=True
    )
    
    APARTAMENTOS = [f"Apto {i}" for i in range(1, 14)]
    METODOS_PAGO = ["Transferencia Bancaria", "Pago Móvil", "Zelle", "Efectivo $"]

    if opcion == "📥 Reportar un Pago":
        st.subheader("Reportar Comprobante de Pago")
        
        with st.form("form_pago_propietario", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                apartamento = st.selectbox("Selecciona tu Apartamento", APARTAMENTOS)
                mes_anio = st.text_input("Mes / Año a Pagar", value=datetime.now().strftime("%Y-%m"))
                monto = st.number_input("Monto Pagado ($ / Bs)", min_value=0.01, step=0.01, format="%.2f")

            with col2:
                metodo = st.selectbox("Método de Pago", METODOS_PAGO)
                referencia = st.text_input("Número de Referencia")
                fecha_pago = st.date_input("Fecha de Transferencia", value=datetime.now().date())

            comprobante = st.file_uploader("Adjuntar Comprobante (Imagen/PDF)", type=["png", "jpg", "jpeg", "pdf"])
            
            submit = st.form_submit_button("🚀 Registrar Pago")

            if submit:
                if not referencia.strip():
                    st.error("⚠️ Por favor ingresa el número de referencia del pago.")
                else:
                    nombre_archivo = comprobante.name if comprobante else "Sin archivo"
                    try:
                        with engine.connect() as conn:
                            conn.execute(text("""
                                INSERT INTO pagos_reportados 
                                (apartamento, mes_anio, monto, metodo_pago, referencia, fecha_pago, comprobante_nombre, estatus)
                                VALUES (:apto, :mes, :monto, :metodo, :ref, :fecha, :comp, 'Pendiente')
                            """), {
                                "apto": apartamento,
                                "mes": mes_anio,
                                "monto": monto,
                                "metodo": metodo,
                                "ref": referencia,
                                "fecha": fecha_pago,
                                "comp": nombre_archivo
                            })
                            conn.commit()
                        st.success(f"✅ ¡Pago registrado con éxito para el {apartamento}!")
                    except Exception as e:
                        st.error(f"Error guardando el registro: {e}")

    elif opcion == "📋 Ver Mis Pagos Reportados":
        st.subheader("Historial de Pagos Reportados")
        apto_consulta = st.selectbox("Selecciona tu Apartamento para consultar", APARTAMENTOS)
        
        try:
            with engine.connect() as conn:
                df_mis_pagos = pd.read_sql(
                    text("SELECT mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus FROM pagos_reportados WHERE apartamento = :apto ORDER BY id DESC"),
                    conn,
                    params={"apto": apto_consulta}
                )
            
            if df_mis_pagos.empty:
                st.info(f"No se encontraron registros de pago para el {apto_consulta}.")
            else:
                st.dataframe(df_mis_pagos, use_container_width=True)
        except Exception as e:
            st.error(f"Error al consultar la base de datos: {e}")


def vista_administrador():
    col_head, col_btn = st.columns([4, 1])
    with col_head:
        st.title("⚙️ Panel de Administración")
    with col_btn:
        st.write("")
        if st.button("🚪 Cambiar Rol"):
            st.session_state.rol_activo = "Inicio"
            st.rerun()

    if "admin_autenticado" not in st.session_state:
        st.session_state.admin_autenticado = False

    if not st.session_state.admin_autenticado:
        st.subheader("🔒 Acceso Restringido")
        clave = st.text_input("Ingresa la clave de administrador:", type="password")
        if st.button("Ingresar"):
            if clave == "admin123":
                st.session_state.admin_autenticado = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
        return

    if not engine:
        st.error("❌ La base de datos no está conectada. No puedes gestionar gastos ni aprobar pagos.")
        return

    tab1, tab2, tab3 = st.tabs(["📊 Gastos del Condominio", "✅ Aprobar Pagos", "📄 Resumen General"])
    
    with tab1:
        st.subheader("Registrar Nuevo Gasto Común")
        with st.form("form_gastos"):
            mes = st.text_input("Mes / Año", value=datetime.now().strftime("%Y-%m"))
            concepto = st.text_input("Concepto del Gasto")
            monto_gasto = st.number_input("Monto", min_value=0.0, step=0.01)
            btn_gasto = st.form_submit_button("Guardar Gasto")
            
            if btn_gasto and concepto:
                try:
                    with engine.connect() as conn:
                        conn.execute(text("""
                            INSERT INTO gastos (mes_anio, concepto, monto, estatus)
                            VALUES (:mes, :concepto, :monto, 'Aprobado')
                        """), {"mes": mes, "concepto": concepto, "monto": monto_gasto})
                        conn.commit()
                    st.success("Gasto registrado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al registrar gasto: {e}")

    with tab2:
        st.subheader("Pagos Pendientes por Validar")
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
                
                pago_id = st.selectbox("Selecciona ID del Pago a Gestionar:", df_pendientes["id"].tolist())
                col_a, col_r = st.columns(2)
                
                with col_a:
                    if st.button("✅ Aprobar Pago"):
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE pagos_reportados SET estatus = 'Aprobado' WHERE id = :id"), {"id": pago_id})
                            conn.commit()
                        st.success(f"Pago #{pago_id} Aprobado.")
                        st.rerun()
                        
                with col_r:
                    if st.button("❌ Rechazar Pago"):
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE pagos_reportados SET estatus = 'Rechazado' WHERE id = :id"), {"id": pago_id})
                            conn.commit()
                        st.warning(f"Pago #{pago_id} Rechazado.")
                        st.rerun()
        except Exception as e:
            st.error(f"Error consultando pagos pendientes: {e}")

    with tab3:
        st.subheader("Total Gastos por Mes")
        mes_filtro = st.text_input("Filtrar por Mes (AAAA-MM)", value=datetime.now().strftime("%Y-%m"), key="filtro_admin")
        
        try:
            with engine.connect() as conn:
                df_gastos_mes = pd.read_sql(
                    text("SELECT concepto, monto FROM gastos WHERE mes_anio = :mes AND estatus = 'Aprobado'"),
                    conn,
                    params={"mes": mes_filtro}
                )
            
            total_gastos = df_gastos_mes["monto"].sum() if not df_gastos_mes.empty else 0.0
            st.metric("Total Gastos Comunes del Mes", f"${total_gastos:,.2f}")
            st.dataframe(df_gastos_mes, use_container_width=True)
        except Exception as e:
            st.error(f"Error consultando el resumen: {e}")

# -----------------------------------------------------------------------------
# 3. CONTROL DE NAVEGACIÓN Y BARRA LATERAL
# -----------------------------------------------------------------------------
st.sidebar.title("🏢 Condominio")

if st.sidebar.button("🏠 Ir al Inicio"):
    st.session_state.rol_activo = "Inicio"
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("Estado de Base de Datos:")
if engine:
    st.sidebar.success("🟢 Conectado a Supabase")
else:
    st.sidebar.error("🔴 Desconectado")

# Renderizado dinámico según la opción activa
if st.session_state.rol_activo == "Inicio":
    vista_inicio_neutro()
elif st.session_state.rol_activo == "Propietario":
    vista_propietario()
elif st.session_state.rol_activo == "Administrador":
    vista_administrador()
