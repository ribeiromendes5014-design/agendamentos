import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import os

# Google Calendar
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ========== Função para criar evento no Google Calendar ==========
def criar_evento_google_calendar(info_evento):
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    # Pega credenciais do secrets do Streamlit
    service_account_info = st.secrets["google_service_account"]

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info, scopes=SCOPES)

    service = build('calendar', 'v3', credentials=credentials)

    evento = {
        'summary': f"{info_evento['tipo_servico']} - {info_evento['cliente']}",
        'location': info_evento['local'],
        'description': f"Valor total: R${info_evento['valor_total']:.2f}\n"
                       f"Entrada: R${info_evento['valor_entrada']:.2f}\n"
                       f"Forma de pagamento: {info_evento['forma_pagamento']}\n",
        'start': {
            'dateTime': info_evento['data_hora'].isoformat(),
            'timeZone': 'America/Sao_Paulo',
        },
        'end': {
            'dateTime': (info_evento['data_hora'] + timedelta(minutes=info_evento['duracao'])).isoformat(),
            'timeZone': 'America/Sao_Paulo',
        },
    }

    calendar_id = 'primary'
    evento_criado = service.events().insert(calendarId=calendar_id, body=evento).execute()
    return evento_criado.get('htmlLink')

# ========== App Streamlit ==========
st.set_page_config(page_title="Sistema de Agendamentos", layout="centered")
st.title("📅 Sistema de Agendamento com Google Calendar")

with st.form("form_agendamento"):
    cliente = st.text_input("👤 Nome do Cliente")
    tipo_servico = st.selectbox("🛠 Tipo de Serviço", ["Fotos", "Consultoria", "Outro"])
    
    if tipo_servico == "Fotos":
        quantidade_fotos = st.number_input("📷 Quantidade de Fotos", min_value=1, step=1)
        duracao = quantidade_fotos * 5
    else:
        duracao = st.number_input("⏱ Duração do Serviço (minutos)", min_value=15, step=15)
    
    local = st.text_input("📍 Local")
    data = st.date_input("📆 Data")
    hora = st.time_input("⏰ Horário")

    valor_total = st.number_input("💰 Valor Total (R$)", min_value=0.0, step=10.0)
    
    entrada = st.checkbox("✅ Houve entrada de dinheiro?")
    valor_entrada = 0.0
    forma_pagamento = ""
    if entrada:
        valor_entrada = st.number_input("💵 Valor da Entrada (R$)", min_value=0.0, max_value=valor_total, step=10.0)
        forma_pagamento = st.selectbox("💳 Forma de Pagamento", ["Pix", "Dinheiro", "Cartão", "Transferência", "Outro"])

    submitted = st.form_submit_button("Agendar")

# ========== Processamento ==========
if submitted:
    data_hora = datetime.combine(data, hora)

    dados = {
        "cliente": cliente,
        "tipo_servico": tipo_servico,
        "duracao": duracao,
        "local": local,
        "data_hora": data_hora,
        "valor_total": valor_total,
        "valor_entrada": valor_entrada,
        "forma_pagamento": forma_pagamento
    }

    try:
        link_evento = criar_evento_google_calendar(dados)
        st.success("✅ Agendamento criado com sucesso no Google Calendar!")
        st.markdown(f"[📅 Ver no Google Calendar]({link_evento})")

        # Salvar em CSV
        linha = {
            "Data e Hora": data_hora.strftime("%Y-%m-%d %H:%M"),
            "Cliente": cliente,
            "Serviço": tipo_servico,
            "Duração (min)": duracao,
            "Local": local,
            "Valor Total": valor_total,
            "Entrada": valor_entrada,
            "Forma de Pagamento": forma_pagamento,
            "Link do Evento": link_evento
        }

        arquivo_csv = "agendamentos.csv"
        if os.path.exists(arquivo_csv):
            df_existente = pd.read_csv(arquivo_csv)
            df_novo = pd.concat([df_existente, pd.DataFrame([linha])], ignore_index=True)
        else:
            df_novo = pd.DataFrame([linha])

        df_novo.to_csv(arquivo_csv, index=False)

    except Exception as e:
        st.error("❌ Erro ao criar evento no Google Calendar")
        st.text(str(e))
