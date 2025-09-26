# -*- coding: utf-8 -*-
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import os
import json
import pytz

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
    tz = pytz.timezone('America/Sao_Paulo')
    data_hora_inicio_aware = tz.localize(info_evento['data_hora_inicio'])
    data_hora_fim_aware = tz.localize(info_evento['data_hora_fim'])

    # Configurar lembretes
    reminders_list = [{'method': 'popup', 'minutes': m} for m in info_evento['lembretes_minutos']]
    
    reminders = {
        'useDefault': False,
        'overrides': reminders_list
    }

    # Adicionar o local de forma mais detalhada
    local = info_evento['local']
    if info_evento['endereco']:
        local = f"{info_evento['local']} ({info_evento['endereco']})"

    evento = {
        'summary': f"{info_evento['tipo_servico']} - {info_evento['cliente']}",
        'location': local,
        'description': f"Valor total: R${info_evento['valor_total']:.2f}\n"
                       f"Entrada: R${info_evento['valor_entrada']:.2f}\n"
                       f"Forma de pagamento: {info_evento['forma_pagamento']}\n",
        'start': {
            'dateTime': data_hora_inicio_aware.isoformat(),
            'timeZone': 'America/Sao_Paulo',
        },
        'end': {
            'dateTime': data_hora_fim_aware.isoformat(),
            'timeZone': 'America/Sao_Paulo',
        },
        'reminders': reminders,
    }

    try:
        calendar_id = 'ribeiromendes5016@gmail.com'
        evento_criado = service.events().insert(calendarId=calendar_id, body=evento).execute()
        return evento_criado.get('htmlLink')
    except HttpError as error:
        st.error(f"Erro na API do Google Calendar: {error}")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro: {e}")
        return None

# --- App Streamlit ---
st.set_page_config(page_title="Sistema de Agendamentos", layout="centered")
st.title("📅 Sistema de Agendamento com Google Calendar")

service = get_google_calendar_service()

if service:
    with st.form("form_agendamento", clear_on_submit=True):
        st.subheader("Informações do Agendamento")
        cliente = st.text_input("👤 Nome do Cliente")
        tipo_servico = st.text_input("🛠 Tipo de Serviço (ex: Sessão de Fotos, Consultoria)")
        
        local = st.text_input("📍 Local")
        endereco = st.text_input("Endereço completo (opcional)")
        
        col1, col2 = st.columns(2)
        with col1:
            data_inicio = st.date_input("📆 Data de Início")
            hora_inicio = st.time_input("⏰ Horário de Início")
        with col2:
            data_fim = st.date_input("📆 Data de Fim")
            hora_fim = st.time_input("⏰ Horário de Fim")

        st.subheader("Lembretes")
        lembrete_opcoes = {
            "15 minutos antes": 15,
            "30 minutos antes": 30,
            "1 hora antes": 60,
            "2 horas antes": 120,
            "1 dia antes": 1440
        }
        lembretes_selecionados = st.multiselect("🔔 Quero ser alertado:", list(lembrete_opcoes.keys()), default=["15 minutos antes"])
        lembretes_minutos = [lembrete_opcoes[l] for l in lembretes_selecionados]

        st.subheader("Informações Financeiras")
        valor_total = st.number_input("💰 Valor Total (R$)", min_value=0.0, value=100.0, step=10.0, format="%.2f")
        
        entrada = st.checkbox("✅ Houve entrada de dinheiro?")
        
        valor_entrada_input = 0.0
        forma_pagamento_input = "Não houve entrada"
        
        if entrada:
            valor_entrada_input = st.number_input("💵 Valor da Entrada (R$)", min_value=0.0, max_value=valor_total, step=10.0, format="%.2f")
            forma_pagamento_input = st.selectbox("💳 Forma de Pagamento", ["Pix", "Dinheiro", "Cartão", "Transferência", "Outro"])

        submitted = st.form_submit_button("Agendar")
        
        if submitted:
            data_hora_inicio = datetime.combine(data_inicio, hora_inicio)
            data_hora_fim = datetime.combine(data_fim, hora_fim)
            
            valor_entrada = 0.0
            forma_pagamento = "Não houve entrada"
            if entrada:
                valor_entrada = valor_entrada_input
                forma_pagamento = forma_pagamento_input
            
            # Validar campos
            if not cliente:
                st.error("O campo 'Nome do Cliente' é obrigatório.")
            elif not tipo_servico:
                st.error("O campo 'Tipo de Serviço' é obrigatório.")
            elif not local:
                st.error("O campo 'Local' é obrigatório.")
            elif data_hora_inicio >= data_hora_fim:
                st.error("A data/hora de início deve ser anterior à data/hora de fim.")
            else:
                dados = {
                    "cliente": cliente,
                    "tipo_servico": tipo_servico,
                    "duracao": (data_hora_fim - data_hora_inicio).total_seconds() / 60,
                    "local": local,
                    "endereco": endereco,
                    "data_hora_inicio": data_hora_inicio,
                    "data_hora_fim": data_hora_fim,
                    "valor_total": valor_total,
                    "valor_entrada": valor_entrada,
                    "forma_pagamento": forma_pagamento,
                    "lembretes_minutos": lembretes_minutos
                }
                
                link_evento = criar_evento_google_calendar(service, dados)
                if link_evento:
                    st.success("✅ Agendamento criado com sucesso no Google Calendar!")
                    st.markdown(f"[📅 Ver no Google Calendar]({link_evento})")

                    linha = {
                        "Data e Hora Início": data_hora_inicio.strftime("%Y-%m-%d %H:%M"),
                        "Data e Hora Fim": data_hora_fim.strftime("%Y-%m-%d %H:%M"),
                        "Cliente": cliente,
                        "Serviço": tipo_servico,
                        "Duração (min)": dados["duracao"],
                        "Local": local,
                        "Endereço": endereco,
                        "Valor Total": valor_total,
                        "Entrada": valor_entrada,
                        "Forma de Pagamento": forma_pagamento,
                        "Link do Evento": link_evento,
                    }

                    arquivo_csv = "agendamentos.csv"
                    if os.path.exists(arquivo_csv):
                        df_existente = pd.read_csv(arquivo_csv)
                        df_novo = pd.concat([df_existente, pd.DataFrame([linha])], ignore_index=True)
                    else:
                        df_novo = pd.DataFrame([linha])

                    df_novo.to_csv(arquivo_csv, index=False)
