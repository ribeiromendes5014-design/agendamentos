# -*- coding: utf-8 -*-
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import os
import json

# Google Calendar
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Escopo para acessar o Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_google_calendar_service():
    """Autentica usando a conta de serviço do secrets e retorna o serviço do Google Calendar."""
    try:
        # Carregar credenciais do secrets
        service_account_info = st.secrets["google_service_account"]

        # Converter para dict caso esteja em string JSON
        if isinstance(service_account_info, str):
            service_account_info = json.loads(service_account_info)

        creds = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES)

        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        st.error(f"Erro ao autenticar com a conta de serviço: {e}")
        return None

def criar_evento_google_calendar(service, info_evento):
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

    try:
        calendar_id = 'primary'  # ou o ID do calendário que você compartilhou com a conta de serviço
        evento_criado = service.events().insert(calendarId=calendar_id, body=evento).execute()
        return evento_criado.get('htmlLink')
    except HttpError as error:
        st.error(f"Erro na API do Google Calendar: {error}")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro: {e}")
        return None

# --- Seu app continua igual abaixo ---

st.set_page_config(page_title="Sistema de Agendamentos", layout="centered")
st.title("📅 Sistema de Agendamento com Google Calendar")

service = get_google_calendar_service()

if service:
    with st.form("form_agendamento"):
        st.subheader("Informações do Agendamento")
        cliente = st.text_input("👤 Nome do Cliente")
        tipo_servico = st.selectbox("🛠 Tipo de Serviço", ["Fotos", "Consultoria", "Outro"])

        duracao = 0
        if tipo_servico == "Fotos":
            quantidade_fotos = st.number_input("📷 Quantidade de Fotos", min_value=1, step=1, key="fotos_input")
            duracao = quantidade_fotos * 5
        else:
            duracao = st.number_input("⏱ Duração do Serviço (minutos)", min_value=15, step=15, key="duracao_input")

        local = st.text_input("📍 Local")
        data = st.date_input("📆 Data")
        hora = st.time_input("⏰ Horário")

        st.subheader("Informações Financeiras")
        valor_total = st.number_input("💰 Valor Total (R$)", min_value=0.0, step=10.0)

        entrada = st.checkbox("✅ Houve entrada de dinheiro?")
        valor_entrada = 0.0
        forma_pagamento = ""
        if entrada:
            valor_entrada = st.number_input("💵 Valor da Entrada (R$)", min_value=0.0, max_value=valor_total, step=10.0, key="entrada_input")
            forma_pagamento = st.selectbox("💳 Forma de Pagamento", ["Pix", "Dinheiro", "Cartão", "Transferência", "Outro"], key="pagamento_input")

        submitted = st.form_submit_button("Agendar")

    if submitted:
        if not cliente:
            st.error("O campo 'Nome do Cliente' é obrigatório.")
        elif not local:
            st.error("O campo 'Local' é obrigatório.")
        else:
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

            link_evento = criar_evento_google_calendar(service, dados)
            if link_evento:
                st.success("✅ Agendamento criado com sucesso no Google Calendar!")
                st.markdown(f"[📅 Ver no Google Calendar]({link_evento})")

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
else:
    st.warning("Erro na autenticação com Google Calendar. Verifique suas credenciais e permissões do calendário.")
