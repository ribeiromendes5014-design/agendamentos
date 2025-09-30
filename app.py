# -*- coding: utf-8 -*-
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import os
import json
import pytz
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Configurações Essenciais ---
SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_ID = "ribeiromendes5016@gmail.com"
ARQUIVO_CSV = "agendamentos.csv"
TIMEZONE = 'America/Sao_Paulo'

# Carregar secrets de forma segura
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID")
TOPICO_ID = 64

# --- Funções de Serviço (Google & Telegram) ---
def get_google_calendar_service():
    try:
        service_account_info = st.secrets["google_service_account"]
        creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Erro de autenticação: {e}")
        return None

def criar_evento_google_calendar(service, info_evento):
    tz = pytz.timezone(TIMEZONE)
    evento_body = {
        'summary': f"{info_evento['tipo_servico']} - {info_evento['cliente']}",
        'location': f"{info_evento['local']} ({info_evento['endereco']})" if info_evento['endereco'] else info_evento['local'],
        'description': f"Valor total: R${info_evento['valor_total']:.2f}\nEntrada: R${info_evento['valor_entrada']:.2f}\nForma de pagamento: {info_evento['forma_pagamento']}",
        'start': {'dateTime': tz.localize(info_evento['data_hora_inicio']).isoformat(), 'timeZone': TIMEZONE},
        'end': {'dateTime': tz.localize(info_evento['data_hora_fim']).isoformat(), 'timeZone': TIMEZONE},
        'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': m} for m in info_evento['lembretes_minutos']]},
    }
    try:
        evento_criado = service.events().insert(calendarId=CALENDAR_ID, body=evento_body).execute()
        return evento_criado.get('htmlLink')
    except HttpError as error:
        st.error(f"Erro na API do Google: {error}")
        return None

def enviar_mensagem_telegram(cliente, data, hora, tipo_servico):
    if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]): return
    mensagem = f"📅 Novo Agendamento\n👤 *Cliente:* {cliente}\n🛠 *Serviço:* {tipo_servico}\n📆 *Data:* {data.strftime('%d/%m/%Y')} às {hora.strftime('%H:%M')}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown", "message_thread_id": TOPICO_ID}
    try:
        requests.post(url, data=payload)
    except Exception:
        pass # Falha silenciosa para não interromper o fluxo

# --- Funções de Gerenciamento de Dados (CSV & Google Sync) ---
def carregar_agendamentos_csv():
    if not os.path.exists(ARQUIVO_CSV): return pd.DataFrame(columns=['Status'])
    df = pd.read_csv(ARQUIVO_CSV)
    if 'Status' not in df.columns: df['Status'] = 'Pendente'
    return df

def puxar_eventos_google_calendar(service, periodo="futuro", dias=365):
    try:
        now = datetime.now(pytz.timezone(TIMEZONE))
        params = {'calendarId': CALENDAR_ID, 'maxResults': 2500, 'singleEvents': True, 'orderBy': 'startTime'}
        if periodo == "futuro":
            params['timeMin'] = now.isoformat()
        else:
            params['timeMax'] = now.isoformat()
            params['timeMin'] = (now - timedelta(days=dias)).isoformat()
        
        events = service.events().list(**params).execute().get('items', [])
        event_list = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'Sem Título')
            cliente, servico = (summary.split(' - ') + ['N/A'])[:2]
            event_list.append({
                'Data e Hora Início': pd.to_datetime(start).tz_convert(TIMEZONE).tz_localize(None),
                'Cliente': cliente, 'Serviço': servico,
            })
        return pd.DataFrame(event_list)
    except HttpError as error:
        st.error(f"Erro ao buscar eventos: {error}")
        return pd.DataFrame()

def sincronizar_google_para_csv(service):
    with st.spinner("Sincronizando histórico do Google Calendar..."):
        df_google = puxar_eventos_google_calendar(service, periodo="passado")
        if df_google.empty:
            st.warning("Nenhum evento passado encontrado no Google Calendar.")
            return

        df_csv = carregar_agendamentos_csv()
        ids_existentes = set()
        if not df_csv.empty and 'Data e Hora Início' in df_csv.columns:
            ids_existentes = set(pd.to_datetime(df_csv['Data e Hora Início']).dt.strftime('%Y-%m-%d %H:%M') + df_csv['Cliente'])

        novas_linhas = [
            {
                "Data e Hora Início": row['Data e Hora Início'].strftime("%Y-%m-%d %H:%M"),
                "Cliente": row['Cliente'], "Serviço": row['Serviço'], "Status": "Concluído"
            }
            for _, row in df_google.iterrows()
            if (row['Data e Hora Início'].strftime('%Y-%m-%d %H:%M') + row['Cliente']) not in ids_existentes
        ]

        if novas_linhas:
            df_atualizado = pd.concat([df_csv, pd.DataFrame(novas_linhas)], ignore_index=True)
            df_atualizado.to_csv(ARQUIVO_CSV, index=False)
            st.success(f"{len(novas_linhas)} agendamentos importados para o CSV!")
            st.rerun()
        else:
            st.success("Seu backup CSV já está sincronizado!")

# --- Interface do Aplicativo ---
st.set_page_config(page_title="Agendamentos", layout="centered")
st.title("📅 Agenda")

service = get_google_calendar_service()
if service:
    tab1, tab2 = st.tabs(["➕ Agendar", "📋 Consultar"])

    with tab1:
        with st.form("form_agendamento", clear_on_submit=True):
            col1, col2 = st.columns(2)
            cliente = col1.text_input("👤 Cliente")
            tipo_servico = col2.text_input("🛠️ Serviço")
            local = st.text_input("📍 Local")
            
            data_inicio = col1.date_input("🗓️ Data")
            hora_inicio = col2.time_input("⏰ Hora")
            duracao = st.number_input("⏳ Duração (minutos)", min_value=1, value=60, step=15)

            with st.expander("Mais detalhes (opcional)"):
                endereco = st.text_input("Endereço completo")
                lembretes_opcoes = {"15 min": 15, "30 min": 30, "1 hora": 60, "1 dia": 1440}
                lembretes_selecionados = st.multiselect("🔔 Alertas", list(lembretes_opcoes.keys()))
                valor_total = st.number_input("💰 Valor Total (R$)", min_value=0.0, step=10.0, format="%.2f")
            
            submitted = st.form_submit_button("Agendar", use_container_width=True, type="primary")
            if submitted:
                if cliente and tipo_servico and local:
                    data_hora_inicio = datetime.combine(data_inicio, hora_inicio)
                    data_hora_fim = data_hora_inicio + timedelta(minutes=duracao)
                    dados = {
                        "cliente": cliente, "tipo_servico": tipo_servico, "local": local, "endereco": endereco,
                        "data_hora_inicio": data_hora_inicio, "data_hora_fim": data_hora_fim,
                        "valor_total": valor_total, "valor_entrada": 0.0, "forma_pagamento": "N/A",
                        "lembretes_minutos": [lembretes_opcoes[l] for l in lembretes_selecionados]
                    }
                    link = criar_evento_google_calendar(service, dados)
                    if link:
                        st.success(f"Agendado! [Ver no Google Calendar]({link})")
                        enviar_mensagem_telegram(cliente, data_inicio, hora_inicio, tipo_servico)
                        linha = {"Data e Hora Início": data_hora_inicio.strftime("%Y-%m-%d %H:%M"), "Cliente": cliente, "Serviço": tipo_servico, "Status": "Pendente"}
                        df_novo = pd.concat([carregar_agendamentos_csv(), pd.DataFrame([linha])], ignore_index=True)
                        df_novo.to_csv(ARQUIVO_CSV, index=False)
                else:
                    st.warning("Preencha Cliente, Serviço e Local.")

    with tab2:
        df_futuros = puxar_eventos_google_calendar(service, "futuro")
        if not df_futuros.empty:
            st.subheader("Próximo Compromisso")
            proximo = df_futuros.iloc[0]
            st.info(f"**{proximo['Cliente']}** - {proximo['Serviço']} em {proximo['Data e Hora Início'].strftime('%d/%m/%Y às %H:%M')}")
        else:
            st.info("Nenhum compromisso futuro no Google Calendar.")

        st.subheader("Gerenciar Backup Local (CSV)")
        if st.button("Sincronizar Histórico do Google", help="Importa agendamentos passados do Google Calendar para o arquivo CSV de backup."):
            sincronizar_google_para_csv(service)

        df_csv = carregar_agendamentos_csv()
        df_pendentes = df_csv[df_csv['Status'] == 'Pendente']

        if df_pendentes.empty:
            st.success("🎉 Nenhuma tarefa pendente no backup.")
        else:
            for index, row in df_pendentes.iterrows():
                col1, col2 = st.columns([4, 1])
                cliente = row.get('Cliente', 'N/A')
                data = pd.to_datetime(row.get('Data e Hora Início')).strftime('%d/%m %H:%M') if pd.notna(row.get('Data e Hora Início')) else ''
                col1.markdown(f"**{cliente}** `{data}`")
                if col2.button("✅", key=f"concluir_{index}", help="Marcar como concluído"):
                    df_csv.loc[index, 'Status'] = 'Concluído'
                    df_csv.to_csv(ARQUIVO_CSV, index=False)
                    st.rerun()
else:
    st.warning("Falha na autenticação com Google Calendar. Verifique os `secrets`.")

