import urllib.parse
import pandas as pd
import streamlit as st

st.title("📄 Recibo General de Condominio")

# 1. Configuración de datos del edificio y apartamentos (13 unidades)
alicuotas_aptos = {
    "1A": 0.06,
    "1B": 0.06,
    "2": 0.12,
    "3A": 0.06,
    "3B": 0.06,
    "4A": 0.06,
    "4B": 0.06,
    "5A": 0.06,
    "5B": 0.06,
    "6A": 0.06,
    "6B": 0.06,
    "7": 0.12,
    "PH": 0.16,
}

# 2. Resumen de Gastos del Mes
st.subheader("📌 Gastos del Mes")
gastos = [
    {"Concepto": "Mantenimiento de Ascensor", "Monto ($)": 150.00},
    {"Concepto": "Luz Áreas Comunes", "Monto ($)": 80.00},
    {"Concepto": "Servicio de Limpieza", "Monto ($)": 120.00},
]
df_gastos = pd.DataFrame(gastos)
total_gastos = df_gastos["Monto ($)"].sum()

st.table(df_gastos)
st.markdown(f"**Total Gastos del Mes:** `${total_gastos:,.2f}`")

# 3. Cálculo del Recibo General por Alícuota
st.subheader("🏢 Desglose por Apartamento")
recibo_data = []
for apto, alicuota in alicuotas_aptos.items():
    monto_apto = total_gastos * alicuota
    recibo_data.append(
        {
            "Apartamento": apto,
            "Alícuota (%)": f"{alicuota * 100:.0f}%",
            "Monto a Pagar ($)": f"${monto_apto:,.2f}",
        }
    )

df_recibo = pd.DataFrame(recibo_data)
st.dataframe(df_recibo, use_container_width=True)

# 4. Generador de Pestaña/Botón para Enviar por WhatsApp
st.subheader("📲 Enviar Recibo por WhatsApp")

# Selección del apartamento a enviar
apto_seleccionado = st.selectbox(
    "Seleccione el apartamento:", list(alicuotas_aptos.keys())
)
telefono_propietario = st.text_input(
    "Número de teléfono (con código de país, ej. 584120000000):",
    value="58",
)

monto_apto_sel = total_gastos * alicuotas_aptos[apto_seleccionado]

# Construcción del mensaje predeterminado
mensaje = (
    f" *RECIBO DE CONDOMINIO - EDIFICIO*\n\n"
    f"Apartamento: *{apto_seleccionado}*\n"
    f"Alícuota: *{alicuotas_aptos[apto_seleccionado]*100:.0f}%*\n"
    f"Total Gastos Edificio: *${total_gastos:,.2f}*\n"
    f"Monto a Pagar: *${monto_apto_sel:,.2f}*\n\n"
    f"Por favor realizar el pago correspondiente a las cuentas registradas."
)

# Formatear el link de WhatsApp API
mensaje_url = urllib.parse.quote(mensaje)
link_whatsapp = (
    f"https://api.whatsapp.com/send?phone={telefono_propietario}&text={mensaje_url}"
)

# Pestaña/Enlace visual de WhatsApp
st.markdown(
    f"""
    <a href="{link_whatsapp}" target="_blank">
        <button style="
            background-color: #25D366;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;">
            🟢 Enviar Recibo por WhatsApp
        </button>
    </a>
    """,
    unsafe_allow_html=True,
)
