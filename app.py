import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

# ---------------------------------------------------------
# CONEXIÓN A LA BASE DE DATOS (SUPABASE / POSTGRESQL)
# ---------------------------------------------------------
DB_URL = "postgresql://postgres.psathqqomnsvzhytvbsu:man09go06yra@aws-0-ca-central-1.pooler.supabase.com:6543/postgres"

@st.cache_resource
def get_db_engine():
    return create_engine(DB_URL, pool_pre_ping=True)

engine = get_db_engine()

# ---------------------------------------------------------
# INICIALIZACIÓN DE TABLAS Y DATOS DEL EDIFICIO
# ---------------------------------------------------------
def init_db():
    with engine.begin() as conn:
        # 1. Tabla de Propietarios / Apartamentos
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS propietarios (
                apartamento VARCHAR(10) PRIMARY KEY,
                propietario VARCHAR(100) DEFAULT 'Por asignar',
                telefono VARCHAR(50) DEFAULT '',
                email VARCHAR(100) DEFAULT '',
                alicuota NUMERIC(5,4) NOT NULL
            );
        """))
        
        # Migración automática de columnas para propietarios
        conn.execute(text("ALTER TABLE propietarios ADD COLUMN IF NOT EXISTS telefono VARCHAR(50) DEFAULT '';"))
        conn.execute(text("ALTER TABLE propietarios ADD COLUMN IF NOT EXISTS email VARCHAR(100) DEFAULT '';"))
        conn.execute(text("ALTER TABLE propietarios ADD COLUMN IF NOT EXISTS propietario VARCHAR(100) DEFAULT 'Por asignar';"))

        # 2. Tabla de Gastos Comunes
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS gastos (
                id SERIAL PRIMARY KEY,
                mes_anio VARCHAR(7) NOT NULL,
                concepto VARCHAR(200) NOT NULL,
                monto NUMERIC(12,2) NOT NULL,
                fecha DATE DEFAULT CURRENT_DATE
            );
        """))

        # 3. Tabla de Pagos
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pagos (
                id SERIAL PRIMARY KEY,
                apartamento VARCHAR(10) NOT NULL,
                mes_anio VARCHAR(7) NOT NULL,
                monto NUMERIC(12,2) NOT NULL,
                referencia VARCHAR(100) DEFAULT '',
                estatus VARCHAR(20) DEFAULT 'Pendiente',
                fecha_registro DATE DEFAULT CURRENT_DATE
            );
        """))

        # 4. Tabla de Configuración del Edificio
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS configuracion (
                id INT PRIMARY KEY DEFAULT 1,
                nombre_edificio VARCHAR(150) NOT NULL,
                rif VARCHAR(30) DEFAULT '',
                direccion TEXT DEFAULT '',
                logo_url TEXT DEFAULT ''
            );
        """))

        # Insertar configuración por defecto si está vacía
        res_cfg = conn.execute(text("SELECT COUNT(*) FROM configuracion")).fetchone()
        if res_cfg[0] == 0:
            conn.execute(text("""
                INSERT INTO configuracion (id, nombre_edificio, rif, direccion, logo_url)
                VALUES (1, 'Residencias El Roble', 'J-12345678-0', 'Av. Principal, Caracas', '')
            """))

        # Insertar distribución exacta de los 13 apartamentos si la tabla está vacía
        result = conn.execute(text("SELECT COUNT(*) FROM propietarios")).fetchone()
        if result[0] == 0:
            apts_data = [
                ('1A', 0.0600), ('1B', 0.0600),
                ('2',  0.1200),
                ('3A', 0.0600), ('3B', 0.0600),
                ('4A', 0.0600), ('4B', 0.0600),
                ('5A', 0.0600), ('5B', 0.0600),
                ('6A', 0.0600), ('6B', 0.0600),
                ('7',  0.1200),
                ('PH', 0.1600)
            ]
            for apt, alic in apts_data:
                conn.execute(
                    text("INSERT INTO propietarios (apartamento, alicuota) VALUES (:apt, :alic)"),
                    {"apt": apt, "alic": alic}
                )

try:
    init_db()
except Exception as e:
    st.error(f"Error al inicializar la base de datos: {e}")
    st.stop()

# ---------------------------------------------------------
# CARGAR CONFIGURACIÓN DEL EDIFICIO
# ---------------------------------------------------------
def get_config():
    with engine.connect() as conn:
        res = conn.execute(text("SELECT nombre_edificio, rif, direccion, logo_url FROM configuracion WHERE id = 1")).fetchone()
        if res:
            return {
                "nombre": res[0],
                "rif": res[1],
                "direccion": res[2],
                "logo": res[3]
            }
        return {"nombre": "Mi Edificio", "rif": "", "direccion": "", "logo": ""}

config = get_config()

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title=config["nombre"],
    page_icon="🏢",
    layout="wide"
)

# ---------------------------------------------------------
# AUTENTICACIÓN
# ---------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title(f"🏢 {config['nombre']}")
    if config["rif"]:
        st.caption(f"RIF: {config['rif']}")
    if config["logo"]:
        st.image(config["logo"], width=200)
        
    st.subheader("Acceso al Sistema de Condominio")
    
    with st.form("login_form"):
        usuario = st.text_input("Usuario")
        clave = st.text_input("Clave", type="password")
        submit = st.form_submit_button("Ingresar")
        
        if submit:
            if usuario == "admin" and clave == "elroble2026":
                st.session_state.authenticated = True
                st.session_state.user = usuario
                st.rerun()
            elif usuario == "propietario" and clave == "roble123":
                st.session_state.authenticated = True
                st.session_state.user = usuario
                st.rerun()
            else:
                st.error("Usuario o clave incorrectos")
    st.stop()

# ---------------------------------------------------------
# MENÚ LATERAL Y NAVEGACIÓN
# ---------------------------------------------------------
if config["logo"]:
    st.sidebar.image(config["logo"], use_column_width=True)

st.sidebar.title(config["nombre"])
if config["rif"]:
    st.sidebar.caption(f"RIF: {config['rif']}")
st.sidebar.caption(f"Usuario activo: {st.session_state.get('user', 'Usuario')}")

if st.sidebar.button("Cerrar Sesión"):
    st.session_state.authenticated = False
    st.rerun()

menu = st.sidebar.radio(
    "Navegación",
    [
        "📋 Información del Edificio",
        "⚙️ Configuración del Edificio",
        "💵 Gastos Comunes",
        "📊 Estado de Cuenta y Alícuotas",
        "💳 Registro y Verificación de Pagos"
    ]
)

# ---------------------------------------------------------
# 1. INFORMACIÓN DEL EDIFICIO
# ---------------------------------------------------------
if menu == "📋 Información del Edificio":
    st.header(f"🏢 {config['nombre']}")
    if config["rif"]:
        st.subheader(f"RIF: {config['rif']}")
    if config["direccion"]:
        st.write(f"📍 **Dirección:** {config['direccion']}")
    
    if config["logo"]:
        st.image(config["logo"], width=250)

    st.markdown("---")
    
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    apartamento, 
                    propietario, 
                    telefono, 
                    email, 
                    CAST(alicuota * 100 AS FLOAT) as alicuota_porcentaje 
                FROM propietarios 
                ORDER BY apartamento
            """)
            df_props = pd.read_sql(query, conn)
    except Exception as err:
        st.error(f"⚠️ Error al leer la tabla 'propietarios': {err}")
        st.stop()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Apartamentos", f"{len(df_props)}")
    col2.metric("Suma Total Alícuotas", f"{df_props['alicuota_porcentaje'].sum():.2f}%" if not df_props.empty else "0.00%")
    col3.metric("Alícuota Penthouse", "16.00%")

    st.subheader("Listado de Apartamentos")
    st.dataframe(
        df_props.rename(columns={
            "apartamento": "Apto",
            "propietario": "Propietario",
            "telefono": "Teléfono",
            "email": "Correo",
            "alicuota_porcentaje": "Alícuota (%)"
        }),
        use_container_width=True
    )

    with st.expander("✏️ Actualizar Datos de Propietario"):
        with st.form("update_owner"):
            apt_list = df_props['apartamento'].tolist() if not df_props.empty else []
            apt_select = st.selectbox("Seleccionar Apartamento", apt_list)
            nombre = st.text_input("Nombre del Propietario")
            telefono = st.text_input("Teléfono")
            email = st.text_input("Correo Electrónico")
            btn_actualizar = st.form_submit_button("Guardar Cambios")

            if btn_actualizar and apt_select:
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE propietarios 
                            SET propietario = :nombre, telefono = :telefono, email = :email 
                            WHERE apartamento = :apt
                        """),
                        {"nombre": nombre, "telefono": telefono, "email": email, "apt": apt_select}
                    )
                st.success(f"Datos del apartamento {apt_select} actualizados.")
                st.rerun()

# ---------------------------------------------------------
# 2. CONFIGURACIÓN DEL EDIFICIO (NUEVA SECCIÓN)
# ---------------------------------------------------------
elif menu == "⚙️ Configuración del Edificio":
    st.header("⚙️ Editar Datos del Edificio")
    st.info("Modifica el nombre oficial, RIF, dirección e imagen del edificio. Los cambios se actualizarán inmediatamente en todo el sistema.")

    with st.form("form_config"):
        nuevo_nombre = st.text_input("Nombre del Edificio / Condominio", value=config["nombre"])
        nuevo_rif = st.text_input("RIF / Documento Fiscal", value=config["rif"])
        nueva_direccion = st.text_area("Dirección Física", value=config["direccion"])
        nuevo_logo = st.text_input("URL de Imagen / Logo (Opcional - enlace público de imagen)", value=config["logo"])

        btn_guardar_config = st.form_submit_button("💾 Guardar Configuración")

        if btn_guardar_config:
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        UPDATE configuracion 
                        SET nombre_edificio = :nom, rif = :rif, direccion = :dir, logo_url = :logo
                        WHERE id = 1
                    """),
                    {
                        "nom": nuevo_nombre,
                        "rif": nuevo_rif,
                        "dir": nueva_direccion,
                        "logo": nuevo_logo
                    }
                )
            st.success("Configuración actualizada correctamente.")
            st.rerun()

# ---------------------------------------------------------
# 3. GASTOS COMUNES
# ---------------------------------------------------------
elif menu == "💵 Gastos Comunes":
    st.header("💵 Carga de Gastos Comunes")
    
    col1, col2 = st.columns(2)
    mes = col1.selectbox("Mes", ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"])
    anio = col2.text_input("Año", value="2026")
    mes_anio = f"{anio}-{mes}"

    with st.form("form_gastos"):
        concepto = st.text_input("Concepto del Gasto (Ej: Mantenimiento Ascensor, Vigilancia)")
        monto = st.number_input("Monto ($)", min_value=0.0, step=10.0, format="%.2f")
        btn_gasto = st.form_submit_button("Registrar Gasto")

        if btn_gasto:
            if concepto and monto > 0:
                with engine.begin() as conn:
                    conn.execute(
                        text("INSERT INTO gastos (mes_anio, concepto, monto) VALUES (:m, :c, :mo)"),
                        {"m": mes_anio, "c": concepto, "mo": monto}
                    )
                st.success("Gasto registrado correctamente.")
                st.rerun()

    st.subheader(f"Gastos Registrados para {mes_anio}")
    with engine.connect() as conn:
        df_gastos = pd.read_sql(
            text("SELECT id, concepto, monto, fecha FROM gastos WHERE mes_anio = :m ORDER BY id DESC"),
            conn,
            params={"m": mes_anio}
        )
    if not df_gastos.empty:
        st.dataframe(df_gastos, use_container_width=True)
        st.metric("Total Gastos del Mes", f"${df_gastos['monto'].sum():,.2f}")
    else:
        st.info("No hay gastos registrados para este mes.")

# ---------------------------------------------------------
# 4. ESTADO DE CUENTA Y ALÍCUOTAS
# ---------------------------------------------------------
elif menu == "📊 Estado de Cuenta y Alícuotas":
    st.header("📊 Cálculo de Cuotas por Alícuota")

    col1, col2 = st.columns(2)
    mes = col1.selectbox("Mes a Consultar", ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"])
    anio = col2.text_input("Año a Consultar", value="2026")
    mes_anio = f"{anio}-{mes}"

    with engine.connect() as conn:
        df_gastos = pd.read_sql(
            text("SELECT SUM(monto) as total FROM gastos WHERE mes_anio = :m"),
            conn,
            params={"m": mes_anio}
        )
        df_props = pd.read_sql(
            text("SELECT apartamento, propietario, alicuota FROM propietarios ORDER BY apartamento"), 
            conn
        )
    
    total_gastos = df_gastos['total'].iloc[0] if df_gastos['total'].iloc[0] is not None else 0.0
    st.metric("Total Gastos del Mes a Repartir", f"${total_gastos:,.2f}")

    df_props['Alícuota (%)'] = (df_props['alicuota'] * 100).round(2).astype(str) + "%"
    df_props['Cuota Asignada ($)'] = (df_props['alicuota'] * float(total_gastos)).round(2)

    st.subheader(f"Cuotas Correspondientes al Período {mes_anio}")
    st.dataframe(
        df_props[['apartamento', 'propietario', 'Alícuota (%)', 'Cuota Asignada ($)']].rename(columns={
            "apartamento": "Apartamento",
            "propietario": "Propietario"
        }),
        use_container_width=True
    )

# ---------------------------------------------------------
# 5. REGISTRO Y VERIFICACIÓN DE PAGOS
# ---------------------------------------------------------
elif menu == "💳 Registro y Verificación de Pagos":
    st.header("💳 Registro y Verificación de Pagos")

    tab1, tab2 = st.tabs(["Reportar Pago", "Verificar Pagos"])

    with tab1:
        st.subheader("Reportar Pago de Condominio")
        
        with engine.connect() as conn:
            df_props = pd.read_sql(
                text("SELECT apartamento FROM propietarios ORDER BY apartamento"), 
                conn
            )
        
        with st.form("form_pago"):
            apt = st.selectbox("Apartamento", df_props['apartamento'].tolist())
            mes_pago = st.selectbox("Mes de Pago", ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"])
            anio_pago = st.text_input("Año de Pago", value="2026", key="pago_anio")
            mes_anio_pago = f"{anio_pago}-{mes_pago}"
            
            monto_pago = st.number_input("Monto Pagado ($)", min_value=0.0, format="%.2f")
            referencia = st.text_input("Número de Referencia")
            
            btn_pago = st.form_submit_button("Guardar Pago")

            if btn_pago:
                if monto_pago > 0:
                    with engine.begin() as conn:
                        conn.execute(
                            text("""
                                INSERT INTO pagos (apartamento, mes_anio, monto, referencia, estatus)
                                VALUES (:apt, :m, :mo, :ref, 'Pendiente')
                            """),
                            {"apt": apt, "m": mes_anio_pago, "mo": monto_pago, "ref": referencia}
                        )
                    st.success("Pago registrado correctamente (Estatus: Pendiente).")
                    st.rerun()

    with tab2:
        st.subheader("Lista de Pagos Registrados")
        
        with engine.connect() as conn:
            df_pagos = pd.read_sql(
                text("SELECT id, apartamento, mes_anio, monto, referencia, estatus, fecha_registro FROM pagos ORDER BY id DESC"), 
                conn
            )
        
        if not df_pagos.empty:
            st.dataframe(df_pagos, use_container_width=True)
            
            with st.expander("Aprobar o Reclamar Pago"):
                pago_id = st.number_input("ID del Pago", min_value=1, step=1)
                nuevo_estatus = st.selectbox("Nuevo Estatus", ["Aprobado", "Pendiente", "Rechazado"])
                if st.button("Cambiar Estatus"):
                    with engine.begin() as conn:
                        conn.execute(
                            text("UPDATE pagos SET estatus = :est WHERE id = :id"),
                            {"est": nuevo_estatus, "id": pago_id}
                        )
                    st.success(f"Pago ID {pago_id} cambiado a '{nuevo_estatus}'.")
                    st.rerun()
        else:
            st.info("Aún no se han registrado pagos.")
