"""Painel da prévia de cotas, identidade Hedge Investments. Uso: streamlit run painel.py"""
import io
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import previa as pv

PALETA = {
    "marinho": "#0A4263", "azul": "#00A0D7", "celeste": "#81C1D7", "petroleo": "#145A75",
    "verde": "#4B7C25", "vermelho": "#C44000", "laranja": "#F98909", "cinza": "#736154", "fundo": "#F2F6F9",
}
JAN = list(pv.JANELAS)
TODAS = pv.todas_janelas()
COR_JANELA = {"1m": PALETA["celeste"], "2m": PALETA["azul"], "3m": PALETA["petroleo"], "12m": PALETA["marinho"],
              "combinada": PALETA["laranja"]}
FONTE = "'Compass', 'Compass Sans', 'Compass Pro', 'Segoe UI', Helvetica, Arial, sans-serif"
R = pv.rot
AMPLITUDE_MIN = 0.0025
LARG = {"Fundo": st.column_config.TextColumn("Fundo", width="large"),
        "Nome": st.column_config.TextColumn("Fundo", width="large"),
        "Gestor": st.column_config.TextColumn("Gestor", width="medium")}
LARG_TOP = {"Fundo": st.column_config.TextColumn("Fundo", width="medium")}
MIL = lambda x: f"{x:,.0f}".replace(",", ".")

st.set_page_config(page_title="Prévia de Cotas · Hedge Investments", layout="wide")


def _font_faces() -> str:
    pasta = Path(__file__).resolve().parent / "static" / "fonts"
    pesos = {"thin": 100, "extralight": 200, "light": 300, "regular": 400, "book": 400, "medium": 500,
             "semibold": 600, "bold": 700, "extrabold": 800, "black": 900, "heavy": 900}
    formatos = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}
    css = []
    for f in sorted(pasta.glob("*")) if pasta.exists() else []:
        if f.suffix.lower() in formatos:
            nome = f.stem.lower().replace("-", "").replace("_", "")
            peso = next((p for k, p in sorted(pesos.items(), key=lambda kv: -len(kv[0])) if k in nome), 400)
            css.append(f"@font-face{{font-family:'Compass';src:url('app/static/fonts/{f.name}') "
                       f"format('{formatos[f.suffix.lower()]}');font-weight:{peso};"
                       f"font-style:{'italic' if 'italic' in nome else 'normal'};font-display:swap;}}")
    return "\n".join(css)


st.markdown(f"""
<style>
{_font_faces()}
html, body, [class*="css"], .stApp, .stMarkdown, .stDataFrame, button, input, textarea, select,
[data-testid="stMetric"], [data-testid="stSidebar"] {{ font-family: {FONTE} !important; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.2rem; max-width: 1500px; }}
[data-testid="stSidebar"] {{ background: {PALETA["fundo"]}; border-right: 1px solid #DCE6EE; }}
[data-testid="stSidebar"] h2 {{ color: {PALETA["marinho"]}; font-size: .95rem; letter-spacing: .08em; text-transform: uppercase; }}
h1, h2, h3 {{ color: {PALETA["marinho"]}; font-weight: 600; }}
.topo {{ background: {PALETA["marinho"]}; color: #fff; border-radius: 6px; padding: 18px 26px 16px; margin-bottom: 6px;
    border-bottom: 4px solid {PALETA["azul"]}; display:flex; justify-content:space-between; align-items:flex-end;
    flex-wrap:wrap; gap:8px; }}
.topo .marca {{ font-size: .78rem; letter-spacing: .22em; text-transform: uppercase; color: {PALETA["celeste"]}; }}
.topo .titulo {{ font-size: 1.7rem; font-weight: 600; line-height: 1.15; }}
.topo .info {{ font-size: .85rem; color: {PALETA["celeste"]}; text-align:right; }}
.secao {{ color: {PALETA["marinho"]}; font-size: .8rem; font-weight: 600; letter-spacing: .14em; text-transform: uppercase;
    border-bottom: 2px solid {PALETA["azul"]}; padding-bottom: 4px; margin: 18px 0 10px; }}
.cards {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:10px; }}
.card {{ background:{PALETA["fundo"]}; border-left: 4px solid {PALETA["azul"]}; border-radius:4px; padding:10px 14px; }}
.card.destaque {{ border-left-color: {PALETA["laranja"]}; }}
.card .rot {{ font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; color:{PALETA["cinza"]}; }}
.card .val {{ font-size:1.35rem; font-weight:600; color:{PALETA["marinho"]}; font-variant-numeric: tabular-nums; }}
.card .sub {{ font-size:.75rem; color:{PALETA["cinza"]}; }}
.pos {{ color:{PALETA["verde"]} !important; }} .neg {{ color:{PALETA["vermelho"]} !important; }}
.nota {{ font-size:.8rem; color:{PALETA["cinza"]}; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 2px solid #DCE6EE; }}
.stTabs [data-baseweb="tab"] {{ color: {PALETA["marinho"]}; font-weight: 600; letter-spacing: .04em; padding: 8px 16px; }}
.stTabs [aria-selected="true"] {{ color: {PALETA["azul"]}; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: {PALETA["azul"]}; }}
div.stDownloadButton > button {{ background:{PALETA["marinho"]}; color:#fff; border:0; border-radius:4px; }}
div.stDownloadButton > button:hover {{ background:{PALETA["azul"]}; color:#fff; }}
</style>
""", unsafe_allow_html=True)


@alt.theme.register("hedge", enable=True)
def _tema():
    return alt.theme.ThemeConfig({"config": {
        "font": FONTE.replace("'", ""),
        "axis": {"labelColor": PALETA["marinho"], "titleColor": PALETA["marinho"], "gridColor": "#E6EDF2",
                 "domainColor": "#C9D6E0", "labelFontSize": 11, "titleFontSize": 11, "titleFontWeight": 500},
        "legend": {"labelColor": PALETA["marinho"], "titleColor": PALETA["marinho"], "orient": "top"},
        "view": {"stroke": None},
    }})


def secao(txt):
    st.markdown(f'<div class="secao">{txt}</div>', unsafe_allow_html=True)


def nota(txt, alvo=st):
    alvo.markdown(f'<p class="nota">{txt}</p>', unsafe_allow_html=True)


def cards(itens, alvo=st):
    html = "".join(f'<div class="card {d}"><div class="rot">{r}</div><div class="val {c}">{v}</div>'
                   f'<div class="sub">{s}</div></div>' for r, v, c, s, d in itens)
    alvo.markdown(f'<div class="cards">{html}</div>', unsafe_allow_html=True)


def cls(v):
    return "pos" if v > 0 else ("neg" if v < 0 else "")


def cor_sinal(x):
    if isinstance(x, (float, np.floating)) and pd.notna(x) and x != 0:
        return f"color:{PALETA['verde'] if x > 0 else PALETA['vermelho']}"
    return ""


def para_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    pv._salvar_excel(df, buf)
    return buf.getvalue()


def _mtime():
    return tuple((pv.DADOS / n).stat().st_mtime if (pv.DADOS / n).exists() else 0
                 for n in ["betas.parquet", "calibracao.parquet", "fatores.parquet"])


@st.cache_data(show_spinner="Carregando base…")
def base(_m):
    univ, cot, bet = pv.carregar_base()
    px, cdi = pv.carregar_fatores()
    return univ, cot, bet, px, cdi, pv.carregar_calibracao()


@st.cache_data(show_spinner="Rodando backtest (só na primeira vez do dia)…")
def qualidade(_m):
    univ, cot, _, px, cdi, _ = base(_m)
    bt = pv._backtest_fundos(univ, cot, px, cdi)
    ok = bt[bt["usada_estim"]]
    pf = (ok.assign(e=(np.expm1(ok["real"]) - np.expm1(ok["prev_comb"])).abs() * 1e4)
          .groupby("chave")["e"].mean())
    return pv.resumir_backtest(ok), pf, (ok["data"].min(), ok["data"].max(), len(ok))


TRAVA = pv.DADOS / ".atualizando"
FALHA = pv.DADOS / ".falha_atualizacao"
AUTO_ATUALIZAR = True          # atualiza sozinho 1x por dia útil, a partir das 8h30 (útil no Streamlit Cloud)


def _agora_br():
    return pd.Timestamp.now(tz="America/Sao_Paulo")


def _travado() -> bool:
    return TRAVA.exists() and (pd.Timestamp.now().timestamp() - TRAVA.stat().st_mtime) < 30 * 60


def atualizar_base(rotulo="Atualizando a base…"):
    import contextlib
    if _travado():
        st.info("Outra sessão está atualizando a base. Esta página recarrega sozinha quando terminar.")
        import time
        time.sleep(20)
        st.rerun()
    pv.DADOS.mkdir(parents=True, exist_ok=True)
    TRAVA.write_text(str(_agora_br()))
    linhas = []

    class _Escreve(io.StringIO):
        def write(self, txt):
            if txt.strip():
                linhas.append(txt.strip())
                caixa.code("\n".join(linhas[-12:]), language=None)
            return len(txt)

    try:
        with st.status(rotulo, expanded=True) as status:
            caixa = st.empty()
            try:
                with contextlib.redirect_stdout(_Escreve()):
                    pv.atualizar()
                    pv.estimar()
            except Exception as e:
                msg = ("sem conexão com a CVM, o Yahoo ou o Banco Central" if "Connection" in type(e).__name__
                       or "Max retries" in str(e) else str(e)[:160])
                status.update(label=f"Falha na atualização: {msg}. A base anterior foi mantida.", state="error")
                FALHA.write_text(msg)
                return
            status.update(label="Base atualizada", state="complete")
            FALHA.unlink(missing_ok=True)
    finally:
        TRAVA.unlink(missing_ok=True)
    st.cache_data.clear()
    pv._CACHE.clear()
    st.rerun()


def _base_desatualizada() -> bool:
    p = pv.DADOS / "betas.parquet"
    if not p.exists():
        return True
    feita = pd.Timestamp(p.stat().st_mtime, unit="s", tz="UTC").tz_convert("America/Sao_Paulo")
    agora = _agora_br()
    return agora.weekday() < 5 and (agora.hour, agora.minute) >= (8, 30) and feita.date() < agora.date()


if not (pv.DADOS / "betas.parquet").exists():
    st.markdown('<div class="topo"><div><div class="marca">Hedge Investments</div>'
                '<div class="titulo">Prévia Diária de Cotas</div></div></div>', unsafe_allow_html=True)
    st.info("Primeira execução: montando a base (12 meses de cotas da CVM, cadastro, fatores do Yahoo e CDI) "
            "e estimando os modelos. Leva alguns minutos e só acontece uma vez por dia.")
    atualizar_base("Montando a base…")
    st.stop()

falhou_recente = FALHA.exists() and (pd.Timestamp.now().timestamp() - FALHA.stat().st_mtime) < 60 * 60
if AUTO_ATUALIZAR and _base_desatualizada() and not _travado() and not falhou_recente:
    st.info("Base de ontem: atualizando com as cotas de hoje da CVM. Leva alguns minutos.")
    atualizar_base("Atualizando a base do dia…")

M = _mtime()
univ, cot, bet, px, cdi, cal = base(M)
d_ref = cot["data"].max()
d_ant = pv.fechamento_anterior(px)


@st.cache_data(ttl=30, show_spinner=False)
def precos(colunas: tuple):
    try:
        agora, ts = pv.precos_ao_vivo(list(colunas))
        return agora, ts, None
    except Exception as e:
        return None, None, str(e)


def limpar_manual():
    for fz in px.columns:
        st.session_state[f"man_{fz}"] = None


def aplicar_manual(agora: pd.Series, manual: dict) -> pd.Series:
    """Substitui o preço atual pelo movimento digitado, a partir do fechamento anterior."""
    agora = agora.copy()
    ant = px.ffill().loc[:d_ant].iloc[-1]
    for fz, x in manual.items():
        agora[fz] = ant[fz] + x if fz.startswith("TX_") else ant[fz] * (1 + x / 100)
    return agora


with st.sidebar:
    st.header("Filtros")
    estr = st.multiselect("Estratégia", sorted(univ["Estrategia"].unique()),
                          default=sorted(univ["Estrategia"].unique()))
    gest = st.multiselect("Gestor", sorted(univ["Gestor"].dropna().unique()), placeholder="Todos")
    busca = st.text_input("Nome ou CNPJ")
    jref = st.selectbox("Janela de referência", TODAS, index=0, format_func=R,
                        help="Combinada: média das janelas ponderada pelo erro recente de cada fundo.")
    r2min = st.slider("R² mínimo", 0.0, 1.0, 0.0, 0.05)
    plmin = st.number_input("PL mínimo (R$ mi)", min_value=0, value=0, step=50)
    com_alfa = st.toggle("Somar α estimado", value=False)
    intervalo = st.select_slider("Atualizar a cada", [30, 60, 120, 300], value=60, format_func=lambda s: f"{s}s")
    if cal is None:
        st.warning("Sem calibração. Rode a atualização abaixo para ativar a combinada.")

    st.header("Atualização")
    if st.button("Atualizar preços agora", width="stretch"):
        precos.clear()
    if st.button("Atualizar base e recalcular", width="stretch", type="primary",
                 help="Baixa CVM, cadastro, fatores e CDI e reestima os βs (alguns minutos)."):
        atualizar_base()

    with st.expander("Movimento manual dos fatores"):
        nota("Preencha só os fatores que quer fixar; os vazios seguem o Yahoo. Valor = variação do dia "
             f"desde o fechamento de {d_ant:%d/%m}, em % (taxas TX_ em pontos percentuais).")
        manual = {}
        for fz in px.columns:
            manual[fz] = st.number_input(fz, value=None, step=0.1, format="%.2f", key=f"man_{fz}",
                                         placeholder="Yahoo")
        st.button("Limpar valores manuais", width="stretch", on_click=limpar_manual)
    manual = {k: x for k, x in manual.items() if x is not None}

    nota(f"Última cota CVM: {d_ref:%d/%m/%Y}<br>βs estimados em {pd.Timestamp(M[0], unit='s', tz='UTC').tz_convert('America/Sao_Paulo'):%d/%m %H:%M}"
         f"<br>{len(univ)} fundos no universo<br>Cotações Yahoo (B3 com ~15 min de atraso)")


def aplicar_filtros(df):
    m = df["Estrategia"].isin(estr) & (df[f"r2_{jref}"].fillna(0) >= r2min) & (df["pl"] >= plmin * 1e6)
    if gest:
        m &= df["Gestor"].isin(gest)
    if busca:
        m &= pv._contem(df["Nome"], busca) | df["CNPJ"].str.contains(busca, regex=False)
    return df[m]


def nome_curto(v):
    return v["Nome"].str.slice(0, 55) + np.where(v["Subclasse"].fillna("") != "", " · " + v["Subclasse"], "")


@st.fragment(run_every=intervalo)
def ao_vivo():
    agora, ts, erro = precos(tuple(px.columns))
    if erro is None:
        quando = f"Preços até {ts:%d/%m %H:%M}"
    else:
        agora, quando = px.ffill().iloc[-1], "Sem preço ao vivo · último fechamento"
    agora = agora.reindex(px.columns).fillna(px.ffill().iloc[-1])
    if manual:
        agora = aplicar_manual(agora, manual)
        quando += " · manual: " + ", ".join(f"{k} {x:+.2f}{'pp' if k.startswith('TX_') else '%'}"
                                            for k, x in manual.items())
    df = pv.calcular_previa(univ, cot, bet, px, cdi, agora, com_alfa=com_alfa, cal=cal)

    st.markdown(f"""<div class="topo">
      <div><div class="marca">Hedge Investments</div><div class="titulo">Prévia Diária de Cotas</div></div>
      <div class="info">{pd.Timestamp.now():%d/%m/%Y}<br>{quando}<br>Base: fechamento de {d_ant:%d/%m}</div>
    </div>""", unsafe_allow_html=True)

    v = aplicar_filtros(df)
    aba_geral, aba_fundos, aba_fundo, aba_qual = st.tabs(["Visão geral", "Fundos", "Fundo", "Qualidade do modelo"])

    with aba_geral:
        mov = pv.movimento_fatores(px, agora, d_ant)
        secao("Fatores no dia")
        cards([(k, f"{x:+.2%}" if not k.startswith("TX_") else f"{x:+.2f} pp", cls(x),
                "manual" if k in manual else "", "destaque" if k in manual else "") for k, x in mov.items()])
        if v.empty:
            st.info("Nenhum fundo com esses filtros.")
            return
        secao(f"Prévia {R(jref)} por estratégia")
        g = v.groupby("Estrategia")
        cards([(e, f"{x:+.2%}", cls(x), f"{g.size()[e]} fundos · ±{((gg[f'previa_{jref}_max'] - gg[f'previa_{jref}_min']) / 2).median():.2%}",
                "destaque" if jref == "comb" else "")
               for e, gg in g for x in [gg[f"previa_{jref}"].median()]])

        med = g[[f"previa_{j}" for j in TODAS]].median().rename(columns=lambda c: R(c.replace("previa_", "")))
        longo = med.reset_index().melt(id_vars="Estrategia", var_name="Janela", value_name="Prévia")
        dom = [R(j) for j in TODAS]
        graf = alt.Chart(longo).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
            x=alt.X("Estrategia:N", title=None, axis=alt.Axis(labelAngle=0, labelFontWeight=600)),
            xOffset=alt.XOffset("Janela:N", sort=dom),
            y=alt.Y("Prévia:Q", axis=alt.Axis(format="+.2%"), title=None),
            color=alt.Color("Janela:N", sort=dom, title="Janela", scale=alt.Scale(domain=dom, range=[COR_JANELA[d] for d in dom])),
            tooltip=[alt.Tooltip("Estrategia:N", title="Estratégia"), "Janela", alt.Tooltip("Prévia:Q", format="+.2%")],
        ).properties(height=240)
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#9FB3C2").encode(y="y:Q")
        st.altair_chart(graf + zero, width="stretch")

        c1, c2 = st.columns(2, gap="large")
        top = pd.DataFrame({"Fundo": v["Nome"].str.slice(0, 42), "Estratégia": v["Estrategia"], "Prévia": v[f"previa_{jref}"],
                            "Mín": v[f"previa_{jref}_min"], "Máx": v[f"previa_{jref}_max"]})
        fmt = {"Prévia": "{:+.2%}", "Mín": "{:+.2%}", "Máx": "{:+.2%}"}
        with c1:
            secao("Maiores altas")
            st.dataframe(top.nlargest(8, "Prévia").style.format(fmt).map(cor_sinal, subset=list(fmt)),
                         hide_index=True, width="stretch", column_config=LARG_TOP)
        with c2:
            secao("Maiores quedas")
            st.dataframe(top.nsmallest(8, "Prévia").style.format(fmt).map(cor_sinal, subset=list(fmt)),
                         hide_index=True, width="stretch", column_config=LARG_TOP)

        secao("Alertas")
        lim_amp = max(df["amplitude_janelas"].quantile(0.9), AMPLITUDE_MIN)
        alertas = v[(v["amplitude_janelas"] >= lim_amp) | (v[f"r2_{jref}"] < 0.4) | (v["dias_desde_base"] > 2)]
        if alertas.empty:
            nota("Sem alertas para os filtros atuais.")
        else:
            motivo = np.select(
                [alertas["amplitude_janelas"] >= lim_amp, alertas[f"r2_{jref}"] < 0.4, alertas["dias_desde_base"] > 2],
                ["Janelas divergem: possível mudança de posição", "Ajuste fraco (R² < 0,4)",
                 "Cota CVM atrasada"], "")
            ta = pd.DataFrame({"Fundo": nome_curto(alertas), "Estratégia": alertas["Estrategia"], "Motivo": motivo,
                               "Prévia": alertas[f"previa_{jref}"], "Amplitude": alertas["amplitude_janelas"],
                               "R²": alertas[f"r2_{jref}"], "Última cota": alertas["data_base"].dt.strftime("%d/%m")})
            st.dataframe(ta.sort_values("Amplitude", ascending=False).head(25).style
                         .format({"Prévia": "{:+.2%}", "Amplitude": "{:.2%}", "R²": "{:.2f}"})
                         .map(cor_sinal, subset=["Prévia"]), hide_index=True, width="stretch", column_config=LARG)
            nota(f"{len(alertas)} fundo(s). Divergência: amplitude entre janelas ≥ {lim_amp:.2%} "
                 f"(10% maiores, mínimo {AMPLITUDE_MIN:.2%}).")

    with aba_fundos:
        secao(f"Fundos · {len(v)}")
        t = pd.DataFrame({
            "Fundo": nome_curto(v), "Estratégia": v["Estrategia"], "Gestor": v["Gestor"].str.slice(0, 32),
            "PL (R$ mi)": v["pl"] / 1e6, "Última cota": v["data_base"].dt.strftime("%d/%m"),
            **{f"Prévia {R(j)}": v[f"previa_{j}"] for j in TODAS},
            f"Mín 95% {R(jref)}": v[f"previa_{jref}_min"], f"Máx 95% {R(jref)}": v[f"previa_{jref}_max"],
            "Amplitude": v["amplitude_janelas"], f"Cota estimada {R(jref)}": v[f"cota_est_{jref}"],
            f"R² {R(jref)}": v[f"r2_{jref}"], "CNPJ": v["CNPJ"],
        }).sort_values(f"Prévia {R(jref)}", ascending=False)
        pcols = [c for c in t if c.startswith(("Prévia", "Mín", "Máx"))]
        sty = (t.style.format({**{c: "{:+.2%}" for c in pcols}, "Amplitude": "{:.2%}", "PL (R$ mi)": MIL,
                               f"Cota estimada {R(jref)}": "{:.6f}", f"R² {R(jref)}": "{:.2f}"}, na_rep="–")
               .map(cor_sinal, subset=pcols)
               .bar(subset=[f"R² {R(jref)}"], color=PALETA["celeste"], vmin=0, vmax=1))
        st.dataframe(sty, hide_index=True, width="stretch", height=560, column_config=LARG)
        nota(f"Prévia = retorno só de hoje. Mín/Máx = IC {pv.IC_NIVEL:.0%} bicaudal calibrado pelos erros do fundo "
             f"(janela {R(jref)}). Combinada = média das janelas ponderada pelo inverso do erro dos últimos "
             f"{pv.CALIB_DIAS} dias.")
        b1, b2, _ = st.columns([1, 1, 4])
        agora_txt = pd.Timestamp.now().strftime("%Y%m%d_%H%M")
        b1.download_button("Baixar Excel", para_excel(t), f"previa_{agora_txt}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        b2.download_button("Baixar CSV", t.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig"),
                           f"previa_{agora_txt}.csv", "text/csv")

    with aba_fundo:
        op = v.assign(rot=nome_curto(v) + " · " + v["CNPJ"]).sort_values("pl", ascending=False)
        sel = st.selectbox("Fundo", op["rot"], index=0 if len(op) else None, placeholder="Escolha um fundo")
        if sel:
            f = op[op["rot"] == sel].iloc[0]
            st.markdown(f"**{f['Estrategia']}** · {f['Classe_ANBIMA']} · {f['Gestor']} · "
                        f"PL R$ {f['pl'] / 1e6:,.0f} mi".replace(",", "."))
            cards([(R(j), f"{f[f'previa_{j}']:+.2%}", cls(f[f"previa_{j}"]),
                    f"[{f[f'previa_{j}_min']:+.2%}; {f[f'previa_{j}_max']:+.2%}]"
                    + (f" · peso {f[f'peso_{j}']:.0%}" if j != "comb" else ""), "destaque" if j == "comb" else "")
                   for j in TODAS])
            nota(f"Cota estimada ({R(jref)}): {f[f'cota_est_{jref}']:.6f} "
                 f"[{f[f'cota_est_{jref}_min']:.6f}; {f[f'cota_est_{jref}_max']:.6f}] · última cota "
                 f"{f['data_base']:%d/%m}: {f['cota_base']:.6f}")
            b = bet[bet["chave"] == f["chave"]].set_index("janela").reindex(JAN)
            bcols = [c for c in b if c.startswith("b_") and b[c].notna().any()]
            tb = b[bcols].T
            tb.index = [c[2:] for c in bcols]
            q = b[["r2", "te", "n"]].T
            q.index = ["R²", "Erro anual", "Obs."]
            tab = pd.concat([tb, q])
            tab.columns = [f"β {j}" for j in JAN]
            idx = pd.IndexSlice
            c1, c2 = st.columns([1, 2], gap="large")
            c1.dataframe(tab.style.format("{:.2f}", na_rep="–", subset=idx[list(tb.index) + ["R²"], :])
                         .format("{:.1%}", na_rep="–", subset=idx[["Erro anual"], :])
                         .format("{:.0f}", na_rep="–", subset=idx[["Obs."], :]), width="stretch")
            bt = pv._backtest_fundos(univ[univ["chave"] == f["chave"]], cot, px, cdi).tail(63)
            if not bt.empty:
                gd = pd.DataFrame({"Data": bt["data"].values, "Real": np.expm1(bt["real"].values),
                                   "Prévia": np.expm1(bt[f"prev_{jref}"].values),
                                   "Mín": np.expm1(bt[f"ic_{jref}_min"].values),
                                   "Máx": np.expm1(bt[f"ic_{jref}_max"].values)})
                dentro = ((gd["Real"] >= gd["Mín"]) & (gd["Real"] <= gd["Máx"])).mean()
                erro = (gd["Real"] - gd["Prévia"]).abs().mean() * 1e4
                x = alt.X("Data:T", title=None, axis=alt.Axis(format="%d/%m"))
                faixa = alt.Chart(gd).mark_area(color=PALETA["celeste"], opacity=.35).encode(
                    x=x, y=alt.Y("Mín:Q", axis=alt.Axis(format="+.1%"), title="Retorno do dia"), y2="Máx:Q")
                real = alt.Chart(gd).mark_bar(color=PALETA["marinho"], size=5).encode(
                    x=x, y="Real:Q", tooltip=[alt.Tooltip("Data:T", format="%d/%m"), alt.Tooltip("Real:Q", format="+.2%"),
                                              alt.Tooltip("Prévia:Q", format="+.2%")])
                linha = alt.Chart(gd).mark_line(color=PALETA["azul"], strokeWidth=2).encode(x=x, y="Prévia:Q")
                c2.altair_chart((faixa + real + linha).properties(height=280), width="stretch")
                nota(f"Últimos {len(gd)} dias, fora da amostra. Erro médio {erro:.0f} bps · real dentro do IC em "
                     f"{dentro:.0%} dos dias.", c2)

    with aba_qual:
        r, pf, (ini, fim, nobs) = qualidade(M)
        nota(f"Backtest fora da amostra: cada dia previsto só com dados até a véspera. {nobs:,} fundo-dias de "
             f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}.".replace(",", "."))
        ordem = [o for o in ["Todas", "Long Only", "Long Biased", "Long Short", "Macro"] if o in set(r["Estrategia"])]
        modelos = TODAS + ["só CDI"]
        erro = r.pivot(index="Estrategia", columns="Modelo", values="MAE_bps").reindex(ordem)[modelos]
        erro.columns = [R(m) for m in modelos]
        erro = erro.rename_axis("Estratégia")
        secao("Erro médio da prévia diária (bps)")
        longo = erro.reset_index().melt(id_vars="Estratégia", var_name="Modelo", value_name="Erro")
        dom = [R(m) for m in modelos]
        cores = [COR_JANELA.get(d, "#BBBBBB") for d in dom]
        st.altair_chart(alt.Chart(longo).mark_bar().encode(
            x=alt.X("Estratégia:N", title=None, axis=alt.Axis(labelAngle=0, labelFontWeight=600)),
            xOffset=alt.XOffset("Modelo:N", sort=dom), y=alt.Y("Erro:Q", title="bps"),
            color=alt.Color("Modelo:N", sort=dom, scale=alt.Scale(domain=dom, range=cores)),
            tooltip=["Estratégia", "Modelo", alt.Tooltip("Erro:Q", format=".1f")]).properties(height=240), width="stretch")
        st.dataframe(erro.style.format("{:.1f}").highlight_min(axis=1, subset=[R(m) for m in TODAS],
                                                                 props=f"background:{PALETA['fundo']};font-weight:600"),
                     width="stretch")
        secao(f"Cobertura do IC {pv.IC_NIVEL:.0%} (ideal ≈ {pv.IC_NIVEL:.0%})")
        cob = lambda campo: (r[r["Modelo"].isin(TODAS)].pivot(index="Estrategia", columns="Modelo", values=campo)
                             .reindex(ordem)[TODAS].rename(columns=R).rename_axis("Estratégia"))
        tc = pd.concat({"Teórica": cob("cobertura_IC_teo"), "Calibrada": cob("cobertura_IC")}, axis=1)
        st.dataframe(tc.style.format("{:.0%}"), width="stretch")
        secao("Fundos com maior erro (combinada)")
        pior = (pf.rename("Erro (bps)").to_frame().join(univ.set_index("chave")[["Nome", "Estrategia", "Gestor"]])
                .nlargest(15, "Erro (bps)").rename(columns={"Estrategia": "Estratégia"}))
        pior["Nome"] = pior["Nome"].str.slice(0, 60)
        pior["Gestor"] = pior["Gestor"].str.slice(0, 35)
        st.dataframe(pior[["Nome", "Estratégia", "Gestor", "Erro (bps)"]].style.format({"Erro (bps)": "{:.0f}"}),
                     hide_index=True, width="stretch", column_config=LARG)


ao_vivo()
