"""
Dashboard NPS KeyCore (Streamlit + Plotly) - responsivo, tema claro e escuro

Instalar:  pip install -r requirements-dashboard.txt
Rodar:     streamlit run dashboard/nps_dashboard.py   (a partir da raiz do projeto,
           para pegar o tema de .streamlit/config.toml)
"""
from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from gemini_service import (
    LIMITE_POR_EXECUCAO, MODELO, PROMPT_VERSAO, analisar_comentarios, ia_configurada,
)

st.set_page_config(page_title="NPS", layout="wide")

# Cores que funcionam nos dois temas (claro/escuro em .streamlit/config.toml).
# Não dependem do tema ativo: o Streamlit não reexecuta o script ao trocar de
# tema, então qualquer cor escolhida em Python ficaria presa no tema antigo.
# Fundos, textos e eixos ficam por conta do Streamlit/Plotly (theme="streamlit");
# no CSS, texto herda a cor do tema e fundos/bordas são cinzas translúcidos.
GREEN, RED, BLUE = "#00C060", "#F25555", "#4F7FBF"
GRAY = "rgba(128, 128, 128, 0.35)"   # translúcido: cinza neutro no claro e no escuro
LINE = "#8B7CF6"                     # linha da pontuação e links, legível nos dois fundos
MUTED = "#8A8A93"
UP, DOWN = "#16A34A", "#EF4444"      # variação dos KPIs

st.markdown(
    f"""
    <style>
    .block-container {{ padding: 1.5rem 2rem 3rem; max-width: 1400px; }}

    /* KPIs: grid que quebra sozinho conforme a largura */
    .kpi-grid {{ display:grid; gap:16px; margin:8px 0 16px;
                grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); }}
    .kpi {{ background:rgba(128,128,128,.06); border:1px solid rgba(128,128,128,.2);
           border-radius:8px; padding:16px 18px; }}
    .kpi .t {{ color:{MUTED}; font-size:.9rem; }}
    .kpi .row {{ display:flex; justify-content:space-between;
                align-items:baseline; margin-top:8px; }}
    .kpi .v {{ font-size:1.6rem; font-weight:600; }}
    .kpi .d {{ font-size:.8rem; font-weight:600; }}

    /* legenda do donut */
    .legend-item {{ margin:14px 0; font-size:1.05rem; }}

    /* mobile */
    @media (max-width: 640px) {{
        .block-container {{ padding: 1rem .75rem 2rem; }}
        .kpi-grid {{ grid-template-columns: repeat(2, 1fr); gap:10px; }}
        .kpi {{ padding:12px; }}
        .kpi .v {{ font-size:1.3rem; }}
        h1 {{ font-size:1.6rem !important; }}
    }}

    /* ---------- cards de resposta (melhores/piores) ---------- */
    .resp-card {{ border:1px solid rgba(128,128,128,.2); border-radius:8px;
                  padding:12px 14px; margin-bottom:10px; }}
    .resp-top {{ display:flex; align-items:center; gap:10px; }}
    .resp-top .nota {{ color:#fff; font-weight:700; border-radius:6px;
                       min-width:30px; text-align:center; padding:2px 6px; }}
    .resp-meta {{ color:{MUTED}; font-size:.8rem; }}
    .resp-txt {{ margin:8px 0 6px; line-height:1.4; }}
    .resp-ia {{ color:{MUTED}; font-size:.8rem; }}

    /* ---------- tabela de tags ---------- */
    .tags-table {{ width:100%; margin-top:8px; }}
    .tags-head, .tags-row {{
        display:grid; align-items:center; column-gap:16px;
        grid-template-columns: 2.2fr 1fr 1fr 3fr 1.3fr 32px;
        padding: 0 20px;
    }}
    .tags-head {{ background:rgba(128,128,128,.12); height:56px; font-weight:600;
                  border-radius:6px; }}
    .tags-row {{ min-height:84px; border-bottom:1px solid rgba(128,128,128,.2); }}
    .tags-row:hover {{ background:rgba(128,128,128,.06); }}
    .tags-row a {{ color:{LINE}; text-decoration:underline; font-weight:500; }}
    .tags-row .menu {{ text-align:center; font-size:1.4rem; }}
    .bar {{ display:flex; height:7px; border-radius:4px; overflow:hidden;
            background:rgba(128,128,128,.15); }}
    .bar span {{ display:block; height:100%; }}
    .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
    .lbl {{ display:none; }}

    @media (max-width: 760px) {{
        .tags-head {{ display:none; }}
        .tags-row {{
            grid-template-columns: 1fr 1fr 1fr; row-gap:8px; padding:14px 12px;
            grid-template-areas: "name name menu" "resp score sent" "bar bar bar";
        }}
        .tags-row .c-name  {{ grid-area:name; font-weight:600; }}
        .tags-row .c-resp  {{ grid-area:resp; }}
        .tags-row .c-score {{ grid-area:score; }}
        .tags-row .c-sent  {{ grid-area:sent; }}
        .tags-row .c-bar   {{ grid-area:bar; }}
        .tags-row .menu    {{ grid-area:menu; text-align:right; }}
        .lbl {{ display:block; font-size:.7rem; color:{MUTED}; text-transform:uppercase; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Fundo transparente: o gráfico fica com o fundo do card/tema; vírgula decimal
PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    separators=",.",
    autosize=True,
)
PLOT_CFG = {"displayModeBar": False, "responsive": True}


# ---------------------------------------------------------------- dados
def calc_nps(promoters: int, passives: int, detractors: int) -> float:
    total = promoters + passives + detractors
    return round((promoters - detractors) / total * 100, 1) if total else 0.0


SENT_COLOR = {"Positivo": GREEN, "Neutro": MUTED, "Negativo": RED}
FAIXA_COLOR = {"Promotor": GREEN, "Neutro": MUTED, "Detrator": RED}

# Comentários de exemplo por faixa. Os detratores e neutros cobrem as classes de
# problema da IA (valor, sistema, demora, cobrança indevida, outros).
_COMENTARIOS = {
    "Promotor": [
        "Atendimento excelente, resolveram meu problema no mesmo dia.",
        "A plataforma é muito fácil de usar, recomendo para todo mundo.",
        "Entrega antes do prazo e produto de ótima qualidade.",
        "Suporte rápido e atencioso, superou minhas expectativas.",
        "Melhor custo-benefício que já encontrei no mercado.",
        "Uso todos os dias no trabalho e nunca me deixou na mão.",
        "O time de suporte é muito educado e explica tudo com paciência.",
        "Os relatórios novos ajudaram muito a minha equipe.",
        "Migrar para a KeyCore foi a melhor decisão do ano.",
        "Aplicativo rápido, bonito e sem travamentos.",
        "Gostei muito da transparência na cobrança, sem surpresas na fatura.",
        "Resolveram uma dúvida complexa em poucos minutos pelo chat.",
        "Produto confiável, já indiquei para dois parceiros.",
        "A implantação foi tranquila e bem acompanhada.",
        "Preço justo pelo que entrega, vale cada centavo.",
        "Adoro as atualizações frequentes, sempre trazem algo útil.",
        "Atendimento humanizado, me senti muito bem tratado.",
        "Tudo funciona como prometido, sem complicação.",
    ],
    "Neutro": [
        "Bom produto, mas o preço poderia ser menor.",
        "Funciona bem, porém a interface é um pouco confusa.",
        "O prazo de entrega atrasou alguns dias.",
        "Atende ao básico, sem grandes diferenciais.",
        "Gosto do sistema, mas às vezes fica lento no fim do mês.",
        "O suporte resolve, mas demora um pouco para responder.",
        "O plano ficou mais caro depois do reajuste.",
        "Falta integração com outras ferramentas que usamos.",
        "Bom no geral, mas o aplicativo trava de vez em quando.",
        "Vi uma taxa na fatura que não entendi direito.",
        "Poderiam ter mais opções de relatório.",
        "Cumpre o que promete, nada além disso.",
        "A documentação é fraca, tive que pedir ajuda para configurar.",
        "Atendimento educado, mas precisei explicar o problema três vezes.",
    ],
    "Detrator": [
        "Demoraram uma semana para responder meu chamado.",
        "O sistema caiu várias vezes durante o mês.",
        "Cobrança indevida e ninguém resolve.",
        "Produto chegou com defeito e a troca foi um sofrimento.",
        "Muito caro para o que entrega.",
        "Fui cobrado duas vezes no mesmo mês e o estorno não saiu.",
        "Cancelei o plano e continuaram cobrando no cartão.",
        "Apareceu um serviço na fatura que eu nunca contratei.",
        "O aplicativo fecha sozinho toda vez que tento salvar.",
        "Perdi dados importantes depois de uma atualização do sistema.",
        "A plataforma fica fora do ar justo no horário de pico.",
        "O login dá erro quase todo dia.",
        "Esperei mais de uma hora na fila do atendimento.",
        "A entrega atrasou quinze dias e ninguém avisou nada.",
        "Abri o chamado há um mês e continua sem solução.",
        "O reajuste foi absurdo, quase dobrou o valor da mensalidade.",
        "Pelo preço que pago esperava muito mais.",
        "A concorrência oferece o mesmo pela metade do valor.",
        "O atendente foi grosso e desligou na minha cara.",
        "Prometeram uma funcionalidade na venda que não existe.",
        "Não consigo falar com ninguém, só robô respondendo.",
        "O contrato tem cláusulas escondidas que ninguém explicou.",
    ],
}
_CHANCE_COMENTARIO = 0.8   # o resto responde só a nota
DIAS_HISTORICO = 180       # o mock cobre 180 dias: período atual + anterior
DIAS_PERIODO = {"Últimos 7 dias": 7, "Últimos 30 dias": 30, "Últimos 90 dias": 90}


def faixa_nps(nota: int) -> str:
    return "Promotor" if nota >= 9 else "Neutro" if nota >= 7 else "Detrator"


@st.cache_data
def load_respostas(seed: int = 11, n: int = 1000) -> pd.DataFrame:
    """
    Dados mock das respostas. Troque por consulta ao banco/API.

    As colunas *_ia ficam vazias até a camada de IA existir. Ela vai preencher
    a análise sugerida (sentimento, tema, confiança, justificativa) sem nunca
    alterar a nota nem o NPS.
    """
    rng = np.random.default_rng(seed)
    hoje = pd.Timestamp.today().normalize()
    notas = rng.choice(11, size=n, p=[.03, .02, .03, .03, .04, .05, .07, .10, .13, .20, .30])
    rows = []
    for i, nota in enumerate(notas):
        faixa = faixa_nps(int(nota))
        rows.append({
            "id": f"R{i + 1:04d}",
            "data": hoje - pd.Timedelta(days=int(rng.integers(0, DIAS_HISTORICO))),
            "nota": int(nota),
            "faixa": faixa,
            "comentario": (str(rng.choice(_COMENTARIOS[faixa]))
                           if rng.random() < _CHANCE_COMENTARIO else ""),
            "segmento": str(rng.choice(["Empresarial", "PME", "Gratuito"])),
            "empresa": str(rng.choice(["Empresa A", "Empresa B"])),
            "sentimento_ia": None,
            "tema_ia": None,
            "confianca_ia": None,
            "justificativa_ia": None,
            "problema_ia": None,
            "status_ia": None,
        })
    return pd.DataFrame(rows)


@st.cache_data
def load_exibicoes(seed: int = 23) -> pd.DataFrame:
    """
    Dados mock: pesquisas exibidas que NÃO viraram resposta (dispensadas ou
    ignoradas). Total exibido = respostas + estas. Troque por consulta ao banco/API.
    """
    rng = np.random.default_rng(seed)
    hoje = pd.Timestamp.today().normalize()
    n = int(len(load_respostas()) * 1.8)
    return pd.DataFrame({
        "data": [hoje - pd.Timedelta(days=int(d)) for d in rng.integers(0, DIAS_HISTORICO, n)],
        "segmento": rng.choice(["Empresarial", "PME", "Gratuito"], n),
        "empresa": rng.choice(["Empresa A", "Empresa B"], n),
        "resultado": rng.choice(["dispensou", "ignorou"], n, p=[0.4, 0.6]),
    })


SENTIMENTO_LABEL = {"POSITIVO": "Positivo", "NEUTRO": "Neutro", "NEGATIVO": "Negativo"}
TEMA_LABEL = {"atendimento": "Atendimento", "preco": "Preço", "produto": "Produto",
              "prazo": "Prazo", "usabilidade": "Usabilidade", "outro": "Outro"}
PROBLEMA_LABEL = {"valor": "Valor", "sistema": "Sistema", "demora": "Demora",
                  "cobranca_indevida": "Cobrança indevida", "outros": "Outros"}
STATUS_IA_LABEL = {"CONCLUIDA": "Concluída", "BAIXA_CONFIANCA": "Baixa confiança",
                   "FALHA_SCHEMA": "Falha de formato", "PENDENTE": "Pendente"}


def aplicar_analises(df: pd.DataFrame, analises: dict[str, dict]) -> pd.DataFrame:
    """Preenche as colunas *_ia com as análises sugeridas já geradas (nota intocada)."""
    df = df.copy()
    pega = lambda campo: df["id"].map(lambda i: analises.get(i, {}).get(campo))
    df["sentimento_ia"] = pega("sentimento").map(SENTIMENTO_LABEL)
    df["tema_ia"] = pega("tema").map(TEMA_LABEL)
    df["confianca_ia"] = pega("confianca")
    df["justificativa_ia"] = pega("justificativa")
    df["problema_ia"] = pega("problema").map(PROBLEMA_LABEL)
    df["status_ia"] = pega("status").map(STATUS_IA_LABEL)
    return df


def aplicar_filtros(df: pd.DataFrame, seg: str, emp: str, per: str,
                    anterior: bool = False) -> pd.DataFrame:
    """Segmento, empresa e janela de datas (o período escolhido ou o imediatamente anterior)."""
    dias = DIAS_PERIODO[per]
    fim = pd.Timestamp.today().normalize() - pd.Timedelta(days=dias if anterior else 0)
    df = df[(df["data"] > fim - pd.Timedelta(days=dias)) & (df["data"] <= fim)]
    if not seg.startswith("Todos"):
        df = df[df["segmento"] == seg]
    if not emp.startswith("Todas"):
        df = df[df["empresa"] == emp]
    return df


def contagem_faixas(df: pd.DataFrame) -> tuple[int, int, int]:
    cont = df["faixa"].value_counts()
    return tuple(int(cont.get(f, 0)) for f in ("Promotor", "Neutro", "Detrator"))


def metricas_exibicao(resp: pd.DataFrame, exib: pd.DataFrame) -> dict:
    exibidas = len(resp) + len(exib)
    return {
        "exibidas": exibidas,
        "respostas": len(resp),
        "taxa": len(resp) / exibidas if exibidas else 0.0,
        "dispensadas": int((exib["resultado"] == "dispensou").sum()),
        "qualitativas": int((resp["comentario"].str.strip() != "").sum()),
    }


def historico(df: pd.DataFrame, dias: int) -> pd.DataFrame:
    """NPS e faixas por dia (7 dias) ou por semana (30/90 dias)."""
    freq = "D" if dias <= 7 else "W"
    g = (df.assign(periodo=df["data"].dt.to_period(freq).dt.start_time)
         .groupby("periodo")["faixa"].value_counts().unstack(fill_value=0)
         .reindex(columns=["Promotor", "Neutro", "Detrator"], fill_value=0))
    g["total"] = g.sum(axis=1)
    g["score"] = [calc_nps(p, n, d) for p, n, d in zip(g["Promotor"], g["Neutro"], g["Detrator"])]
    g = g.reset_index()
    g["period"] = g["periodo"].dt.strftime("%d/%m")
    return g


def resumo_tags(df: pd.DataFrame, coluna: str, nomes: list[str]) -> pd.DataFrame:
    """Uma linha por tag fixa (mesmo sem respostas), a partir da análise sugerida."""
    linhas = []
    for nome in nomes:
        g = df[df[coluna] == nome]
        n = len(g)
        p, ne, d = contagem_faixas(g)
        linhas.append({
            "nome": nome,
            "respostas": n,
            "pro": p / n * 100 if n else 0, "pas": ne / n * 100 if n else 0,
            "det": d / n * 100 if n else 0,
            "score": calc_nps(p, ne, d) if n else None,
            "sentimento": g["sentimento_ia"].mode().iloc[0] if n else "—",
        })
    return pd.DataFrame(linhas).sort_values("respostas", ascending=False)


def ranquear(df: pd.DataFrame, melhores: bool, n: int = 5) -> pd.DataFrame:
    """
    Melhores/piores respostas com comentário.

    Ordena pela nota. No empate, usa o sentimento sugerido pela IA ponderado
    pela confiança (só análises concluídas, confiança >= 0,6) e, por fim, a
    resposta mais recente. A IA só desempata: nunca muda a nota.
    """
    com_texto = df[df["comentario"].str.strip() != ""].copy()
    sinal = com_texto["sentimento_ia"].map({"Positivo": 1, "Neutro": 0, "Negativo": -1})
    valido = com_texto["status_ia"] == "Concluída"
    com_texto["_ia"] = (sinal * com_texto["confianca_ia"]).where(valido, 0).fillna(0)
    return com_texto.sort_values(
        ["nota", "_ia", "data"], ascending=[not melhores, not melhores, False]
    ).head(n)


def render_filters(key: str) -> tuple[str, str, str]:
    """Filtros de segmento, empresa e período (3 colunas; empilham no mobile)."""
    f1, f2, f3 = st.columns(3)
    seg = f1.selectbox("Segmento", ["Todos os segmentos", "Empresarial", "PME", "Gratuito"],
                       key=f"{key}_seg")
    emp = f2.selectbox("Empresa", ["Todas as empresas", "Empresa A", "Empresa B"],
                       key=f"{key}_emp")
    per = f3.selectbox("Período", ["Últimos 7 dias", "Últimos 30 dias", "Últimos 90 dias"],
                       key=f"{key}_per")
    return seg, emp, per


def kpi_grid(itens: list[tuple[str, str]]) -> None:
    """Cards de indicador sem variação (título, valor)."""
    cards = "".join(
        f'<div class="kpi"><div class="t">{t}</div>'
        f'<div class="row"><span class="v">{v}</span></div></div>'
        for t, v in itens
    )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def kpi_grid_delta(itens: list[tuple[str, str, float | None, bool]]) -> None:
    """
    Cards com variação contra o período anterior: (título, valor, variação %, inverso).
    Variação None = sem base para comparar. inverso=True quando subir é ruim.
    """
    cards = ""
    for titulo, valor, delta, inverso in itens:
        if delta is None:
            d = f'<span class="d" style="color:{MUTED}">—</span>'
        else:
            bom = (delta >= 0) != inverso
            seta = "↑" if delta >= 0 else "↓"
            d = f'<span class="d" style="color:{UP if bom else DOWN}">{seta} {abs(delta):.0f}%</span>'
        cards += (f'<div class="kpi"><div class="t">{titulo}</div>'
                  f'<div class="row"><span class="v">{valor}</span>{d}</div></div>')
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def botao_analise(df: pd.DataFrame, key: str) -> None:
    """Botão que manda para a IA os comentários de df ainda sem análise válida."""
    com_texto = df[df["comentario"].str.strip() != ""]
    pendentes = com_texto[~com_texto["status_ia"].isin(["Concluída", "Baixa confiança"])]
    if not ia_configurada():
        st.button("Gerar análise", disabled=True, width="stretch", key=key)
        st.warning("Chave do Gemini não encontrada. Defina GEMINI_API_KEY no .env.")
        return
    if st.button(f"Gerar análise ({len(pendentes)})", type="primary",
                 disabled=pendentes.empty, width="stretch", key=key):
        with st.spinner("Analisando comentários com o Gemini..."):
            novas = analisar_comentarios(dict(zip(pendentes["id"], pendentes["comentario"])))
        st.session_state["analises_ia"].update(novas)
        st.rerun()


def card_resposta(r) -> str:
    """Card de uma resposta. Comentário vem do cliente: sempre escapado."""
    cor = FAIXA_COLOR[r.faixa]
    if r.status_ia in ("Concluída", "Baixa confiança"):
        # sem reclamação vem NaN do pandas (que é "verdadeiro"): checar com notna
        problema = f" · problema: {escape(r.problema_ia)}" if pd.notna(r.problema_ia) else ""
        ia = (f"{escape(r.sentimento_ia)} · {escape(r.tema_ia)}{problema} · "
              f"{r.confianca_ia:.0%} de confiança")
        if r.status_ia == "Baixa confiança":
            ia += " (baixa, fora das contagens)"
        if r.justificativa_ia:
            ia += f'<br><i>{escape(r.justificativa_ia)}</i>'
    else:
        ia = escape(str(r.status_ia or "pendente")).lower()
    return (
        '<div class="resp-card">'
        f'<div class="resp-top"><span class="nota" style="background:{cor}">{r.nota}</span>'
        f'<span class="resp-meta">{r.faixa} · {r.data:%d/%m/%Y} · {escape(r.empresa)}</span></div>'
        f'<div class="resp-txt">“{escape(r.comentario)}”</div>'
        f'<div class="resp-ia">🤖 Análise sugerida: {ia}</div>'
        "</div>"
    )


# ---------------------------------------------------------------- análises da IA (sessão)
analises = st.session_state.setdefault("analises_ia", {})
# prompt mudou → análises antigas saem e a resposta volta a ficar pendente
for id_resp in [k for k, a in analises.items() if a.get("versao_prompt") != PROMPT_VERSAO]:
    del analises[id_resp]
base = aplicar_analises(load_respostas(), analises)

# ---------------------------------------------------------------- cabeçalho
col_title, col_btn = st.columns([5, 1], vertical_alignment="center")
col_title.title("NPS")
col_btn.button("Editar NPS", type="primary", width="stretch")

tab_overview, tab_responses, tab_tags = st.tabs(["Visão geral", "Respostas", "Tags"])

with tab_overview:
    filtros_ov = render_filters("ov")
    dias = DIAS_PERIODO[filtros_ov[2]]
    atual = aplicar_filtros(base, *filtros_ov)
    m_at = metricas_exibicao(atual, aplicar_filtros(load_exibicoes(), *filtros_ov))
    m_ant = metricas_exibicao(aplicar_filtros(base, *filtros_ov, anterior=True),
                              aplicar_filtros(load_exibicoes(), *filtros_ov, anterior=True))

    def variacao(chave: str) -> float | None:
        a, b = m_at[chave], m_ant[chave]
        return (a - b) / b * 100 if b else None

    # ------------------------------------------------------------ KPIs
    kpi_grid_delta([
        ("👁 Total exibido", fmt_int(m_at["exibidas"]), variacao("exibidas"), False),
        ("💬 Total de respostas", fmt_int(m_at["respostas"]), variacao("respostas"), False),
        ("📈 Taxa de resposta", f"{m_at['taxa']:.1%}".replace(".", ","), variacao("taxa"), False),
        ("⊗ Dispensadas", fmt_int(m_at["dispensadas"]), variacao("dispensadas"), True),
        ("✅ Respostas qualitativas", fmt_int(m_at["qualitativas"]),
         variacao("qualitativas"), False),
    ])
    st.caption(f"Variação comparada aos {dias} dias anteriores.")

    if atual.empty:
        st.info("Nenhuma resposta para os filtros escolhidos.")
    else:
        # -------------------------------------------------------- Pontuação + Respostas
        promoters, passives, detractors = contagem_faixas(atual)
        score = calc_nps(promoters, passives, detractors)
        total = promoters + passives + detractors

        c1, c2 = st.columns(2)

        with c1, st.container(border=True):
            st.subheader("Pontuação")
            gauge = go.Figure(
                go.Indicator(
                    mode="gauge+number",
                    value=score,
                    number={"font": {"color": BLUE, "size": 44}},
                    gauge={
                        "axis": {"range": [-100, 100], "tickvals": [-100, 0, 100]},
                        "bar": {"color": BLUE, "thickness": 0.35},
                        "bgcolor": GRAY,
                        "borderwidth": 0,
                    },
                )
            )
            gauge.update_layout(**PLOT_LAYOUT, height=280, margin=dict(t=30, b=10, l=30, r=30))
            st.plotly_chart(gauge, width="stretch", config=PLOT_CFG)

        with c2, st.container(border=True):
            st.subheader("Respostas")
            d1, d2 = st.columns(2, vertical_alignment="center")
            donut = go.Figure(
                go.Pie(
                    values=[promoters, passives, detractors],
                    labels=["Promotores", "Neutros", "Detratores"],
                    hole=0.78,
                    marker_colors=[GREEN, GRAY, RED],
                    textinfo="none",
                    sort=False,
                )
            )
            donut.update_layout(
                **PLOT_LAYOUT, height=260, showlegend=False,
                margin=dict(t=10, b=10, l=10, r=10),
            )
            d1.plotly_chart(donut, width="stretch", config=PLOT_CFG)

            legend = ""
            for icon, label, val, color in [
                ("😊", "Promotores", promoters, GREEN),
                ("😐", "Neutros", passives, MUTED),
                ("☹️", "Detratores", detractors, RED),
            ]:
                legend += (
                    f'<div class="legend-item"><span style="color:{color}">{icon}</span> '
                    f"{label}<br><b>{val} ({val / total:.0%})</b></div>"
                )
            d2.markdown(legend, unsafe_allow_html=True)

        # -------------------------------------------------------- Histórico
        with st.container(border=True):
            st.subheader("Histórico do NPS")
            st.caption("Por dia" if dias <= 7 else "Por semana")
            df = historico(atual, dias)
            pct = lambda col: df[col] / df["total"] * 100

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            # barras empilhadas (% de respostas) -> eixo secundário
            fig.add_bar(x=df["period"], y=pct("Detrator"), name="Detratores",
                        marker_color=RED, secondary_y=True)
            fig.add_bar(x=df["period"], y=pct("Neutro"), name="Neutros",
                        marker_color=GRAY, secondary_y=True)
            fig.add_bar(x=df["period"], y=pct("Promotor"), name="Promotores",
                        marker_color=GREEN, secondary_y=True)

            # linha de pontuação: sólida até o penúltimo ponto, tracejada no último
            # (o período mais recente ainda está em andamento)
            fig.add_scatter(x=df["period"][:-1], y=df["score"][:-1], name="Pontuação",
                            mode="lines+markers", line=dict(color=LINE, shape="spline"),
                            secondary_y=False)
            fig.add_scatter(x=df["period"][-2:], y=df["score"][-2:], showlegend=False,
                            mode="lines+markers", line=dict(color=LINE, dash="dash"),
                            secondary_y=False)

            fig.update_layout(
                **PLOT_LAYOUT, barmode="stack", height=400, bargap=0.5,
                legend=dict(orientation="h", y=1.15, x=0),
                margin=dict(t=40, b=20, l=10, r=10),
            )
            fig.update_yaxes(title_text="Pontuação", range=[-100, 100], secondary_y=False)
            fig.update_yaxes(title_text="Respostas", range=[0, 100], ticksuffix="%",
                             showgrid=False, secondary_y=True)
            st.plotly_chart(fig, width="stretch", config=PLOT_CFG)

with tab_responses:
    resp = aplicar_filtros(base, *render_filters("rs"))

    if resp.empty:
        st.info("Nenhuma resposta para os filtros escolhidos.")
    else:
        # -------------------------------------------------------- Análise sugerida (IA)
        with st.container(border=True):
            a1, a2 = st.columns([3, 1], vertical_alignment="center")
            a1.subheader("🤖 Análise sugerida pela IA")
            a1.caption(
                f"Gemini `{MODELO}` · prompt `{PROMPT_VERSAO}`. Antes do envio, CPF, e-mail e "
                "telefone são mascarados; se não der para mascarar com segurança, o comentário "
                f"não é enviado. Até {LIMITE_POR_EXECUCAO} comentários distintos por vez. "
                "A IA só sugere: nunca altera a nota nem o NPS."
            )
            with a2:
                botao_analise(resp, "btn_ia")

            falhas = [a["erro"] for a in analises.values() if a["status"] == "PENDENTE" and a["erro"]]
            if falhas:
                st.warning(f"{len(falhas)} comentário(s) ficaram pendentes: {falhas[0]}")


        # -------------------------------------------------------- Resumo
        cont = resp["faixa"].value_counts()
        com_texto = (resp["comentario"].str.strip() != "").mean()
        nps = calc_nps(cont.get("Promotor", 0), cont.get("Neutro", 0), cont.get("Detrator", 0))
        kpi_grid([
            ("📊 NPS do período", f"{nps:.1f}".replace(".", ",")),
            ("💬 Respostas", f"{len(resp)}"),
            ("⭐ Nota média", f"{resp['nota'].mean():.1f}".replace(".", ",")),
            ("✍️ Com comentário", f"{com_texto:.0%}"),
            # baixa confiança fica fora das contagens
            ("🤖 Analisadas pela IA", f"{(resp['status_ia'] == 'Concluída').sum()}"),
        ])

        # -------------------------------------------------------- Distribuição
        with st.container(border=True):
            st.subheader("Distribuição das notas")
            dist = resp["nota"].value_counts().reindex(range(11), fill_value=0)
            barras = go.Figure(go.Bar(
                x=list(dist.index), y=list(dist.values),
                marker_color=[FAIXA_COLOR[faixa_nps(n)] for n in dist.index],
                hovertemplate="Nota %{x}: %{y} respostas<extra></extra>",
            ))
            barras.update_layout(**PLOT_LAYOUT, height=280, bargap=0.25,
                                 margin=dict(t=10, b=10, l=10, r=10))
            barras.update_xaxes(title_text="Nota", tickmode="linear", dtick=1)
            barras.update_yaxes(title_text="Respostas")
            st.plotly_chart(barras, width="stretch", config=PLOT_CFG)

        # -------------------------------------------------------- Melhores x piores
        m1, m2 = st.columns(2)
        with m1, st.container(border=True):
            st.subheader("😊 Melhores respostas")
            st.markdown("".join(card_resposta(r) for r in ranquear(resp, True).itertuples()),
                        unsafe_allow_html=True)
        with m2, st.container(border=True):
            st.subheader("☹️ Piores respostas")
            st.markdown("".join(card_resposta(r) for r in ranquear(resp, False).itertuples()),
                        unsafe_allow_html=True)

        # -------------------------------------------------------- Problemas por classe
        with st.container(border=True):
            st.subheader("🚨 Problemas por classe (análise sugerida)")
            # só análises concluídas (baixa confiança fica fora das contagens)
            problemas = resp[(resp["status_ia"] == "Concluída") & resp["problema_ia"].notna()]
            if problemas.empty:
                st.info("Gere a análise sugerida acima para classificar as reclamações em "
                        "Valor, Sistema, Demora, Cobrança indevida e Outros.")
            else:
                classes = list(PROBLEMA_LABEL.values())
                resumo = (
                    problemas.groupby("problema_ia")
                    .agg(reclamacoes=("id", "size"),
                         detratores=("faixa", lambda f: (f == "Detrator").sum()),
                         nota_media=("nota", "mean"))
                    .reindex(classes, fill_value=0)
                    .reset_index(names="classe")
                )
                # classe sem reclamação não tem nota média (não é 0)
                resumo["nota_media"] = resumo["nota_media"].where(resumo["reclamacoes"] > 0)
                resumo["pct"] = resumo["reclamacoes"] / resumo["reclamacoes"].sum()
                resumo = resumo.sort_values("reclamacoes", ascending=False)

                st.dataframe(
                    resumo,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "classe": "Classe",
                        "reclamacoes": st.column_config.NumberColumn("Reclamações", format="%d"),
                        "detratores": st.column_config.NumberColumn("Detratores", format="%d"),
                        "nota_media": st.column_config.NumberColumn("Nota média", format="%.1f"),
                        "pct": st.column_config.ProgressColumn(
                            "% das reclamações", min_value=0, max_value=1, format="percent"),
                    },
                )

                # respostas de cada classe, piores primeiro
                for classe in resumo.loc[resumo["reclamacoes"] > 0, "classe"]:
                    grupo = problemas[problemas["problema_ia"] == classe].sort_values(
                        ["nota", "data"], ascending=[True, False])
                    with st.expander(f"{classe} · {len(grupo)} resposta(s)"):
                        st.dataframe(
                            grupo,
                            hide_index=True,
                            width="stretch",
                            column_order=["data", "nota", "faixa", "comentario",
                                          "justificativa_ia", "confianca_ia"],
                            column_config={
                                "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                "nota": st.column_config.NumberColumn("Nota", format="%d"),
                                "faixa": "Faixa",
                                "comentario": st.column_config.TextColumn("Comentário",
                                                                          width="large"),
                                "justificativa_ia": st.column_config.TextColumn(
                                    "Justificativa (sugerida)", width="large"),
                                "confianca_ia": st.column_config.ProgressColumn(
                                    "Confiança", min_value=0, max_value=1, format="percent"),
                            },
                        )

        # -------------------------------------------------------- Todas as respostas
        with st.container(border=True):
            t1, t2, t3 = st.columns([2, 3, 1], vertical_alignment="center")
            t1.subheader("Todas as respostas")
            faixa_sel = t2.segmented_control(
                "Faixa", ["Todas", "Promotor", "Neutro", "Detrator"],
                default="Todas", key="rs_faixa", label_visibility="collapsed",
            )
            tabela = resp if faixa_sel in (None, "Todas") else resp[resp["faixa"] == faixa_sel]
            tabela = tabela.sort_values("data", ascending=False)

            # Comentários vêm do cliente: o CSV aberto no Excel não pode
            # executar fórmula (=, +, -, @ no início viram texto)
            exp = tabela[["data", "nota", "faixa", "comentario", "empresa", "segmento"]].copy()
            exp["comentario"] = exp["comentario"].where(
                ~exp["comentario"].str.match(r"^[=+\-@]"), "'" + exp["comentario"]
            )
            t3.download_button(
                "⬇ Exportar",
                exp.to_csv(index=False, sep=";", date_format="%d/%m/%Y").encode("utf-8-sig"),
                "respostas_nps.csv", "text/csv", width="stretch",
            )

            st.dataframe(
                tabela,
                hide_index=True,
                width="stretch",
                column_order=["data", "nota", "faixa", "comentario", "empresa",
                              "sentimento_ia", "tema_ia", "problema_ia", "confianca_ia",
                              "status_ia", "justificativa_ia"],
                column_config={
                    "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "nota": st.column_config.NumberColumn("Nota", format="%d"),
                    "faixa": "Faixa",
                    "comentario": st.column_config.TextColumn("Comentário", width="large"),
                    "empresa": "Empresa",
                    "sentimento_ia": "Sentimento (sugerido)",
                    "tema_ia": "Tema (sugerido)",
                    "problema_ia": "Problema (sugerido)",
                    "confianca_ia": st.column_config.ProgressColumn(
                        "Confiança", min_value=0, max_value=1, format="percent"),
                    "status_ia": "Status da análise",
                    "justificativa_ia": st.column_config.TextColumn("Justificativa (sugerida)",
                                                                    width="large"),
                },
            )
            st.caption(
                "🤖 Colunas *sugerido*: análise sugerida pela IA. Confiança abaixo de 60% "
                "fica como baixa confiança e fora das contagens. A IA nunca altera a nota nem o NPS."
            )

with tab_tags:
    dados = aplicar_filtros(base, *render_filters("tg"))

    with st.container(border=True):
        h1, h2, h3, h4 = st.columns([1, 2, 3, 1], vertical_alignment="center")
        h1.subheader("Tags")
        agrupar = h2.segmented_control(
            "Agrupar por", ["Tema", "Problema"], default="Tema", key="tg_grupo",
            label_visibility="collapsed",
        ) or "Tema"
        busca = h3.text_input("Buscar tags", placeholder="🔍 Buscar tags...",
                              label_visibility="collapsed")

        # tags fixas: as listas fechadas da IA. Ela só identifica a qual tag cada
        # comentário pertence; baixa confiança fica fora das contagens
        coluna, nomes = (("tema_ia", list(TEMA_LABEL.values())) if agrupar == "Tema"
                         else ("problema_ia", list(PROBLEMA_LABEL.values())))
        analisadas = dados[dados["status_ia"] == "Concluída"]
        tags = resumo_tags(analisadas, coluna, nomes)
        if busca:
            tags = tags[tags["nome"].str.contains(busca, case=False, regex=False)]

        # ";" como separador: o Excel em português abre direto em colunas
        csv = tags[["nome", "respostas", "score", "sentimento"]].rename(
            columns={"nome": "Nome", "respostas": "Respostas",
                     "score": "Pontuação", "sentimento": "Sentimento"}
        ).to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
        h4.download_button("⬇ Exportar", csv, "tags_nps.csv", "text/csv",
                           width="stretch")

        n_texto = int((dados["comentario"].str.strip() != "").sum())
        b1, b2 = st.columns([3, 1], vertical_alignment="center")
        falta = "" if len(analisadas) >= n_texto else " Gere a análise para incluir os que faltam."
        b1.caption(
            f"🤖 Tags identificadas pela análise sugerida: {len(analisadas)} de {n_texto} "
            f"comentários do período classificados.{falta}"
        )
        with b2:
            botao_analise(dados, "btn_ia_tg")

        if tags.empty:
            st.info("Nenhuma tag encontrada.")
        else:
            rows = ""
            for t in tags.itertuples():
                cor = SENT_COLOR.get(t.sentimento, MUTED)
                score = "—" if pd.isna(t.score) else f"{t.score:.0f}"
                rows += (
                    '<div class="tags-row">'
                    f'<div class="c-name">{escape(t.nome)}</div>'
                    f'<div class="c-resp"><span class="lbl">Respostas</span>{t.respostas}</div>'
                    f'<div class="c-score"><span class="lbl">Pontuação</span>{score}</div>'
                    '<div class="c-bar"><div class="bar">'
                    f'<span style="width:{t.pro:.1f}%;background:{GREEN}"></span>'
                    f'<span style="width:{t.pas:.1f}%;background:{GRAY}"></span>'
                    f'<span style="width:{t.det:.1f}%;background:{RED}"></span>'
                    "</div></div>"
                    f'<div class="c-sent"><span class="lbl">Sentimento</span>'
                    f'<span class="dot" style="background:{cor}"></span>{escape(t.sentimento)}</div>'
                    '<div class="menu">⋮</div>'
                    "</div>"
                )
            st.markdown(
                '<div class="tags-table"><div class="tags-head">'
                "<div>Nome</div><div>Respostas</div><div>Pontuação</div>"
                "<div></div><div>Sentimento</div><div></div></div>"
                f"{rows}</div>",
                unsafe_allow_html=True,
            )
