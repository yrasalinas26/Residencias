import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime

# ==========================================
# 1. BASE DE DATOS Y CONFIGURACIÓN INICIAL
# ==========================================
st.set_page_config(page_title="Sistema de Condominio", page_icon="🏢", layout="wide")

def obtener_conexion():
    return sqlite3.connect("condominio.db")

def inicializar_db():
    conn = obtener_conexion()
    cursor = conn.cursor()

    # Tabla Configuración del Edificio (Permite editar datos desde la Web)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            rif TEXT,
            direccion TEXT,
            logo_url TEXT
        )
    """)

    # Cargar datos por defecto del edificio si está vacía
    cursor.execute("SELECT COUNT(*) FROM configuracion")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO configuracion (id, nombre, rif, direccion, logo_url)
            VALUES (1, 'Residencias El Roble', 'J-12345678-9', 'Av. Principal, Urb. Los Palos Grandes', 'https://cdn-icons-png.flaticon.com/512/25/25694.png')
        """)

    # Tabla Usuarios (Admin + 13 Apartamentos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            usuario TEXT PRIMARY KEY,
            clave TEXT,
            propietario TEXT,
            rol TEXT,
            apto TEXT
        )
    """)

    # Tabla Gastos Comunes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            concepto TEXT,
            monto REAL,
            proveedor TEXT
        )
    """)

    # Tabla Pagos a Proveedores (Egresos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagos_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            proveedor TEXT,
            concepto TEXT,
            monto REAL,
            referencia TEXT
        )
    """)

    # Tabla Pagos de Propietarios (Ingresos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagos_propietarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apto TEXT,
            fecha TEXT,
            referencia TEXT,
            monto REAL,
            metodo TEXT,
            estado TEXT DEFAULT 'Pendiente'
        )
    """)

    # Usuarios iniciales
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO usuarios VALUES ('admin', 'admin123', 'Administrador General', 'Admin', 'N/A')")
        
        aptos_6 = ["1A", "1B", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B"]
        for a in aptos_6:
            cursor.execute("INSERT INTO usuarios VALUES (?, '123456', ?, 'Propietario', ?)", 
                           (f"apto_{a.lower()}", f"Propietario Apt {a}", a))
        
        cursor.execute("INSERT INTO usuarios VALUES ('apto_2', '123456', 'Propietario Apt 2', 'Propietario', '2')")
        cursor.execute("INSERT INTO usuarios VALUES ('apto_7', '123456', 'Propietario Apt 7', 'Propietario', '7')")
        cursor.execute("INSERT INTO usuarios VALUES ('apto_ph', '123456', 'Propietario PH', 'Propietario', 'PH')")

    conn.commit()
    conn.close()

def obtener_datos_edificio():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT nombre, rif, direccion, logo_url FROM configuracion WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"nombre": row[0], "rif": row[1], "direccion": row[2], "logo_url": row[3]}
    return {"nombre": "Condominio", "rif": "N/A", "direccion": "", "logo_url": ""}

inicializar_db()

# Alícuotas
ALICUOTAS = {
    "1A": 0.06, "1B": 0.06,
    "3A": 0.06, "3B": 0.06,
    "4A": 0.06, "4B": 0.06,
    "5A": 0.06, "5B": 0.06,
    "6A": 0.06, "6B": 0.06,
    "2": 0.12,
    "7": 0.12,
    "PH": 0.16
}

# ==========================================
# 2. ENCABEZADO Y AUTENTICACIÓN
# ==========================================
datos_edificio = obtener_datos_edificio()

col_logo, col_header = st.columns([1, 4])
with col_logo:
    if datos_edificio["logo_url"]:
        st.image(datos_edificio["logo_url"], width=100)
with col_header:
    st.title(datos_edificio["nombre"])
    st.caption(f"**RIF:** {datos_edificio['rif']} | **Dirección:** {datos_edificio['direccion']}")

st.divider()

if "usuario_actual" not in st.session_state:
    st.session_state.usuario_actual = None

def validar_login(usr, pwd):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT usuario, clave, propietario, rol, apto FROM usuarios WHERE usuario = ? AND clave = ?", (usr, pwd))
    res = cursor.fetchone()
    conn.close()
    return res

if st.session_state.usuario_actual is None:
    st.subheader("🔐 Acceso a la Plataforma Web")

    col_form, col_info = st.columns([1, 1])
    with col_form:
        with st.form("form_login"):
            u_input = st.text_input("Usuario")
            p_input = st.text_input("Contraseña", type="password")
            btn_submit = st.form_submit_button("Entrar", type="primary")

            if btn_submit:
                user_data = validar_login(u_input, p_input)
                if user_data:
                    st.session_state.usuario_actual = {
                        "usuario": user_data[0],
                        "nombre": user_data[2],
                        "rol": user_data[3],
                        "apto": user_data[4]
                    }
                    st.success("¡Bienvenido!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
    
    with col_info:
        st.info("""
        🔑 **Credenciales de prueba:**
        - **Admin:** Usuario `admin` | Clave `admin123`
        - **Propietarios:** Clave genérica `123456`
        """)
    st.stop()

# Usuario en sesión
user = st.session_state.usuario_actual
st.sidebar.write(f"👤 **{user['nombre']}**")
st.sidebar.write(f"Rol: **{user['rol']}**")
if user["apto"] != "N/A":
    st.sidebar.write(f"Apartamento: **{user['apto']}**")

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state.usuario_actual = None
    st.rerun()

# ==========================================
# 3. VISTA ADMINISTRADOR
# ==========================================
if user["rol"] == "Admin":
    st.title("⚙️ Panel de Control de Administración")
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📝 Cargar Gastos", 
        "💳 Conciliar Pagos Propietarios", 
        "🚚 Pagos a Proveedores", 
        "📊 Resumen del Mes", 
        "👥 Usuarios y Claves",
        "🏢 Editar Datos del Edificio"
    ])

    # 1. CARGAR GASTOS
    with tab1:
        st.subheader("Registrar nuevo gasto común")
        with st.form("form_gasto", clear_on_submit=True):
            concepto = st.text_input("Concepto del gasto")
            proveedor = st.text_input("Nombre del Proveedor / Empresa")
            monto = st.number_input("Monto total ($)", min_value=0.01, step=10.0, format="%.2f")
            fecha = st.date_input("Fecha", datetime.now())
            
            if st.form_submit_button("Guardar Gasto", type="primary"):
                if concepto and monto > 0:
                    conn = obtener_conexion()
                    c = conn.cursor()
                    c.execute("INSERT INTO gastos (fecha, concepto, monto, proveedor) VALUES (?, ?, ?, ?)", 
                              (str(fecha), concepto, monto, proveedor))
                    conn.commit()
                    conn.close()
                    st.success("Gasto registrado correctamente.")
                    st.rerun()

    # 2. PAGOS DE PROPIETARIOS
    with tab2:
        st.subheader("Reportes de Pago Recibidos de los Propietarios")
        conn = obtener_conexion()
        df_pagos = pd.read_sql_query("SELECT * FROM pagos_propietarios ORDER BY id DESC", conn)
        conn.close()
        
        if not df_pagos.empty:
            st.dataframe(df_pagos, use_container_width=True)
        else:
            st.info("No hay pagos reportados por propietarios aún.")

    # 3. PAGOS A PROVEEDORES
    with tab3:
        st.subheader("Registrar Pago Saliente a Proveedor")
        with st.form("form_prov", clear_on_submit=True):
            prov = st.text_input("Proveedor")
            conc = st.text_input("Concepto del Pago")
            monto_p = st.number_input("Monto Pagado ($)", min_value=0.01, format="%.2f")
            ref_p = st.text_input("Número de Referencia Bancaria")
            fecha_p = st.date_input("Fecha de Pago", datetime.now())

            if st.form_submit_button("Registrar Egreso", type="primary"):
                if prov and monto_p > 0:
                    conn = obtener_conexion()
                    c = conn.cursor()
                    c.execute("INSERT INTO pagos_proveedores (fecha, proveedor, concepto, monto, referencia) VALUES (?, ?, ?, ?, ?)",
                              (str(fecha_p), prov, conc, monto_p, ref_p))
                    conn.commit()
                    conn.close()
                    st.success("Pago a proveedor guardado.")
                    st.rerun()
        
        st.divider()
        st.write("### Historial de Pagos a Proveedores")
        conn = obtener_conexion()
        df_prov = pd.read_sql_query("SELECT * FROM pagos_proveedores ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(df_prov, use_container_width=True)

    # 4. RESUMEN DEL MES
    with tab4:
        st.subheader("Cálculo de Cuotas y Alícuotas")
        conn = obtener_conexion()
        df_gastos = pd.read_sql_query("SELECT * FROM gastos", conn)
        conn.close()

        total_gastos = df_gastos["monto"].sum() if not df_gastos.empty else 0.0
        st.metric("Total Gastos del Mes", f"${total_gastos:,.2f} USD")
        
        if not df_gastos.empty:
            cuotas = []
            for apto, alicuota in ALICUOTAS.items():
                cuotas.append({
                    "Apartamento": apto,
                    "Alícuota": f"{int(alicuota*100)}%",
                    "Monto a Pagar ($)": round(total_gastos * alicuota, 2)
                })
            st.table(pd.DataFrame(cuotas))

    # 5. GESTIÓN DE USUARIOS Y CLAVES
    with tab5:
        st.subheader("Lista de Propietarios y Credenciales")
        conn = obtener_conexion()
        df_users = pd.read_sql_query("SELECT usuario, propietario, rol, apto, clave FROM usuarios", conn)
        conn.close()
        st.dataframe(df_users, use_container_width=True)

    # 6. CONFIGURACIÓN DE DATOS DEL EDIFICIO (NUEVA PESTAÑA)
    with tab6:
        st.subheader("Modificar Información General del Condominio")
        with st.form("form_edificio"):
            nuevo_nombre = st.text_input("Nombre del Edificio / Condominio", value=datos_edificio["nombre"])
            nuevo_rif = st.text_input("RIF / Documento de Identificación Fiscal", value=datos_edificio["rif"])
            nueva_direccion = st.text_area("Dirección Física", value=datos_edificio["direccion"])
            nuevo_logo = st.text_input("Enlace / URL de la Imagen o Logo", value=datos_edificio["logo_url"])

            if st.form_submit_button("Guardar Cambios", type="primary"):
                conn = obtener_conexion()
                c = conn.cursor()
                c.execute("""
                    UPDATE configuracion 
                    SET nombre = ?, rif = ?, direccion = ?, logo_url = ?
                    WHERE id = 1
                """, (nuevo_nombre, nuevo_rif, nueva_direccion, nuevo_logo))
                conn.commit()
                conn.close()
                st.success("¡Datos del edificio actualizados en la base de datos!")
                st.rerun()

# ==========================================
# 4. VISTA PROPIETARIO
# ==========================================
else:
    apto_user = user["apto"]
    alicuota_user = ALICUOTAS[apto_user]
    st.title(f"🏠 Panel del Apartamento {apto_user}")
    
    tab1, tab2, tab3 = st.tabs(["📄 Mi Recibo de Condominio", "💳 Reportar Pago", "🔑 Cambiar Mi Clave"])
    
    conn = obtener_conexion()
    df_gastos = pd.read_sql_query("SELECT * FROM gastos", conn)
    conn.close()

    total_gastos = df_gastos["monto"].sum() if not df_gastos.empty else 0.0
    cuota_personal = total_gastos * alicuota_user
    
    with tab1:
        st.subheader(f"Recibo Mensual - Apt {apto_user}")
        col1, col2 = st.columns(2)
        col1.metric("Alícuota Asignada", f"{int(alicuota_user * 100)}%")
        col2.metric("Total a Pagar", f"${cuota_personal:,.2f} USD")
        
        st.divider()
        st.write("### Desglose de Gastos Comunes")
        if not df_gastos.empty:
            df_gastos["Mi Cuota ($)"] = df_gastos["monto"] * alicuota_user
            st.dataframe(df_gastos[["fecha", "concepto", "proveedor", "monto", "Mi Cuota ($)"]], use_container_width=True)
        else:
            st.info("No hay gastos registrados este mes.")

    with tab2:
        st.subheader("Reportar Pago Realizado")
        with st.form("form_pago_prop", clear_on_submit=True):
            ref = st.text_input("Número de Referencia / Transacción")
            monto_pagado = st.number_input("Monto Pagado ($)", value=float(cuota_personal), format="%.2f")
            metodo = st.selectbox("Método de Pago", ["Transferencia Bancaria", "Pago Móvil", "Zelle", "Efectivo USD"])
            
            if st.form_submit_button("Enviar Reporte de Pago", type="primary"):
                if ref and monto_pagado > 0:
                    conn = obtener_conexion()
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO pagos_propietarios (apto, fecha, referencia, monto, metodo, estado)
                        VALUES (?, ?, ?, ?, ?, 'Pendiente')
                    """, (apto_user, str(datetime.now().strftime("%Y-%m-%d")), ref, monto_pagado, metodo))
                    conn.commit()
                    conn.close()
                    st.success("¡Pago reportado con éxito!")
                else:
                    st.warning("Escribe el número de referencia.")

    with tab3:
        st.subheader("Cambiar Contraseña de Acceso")
        with st.form("form_cambio_clave", clear_on_submit=True):
            nueva_clave = st.text_input("Nueva Contraseña", type="password")
            confirmar = st.text_input("Confirmar Nueva Contraseña", type="password")
            
            if st.form_submit_button("Actualizar Clave"):
                if nueva_clave and nueva_clave == confirmar:
                    conn = obtener_conexion()
                    c = conn.cursor()
                    c.execute("UPDATE usuarios SET clave = ? WHERE usuario = ?", (nueva_clave, user["usuario"]))
                    conn.commit()
                    conn.close()
                    st.success("Contraseña actualizada correctamente.")
                else:
                    st.error("Las contraseñas no coinciden.")