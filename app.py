# -*- coding: utf-8 -*-
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import os
import json
import pytz
import requests

# Google Calendar
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Escopo para acessar o Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']

# --- Configurações ---
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN_HERE")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")
TOPICO_ID = 64
ARQUIVO_CSV = "agendamentos.csv"
TIMEZONE = 'America/Sao_Paulo'


def get_google_calendar_service():
    """Autentica e retorna o serviço do Google Calendar."""
    try:
        service_account_info = st.secrets["google_service_account"]
        if isinstance(service_account_info, str):
            service_account_info = json.loads(service_account_info)
        creds = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES)
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Erro ao autenticar com a conta de serviço: {e}")
        return None


def criar_evento_google_calendar(service, info_evento):
    """Cria um evento no Google Calendar."""
    tz = pytz.timezone(TIMEZONE)
    data_hora_inicio_aware = tz.localize(info_evento['data_hora_inicio'])
    data_hora_fim_aware = tz.localize(info_evento['data_hora_fim'])
    # ... (código da função original sem alterações) ...
    reminders_list = [{'method': 'popup', 'minutes': m} for m in info_evento['lembretes_minutos']]
    reminders = {'useDefault': False, 'overrides': reminders_list}

    local = info_evento['local']
    if info_evento['endereco']:
        local = f"{info_evento['local']} ({info_evento['endereco']})"

    evento = {
        'summary': f"{info_evento['tipo_servico']} - {info_evento['cliente']}",
        'location': local,
        'description': (f"Valor total: R${info_evento['valor_total']:.2f}\n"
                        f"Entrada: R${info_evento['valor_entrada']:.2f}\n"
                        f"Forma de pagamento: {info_evento['forma_pagamento']}\n"),
        'start': {'dateTime': data_hora_inicio_aware.isoformat(), 'timeZone': TIMEZONE},
        'end': {'dateTime': data_hora_fim_aware.isoformat(), 'timeZone': TIMEZONE},
        'reminders': reminders,
    }
    try:
        calendar_id = 'primary' # Usando o calendário principal
        evento_criado = service.events().insert(calendarId=calendar_id, body=evento).execute()
        return evento_criado.get('htmlLink')
    except HttpError as error:
        st.error(f"Erro na API do Google Calendar: {error}")
    return None


def enviar_mensagem_telegram_agendamento(cliente, data, hora, valor_total, valor_entrada, tipo_servico):
    """Envia uma mensagem de confirmação para o Telegram."""
    # ... (código da função original sem alterações) ...
    mensagem = (
        f"📅 *Novo Agendamento Realizado!*\n\n"
        f"👤 *Cliente:* {cliente}\n"
        f"🛠 *Serviço:* {tipo_servico}\n"
        f"📆 *Data:* {data.strftime('%d/%m/%Y')}\n"
        f"⏰ *Horário:* {hora.strftime('%H:%M')}\n"
        f"💰 *Valor Total:* R$ {valor_total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + "\n"
        f"💵 *Entrada:* R$ {valor_entrada:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown", "message_thread_id": TOPICO_ID}
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        st.error(f"Erro ao enviar mensagem para o Telegram: {response.json()}")
    else:
        st.success("📨 Mensagem de confirmação enviada para o grupo do Telegram!")


def carregar_agendamentos_csv():
    """Carrega os agendamentos do arquivo CSV local."""
    if os.path.exists(ARQUIVO_CSV):
        return pd.read_csv(ARQUIVO_CSV)
    return pd.DataFrame()


def puxar_eventos_google_calendar(service):
    """Puxa os próximos eventos diretamente do Google Calendar."""
    try:
        now_utc = datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary', timeMin=now_utc,
            maxResults=250, singleEvents=True, orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        
        lista_eventos = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            summary = event.get('summary', 'Sem Título')
            cliente, servico = (summary.split(' - ') + ['N/A'])[:2]

            lista_eventos.append({
                'Data e Hora Início': pd.to_datetime(start).tz_convert(TIMEZONE),
                'Data e Hora Fim': pd.to_datetime(end).tz_convert(TIMEZONE),
                'Cliente': cliente,
                'Serviço': servico,
                'Local': event.get('location', 'N/A'),
                'Link do Evento': event.get('htmlLink', '#')
            })
        return pd.DataFrame(lista_eventos)
    except HttpError as error:
        st.error(f"Erro ao buscar eventos do Google Calendar: {error}")
    return pd.DataFrame()


# --- App Streamlit ---
st.set_page_config(page_title="Sistema de Agendamentos", layout="centered")
st.title("📅 Sistema de Agendamento")

service = get_google_calendar_service()

if service:
    # CORREÇÃO: Movido para fora da aba para evitar NameError
    lembrete_opcoes = {
        "15 minutos antes": 15, "30 minutos antes": 30, "1 hora antes": 60,
        "2 horas antes": 120, "1 dia antes": 1440
    }
    tab1, tab2 = st.tabs(["➕ Novo Agendamento", "📋 Consultar Agendamentos"])

    with tab1:
        # --- Formulário de Novo Agendamento ---
        st.subheader("Informações do Agendamento")
        cliente = st.text_input("👤 Nome do Cliente")
        tipo_servico = st.text_input("🛠 Tipo de Serviço (ex: Sessão de Fotos)")
        local = st.text_input("📍 Local")
        endereco = st.text_input("Endereço completo (opcional)")
        st.markdown("---")

        metodo_termino = st.radio("Como definir o término?", ('Definir Duração', 'Manualmente'), horizontal=True)
        col1, col2 = st.columns(2)
        data_inicio = col1.date_input("📆 Data de Início")
        hora_inicio = col1.time_input("⏰ Horário de Início")
        
        data_hora_fim = None
        if metodo_termino == 'Manualmente':
            data_fim_input = col2.date_input("📆 Data de Fim")
            hora_fim_input = col2.time_input("⏰ Horário de Fim")
            if data_fim_input and hora_fim_input:
                data_hora_fim = datetime.combine(data_fim_input, hora_fim_input)
        else:
            duracao_minutos = col2.number_input("⏳ Duração (min)", min_value=1, value=60, step=1)
            if data_inicio and hora_inicio:
                dt_inicio = datetime.combine(data_inicio, hora_inicio)
                dt_fim = dt_inicio + timedelta(minutes=duracao_minutos)
                col2.markdown(f"**Término:** {dt_fim.strftime('%d/%m/%Y às %H:%M')}")
                data_hora_fim = dt_fim
        
        st.markdown("---")
        st.subheader("Lembretes")
        lembretes_selecionados = st.multiselect("🔔 Alertas:", list(lembrete_opcoes.keys()), default=["15 minutos antes"])
        
        st.markdown("---")
        st.subheader("Informações Financeiras")
        # ... (seção financeira sem alterações) ...
        valor_total = st.number_input("💰 Valor Total (R$)", min_value=0.0, value=100.0, step=10.0, format="%.2f")
        entrada = st.checkbox("✅ Houve entrada de dinheiro?")
        valor_entrada_input = 0.0
        forma_pagamento_input = "Não houve entrada"
        if entrada:
            valor_entrada_input = st.number_input("💵 Valor da Entrada (R$)", min_value=0.0, max_value=valor_total, step=10.0, format="%.2f")
            forma_pagamento_input = st.selectbox("💳 Forma de Pagamento", ["Pix", "Dinheiro", "Cartão", "Transferência", "Outro"])

        st.markdown("---")
        if st.button("Agendar Evento", type="primary"):
            # Lógica de validação e criação do evento
            data_hora_inicio = datetime.combine(data_inicio, hora_inicio)
            if data_hora_fim is None: st.error("Defina um horário de término.")
            elif not all([cliente, tipo_servico, local]): st.error("Preencha Cliente, Serviço e Local.")
            elif data_hora_inicio >= data_hora_fim: st.error("Início deve ser antes do fim.")
            else:
                dados = {
                    "cliente": cliente, "tipo_servico": tipo_servico, "local": local, "endereco": endereco,
                    "data_hora_inicio": data_hora_inicio, "data_hora_fim": data_hora_fim,
                    "valor_total": valor_total, "valor_entrada": valor_entrada_input if entrada else 0.0,
                    "forma_pagamento": forma_pagamento_input if entrada else "Não houve entrada",
                    "lembretes_minutos": [lembrete_opcoes[l] for l in lembretes_selecionados]
                }
                with st.spinner("Criando evento..."): link_evento = criar_evento_google_calendar(service, dados)
                if link_evento:
                    st.success("✅ Agendamento criado com sucesso!")
                    st.markdown(f"[📅 Ver no Google Calendar]({link_evento})")
                    enviar_mensagem_telegram_agendamento(cliente, data_inicio, hora_inicio, valor_total, dados["valor_entrada"], tipo_servico)
                    # Lógica de salvar no CSV (mantida como backup)
                    linha = {"Data e Hora Início": data_hora_inicio.strftime("%Y-%m-%d %H:%M"), "Data e Hora Fim": data_hora_fim.strftime("%Y-%m-%d %H:%M"), "Cliente": cliente, "Serviço": tipo_servico, "Duração (min)": (data_hora_fim - data_hora_inicio).total_seconds()/60, "Local": local, "Endereço": endereco, "Valor Total": valor_total, "Entrada": dados["valor_entrada"], "Forma de Pagamento": dados["forma_pagamento"], "Link do Evento": link_evento}
                    df_existente = carregar_agendamentos_csv()
                    df_novo = pd.concat([df_existente, pd.DataFrame([linha])], ignore_index=True)
                    df_novo.to_csv(ARQUIVO_CSV, index=False)
                    st.info(f"💾 Agendamento salvo no backup local '{ARQUIVO_CSV}'.")

    with tab2:
        st.header("🗓️ Seus Compromissos")
        with st.spinner("Buscando agendamentos no Google Calendar..."):
            df_google = puxar_eventos_google_calendar(service)

        if df_google.empty:
            st.success("🎉 Nenhum agendamento futuro encontrado no Google Calendar. Você está livre!")
        else:
            st.subheader("Próximo Agendamento")
            proximo = df_google.iloc[0]
            with st.container(border=True):
                st.markdown(f"##### 👤 **Cliente:** {proximo['Cliente']}")
                st.markdown(f"**🛠️ Serviço:** {proximo['Serviço']}")
                st.markdown(f"**🗓️ Data:** {proximo['Data e Hora Início'].strftime('%d/%m/%Y às %H:%M')}")
                st.markdown(f"**📍 Local:** {proximo['Local']}")
            
            st.markdown("---")
            st.subheader("Todos os Agendamentos Futuros")
            df_display = df_google.copy()
            df_display['Data e Hora Início'] = df_display['Data e Hora Início'].dt.strftime('%d/%m/%Y %H:%M')
            df_display['Data e Hora Fim'] = df_display['Data e Hora Fim'].dt.strftime('%d/%m/%Y %H:%M')
            st.dataframe(df_display.drop(columns=['Link do Evento']), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Histórico de Agendamentos (Backup Local)")
        df_csv = carregar_agendamentos_csv()
        if df_csv.empty:
            st.info("Nenhum histórico de agendamento no arquivo de backup.")
        else:
            st.dataframe(df_csv.sort_values(by='Data e Hora Início', ascending=False), use_container_width=True, hide_index=True)
else:
    st.warning("Falha na autenticação com Google Calendar.")

