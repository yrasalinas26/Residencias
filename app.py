import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse
import io

# Importaciones para generación de PDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

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
        alicuota REAL
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

    # Registro de los 13 apartamentos si están vacíos
    cursor.execute("SELECT COUNT(*) FROM apartamentos")
    if cursor.fetchone()[0] == 0:
        aptos_data = [
            ('1A', 'Carlos Mendoza', '+584141234567', 0.06),
            ('1B', 'María Rodríguez', '+584122345678', 0.06),
            ('2',  'Alejandro Silva', '+584163456789', 0.12),
            ('3A', 'Patricia Gómez',  '+584244567890', 0.06),
            ('3B', 'Roberto Fernández','+584145678901', 0.06),
            ('4A', 'Elena Benítez',   '+584126789012', 0.06),
            ('4B', 'Javier Morales',  '+584167890123', 0.06),
            ('5A', 'Carmen Castillo', '+584248901234', 0.06),
            ('5B', 'Diego Torres',    '+584149012345', 0.06),
            ('6A', 'Sofía Vargas',    '+584120123456', 0.06),
            ('6B', 'Gabriel Ruiz',    '+584161234567', 0.06),
            ('7',  'Ricardo Alarcón', '+584242345678', 0.12),
            ('PH', 'Fernando Delgado','+584143456789', 0.16)
        ]
        cursor.executemany("INSERT INTO apartamentos (numero, propietario, telefono, alicuota) VALUES (?, ?, ?, ?)", aptos_data)

    conn.commit()
    conn.close()

# Ejecutar inicialización
inicializar_bd()

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

conn = get_connection()

def get_edificio():
    return pd.read_sql("SELECT * FROM edificio WHERE id=1", conn).iloc[0]

def get_apartamentos():
    return pd.read_sql("SELECT * FROM apartamentos ORDER BY id", conn)

# --- GENERADOR DE PDF ---
def generar_pdf_recibo(edificio, apto_info, periodo, gastos_comunes, gastos_no_comunes, cuota_comun, total_no_comun, monto_total):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, leading=18, alignment=1, textColor=colors.HexColor('#1E3A8A'))
    sub_style = ParagraphStyle('SubStyle', parent=styles['Normal'], fontSize=10, leading=12, alignment=1, textColor=colors.HexColor('#4B5563'))
    
    story.append(Paragraph(f"<b>{edificio['nombre']}</b>", title_style))
    story.append(Paragraph(f"RIF: {edificio['rif']} | {edificio['direccion']}", sub_style))
    story.append(Spacer(1, 15))

    info_data = [
        [f"<b>Propietario:</b> {apto_info['propietario']}", f"<b>Apartamento:</b> {apto_info['numero']}"],
        [f"<b>Teléfono:</b> {apto_info['telefono']}", f"<b>Alícuota:</b> {apto_info['alicuota']*100:.1f}%"],
        [f"<b>Período:</b> {periodo}", ""]
    ]
    t_info = Table(info_data, colWidths=[300, 240])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F3F4F6')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 15))

    story.append(Paragraph("<b>Detalle de Gastos Comunes</b>", styles['Heading3']))
    comunes_data = [["Descripción", "Monto ($)"]]
    for _, r in gastos_comunes.iterrows():
        comunes_data.append([r['descripcion'], f"${r['monto']:.2f}"])
    comunes_data.append(["TOTAL GASTOS COMUNES EDIFICIO", f"${gastos_comunes['monto'].sum() if not gastos_comunes.empty else 0:.2f}"])
    comunes_data.append(["CUOTA CORRESPONDIENTE SEGÚN ALÍCUOTA", f"${cuota_comun:.2f}"])

    t_comunes = Table(comunes_data, colWidths=[400, 140])
    t_comunes.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_comunes)
    story.append(Spacer(1, 15))

    if not gastos_no_comunes.empty:
        story.append(Paragraph("<b>Detalle de Gastos No Comunes</b>", styles['Heading3']))
        nocom_data = [["Descripción", "Monto ($)"]]
        for _, r in gastos_no_comunes.iterrows():
            nocom_data.append([r['descripcion'], f"${r['monto']:.2f}"])
        nocom_data.append(["TOTAL GASTOS NO COMUNES", f"${total_no_comun:.2f}"])
        
        t_nocom = Table(nocom_data, colWidths=[400, 140])
        t_nocom.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4B5563')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(t_nocom)
        story.append(Spacer(1, 15))

    resalte_data = [
        ["MONTO TOTAL A CANCELAR"],
        [f"${monto_total:.2f}"]
    ]
    t_resalte = Table(resalte_data, colWidths=[540])
    t_resalte.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#EFF6FF')),
        ('BORDER', (0,0), (-1,-1), 2, colors.HexColor('#2563EB')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TEXTCOLOR', (0,0), (0,0), colors.HexColor('#1E40AF')),
        ('TEXTCOLOR', (0,1), (0,1), colors.HexColor('#1D4ED8')),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (0,0), 12),
        ('FONTSIZE', (0,1), (0,1), 22),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t_resalte)

    doc.build(story)
    buffer.seek(0)
    return buffer

# --- ESTRUCTURA DE PESTAÑAS Y MENÚ ---
st.title("🏢 Sistema de Gestión de Condominio")
st.sidebar.title("Menú Principal")

opcion = st.sidebar.radio("Navegación:", [
    "1. Registrar Gastos del Mes",
    "2. Generar Recibo & WhatsApp / PDF",
    "3. Registrar Pago de Apartamento",
    "4. Reporte de Morosidad",
    "5. Reporte de Proveedores"
])

edificio = get_edificio()

# --- MÓDULO 1: GASTOS ---
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

# --- MÓDULO 2: RECIBOS & WHATSAPP / PDF ---
elif opcion == "2. Generar Recibo & WhatsApp / PDF":
    st.header("📄 Generador de Recibos de Condominio")
    
    col1, col2 = st.columns(2)
    with col1:
        periodo = st.text_input("Período a consultar (Año-Mes):", "2026-05")
    with col2:
        aptos_df = get_apartamentos()
        apto_sel = st.selectbox("Seleccionar Apartamento:", aptos_df['numero'].tolist())
        
    apto_info = aptos_df[aptos_df['numero'] == apto_sel].iloc[0]
    
    # Consultas de gastos
    gastos_comunes = pd.read_sql(f"SELECT * FROM gastos WHERE periodo='{periodo}' AND es_comun=1", conn)
    gastos_no_comunes = pd.read_sql(f"SELECT * FROM gastos WHERE periodo='{periodo}' AND es_comun=0 AND apto_no_comun='{apto_sel}'", conn)
    
    total_comun = gastos_comunes['monto'].sum() if not gastos_comunes.empty else 0.0
    cuota_comun = total_comun * apto_info['alicuota']
    total_no_comun = gastos_no_comunes['monto'].sum() if not gastos_no_comunes.empty else 0.0
    
    monto_total = cuota_comun + total_no_comun

    # Consulta segura del estado del pago
    pago_registrado = pd.read_sql(
        f"SELECT * FROM pagos_propietarios WHERE apartamento='{apto_sel}' AND periodo='{periodo}'", conn
    )
    
    estado_pago = "PAGADO" if not pago_registrado.empty else "PENDIENTE"
    
    st.markdown("---")
    st.subheader(f"🏢 {edificio['nombre']} — RIF: {edificio['rif']}")
    st.write(f"**Propietario:** {apto_info['propietario']} | **Apartamento:** {apto_sel} | **Alícuota:** {apto_info['alicuota']*100:.1f}%")
    st.write(f"**Teléfono:** {apto_info['telefono']} | **Estado de Pago:** `{estado_pago}`")
    
    st.write("### Gastos Comunes del Edificio")
    st.dataframe(gastos_comunes[['descripcion', 'monto']], use_container_width=True)
    
    if not gastos_no_comunes.empty:
        st.write("### Gastos No Comunes")
        st.dataframe(gastos_no_comunes[['descripcion', 'monto']], use_container_width=True)
        
    # Recuadro resaltado para el monto final
    st.markdown(f'''
        <div style="background-color: #eff6ff; border: 2px dashed #2563eb; padding: 18px; border-radius: 8px; text-align: center; margin: 15px 0;">
            <h4 style="color: #1e40af; margin: 0;">MONTO TOTAL A CANCELAR ({apto_sel})</h4>
            <h1 style="color: #1d4ed8; margin: 5px 0;">${monto_total:.2f}</h1>
        </div>
    ''', unsafe_allow_html=True)
    
    col_pdf, col_wa = st.columns(2)
    
    with col_pdf:
        # Botón de Descarga en PDF
        pdf_bytes = generar_pdf_recibo(edificio, apto_info, periodo, gastos_comunes, gastos_no_comunes, cuota_comun, total_no_comun, monto_total)
        st.download_button(
            label="📥 Descargar Recibo en PDF",
            data=pdf_bytes,
            file_name=f"Recibo_{apto_sel}_{periodo}.pdf",
            mime="application/pdf"
        )
        
    with col_wa:
        # Enlace a WhatsApp
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

# --- MÓDULO 3: REGISTRO DE PAGOS ---
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

# --- MÓDULO 4: REPORTE DE MOROSIDAD ---
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

# --- MÓDULO 5: PROVEEDORES ---
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
