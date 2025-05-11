
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="CRM Imobiliário - Painel Interativo", layout="wide")
st.title("🏘️ Painel de Controle - Empreendimentos Imobiliários")

# Dados simulados
def gerar_dados():
    empreendimentos = ["Saint Louis", "Mont Serrano", "Park Serena", "Poente", "Arty"]
    np.random.seed(42)
    data = []
    for emp in empreendimentos:
        valor_unidade = np.random.randint(150000, 300000)
        unidades = np.random.randint(50, 150)
        vgv_total = valor_unidade * unidades
        vendas_abril = np.random.randint(10, 50)
        vgv_abril = vendas_abril * valor_unidade
        vendas_proj = np.random.randint(40, 100)
        vgv_proj = (vendas_abril + vendas_proj) * valor_unidade
        obra_realizada = round(np.random.uniform(0.15, 0.5) * 100, 1)
        custo_obra = vgv_total * np.random.uniform(0.45, 0.65)

        data.append({
            "Empreendimento": emp,
            "Valor Unidade (R$)": valor_unidade,
            "Unidades Totais": unidades,
            "VGV Total (R$)": round(vgv_total, 2),
            "Vendas Acumuladas até Abr/25": vendas_abril,
            "VGV Vendido até Abr/25 (R$)": round(vgv_abril, 2),
            "Vendas Projetadas Mai-Dez/25": vendas_proj,
            "VGV Vendido Projetado (R$)": round(vgv_proj, 2),
            "% Obra Realizada até Abr/25": obra_realizada,
            "% Obra Projetada até Dez/25": 100.0,
            "Custo Total de Obra Projetado (R$)": round(custo_obra, 2)
        })
    return pd.DataFrame(data)

df = gerar_dados()

# Filtros
empreendimento_select = st.multiselect("Filtrar por Empreendimento", options=df["Empreendimento"].unique(), default=df["Empreendimento"].unique())
df_filtrado = df[df["Empreendimento"].isin(empreendimento_select)]

# KPIs
col1, col2, col3 = st.columns(3)
col1.metric("VGV Total", f"R$ {df_filtrado['VGV Total (R$)'].sum():,.0f}")
col2.metric("VGV Vendido Proj.", f"R$ {df_filtrado['VGV Vendido Projetado (R$)'].sum():,.0f}")
col3.metric("Custo Total de Obra", f"R$ {df_filtrado['Custo Total de Obra Projetado (R$)'].sum():,.0f}")

# Gráficos
st.markdown("---")
st.subheader("📈 Evolução por Empreendimento")

col4, col5 = st.columns(2)

fig_vgv = px.bar(df_filtrado, x="Empreendimento", y=["VGV Vendido até Abr/25 (R$)", "VGV Vendido Projetado (R$)"],
                 title="VGV Vendido (Real x Projetado)", barmode="group", text_auto=True)
col4.plotly_chart(fig_vgv, use_container_width=True)

fig_obra = px.bar(df_filtrado, x="Empreendimento", y=["% Obra Realizada até Abr/25", "% Obra Projetada até Dez/25"],
                  title="Progresso da Obra (Real x Projetado)", barmode="group", text_auto=True)
col5.plotly_chart(fig_obra, use_container_width=True)

# Tabela editável
st.markdown("---")
st.subheader("📋 Dados Detalhados e Editáveis")
edited_df = st.data_editor(df_filtrado, use_container_width=True, num_rows="dynamic")

# Exportar
st.download_button("📥 Baixar Dados em Excel", data=edited_df.to_csv(index=False).encode(), file_name="crm_empreendimentos.csv", mime="text/csv")
