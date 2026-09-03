import streamlit as st
import urllib.parse

def obtener_alicuotas():
    """Retorna el diccionario con las alícuotas correctas del edificio (13 unidades)."""
    return {
        # Diez apartamentos con 6%
        "1A": 0.06, "1B": 0.06,
        "3A": 0.06, "3B": 0.06,
        "4A": 0.06, "4B": 0.06,
        "5A": 0.06, "5B": 0.06,
        "6A": 0.06, "6B": 0.06,
        # Dos apartamentos con 12%
        "2": 0.12, "7": 0.12,
        # Penthouse con 16%
        "PH": 0.16
    }

def generar_recibo_mes(mes_anio, gastos_dict, apto):
    """Genera el texto estructurado del recibo con el desglose y la alícuota correspondiente."""
    total_gastos = sum(gastos_dict.values())
    alicuotas = obtener_alicuotas()
    
    if apto not in alicuotas:
        return "Apartamento no válido."
    
    porcentaje = alicuotas[apto]
    monto_a_pagar = total_gastos * porcentaje
    
    # Construcción del mensaje para el recibo
    recibo = f"*EDIFICIO - RECIBO DE CONDOMINIO*\n"
    recibo += f"*Mes a cancelar:* {mes_anio}\n"
    recibo += f"*Apartamento:* {apto} (Alícuota: *{int(porcentaje * 100)}%*)\n\n"
    
    recibo += "*Desglose de Gastos Generales:*\n"
    for concepto, monto in gastos_dict.items():
        recibo += f"• {concepto}: ${monto:.2f}\n"
        
    recibo += f"\n*Total Gastos del Edificio:* ${total_gastos:.2f}\n"
    recibo += f"*Total a Pagar:* *${monto_a_pagar:.2f}*\n"
    
    return recibo

def mostrar_modulo_recibos():
    st.subheader("🏢 Gestión y Emisión de Recibos Generales")
    st.write("Carga los gastos comunes del mes para calcular de forma automática las alícuotas de los 13 apartamentos.")

    # 1. Datos generales del periodo
    col1, col2 = st.columns(2)
    with col1:
        mes_cancelar = st.text_input("Mes a cancelar", "Septiembre 2026")
    with col2:
        # Puedes integrar aquí una base de datos o diccionario con los teléfonos reales de los propietarios
        pass

    st.markdown("---")
    st.markdown("### 📋 Registro de Gastos del Mes")
    
    # Usamos st.data_editor para que puedas agregar y editar múltiples filas de gastos cómodamente
    if "gastos_df" not in st.session_state:
        import pandas as pd
        st.session_state.gastos_df = pd.DataFrame([
            {"Concepto": "Vigilancia / Seguridad", "Monto": 0.0},
            {"Concepto": "Mantenimiento de Ascensor", "Monto": 0.0},
            {"Concepto": "Electricidad Áreas Comunes", "Monto": 0.0},
            {"Concepto": "Limpieza y Aseo", "Monto": 0.0}
        ])

    gastos_editados = st.data_editor(
        st.session_state.gastos_df, 
        num_rows="dynamic", 
        use_container_width=True,
        key="editor_gastos"
    )

    # Actualizar estado
    st.session_state.gastos_df = gastos_editados

    # Calcular total temporal de gastos
    gastos_dict = {}
    for _, row in gastos_editados.iterrows():
        concepto = str(row["Concepto"]).strip()
        monto = float(row["Monto"])
        if concepto and monto > 0:
            gastos_dict[concepto] = monto

    total_general = sum(gastos_dict.values())
    st.info(f"💵 **Total General de Gastos Calculados:** ${total_general:.2f}")

    st.markdown("---")
    
    # 2. Botón de procesamiento y visualización de recibos por apartamento
    if st.button("🚀 Generar Recibos para Todos los Apartamentos", type="primary"):
        if not gastos_dict:
            st.warning("⚠️ Por favor, ingresa al menos un concepto de gasto con un monto mayor a 0.")
        else:
            st.success("¡Recibos generados con éxito para las 13 unidades!")
            alicuotas = obtener_alicuotas()
            
            # Pestañas o desplegables para organizar la vista de cada apartamento
            for apto in alicuotas.keys():
                texto_recibo = generar_recibo_mes(mes_cancelar, gastos_dict, apto)
                porcentaje_str = int(alicuotas[apto] * 100)
                
                with st.expander(f"🏠 Apartamento {apto} — Alícuota ({porcentaje_str}%)"):
                    st.text_area("Vista previa del mensaje:", value=texto_recibo, height=220, key=f"txt_{apto}")
                    
                    # Generador de enlace para WhatsApp (puedes reemplazar el número por el del propietario registrado)
                    # Ejemplo simulado de número de contacto
                    telefono_ejemplo = "" # Coloca aquí la lógica para buscar el teléfono del propietario si lo tienes guardado
                    texto_encoded = urllib.parse.quote(texto_recibo)
                    
                    col_w1, col_w2 = st.columns([2, 3])
                    with col_w1:
                        num_tel = st.text_input(f"Teléfono Apto {apto}", value="", placeholder="Ej: 584120000000", key=f"tel_{apto}")
                    with col_w2:
                        st.markdown("<br>", unsafe_allow_html=True) # Espaciador visual
                        if num_tel:
                            link_wa = f"https://wa.me/{num_tel}?text={texto_encoded}"
                            st.markdown(f"[📲 Enviar por WhatsApp]({link_wa})", unsafe_allow_html=True)
                        else:
                            st.caption("Ingresa el teléfono para habilitar el enlace directo de WhatsApp.")

# Llamada a la función principal del módulo si se ejecuta directamente en tu app
if __name__ == "__main__":
    mostrar_modulo_recibos()
