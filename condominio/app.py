import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse
import streamlit.components.v1 as components

st.set_page_config(page_title="Gestión de Condominio", page_icon="🏢", layout="wide")

DB_NAME = 'condominio.db'

# --- INICIALIZACIÓN AUTOMÁTICA DE BASE DE DATOS ---
def inicializar_bd():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS edificio (
        id INTEGER PRIMARY KEY,
        nombre TEXT,
        rif TEXT,
        direccion TEXT
    );

    CREATE TABLE IF NOT EXISTS apartamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero TEXT UNIQUE,
        propietario TEXT,
        telefono TEXT,
        alicuota REAL,
        clave TEXT DEFAULT '1234'
    );

    CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        periodo TEXT,
        descripcion TEXT,
        monto REAL,
        es_comun INTEGER,
        apto_no_comun TEXT
    );

    CREATE TABLE IF NOT EXISTS pagos_propietarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        periodo TEXT,
        mes INTEGER,
        anio INTEGER,
        apartamento_id INTEGER,
        apartamento TEXT,
        monto REAL,
        referencia TEXT,
        metodo TEXT,
        estado TEXT
    );

    CREATE TABLE IF NOT EXISTS pagos_proveedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        proveedor TEXT,
        rif_proveedor TEXT,
        concepto TEXT,
        monto REAL,
        num_factura TEXT
    );
    """)

    # Datos iniciales del edificio si está vacío
    cursor.execute("SELECT COUNT(*) FROM edificio")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO edificio VALUES (1, 'RESIDENCIAS EL PARQUE', 'J-12345678-9', 'Av. Principal, Calle 4')")

    # Registro de apartamentos con clave por defecto '1234'
    cursor.execute("SELECT COUNT(*) FROM apartamentos")
    if cursor.fetchone()[0] == 0:
        aptos_data = [
            ('1A', 'Carlos Mendoza', '+584141234567', 0.06, '1234'),
            ('1B', 'María Rodríguez', '+584122345678', 0.06, '1234'),
            ('2',  'Alejandro Silva', '+584163456789', 0.12, '1234'),
            ('3A', 'Patricia Gómez',  '+584244567890', 0.06, '1234'),
            ('3B', 'Roberto Fernández','+584145678901', 0.06, '1234'),
            ('4A', 'Elena Benítez',   '+584126789012', 0.06, '1234'),
            ('4B', 'Javier Morales',  '+584167890123', 0.06, '1234'),
            ('5A', 'Carmen Castillo', '+584248901234', 0.06, '1234'),
            ('5B', 'Diego Torres',    '+584149012345', 0.06, '1234'),
            ('6A', 'Sofía Vargas',    '+584120123456', 0.06, '1234'),
            ('6B', 'Gabriel Ruiz',    '+584161234567', 0.06, '1234'),
            ('7',  'Ricardo Alarcón', '+584242345678', 0.12, '1234'),
            ('PH', 'Fernando Delgado','+584143456789', 0.16, '1234')
        ]
        cursor.executemany("INSERT INTO apartamentos (numero, propietario, telefono, alicuota, clave) VALUES (?, ?, ?, ?, ?)", aptos_data)

    conn.commit()
    conn.close()

inicializar_bd()

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

conn = get_connection()

def get_edificio():
    return pd.read_sql("SELECT * FROM edificio WHERE id=1", conn).iloc[0]

def get_apartamentos():
    return pd.read_sql("SELECT * FROM apartamentos ORDER BY id", conn)

# --- SISTEMA DE AUTENTICACIÓN / INICIO DE SESIÓN ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.rol = None
    st.session_state.apto_usuario = None

def login():
    st.title("🔑 Control de Acceso — Condominio")
    rol_seleccionado = st.radio("Seleccione el Tipo de Usuario:", ["Propietario / Vecino", "Administrador"])
    
    if rol_seleccionado == "Administrador":
        clave_admin = st.text_input("Contraseña de Administrador:", type="password")
        if st.button("Ingresar como Administrador"):
            # Clave predeterminada de Administrador
            if clave_admin == "admin123":
                st.session_state.autenticado = True
                st.session_state.rol = "Admin"
                st.rerun()
            else:
                st.error("Contraseña de administrador incorrecta (Clave por defecto: admin123).")
                
    else:
        aptos_df = get_apartamentos()
        apto_sel = st.selectbox("Seleccione su Apartamento:", aptos_df['numero'].tolist())
        clave_vecino = st.text_input("Contraseña de Propietario:", type="password")
        
        if st.button("Ingresar"):
            apto_info = aptos_df[aptos_df['numero'] == apto_sel].iloc[0]
            # Validar la clave grabada en la base de datos (por defecto '1234')
            if str(clave_vecino) == str(apto_info['clave']):
                st.session_state.autenticado = True
                st.session_state.rol = "Vecino"
                st.session_state.apto_usuario = apto_sel
                st.rerun()
            else:
                st.error("Contraseña incorrecta (Clave por defecto para todos los aptos: 1234).")

if not st.session_state.autenticado:
    login()
    st.stop()

# --- BARRA LATERAL CON BOTÓN DE CERRAR SESIÓN ---
st.sidebar.title("🏢 Menú Principal")
st.sidebar.write(f"**Usuario:** {st.session_state.rol}")
if st.session_state.apto_usuario:
    st.sidebar.write(f"**Apartamento:** {st.session_state.apto_usuario}")

if st.sidebar.button("🔒 Cerrar Sesión"):
    st.session_state.autenticado = False
    st.session_state.rol = None
    st.session_state.apto_usuario = None
    st.rerun()

# --- NAVEGACIÓN SEGÚN ROL ---
if st.session_state.rol == "Admin":
    opciones_menu = [
        "1. Registrar Gastos del Mes",
        "2. Generar Recibo & WhatsApp / PDF",
        "3. Registrar Pago de Apartamento",
        "4. Reporte de Morosidad",
        "5. Reporte de Proveedores"
    ]
else:
    opciones_menu = [
        "2. Generar Recibo & WhatsApp / PDF"
    ]

opcion = st.sidebar.radio("Navegación:", opciones_menu)
edificio = get_edificio()

# --- MÓDULO 1: GASTOS (Solo Admin) ---
if opcion == "1. Registrar Gastos del Mes":
    st.header("📝 Cargar Gastos Comunes y No Comunes")
    
    col1, col2 = st.columns(2)
    with col1:
        periodo = st.text_input("Período (Año-Mes):", "2026-05")
        descripcion = st.text_input("Descripción del Gasto:")
        monto = st.number_input("Monto ($):", min_value=0.0, step=10.0)
    
    with col2:
        tipo_gasto = st.selectbox("Tipo de Gasto:", ["Común (Aplica a todos por alícuota)", "No Común (Aplica a un solo Apto)"])
        apto_destino = None
        if "No Común" in tipo_gasto:
            aptos = get_apartamentos()['numero'].tolist()
            apto_destino = st.selectbox("Apartamento Responsable:", aptos)
            
    if st.button("💾 Guardar Gasto"):
        es_comun = 1 if "Común" in tipo_gasto else 0
        cursor = conn.cursor()
        cursor.execute("INSERT INTO gastos (periodo, descripcion, monto, es_comun, apto_no_comun) VALUES (?,?,?,?,?)",
                       (periodo, descripcion, monto, es_comun, apto_destino))
        conn.commit()
        st.success("Gasto registrado con éxito.")

    st.subheader(f"Gastos Registrados en {periodo}")
    st.dataframe(pd.read_sql(f"SELECT * FROM gastos WHERE periodo='{periodo}'", conn), use_container_width=True)

# --- MÓDULO 2: RECIBOS & WHATSAPP / IMPRESIÓN PDF ---
elif opcion == "2. Generar Recibo & WhatsApp / PDF":
    st.header("📄 Generador de Recibos de Condominio")
    
    col1, col2 = st.columns(2)
    with col1:
        periodo = st.text_input("Período a consultar (Año-Mes):", "2026-05")
    with col2:
        aptos_df = get_apartamentos()
        if st.session_state.rol == "Admin":
            apto_sel = st.selectbox("Seleccionar Apartamento:", aptos_df['numero'].tolist())
        else:
            apto_sel = st.session_state.apto_usuario
            st.info(f"Consultando recibo asignado al Apartamento: **{apto_sel}**")
        
    apto_info = aptos_df[aptos_df['numero'] == apto_sel].iloc[0]
    
    gastos_comunes = pd.read_sql(f"SELECT * FROM gastos WHERE periodo='{periodo}' AND es_comun=1", conn)
    gastos_no_comunes = pd.read_sql(f"SELECT * FROM gastos WHERE periodo='{periodo}' AND es_comun=0 AND apto_no_comun='{apto_sel}'", conn)
    
    total_comun = gastos_comunes['monto'].sum() if not gastos_comunes.empty else 0.0
    cuota_comun = total_comun * apto_info['alicuota']
    total_no_comun = gastos_no_comunes['monto'].sum() if not gastos_no_comunes.empty else 0.0
    
    monto_total = cuota_comun + total_no_comun

    pago_registrado = pd.read_sql(
        f"SELECT * FROM pagos_propietarios WHERE apartamento='{apto_sel}' AND periodo='{periodo}'", conn
    )
    estado_pago = "PAGADO" if not pago_registrado.empty else "PENDIENTE"
    
    st.markdown("---")
    st.subheader(f"🏢 {edificio['nombre']} — RIF: {edificio['rif']}")
    st.write(f"**Propietario:** {apto_info['propietario']} | **Apartamento:** {apto_sel} | **Alícuota:** {apto_info['alicuota']*100:.1f}%")
    st.write(f"**Teléfono:** {apto_info['telefono']} | **Estatus:** `{estado_pago}`")
    
    st.write("### Gastos Comunes del Edificio")
    st.dataframe(gastos_comunes[['descripcion', 'monto']], use_container_width=True)
    
    if not gastos_no_comunes.empty:
        st.write("### Gastos No Comunes")
        st.dataframe(gastos_no_comunes[['descripcion', 'monto']], use_container_width=True)
        
    # Recuadro resaltado con el monto a pagar
    st.markdown(f'''
        <div style="background-color: #eff6ff; border: 2px dashed #2563eb; padding: 18px; border-radius: 8px; text-align: center; margin: 15px 0;">
            <h4 style="color: #1e40af; margin: 0;">MONTO TOTAL A CANCELAR ({apto_sel})</h4>
            <h1 style="color: #1d4ed8; margin: 5px 0;">${monto_total:.2f}</h1>
        </div>
    ''', unsafe_allow_html=True)
    
    col_pdf, col_wa = st.columns(2)
    
    with col_pdf:
        html_recibo = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; }}
                .box {{ background-color: #eff6ff; border: 2px dashed #2563eb; padding: 15px; text-align: center; border-radius: 8px; margin-top: 15px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #1e3a8a; color: white; }}
            </style>
        </head>
        <body>
            <h2>{edificio['nombre']} - RIF: {edificio['rif']}</h2>
            <p><b>Propietario:</b> {apto_info['propietario']} | <b>Apartamento:</b> {apto_sel} | <b>Alícuota:</b> {apto_info['alicuota']*100:.1f}%</p>
            <p><b>Período:</b> {periodo}</p>
            <h3>Gastos Comunes Totales: ${total_comun:.2f}</h3>
            <h3>Cuota por Alícuota: ${cuota_comun:.2f}</h3>
            <div class="box">
                <h3 style="color: #1e40af; margin: 0;">TOTAL A CANCELAR: ${monto_total:.2f}</h3>
            </div>
            <br>
            <button onclick="window.print()" style="padding: 10px 20px; background-color: #2563eb; color: white; border: none; border-radius: 5px; cursor: pointer;">🖨️ Imprimir / Guardar en PDF</button>
        </body>
        </html>
        """
        components.html(html_recibo, height=350)
        
    with col_wa:
        msg_wa = f'''🏢 *{edificio["nombre"]}*
📄 *RIF:* {edificio["rif"]}
🗓 *Recibo de Condominio - {periodo}*
----------------------------------------
👤 *Propietario:* {apto_info["propietario"]}
🏠 *Apartamento:* {apto_sel} | 📊 *Alícuota:* {apto_info["alicuota"]*100:.1f}%
📞 *Teléfono:* {apto_info["telefono"]}
----------------------------------------
🔹 *Gastos Comunes Total:* ${total_comun:.2f}
🔹 *Tu Cuota por Alícuota:* ${cuota_comun:.2f}
🔧 *Gastos No Comunes:* ${total_no_comun:.2f}
----------------------------------------
┌──────────────────────────────────────┐
│ 💵 *TOTAL A CANCELAR:* *${monto_total:.2f}*
└──────────────────────────────────────┘
----------------------------------------
💳 Por favor remita su comprobante por este chat.'''

        phone_clean = apto_info['telefono'].replace("+", "").replace(" ", "")
        encoded_msg = urllib.parse.quote(msg_wa)
        wa_url = f"https://wa.me/{phone_clean}?text={encoded_msg}"
        st.markdown(f"[📲 Enviar por WhatsApp]({wa_url})", unsafe_allow_html=True)

# --- MÓDULO 3: REGISTRO DE PAGOS (Solo Admin) ---
elif opcion == "3. Registrar Pago de Apartamento":
    st.header("💳 Registrar Pago Recibido")
    col1, col2 = st.columns(2)
    with col1:
        periodo = st.text_input("Período a pagar (Año-Mes):", "2026-05")
        aptos_df = get_apartamentos()
        apto_sel = st.selectbox("Apartamento:", aptos_df['numero'].tolist())
        fecha = st.date_input("Fecha del Pago")
    with col2:
        monto = st.number_input("Monto Recibido ($):", min_value=0.0)
        referencia = st.text_input("Número de Referencia:")
        metodo = st.selectbox("Método de Pago:", ["Pago Móvil", "Transferencia", "Zelle", "Efectivo"])
        
    if st.button("💾 Registrar Pago"):
        apto_id = int(aptos_df[aptos_df['numero'] == apto_sel].iloc[0]['id'])
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pagos_propietarios 
            (fecha, periodo, apartamento_id, apartamento, monto, referencia, metodo, estado) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(fecha), periodo, apto_id, apto_sel, monto, referencia, metodo, 'PAGADO'))
        conn.commit()
        st.success("Pago registrado con éxito.")

# --- MÓDULO 4: REPORTE DE MOROSIDAD (Solo Admin) ---
elif opcion == "4. Reporte de Morosidad":
    st.header("📊 Reporte de Morosidad")
    periodo = st.text_input("Filtrar por Período (Año-Mes):", "2026-05")
    
    aptos_df = get_apartamentos()
    gastos_comunes = pd.read_sql(f"SELECT SUM(monto) as total FROM gastos WHERE periodo='{periodo}' AND es_comun=1", conn).iloc[0]['total'] or 0.0
    pagos_df = pd.read_sql(f"SELECT apartamento, SUM(monto) as pagado FROM pagos_propietarios WHERE periodo='{periodo}' GROUP BY apartamento", conn)
    
    reporte = []
    for _, row in aptos_df.iterrows():
        a_num = row['numero']
        alicuota = row['alicuota']
        cuota = gastos_comunes * alicuota
        no_com = pd.read_sql(f"SELECT SUM(monto) as total FROM gastos WHERE periodo='{periodo}' AND es_comun=0 AND apto_no_comun='{a_num}'", conn).iloc[0]['total'] or 0.0
        deben = cuota + no_com
        
        pagado_row = pagos_df[pagos_df['apartamento'] == a_num]
        pagado = pagado_row.iloc[0]['pagado'] if not pagado_row.empty else 0.0
        saldo = deben - pagado
        estatus = "✅ PAGADO" if saldo <= 0.01 else "❌ MOROSO"
        
        reporte.append({
            "Apto": a_num,
            "Propietario": row['propietario'],
            "Alícuota": f"{alicuota*100:.1f}%",
            "Monto Facturado": round(deben, 2),
            "Monto Pagado": round(pagado, 2),
            "Saldo Pendiente": round(saldo, 2),
            "Estatus": estatus
        })
        
    st.dataframe(pd.DataFrame(reporte), use_container_width=True)

# --- MÓDULO 5: PROVEEDORES (Solo Admin) ---
elif opcion == "5. Reporte de Proveedores":
    st.header("💸 Reporte de Pagos a Proveedores por Período")
    col1, col2 = st.columns(2)
    with col1:
        f_inicio = st.date_input("Fecha Desde:", pd.to_datetime("2026-05-01"))
    with col2:
        f_fin = st.date_input("Fecha Hasta:", pd.to_datetime("2026-05-31"))
        
    prov_df = pd.read_sql(f"SELECT fecha, proveedor, rif_proveedor, concepto, monto, num_factura FROM pagos_proveedores WHERE fecha BETWEEN '{f_inicio}' AND '{f_fin}'", conn)
    st.dataframe(prov_df, use_container_width=True)
    st.metric("Total Pagado a Proveedores", f"${prov_df['monto'].sum():.2f}")
