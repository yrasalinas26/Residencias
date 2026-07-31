import sqlite3
import os
import streamlit as st
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ==========================================
# 1. BASE DE DATOS Y CONFIGURACIÓN INICIAL
# ==========================================
DB_NAME = "condominio.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabla de Apartamentos (incluye clave individual)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS apartamentos (
            id TEXT PRIMARY KEY,
            propietario TEXT,
            telefono TEXT,
            alicuota REAL,
            clave TEXT DEFAULT 'roble123'
        )
    ''')
    
    # Intentar agregar columna 'clave' por si la tabla ya existía sin ella
    try:
        cursor.execute("ALTER TABLE apartamentos ADD COLUMN clave TEXT DEFAULT 'roble123'")
    except sqlite3.OperationalError:
        pass

    # Tabla de Gastos Comunes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos_comunes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes INTEGER,
            anio INTEGER,
            descripcion TEXT,
            monto REAL
        )
    ''')
    
    # Tabla de Gastos No Comunes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos_no_comunes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes INTEGER,
            anio INTEGER,
            apartamento_id TEXT,
            descripcion TEXT,
            monto REAL
        )
    ''')
    
    # Tabla de Proveedores
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            rif TEXT,
            contacto TEXT
        )
    ''')
    
    # Tabla de Pagos a Proveedores
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pagos_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor_id INTEGER,
            fecha TEXT,
            descripcion TEXT,
            monto REAL,
            metodo TEXT
        )
    ''')
    
    # Tabla de Pagos de Propietarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pagos_propietarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apartamento_id TEXT,
            mes INTEGER,
            anio INTEGER,
            fecha TEXT,
            monto REAL,
            referencia TEXT,
            estado TEXT DEFAULT 'Pendiente'
        )
    ''')

    # Cargar los 13 apartamentos con sus alícuotas correspondientes
    cursor.execute("SELECT COUNT(*) FROM apartamentos")
    if cursor.fetchone()[0] == 0:
        apts_iniciales = [
            ('1A', 'Propietario 1A', '+584140000000', 0.06, 'roble123'),
            ('1B', 'Propietario 1B', '+584140000000', 0.06, 'roble123'),
            ('3A', 'Propietario 3A', '+584140000000', 0.06, 'roble123'),
            ('3B', 'Propietario 3B', '+584140000000', 0.06, 'roble123'),
            ('4A', 'Propietario 4A', '+584140000000', 0.06, 'roble123'),
            ('4B', 'Propietario 4B', '+584140000000', 0.06, 'roble123'),
            ('5A', 'Propietario 5A', '+584140000000', 0.06, 'roble123'),
            ('5B', 'Propietario 5B', '+584140000000', 0.06, 'roble123'),
            ('6A', 'Propietario 6A', '+584140000000', 0.06, 'roble123'),
            ('6B', 'Propietario 6B', '+584140000000', 0.06, 'roble123'),
            ('2',  'Propietario 2',  '+584140000000', 0.12, 'roble123'),
            ('7',  'Propietario 7',  '+584140000000', 0.12, 'roble123'),
            ('PH', 'Propietario PH', '+584140000000', 0.16, 'roble123')
        ]
        cursor.executemany("INSERT INTO apartamentos VALUES (?,?,?,?,?)", apts_iniciales)
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 2. GENERACIÓN DE RECIBOS EN PDF
# ==========================================
def generar_pdf_recibo(apt_id, mes, anio, edif_nombre, edif_rif, logo_path, estado_pago="Pendiente"):
    conn = get_db_connection()
    apt = conn.execute("SELECT * FROM apartamentos WHERE id = ?", (apt_id,)).fetchone()
    gastos_comunes = conn.execute("SELECT * FROM gastos_comunes WHERE mes = ? AND anio = ?", (mes, anio)).fetchall()
    gastos_no_comunes = conn.execute("SELECT * FROM gastos_no_comunes WHERE mes = ? AND anio = ? AND apartamento_id = ?", (mes, anio, apt_id)).fetchall()
    conn.close()

    filename = f"Recibo_{apt_id}_{mes}_{anio}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()

    header_data = []
    info_text = f"<b>{edif_nombre}</b><br/>RIF: {edif_rif}<br/><b>RECIBO DE CONDOMINIO</b><br/>Período: {mes}/{anio}"
    p_info = Paragraph(info_text, styles['Normal'])
    
    if logo_path and os.path.exists(logo_path):
        img = Image(logo_path, width=70, height=70)
        header_data.append([img, p_info])
    else:
        header_data.append(["", p_info])

    header_table = Table(header_data, colWidths=[90, 450])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (0,0), (-1,-1), 'LEFT')
    ]))
    story.append(header_table)
    story.append(Spacer(1, 15))

    p_datos = f"<b>Apartamento:</b> {apt['id']} | <b>Propietario:</b> {apt['propietario']} | <b>Alícuota:</b> {apt['alicuota']*100:.1f}%"
    story.append(Paragraph(p_datos, styles['Normal']))
    story.append(Spacer(1, 10))

    if estado_pago == "Verificado":
        p_estado = Paragraph("<font color='#2E7D32'><b>STATUS: CANCELADO / VERIFICADO ✅</b></font>", styles['Heading2'])
    else:
        p_estado = Paragraph("<font color='#C62828'><b>STATUS: PENDIENTE DE PAGO ⏳</b></font>", styles['Heading2'])
    story.append(p_estado)
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b><u>Gastos Comunes del Mes</u></b>", styles['Heading3']))
    t_comunes_data = [["Descripción", "Monto Total", f"Cuota Apt ({apt['alicuota']*100:.1f}%)"]]
    total_comun_global = 0
    total_comun_apt = 0

    for g in gastos_comunes:
        m_apt = g['monto'] * apt['alicuota']
        total_comun_global += g['monto']
        total_comun_apt += m_apt
        t_comunes_data.append([g['descripcion'], f"${g['monto']:.2f}", f"${m_apt:.2f}"])

    t_comunes_data.append(["TOTAL GASTOS COMUNES", f"${total_comun_global:.2f}", f"${total_comun_apt:.2f}"])
    
    t_comunes = Table(t_comunes_data, colWidths=[300, 120, 120])
    t_comunes.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0288D1")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold')
    ]))
    story.append(t_comunes)
    story.append(Spacer(1, 15))

    total_no_comun = 0
    if gastos_no_comunes:
        story.append(Paragraph("<b><u>Gastos No Comunes (Individuales)</u></b>", styles['Heading3']))
        t_nocomun_data = [["Descripción", "Monto"]]
        for gnc in gastos_no_comunes:
            total_no_comun += gnc['monto']
            t_nocomun_data.append([gnc['descripcion'], f"${gnc['monto']:.2f}"])
        t_nocomun_data.append(["TOTAL GASTOS NO COMUNES", f"${total_no_comun:.2f}"])

        t_nocomun = Table(t_nocomun_data, colWidths=[420, 120])
        t_nocomun.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#7CB342")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold')
        ]))
        story.append(t_nocomun)
        story.append(Spacer(1, 15))

    total_pagar = total_comun_apt + total_no_comun
    total_style = ParagraphStyle('TotalStyle', parent=styles['Normal'], fontSize=12, leading=14, textColor=colors.HexColor("#D32F2F"))
    p_total = Paragraph(f"<b>TOTAL A CANCELAR: ${total_pagar:.2f}</b>", total_style)
    story.append(p_total)

    doc.build(story)
    return filename, total_pagar

# ==========================================
# 3. INTERFAZ Y SISTEMA DE AUTENTICACIÓN
# ==========================================
st.set_page_config(page_title="Residencias El Roble", layout="wide")

if 'usuario_rol' not in st.session_state:
    st.session_state['usuario_rol'] = None
if 'apt_login' not in st.session_state:
    st.session_state['apt_login'] = None

# Pantalla de Login si no ha iniciado sesión
if st.session_state['usuario_rol'] is None:
    st.title("🏢 Sistema de Condominio - Residencias El Roble")
    st.subheader("Inicio de Sesión")
    
    tipo_ingreso = st.radio("Seleccione el tipo de acceso:", ["Propietario / Vecino", "Administrador"])
    
    if tipo_ingreso == "Administrador":
        pass_admin = st.text_input("Contraseña de Administrador", type="password")
        if st.button("Ingresar como Administrador"):
            if pass_admin == "admin123":
                st.session_state['usuario_rol'] = 'admin'
                st.success("¡Bienvenido Administrador!")
                st.rerun()
            else:
                st.error("Contraseña de administrador incorrecta.")
                
    else:
        conn = get_db_connection()
        apts = [r['id'] for r in conn.execute("SELECT id FROM apartamentos").fetchall()]
        conn.close()
        
        apt_sel = st.selectbox("Seleccione su Apartamento:", apts)
        pass_prop = st.text_input("Contraseña del Apartamento", type="password")
        
        if st.button("Ingresar como Propietario"):
            conn = get_db_connection()
            user = conn.execute("SELECT * FROM apartamentos WHERE id = ? AND clave = ?", (apt_sel, pass_prop)).fetchone()
            conn.close()
            
            if user:
                st.session_state['usuario_rol'] = 'propietario'
                st.session_state['apt_login'] = apt_sel
                st.success(f"¡Bienvenido Propietario del Apt {apt_sel}!")
                st.rerun()
            else:
                st.error("Contraseña incorrecta para este apartamento.")

else:
    # Muestra el botón de Cerrar Sesión en la barra lateral
    st.sidebar.write(f"**Sesión:** {st.session_state['usuario_rol'].upper()} " + (f"({st.session_state['apt_login']})" if st.session_state['apt_login'] else ""))
    if st.sidebar.button("🔴 Cerrar Sesión"):
        st.session_state['usuario_rol'] = None
        st.session_state['apt_login'] = None
        st.rerun()

    # MENÚ PARA ADMINISTRADOR
    if st.session_state['usuario_rol'] == 'admin':
        st.sidebar.title("🏢 Panel Administrador")
        opcion = st.sidebar.radio("Opciones de Gestión:", [
            "Configuración Edificio",
            "Gestión Apartamentos",
            "Registrar Gastos",
            "Generar Recibos y WhatsApp",
            "Verificar Pagos",
            "Proveedores y Sus Pagos",
            "Reportes Generales"
        ])

        if opcion == "Configuración Edificio":
            st.header("⚙️ Configuración del Edificio")
            nombre_edif = st.text_input("Nombre del Edificio", value=st.session_state.get('edif_nombre', 'Residencias El Roble'))
            rif_edif = st.text_input("RIF del Edificio", value=st.session_state.get('edif_rif', 'J-12345678-9'))
            logo = st.file_uploader("Cargar Logo (PNG o JPG)", type=["png", "jpg", "jpeg"])
            
            if logo:
                with open("logo_temp.png", "wb") as f:
                    f.write(logo.getbuffer())
                st.success("Logo cargado.")
                st.image("logo_temp.png", width=150)
            
            if st.button("Guardar Configuración"):
                st.session_state['edif_nombre'] = nombre_edif
                st.session_state['edif_rif'] = rif_edif
                st.success("Datos actualizados.")

        elif opcion == "Gestión Apartamentos":
            st.header("🏠 Gestión de Apartamentos y Propietarios")
            conn = get_db_connection()
            apts = conn.execute("SELECT id, propietario, telefono, alicuota FROM apartamentos").fetchall()
            conn.close()
            
            tabla_apts = [{"Apt": a['id'], "Propietario": a['propietario'], "Teléfono": a['telefono'], "Alícuota (%)": f"{a['alicuota']*100:.1f}%"} for a in apts]
            st.table(tabla_apts)
            
            st.subheader("Editar Propietario o Cambiar Clave")
            lista_ids = [a['id'] for a in apts]
            apt_sel = st.selectbox("Seleccione el Apartamento:", lista_ids)
            nuevo_prop = st.text_input("Nombre del Propietario")
            nuevo_tel = st.text_input("Teléfono (ej. +584141234567)")
            nueva_clave = st.text_input("Nueva Clave de Acceso (Opcional)")
            
            if st.button("Guardar Cambios del Apartamento"):
                conn = get_db_connection()
                if nuevo_prop and nuevo_tel:
                    conn.execute("UPDATE apartamentos SET propietario = ?, telefono = ? WHERE id = ?", (nuevo_prop, nuevo_tel, apt_sel))
                if nueva_clave:
                    conn.execute("UPDATE apartamentos SET clave = ? WHERE id = ?", (nueva_clave, apt_sel))
                conn.commit()
                conn.close()
                st.success("Apartamento actualizado exitosamente.")
                st.rerun()

        elif opcion == "Registrar Gastos":
            st.header("💸 Cargar Gastos del Mes")
            col1, col2 = st.columns(2)
            with col1:
                mes = st.number_input("Mes (1-12)", min_value=1, max_value=12, value=datetime.now().month)
            with col2:
                anio = st.number_input("Año", min_value=2020, max_value=2030, value=datetime.now().year)

            tipo_gasto = st.radio("Tipo de Gasto:", ["Común (Aplica a todos por Alícuota)", "No Común (Específico para un Apt)"])
            desc = st.text_input("Descripción del Gasto")
            monto = st.number_input("Monto ($)", min_value=0.0, format="%.2f")

            apt_destino = None
            if tipo_gasto.startswith("No Común"):
                conn = get_db_connection()
                apts = [r['id'] for r in conn.execute("SELECT id FROM apartamentos").fetchall()]
                conn.close()
                apt_destino = st.selectbox("Apartamento Responsable:", apts)

            if st.button("Guardar Gasto"):
                if desc and monto > 0:
                    conn = get_db_connection()
                    if tipo_gasto.startswith("Común"):
                        conn.execute("INSERT INTO gastos_comunes (mes, anio, descripcion, monto) VALUES (?,?,?,?)", (mes, anio, desc, monto))
                    else:
                        conn.execute("INSERT INTO gastos_no_comunes (mes, anio, apartamento_id, descripcion, monto) VALUES (?,?,?,?,?)", (mes, anio, apt_destino, desc, monto))
                    conn.commit()
                    conn.close()
                    st.success("Gasto guardado correctamente.")

        elif opcion == "Generar Recibos y WhatsApp":
            st.header("📄 Enviar Recibos por WhatsApp")
            col1, col2 = st.columns(2)
            with col1:
                mes = st.number_input("Mes", min_value=1, max_value=12, value=datetime.now().month)
            with col2:
                anio = st.number_input("Año", min_value=2020, max_value=2030, value=datetime.now().year)

            conn = get_db_connection()
            apts = conn.execute("SELECT * FROM apartamentos").fetchall()
            edif_n = st.session_state.get('edif_nombre', 'Residencias El Roble')
            edif_r = st.session_state.get('edif_rif', 'J-12345678-9')
            logo_p = "logo_temp.png" if os.path.exists("logo_temp.png") else None

            for apt in apts:
                pago = conn.execute("SELECT estado FROM pagos_propietarios WHERE apartamento_id = ? AND mes = ? AND anio = ?", (apt['id'], mes, anio)).fetchone()
                estado_pago = pago['estado'] if pago else "Pendiente"

                with st.expander(f"Apt {apt['id']} - {apt['propietario']} | Status: {'✅ CANCELADO' if estado_pago == 'Verificado' else '⏳ PENDIENTE'}"):
                    filename, total = generar_pdf_recibo(apt['id'], mes, anio, edif_n, edif_r, logo_p, estado_pago)
                    tel_clean = apt['telefono'].replace("+", "").replace(" ", "")
                    mensaje = f"Hola {apt['propietario']}, adjunto su recibo de condominio {apt['id']} del mes {mes}/{anio}. Total a pagar: ${total:.2f}. Status: {estado_pago.upper()}."
                    url_wa = f"https://wa.me/{tel_clean}?text={mensaje.replace(' ', '%20')}"
                    
                    st.markdown(f"[📲 Enviar Recibo por WhatsApp]({url_wa})", unsafe_allow_html=True)
            conn.close()

        elif opcion == "Verificar Pagos":
            st.header("🔍 Aprobar Pagos Reportados por Vecinos")
            conn = get_db_connection()
            pagos_pendientes = conn.execute("SELECT * FROM pagos_propietarios WHERE estado = 'Pendiente'").fetchall()

            if not pagos_pendientes:
                st.info("🎉 ¡No hay pagos pendientes por verificar!")
            else:
                for p in pagos_pendientes:
                    col1, col2, col3 = st.columns([3, 2, 2])
                    with col1:
                        st.markdown(f"**Apt {p['apartamento_id']}** | Período: {p['mes']}/{p['anio']}")
                        st.caption(f"Ref: {p['referencia']} | Fecha: {p['fecha']}")
                    with col2:
                        st.subheader(f"${p['monto']:.2f}")
                    with col3:
                        if st.button(f"✅ Aprobar Pago #{p['id']}", key=f"btn_{p['id']}"):
                            conn.execute("UPDATE pagos_propietarios SET estado = 'Verificado' WHERE id = ?", (p['id'],))
                            conn.commit()
                            st.success(f"¡Pago del Apt {p['apartamento_id']} verificado con éxito!")
                            st.rerun()
                    st.divider()
            conn.close()

        elif opcion == "Proveedores y Sus Pagos":
            st.header("🚚 Proveedores y Pagos")
            sub_menu = st.tabs(["Registrar Proveedor", "Registrar Pago a Proveedor"])
            
            with sub_menu[0]:
                prov_nombre = st.text_input("Nombre / Razón Social")
                prov_rif = st.text_input("RIF / Identificación")
                prov_contacto = st.text_input("Teléfono o Contacto")
                if st.button("Guardar Proveedor"):
                    if prov_nombre:
                        conn = get_db_connection()
                        conn.execute("INSERT INTO proveedores (nombre, rif, contacto) VALUES (?,?,?)", (prov_nombre, prov_rif, prov_contacto))
                        conn.commit()
                        conn.close()
                        st.success("Proveedor registrado.")
                        
            with sub_menu[1]:
                conn = get_db_connection()
                provs = conn.execute("SELECT * FROM proveedores").fetchall()
                conn.close()
                if provs:
                    prov_dict = {f"{p['nombre']} ({p['rif']})": p['id'] for p in provs}
                    prov_sel = st.selectbox("Seleccionar Proveedor:", list(prov_dict.keys()))
                    monto_prov = st.number_input("Monto Pagado ($)", min_value=0.0, format="%.2f")
                    desc_prov = st.text_input("Concepto / Descripción del Pago")
                    metodo_prov = st.selectbox("Método de Pago", ["Transferencia", "Efectivo", "Pago Móvil", "Otro"])
                    fecha_prov = st.date_input("Fecha")

                    if st.button("Registrar Pago a Proveedor"):
                        if monto_prov > 0:
                            conn = get_db_connection()
                            conn.execute("INSERT INTO pagos_proveedores (proveedor_id, fecha, descripcion, monto, metodo) VALUES (?,?,?,?,?)",
                                         (prov_dict[prov_sel], str(fecha_prov), desc_prov, monto_prov, metodo_prov))
                            conn.commit()
                            conn.close()
                            st.success("Pago a proveedor registrado.")

        elif opcion == "Reportes Generales":
            st.header("📊 Reportes y Contabilidad")
            conn = get_db_connection()
            pagos = conn.execute("SELECT apartamento_id, mes, anio, fecha, monto, referencia, estado FROM pagos_propietarios").fetchall()
            datos_tabla = [{"Apt": p['apartamento_id'], "Mes": p['mes'], "Año": p['anio'], "Fecha": p['fecha'], "Monto ($)": f"${p['monto']:.2f}", "Referencia": p['referencia'], "Estado": p['estado']} for p in pagos]
            st.subheader("Historial General de Pagos de Propietarios")
            st.table(datos_tabla)
            conn.close()

    # MENÚ EXCLUSIVO PARA PROPIETARIOS
    elif st.session_state['usuario_rol'] == 'propietario':
        apt_id = st.session_state['apt_login']
        st.sidebar.title(f"🏠 Panel Apt {apt_id}")
        opcion_prop = st.sidebar.radio("Opciones del Propietario:", [
            "Reportar Mi Pago",
            "Consultar / Descargar Mi Recibo",
            "Cambiar Mi Contraseña"
        ])

        if opcion_prop == "Reportar Mi Pago":
            st.header(f"💵 Reportar Pago para el Apartamento {apt_id}")
            col1, col2 = st.columns(2)
            with col1:
                mes = st.number_input("Mes a Pagar", min_value=1, max_value=12, value=datetime.now().month)
                anio = st.number_input("Año a Pagar", min_value=2020, max_value=2030, value=datetime.now().year)
            with col2:
                monto_pago = st.number_input("Monto Transferido/Pagado ($)", min_value=0.0, format="%.2f")
                fecha_pago = st.date_input("Fecha del Pago")
                ref_pago = st.text_input("Número de Referencia Bancaria")

            if st.button("Enviar Reporte de Pago"):
                if monto_pago > 0 and ref_pago:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO pagos_propietarios (apartamento_id, mes, anio, fecha, monto, referencia, estado) VALUES (?,?,?,?,?,?,'Pendiente')",
                                 (apt_id, mes, anio, str(fecha_pago), monto_pago, ref_pago))
                    conn.commit()
                    conn.close()
                    st.success("¡Pago reportado con éxito! El administrador verificará la transferencia.")
                else:
                    st.warning("Por favor ingrese un monto mayor a 0 y la referencia bancaria.")

        elif opcion_prop == "Consultar / Descargar Mi Recibo":
            st.header(f"🔎 Mi Recibo de Condominio - Apt {apt_id}")
            col1, col2 = st.columns(2)
            with col1:
                mes = st.number_input("Mes", min_value=1, max_value=12, value=datetime.now().month)
            with col2:
                anio = st.number_input("Año", min_value=2020, max_value=2030, value=datetime.now().year)

            conn = get_db_connection()
            pago = conn.execute("SELECT * FROM pagos_propietarios WHERE apartamento_id = ? AND mes = ? AND anio = ?", (apt_id, mes, anio)).fetchone()
            conn.close()

            edif_n = st.session_state.get('edif_nombre', 'Residencias El Roble')
            edif_r = st.session_state.get('edif_rif', 'J-12345678-9')
            logo_p = "logo_temp.png" if os.path.exists("logo_temp.png") else None

            if pago:
                estado = pago['estado']
                if estado == "Verificado":
                    st.success("🟢 SU PAGO HA SIDO VERIFICADO Y SU RECIBO SE ENCUENTRA CANCELADO.")
                else:
                    st.warning("🟡 SU PAGO FUE REPORTADO Y ESTÁ PENDIENTE DE REVISIÓN POR EL ADMINISTRADOR.")
            else:
                estado = "Pendiente"
                st.info("ℹ️ NO SE HA REGISTRADO NINGÚN PAGO PARA ESTE MES AÚN.")

            filename, total = generar_pdf_recibo(apt_id, mes, anio, edif_n, edif_r, logo_p, estado)
            
            with open(filename, "rb") as pdf_file:
                st.download_button(
                    label=f"📥 Descargar Recibo PDF (Apt {apt_id})",
                    data=pdf_file,
                    file_name=filename,
                    mime="application/pdf"
                )

        elif opcion_prop == "Cambiar Mi Contraseña":
            st.header(f"🔐 Cambiar Contraseña - Apartamento {apt_id}")
            st.write("Ingresa tu contraseña actual y define tu nueva clave de acceso personal.")
            
            pass_actual = st.text_input("Contraseña Actual", type="password")
            pass_nueva = st.text_input("Nueva Contraseña", type="password")
            pass_confirmar = st.text_input("Confirmar Nueva Contraseña", type="password")
            
            if st.button("Actualizar Mi Contraseña"):
                conn = get_db_connection()
                user = conn.execute("SELECT * FROM apartamentos WHERE id = ? AND clave = ?", (apt_id, pass_actual)).fetchone()
                
                if not user:
                    st.error("La contraseña actual no es correcta.")
                elif not pass_nueva:
                    st.warning("Escribe una nueva contraseña.")
                elif pass_nueva != pass_confirmar:
                    st.error("Las nuevas contraseñas no coinciden.")
                else:
                    conn.execute("UPDATE apartamentos SET clave = ? WHERE id = ?", (pass_nueva, apt_id))
                    conn.commit()
                    st.success("¡Tu contraseña ha sido actualizada con éxito! Úsala la próxima vez que inicies sesión.")
                
                conn.close()
