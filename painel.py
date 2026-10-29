"""Painel executivo da prévia de cotas, identidade Hedge Investments. Uso: streamlit run painel.py"""
import html
import io
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import previa as pv

COR = {
    "marinho": "#0A4263", "tinta": "#0B2C42", "azul": "#00A0D7", "celeste": "#81C1D7", "petroleo": "#145A75",
    "verde": "#3F7A1F", "vermelho": "#B83A00", "laranja": "#F98909", "cinza": "#5F6B75", "linha": "#DCE5EC",
    "fundo": "#F4F7FA",
}
JAN = list(pv.JANELAS)
TODAS = pv.todas_janelas()
COR_JANELA = {"1m": COR["celeste"], "2m": COR["azul"], "3m": COR["petroleo"], "12m": COR["marinho"],
              "combinada": COR["laranja"], "só CDI": "#B8C2CA"}
FONTE = "'Compass', 'Compass Sans', 'Compass Pro', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
R = pv.rot
AMPLITUDE_MIN = 0.0025

st.set_page_config(page_title="Prévia de cotas · Hedge Investments", layout="wide",
                   initial_sidebar_state="collapsed")


# Formatação pt-BR
def pct(x, casas=2, sinal=True):
    if x is None or pd.isna(x):
        return "–"
    s = f"{x * 100:+.{casas}f}" if sinal else f"{x * 100:.{casas}f}"
    return s.replace(".", ",") + "%"


def num(x, casas=0):
    if x is None or pd.isna(x):
        return "–"
    if abs(x) < 0.5 * 10 ** -casas:
        x = 0.0
    return f"{x:,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def data_br(d):
    meses = "jan fev mar abr mai jun jul ago set out nov dez".split()
    return f"{d.day} {meses[d.month - 1]}"


def cls(v):
    return "pos" if v > 0 else ("neg" if v < 0 else "")


def esc(t):
    return html.escape(str(t))


# Estilo
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
html, body, .stApp, .stMarkdown, .stDataFrame, button, input, textarea, select, [data-testid="stSidebar"] {{
  font-family: {FONTE} !important; }}
.stApp {{ background: #FFFFFF; color: {COR["tinta"]}; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: .8rem; padding-bottom: 3rem; max-width: 1320px; }}
[data-testid="stSidebar"] {{ background: {COR["fundo"]}; border-right: 1px solid {COR["linha"]}; }}
[data-testid="stSidebar"] h2 {{ color: {COR["marinho"]}; font-size: 1rem; font-weight: 600; margin-top: .6rem; }}
.num {{ font-variant-numeric: tabular-nums; }}
.pos {{ color: {COR["verde"]}; }} .neg {{ color: {COR["vermelho"]}; }}

.barra-topo {{ display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap;
  background:{COR["marinho"]}; color:#fff; padding:12px 22px; border-radius:4px; }}
.barra-topo .marca {{ font-weight:600; font-size:1.05rem; letter-spacing:.01em; }}
.barra-topo .marca span {{ color:{COR["celeste"]}; font-weight:400; margin-left:10px; }}
.status {{ display:inline-flex; align-items:center; gap:8px; font-size:.86rem; color:#E6F1F7; }}
.status i {{ width:8px; height:8px; border-radius:50%; background:#7FD06B; display:inline-block; }}
.status.parado i {{ background:#C9D3DA; }}

.hero {{ display:grid; grid-template-columns: minmax(0,1.25fr) minmax(0,1fr); gap:40px; padding:30px 4px 22px;
  border-bottom:1px solid {COR["linha"]}; }}
.hero .rotulo {{ font-size:.95rem; color:{COR["cinza"]}; margin-bottom:6px; }}
.hero .fundo {{ font-size:1.35rem; font-weight:600; color:{COR["marinho"]}; line-height:1.25; }}
.hero .grande {{ font-size:4.2rem; font-weight:600; line-height:1; margin:14px 0 12px; letter-spacing:-.02em; }}
.hero .detalhe {{ font-size:.92rem; color:{COR["cinza"]}; line-height:1.55; margin-top:10px; }}
.hero .detalhe b {{ color:{COR["tinta"]}; font-weight:600; }}
.feeders {{ align-self:end; }}
.feeders .linha {{ display:grid; grid-template-columns: 92px 80px 1fr; align-items:center; gap:14px;
  padding:11px 0; border-top:1px solid {COR["linha"]}; }}
.feeders .linha:first-of-type {{ border-top:0; }}
.feeders .nome {{ font-weight:600; color:{COR["marinho"]}; }}
.feeders .nome small {{ display:block; font-weight:400; color:{COR["cinza"]}; font-size:.78rem; }}
.feeders .valor {{ font-size:1.1rem; font-weight:600; text-align:right; }}

.resumo {{ font-size:1.08rem; line-height:1.6; color:{COR["tinta"]}; max-width:78ch; padding:20px 4px 4px; }}
.fita {{ display:flex; flex-wrap:wrap; border:1px solid {COR["linha"]}; border-radius:4px; margin:10px 0 6px; }}
.fita div.item {{ flex:1 1 110px; padding:10px 16px; border-left:1px solid {COR["linha"]}; }}
.fita div.item:first-child {{ border-left:0; }}
.fita .f {{ font-size:.8rem; color:{COR["cinza"]}; }}
.fita .v {{ font-size:1.12rem; font-weight:600; }}
.fita .manual {{ background:#FFF6EA; }}
.fita .manual .f::after {{ content:" (manual)"; color:{COR["laranja"]}; }}

h3.sec {{ font-size:1.12rem; font-weight:600; color:{COR["marinho"]}; margin:30px 0 4px; }}
p.sub {{ font-size:.88rem; color:{COR["cinza"]}; margin:0 0 12px; }}
table.quadro {{ width:100%; border-collapse:collapse; font-size:.95rem; border:0 !important; margin:0; }}
table.quadro tr, table.quadro thead tr {{ background:transparent !important; border:0 !important; }}
table.quadro th {{ text-align:left; font-weight:500; color:{COR["cinza"]}; font-size:.82rem; padding:8px 10px;
  border:0 !important; border-bottom:1px solid {COR["linha"]} !important; background:transparent !important; }}
table.quadro td {{ padding:11px 10px; border:0 !important; border-bottom:1px solid {COR["linha"]} !important;
  vertical-align:middle; }}
table.quadro td.nome {{ line-height:1.3; }}
table.quadro td.nome small {{ font-size:.78rem; }}
table.quadro td.r, table.quadro th.r {{ text-align:right; }}
table.quadro td.est {{ font-weight:600; color:{COR["marinho"]}; }}
table.quadro tr.casa td {{ background:#FFF9F1; }}
table.quadro td small {{ color:{COR["cinza"]}; }}
.nota {{ font-size:.82rem; color:{COR["cinza"]}; line-height:1.5; }}

.stTabs [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 1px solid {COR["linha"]}; margin-top: 18px; }}
.stTabs [data-baseweb="tab"] {{ color: {COR["cinza"]}; font-weight: 600; padding: 10px 14px; }}
.stTabs [aria-selected="true"] {{ color: {COR["marinho"]}; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: {COR["azul"]}; height: 3px; }}
div.stDownloadButton > button, div.stButton > button[kind="primary"] {{ background:{COR["marinho"]}; color:#fff;
  border:0; border-radius:4px; }}
div.stDownloadButton > button:hover, div.stButton > button[kind="primary"]:hover {{ background:{COR["azul"]}; color:#fff; }}
.rolagem {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
.hero > div {{ min-width:0; }}
@media (max-width: 900px) {{
  .hero {{ grid-template-columns: 1fr; gap:22px; padding-top:20px; }} .hero .grande {{ font-size:3.2rem; }}
  table.quadro .opc {{ display:none; }} table.quadro td, table.quadro th {{ padding:9px 6px; }}
  .barra-topo .marca span {{ display:block; margin-left:0; }} }}
</style>
""", unsafe_allow_html=True)


@alt.theme.register("hedge", enable=True)
def _tema():
    return alt.theme.ThemeConfig({"config": {
        "font": FONTE.replace("'", ""),
        "axis": {"labelColor": COR["cinza"], "titleColor": COR["cinza"], "gridColor": "#EDF2F6",
                 "domainColor": COR["linha"], "tickColor": COR["linha"], "labelFontSize": 11, "titleFontSize": 11,
                 "titleFontWeight": 500},
        "legend": {"labelColor": COR["tinta"], "titleColor": COR["cinza"], "orient": "top", "labelFontSize": 12},
        "view": {"stroke": None},
    }})


# Componentes
def faixa_svg(lo, mid, hi, escala, largura=240, altura=22):
    """Barra de faixa: trilho, zero, intervalo de 95% e ponto na estimativa."""
    if any(pd.isna(v) for v in (lo, mid, hi)) or escala <= 0:
        return ""
    x = lambda v: 6 + (np.clip(v, -escala, escala) + escala) / (2 * escala) * (largura - 12)
    cor = COR["verde"] if mid > 0 else (COR["vermelho"] if mid < 0 else COR["marinho"])
    y = altura / 2
    return (f'<svg width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}" role="img" '
            f'style="max-width:100%;height:auto;display:block" preserveAspectRatio="xMidYMid meet" '
            f'aria-label="Estimativa {pct(mid)}, faixa {pct(lo)} a {pct(hi)}">'
            f'<line x1="6" y1="{y}" x2="{largura - 6}" y2="{y}" stroke="{COR["linha"]}" stroke-width="2"/>'
            f'<line x1="{x(0):.1f}" y1="3" x2="{x(0):.1f}" y2="{altura - 3}" stroke="#AFBCC6" stroke-width="1"/>'
            f'<rect x="{x(lo):.1f}" y="{y - 4}" width="{max(x(hi) - x(lo), 2):.1f}" height="8" rx="4" '
            f'fill="{COR["celeste"]}" opacity=".75"/>'
            f'<circle cx="{x(mid):.1f}" cy="{y}" r="5.5" fill="{cor}" stroke="#fff" stroke-width="1.5"/></svg>')


def escala_de(*series, minimo=0.005):
    vals = np.concatenate([np.abs(np.asarray(s, dtype=float)).ravel() for s in series])
    vals = vals[np.isfinite(vals)]
    return max(np.quantile(vals, 0.98) * 1.1 if len(vals) else minimo, minimo)


def titulo(txt, sub=None):
    st.markdown(f'<h3 class="sec">{esc(txt)}</h3>' + (f'<p class="sub">{sub}</p>' if sub else ""),
                unsafe_allow_html=True)


def nota(txt, alvo=st):
    alvo.markdown(f'<p class="nota">{txt}</p>', unsafe_allow_html=True)


def _mapa_marca():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("hedge", [COR["vermelho"], "#F7E3D6", "#FFFFFF", "#D3E8F1", COR["marinho"]])


def fora_do_alvo(x, alvo=0.95, tol=0.03):
    if isinstance(x, (float, np.floating)) and pd.notna(x) and abs(x - alvo) > tol:
        return f"color:{COR['laranja']};font-weight:700"
    return ""


def cor_sinal(x):
    if isinstance(x, (float, np.floating)) and pd.notna(x) and x != 0:
        return f"color:{COR['verde'] if x > 0 else COR['vermelho']}"
    return ""


def fmt_pct(x):
    return pct(x)


def para_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    pv._salvar_excel(df, buf)
    return buf.getvalue()


def nome_curto(v):
    return v["Nome"].str.slice(0, 55) + np.where(v["Subclasse"].fillna("") != "", " · " + v["Subclasse"], "")


def _titulo_fundo(nome, n):
    corta = (" FUNDO DE INVESTIMENTO", " FIF ", " FIC ", " CLASSE DE", " - CLASSE", " RESPONSABILIDADE", " RESP ",
             " GESTÃO", " GESTAO", " ADMINISTRA", " INVESTIMENTOS LTDA", " LTDA", " ASSET", " DISTRIBUIDORA",
             " CORRETORA", " S.A", " DTVM", " GESTORA")
    s = f" {nome} "
    for c in corta:
        i = s.upper().find(c)
        if i > 4:
            s = s[:i]
    s = s.strip().title()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def apelido(cnpj, nome):
    return pv.APELIDOS.get(cnpj, nome[:40])


# Dados
def _mtime():
    return tuple((pv.DADOS / n).stat().st_mtime if (pv.DADOS / n).exists() else 0
                 for n in ["betas.parquet", "calibracao.parquet", "fatores.parquet"])


@st.cache_data(show_spinner="Carregando base…")
def base(_m):
    univ, cot, bet = pv.carregar_base()
    px, cdi = pv.carregar_fatores()
    return univ, cot, bet, px, cdi, pv.carregar_calibracao()


@st.cache_data(show_spinner="Calculando a qualidade do modelo…")
def qualidade(_m):
    univ, cot, _, px, cdi, _ = base(_m)
    bt = pv._backtest_fundos(univ, cot, px, cdi)
    ok = bt[bt["usada_estim"]]
    pf = (ok.assign(e=(np.expm1(ok["real"]) - np.expm1(ok["prev_comb"])).abs() * 1e4).groupby("chave")["e"].mean())
    return pv.resumir_backtest(ok), pf, (ok["data"].min(), ok["data"].max(), len(ok))


@st.cache_data(show_spinner=False)
def historico_fundo(_m, chave):
    univ, cot, _, px, cdi, _ = base(_m)
    return pv._backtest_fundos(univ[univ["chave"] == chave], cot, px, cdi).tail(63)


@st.cache_data(ttl=30, show_spinner=False)
def precos(colunas: tuple):
    try:
        agora, ts = pv.precos_ao_vivo(list(colunas))
        return agora, ts, None
    except Exception as e:
        return None, None, str(e)


# Atualização da base
TRAVA = pv.DADOS / ".atualizando"
FALHA = pv.DADOS / ".falha_atualizacao"
AUTO_ATUALIZAR = True


def _agora_br():
    return pd.Timestamp.now(tz="America/Sao_Paulo")


def _travado() -> bool:
    return TRAVA.exists() and (pd.Timestamp.now().timestamp() - TRAVA.stat().st_mtime) < 30 * 60


def atualizar_base(rotulo="Atualizando a base"):
    import contextlib
    import time
    if _travado():
        st.info("Outra sessão está atualizando a base. A página recarrega quando terminar.")
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
                status.update(label=f"A atualização falhou: {msg}. A base anterior continua valendo.", state="error")
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
    st.markdown('<div class="barra-topo"><div class="marca">Hedge Investments<span>Prévia de cotas</span></div></div>',
                unsafe_allow_html=True)
    st.info("Primeira execução: montando a base com 12 meses de cotas da CVM, cadastro, fatores e CDI. "
            "Leva alguns minutos e acontece uma vez por dia.")
    atualizar_base("Montando a base")
    st.stop()

falhou_recente = FALHA.exists() and (pd.Timestamp.now().timestamp() - FALHA.stat().st_mtime) < 60 * 60
if AUTO_ATUALIZAR and _base_desatualizada() and not _travado() and not falhou_recente:
    st.info("Atualizando com as cotas de hoje da CVM. Leva alguns minutos.")
    atualizar_base("Atualizando a base do dia")

M = _mtime()
univ, cot, bet, px, cdi, cal = base(M)
d_ref = cot["data"].max()
d_ant = pv.fechamento_anterior(px)


def limpar_manual():
    for fz in px.columns:
        st.session_state[f"man_{fz}"] = None


def aplicar_manual(agora: pd.Series, manual: dict) -> pd.Series:
    agora = agora.copy()
    ant = px.ffill().loc[:d_ant].iloc[-1]
    for fz, x in manual.items():
        agora[fz] = ant[fz] + x if fz.startswith("TX_") else ant[fz] * (1 + x / 100)
    return agora


with st.sidebar:
    st.header("Filtros")
    estr = st.multiselect("Estratégias", [e for e in pv.ordenar_estrategias(univ["Estrategia"].unique()) if e != "Todas"],
                          default=None, placeholder="Todas")
    gest = st.multiselect("Gestores", sorted(univ["Gestor"].dropna().unique()), placeholder="Todos")
    busca = st.text_input("Nome ou CNPJ")
    jref = st.selectbox("Modelo de referência", TODAS, index=0, format_func=lambda j: R(j).capitalize(),
                        help="Combinada: média das janelas 1m, 2m, 3m e 12m ponderada pelo erro recente de cada fundo.")
    r2min = st.slider("Qualidade mínima do ajuste (R²)", 0.0, 1.0, 0.0, 0.05)
    plmin = st.number_input("PL mínimo (R$ mi)", min_value=0, value=0, step=50)
    com_alfa = st.toggle("Somar α estimado", value=False)
    intervalo = st.select_slider("Atualizar a cada", [30, 60, 120, 300], value=60, format_func=lambda s: f"{s} s")

    st.header("Atualização")
    if st.button("Atualizar preços agora", width="stretch"):
        precos.clear()
    if st.button("Atualizar base e recalcular", width="stretch", type="primary",
                 help="Baixa CVM, cadastro, fatores e CDI e reestima os modelos. Leva alguns minutos."):
        atualizar_base()
    with st.expander("Movimento manual dos fatores"):
        nota(f"Preencha só o que quiser fixar. Variação do dia desde o fechamento de {data_br(d_ant)}, "
             "em % (pontos percentuais para taxas TX_). Os campos vazios seguem o Yahoo.")
        manual = {fz: st.number_input(fz, value=None, step=0.1, format="%.2f", key=f"man_{fz}", placeholder="Yahoo")
                  for fz in px.columns}
        st.button("Limpar valores manuais", width="stretch", on_click=limpar_manual)
    manual = {k: x for k, x in manual.items() if x is not None}
    if cal is None:
        st.warning("Sem calibração. Use Atualizar base e recalcular.")
    feita = pd.Timestamp(M[0], unit="s", tz="UTC").tz_convert("America/Sao_Paulo")
    nota(f"Cotas CVM até {d_ref:%d/%m/%Y}. Modelos estimados em {feita:%d/%m às %H:%M}. "
         f"{len(univ)} fundos. Cotações do Yahoo, com cerca de 15 min de atraso na B3.")


def aplicar_filtros(df):
    m = (df[f"r2_{jref}"].fillna(0) >= r2min) & (df["pl"] >= plmin * 1e6)
    if estr:
        m &= df["Estrategia"].isin(estr)
    if gest:
        m &= df["Gestor"].isin(gest)
    if busca:
        m &= pv._contem(df["Nome"], busca) | df["CNPJ"].str.contains(busca, regex=False)
    return df[m]


# Blocos da página
def barra_topo(quando, vivo):
    st.markdown(
        f'<div class="barra-topo"><div class="marca">Hedge Investments<span>Prévia de cotas, '
        f'{data_br(_agora_br())} de {_agora_br():%Y}</span></div>'
        f'<div class="status{"" if vivo else " parado"}"><i></i>{esc(quando)}</div></div>',
        unsafe_allow_html=True)


def hero(df):
    h = df[df["CNPJ"].isin(pv.FUNDOS_INCLUIR)].copy()
    if h.empty:
        return
    h["ordem"] = (~h["Nome"].str.upper().str.contains("MASTER")).astype(int)
    h = h.sort_values(["ordem", "pl"], ascending=[True, False])
    m = h.iloc[0]
    j = jref
    esc_h = escala_de(h[f"previa_{j}_min"], h[f"previa_{j}_max"])
    nome = apelido(m["CNPJ"], m["Nome"])
    grande = (f'<div class="rotulo">Prévia de hoje, modelo {R(j)}</div>'
              f'<div class="fundo">Hedge Alternative Investments {esc(nome)}</div>'
              f'<div class="grande num {cls(m[f"previa_{j}"])}">{pct(m[f"previa_{j}"])}</div>'
              f'{faixa_svg(m[f"previa_{j}_min"], m[f"previa_{j}"], m[f"previa_{j}_max"], esc_h, 380, 26)}'
              f'<div class="detalhe">Com 95% de confiança, o retorno de hoje fica entre '
              f'<b class="num">{pct(m[f"previa_{j}_min"])}</b> e <b class="num">{pct(m[f"previa_{j}_max"])}</b>.<br>'
              f'Cota estimada de <b class="num">{num(m[f"cota_est_{j}"], 6)}</b>, sobre a última divulgada, '
              f'<span class="num">{num(m["cota_base"], 6)}</span> em {data_br(m["data_base"])}. '
              f'PL de R$ {num(m["pl"] / 1e6)} mi.</div>')
    linhas = "".join(
        f'<div class="linha"><div class="nome">{esc(apelido(r["CNPJ"], r["Nome"]))}'
        f'<small>R$ {num(r["pl"] / 1e6)} mi</small></div>'
        f'<div class="valor num {cls(r[f"previa_{j}"])}">{pct(r[f"previa_{j}"])}</div>'
        f'<div>{faixa_svg(r[f"previa_{j}_min"], r[f"previa_{j}"], r[f"previa_{j}_max"], esc_h, 240)}</div></div>'
        for _, r in h.iloc[1:].iterrows())
    st.markdown(f'<div class="hero"><div>{grande}</div><div class="feeders">'
                f'<div class="rotulo">Classes feeder</div>{linhas}</div></div>', unsafe_allow_html=True)


def frase_resumo(df, mov):
    nomes = {"IBOV": "Ibovespa", "USD": "dólar", "SPX": "S&P 500"}
    mercado = [f"{nomes[k]} {pct(mov[k])}" for k in ("IBOV", "USD", "SPX") if k in mov and pd.notna(mov[k])]
    med = df.groupby("Estrategia")[f"previa_{jref}"].median()
    partes = [f"{e} {pct(med[e])}" for e in pv.ORDEM_ESTRATEGIAS if e in med.index]
    txt = f"Desde o fechamento de {data_br(d_ant)}: {', '.join(mercado)}. " if mercado else ""
    if len(partes) > 1:
        txt += f"Na mediana dos fundos, a prévia de hoje é {', '.join(partes[:-1])} e {partes[-1]}."
    st.markdown(f'<div class="resumo">{esc(txt)}</div>', unsafe_allow_html=True)


def fita_fatores(mov):
    itens = "".join(
        f'<div class="item{" manual" if k in manual else ""}"><div class="f">{esc(k)}</div>'
        f'<div class="v num {cls(v)}">{pct(v) if not k.startswith("TX_") else num(v, 2) + " pp"}</div></div>'
        for k, v in mov.items())
    st.markdown(f'<div class="fita">{itens}</div>', unsafe_allow_html=True)


def quadro_estrategias(df):
    j = jref
    g = df.groupby("Estrategia")
    ordem = [e for e in pv.ORDEM_ESTRATEGIAS if e in g.groups] + sorted(set(g.groups) - set(pv.ORDEM_ESTRATEGIAS))
    p10, p50, p90 = g[f"previa_{j}"].quantile(.1), g[f"previa_{j}"].median(), g[f"previa_{j}"].quantile(.9)
    escala = escala_de(p10, p90)
    casa = set(pv.FUNDOS_INCLUIR.values())
    linhas = ""
    for e in ordem:
        x = g.get_group(e)[f"previa_{j}"]
        sobe, cai = int((x > 0).sum()), int((x < 0).sum())
        linhas += (f'<tr class="{"casa" if e in casa else ""}">'
                   f'<td class="est">{esc(e)}</td><td class="r num">{len(x)}</td>'
                   f'<td class="r num {cls(p50[e])}"><b>{pct(p50[e])}</b></td>'
                   f'<td>{faixa_svg(p10[e], p50[e], p90[e], escala, 280)}</td>'
                   f'<td class="r num opc"><small>{pct(p10[e])} a {pct(p90[e])}</small></td>'
                   f'<td class="r num"><span class="pos">{sobe}</span> / <span class="neg">{cai}</span></td></tr>')
    st.markdown(f'<div class="rolagem"><table class="quadro"><thead><tr><th>Estratégia</th><th class="r">Fundos</th>'
                f'<th class="r">Mediana</th><th>Dispersão entre fundos</th><th class="r opc">80% dos fundos</th>'
                f'<th class="r">Sobem / caem</th></tr></thead><tbody>{linhas}</tbody></table></div>',
                unsafe_allow_html=True)


def tabela_destaques(v, n, maiores):
    j = jref
    t = v.nlargest(n, f"previa_{j}") if maiores else v.nsmallest(n, f"previa_{j}")
    escala = escala_de(t[f"previa_{j}_min"], t[f"previa_{j}_max"])
    linhas = "".join(
        f'<tr><td class="nome">{esc(_titulo_fundo(r["Nome"], 40))}<br><small>{esc(r["Estrategia"])}, '
        f'{esc(_titulo_fundo(str(r["Gestor"]), 28))}</small></td>'
        f'<td class="r num {cls(r[f"previa_{j}"])}"><b>{pct(r[f"previa_{j}"])}</b></td>'
        f'<td>{faixa_svg(r[f"previa_{j}_min"], r[f"previa_{j}"], r[f"previa_{j}_max"], escala, 200)}</td></tr>'
        for _, r in t.iterrows())
    st.markdown(f'<div class="rolagem"><table class="quadro"><thead><tr><th>Fundo</th><th class="r">Hoje</th>'
                f'<th>Faixa de 95%</th></tr></thead><tbody>{linhas}</tbody></table></div>', unsafe_allow_html=True)


def grafico_real_previa(chave, j, altura=260):
    bt = historico_fundo(M, chave)
    if bt.empty:
        return None, None
    gd = pd.DataFrame({"Data": bt["data"].values, "Real": np.expm1(bt["real"].values),
                       "Prévia": np.expm1(bt[f"prev_{j}"].values),
                       "Mín": np.expm1(bt[f"ic_{j}_min"].values), "Máx": np.expm1(bt[f"ic_{j}_max"].values)})
    x = alt.X("Data:T", title=None, axis=alt.Axis(format="%d/%m", grid=False))
    faixa = alt.Chart(gd).mark_area(color=COR["celeste"], opacity=.35).encode(
        x=x, y=alt.Y("Mín:Q", axis=alt.Axis(format="+.1%"), title=None), y2="Máx:Q")
    real = alt.Chart(gd).mark_bar(color=COR["marinho"], size=5).encode(
        x=x, y="Real:Q", tooltip=[alt.Tooltip("Data:T", format="%d/%m", title="Dia"),
                                  alt.Tooltip("Real:Q", format="+.2%"), alt.Tooltip("Prévia:Q", format="+.2%")])
    linha = alt.Chart(gd).mark_line(color=COR["laranja"] if j == "comb" else COR["azul"], strokeWidth=2).encode(
        x=x, y="Prévia:Q")
    res = {"erro": (gd["Real"] - gd["Prévia"]).abs().mean() * 1e4,
           "dentro": ((gd["Real"] >= gd["Mín"]) & (gd["Real"] <= gd["Máx"])).mean(), "dias": len(gd)}
    return (faixa + real + linha).properties(height=altura), res


def aba_destaques(df, v):
    c1, c2 = st.columns(2, gap="large")
    with c1:
        titulo("Maiores altas previstas")
        tabela_destaques(v, 8, True)
    with c2:
        titulo("Maiores quedas previstas")
        tabela_destaques(v, 8, False)
    lim_amp = max(df["amplitude_janelas"].quantile(0.9), AMPLITUDE_MIN)
    al = v[(v["amplitude_janelas"] >= lim_amp) | (v[f"r2_{jref}"] < 0.4) | (v["dias_desde_base"] > 2)]
    titulo("Pontos de atenção", "Fundos em que a prévia merece cautela hoje.")
    if al.empty:
        nota("Nenhum fundo pede atenção com os filtros atuais.")
        return
    motivo = np.select([al["amplitude_janelas"] >= lim_amp, al[f"r2_{jref}"] < 0.4, al["dias_desde_base"] > 2],
                       ["Janelas divergem: possível mudança de posição", "Modelo explica pouco o fundo (R² < 0,4)",
                        "Cota da CVM atrasada"], "")
    ta = pd.DataFrame({"Fundo": al["Nome"].map(lambda n: _titulo_fundo(n, 48)), "Estratégia": al["Estrategia"],
                       "Gestor": al["Gestor"].astype(str).map(lambda n: _titulo_fundo(n, 26)), "Motivo": motivo,
                       "Prévia": al[f"previa_{jref}"], "Divergência": al["amplitude_janelas"],
                       "R²": al[f"r2_{jref}"], "Última cota": al["data_base"].dt.strftime("%d/%m")})
    st.dataframe(ta.sort_values("Divergência", ascending=False).head(30).style
                 .format({"Prévia": fmt_pct, "Divergência": lambda x: pct(x, sinal=False), "R²": lambda x: num(x, 2)})
                 .map(cor_sinal, subset=["Prévia"]), hide_index=True, width="stretch",
                 column_config={"Fundo": st.column_config.TextColumn(width="large")})
    nota(f"{len(al)} fundos. Divergência = maior menos menor prévia entre as janelas 1m, 2m, 3m e 12m; "
         f"entram os 10% maiores, a partir de {pct(lim_amp, sinal=False)}.")


def aba_fundos(v):
    j = jref
    t = pd.DataFrame({
        "Fundo": nome_curto(v), "Estratégia": v["Estrategia"], "Gestor": v["Gestor"].str.slice(0, 32),
        "PL (R$ mi)": v["pl"] / 1e6, "Última cota": v["data_base"].dt.strftime("%d/%m"),
        **{f"Prévia {R(k)}": v[f"previa_{k}"] for k in TODAS},
        "Mín 95%": v[f"previa_{j}_min"], "Máx 95%": v[f"previa_{j}_max"],
        "Divergência": v["amplitude_janelas"], "Cota estimada": v[f"cota_est_{j}"], "R²": v[f"r2_{j}"],
        "CNPJ": v["CNPJ"],
    }).sort_values(f"Prévia {R(j)}", ascending=False)
    pcols = [c for c in t if c.startswith(("Prévia", "Mín", "Máx"))]
    sty = (t.style.format({**{c: fmt_pct for c in pcols}, "Divergência": lambda x: pct(x, sinal=False),
                           "PL (R$ mi)": num, "Cota estimada": lambda x: num(x, 6), "R²": lambda x: num(x, 2)},
                          na_rep="–")
           .map(cor_sinal, subset=pcols).bar(subset=["R²"], color=COR["celeste"], vmin=0, vmax=1))
    st.dataframe(sty, hide_index=True, width="stretch", height=600,
                 column_config={"Fundo": st.column_config.TextColumn(width="large"),
                                "Gestor": st.column_config.TextColumn(width="medium")})
    nota(f"{len(v)} fundos. Mín e máx 95% e cota estimada pelo modelo {R(j)}.")
    agora_txt = _agora_br().strftime("%Y%m%d_%H%M")
    b1, b2, _ = st.columns([1, 1, 5])
    b1.download_button("Baixar Excel", para_excel(t), f"previa_{agora_txt}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    b2.download_button("Baixar CSV", t.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig"),
                       f"previa_{agora_txt}.csv", "text/csv", width="stretch")


def aba_fundo(v):
    casa = v["CNPJ"].isin(pv.FUNDOS_INCLUIR)
    op = v.assign(_c=(~casa).astype(int)).sort_values(["_c", "pl"], ascending=[True, False])
    rot = dict(zip(op["chave"], nome_curto(op) + "  (" + op["CNPJ"] + ")"))
    sel = st.selectbox("Fundo", list(rot), format_func=rot.get, index=0 if len(rot) else None)
    if not sel:
        return
    f = op[op["chave"] == sel].iloc[0]
    st.markdown(f'<p class="sub">{esc(f["Estrategia"])}, {esc(f["Classe_ANBIMA"])}. Gestor: {esc(f["Gestor"])}. '
                f'PL de R$ {num(f["pl"] / 1e6)} mi.</p>', unsafe_allow_html=True)
    esc_f = escala_de([f[f"previa_{k}_min"] for k in TODAS], [f[f"previa_{k}_max"] for k in TODAS])
    linhas = "".join(
        f'<tr class="{"casa" if k == "comb" else ""}"><td class="est">{R(k).capitalize()}</td>'
        f'<td class="r num {cls(f[f"previa_{k}"])}"><b>{pct(f[f"previa_{k}"])}</b></td>'
        f'<td>{faixa_svg(f[f"previa_{k}_min"], f[f"previa_{k}"], f[f"previa_{k}_max"], esc_f, 300)}</td>'
        f'<td class="r num opc"><small>{pct(f[f"previa_{k}_min"])} a {pct(f[f"previa_{k}_max"])}</small></td>'
        f'<td class="r num">{"" if k == "comb" else pct(f[f"peso_{k}"], 0, False)}</td>'
        f'<td class="r num">{num(f[f"r2_{k}"], 2)}</td></tr>' for k in TODAS)
    st.markdown(f'<div class="rolagem"><table class="quadro"><thead><tr><th>Modelo</th><th class="r">Hoje</th>'
                f'<th>Faixa de 95%</th><th class="r opc">Intervalo</th><th class="r">Peso na combinada</th>'
                f'<th class="r">R²</th></tr></thead><tbody>{linhas}</tbody></table></div>', unsafe_allow_html=True)
    nota(f"Cota estimada ({R(jref)}): {num(f[f'cota_est_{jref}'], 6)}, entre {num(f[f'cota_est_{jref}_min'], 6)} "
         f"e {num(f[f'cota_est_{jref}_max'], 6)}. Última cota divulgada: {num(f['cota_base'], 6)} em "
         f"{data_br(f['data_base'])}.")

    c1, c2 = st.columns([1, 1.6], gap="large")
    with c1:
        titulo("Sensibilidade a cada fator", "Quanto o fundo anda, em %, para cada 1% do fator.")
        b = bet[bet["chave"] == f["chave"]].set_index("janela").reindex(JAN)
        bcols = [c for c in b if c.startswith("b_") and b[c].notna().any()]
        tb = b[bcols].T
        tb.index = [c[2:] for c in bcols]
        tb.columns = JAN
        st.dataframe(tb.style.format(lambda x: num(x, 2), na_rep="–")
                     .background_gradient(cmap=_mapa_marca(), vmin=-1.2, vmax=1.2, axis=None), width="stretch")
    with c2:
        titulo("Prévia contra o realizado", f"Últimos 63 dias, fora da amostra, modelo {R(jref)}.")
        graf, res = grafico_real_previa(f["chave"], jref)
        if graf is not None:
            st.altair_chart(graf, width="stretch")
            nota(f"Barras: retorno realizado. Linha: prévia. Faixa: intervalo de 95%. Erro médio de "
                 f"{num(res['erro'])} bps por dia; o realizado ficou dentro da faixa em {pct(res['dentro'], 0, False)} "
                 f"dos dias.")


def aba_qualidade():
    r, pf, (ini, fim, nobs) = qualidade(M)
    ordem = pv.ordenar_estrategias(set(r["Estrategia"]))
    modelos = TODAS + ["só CDI"]
    erro = r.pivot(index="Estrategia", columns="Modelo", values="MAE_bps").reindex(ordem)[modelos]
    erro.columns = [R(m) for m in modelos]
    erro = erro.rename_axis("Estratégia")
    titulo("Erro médio da prévia diária",
           f"Cada dia foi previsto só com dados até a véspera, de {ini:%d/%m/%Y} a {fim:%d/%m/%Y} "
           f"({num(nobs)} fundo-dias). Em bps (0,01%); menor é melhor. Só CDI é a referência ingênua.")
    longo = erro.reset_index().melt(id_vars="Estratégia", var_name="Modelo", value_name="Erro")
    dom = [R(m) for m in modelos]
    st.altair_chart(alt.Chart(longo).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        x=alt.X("Estratégia:N", title=None, sort=ordem, axis=alt.Axis(labelAngle=0, labelFontWeight=600)),
        xOffset=alt.XOffset("Modelo:N", sort=dom), y=alt.Y("Erro:Q", title="bps"),
        color=alt.Color("Modelo:N", sort=dom, title=None,
                        scale=alt.Scale(domain=dom, range=[COR_JANELA.get(d, "#999") for d in dom])),
        tooltip=["Estratégia", "Modelo", alt.Tooltip("Erro:Q", format=".1f")]).properties(height=260),
        width="stretch")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.dataframe(erro.style.format(lambda x: num(x, 1))
                     .highlight_min(axis=1, subset=[R(m) for m in TODAS], props=f"font-weight:700;color:{COR['marinho']}"),
                     width="stretch")
    with c2:
        cob = (r[r["Modelo"].isin(TODAS)].pivot(index="Estrategia", columns="Modelo", values="cobertura_IC")
               .reindex(ordem)[TODAS].rename(columns=R).rename_axis("Estratégia"))
        st.dataframe(cob.style.format(lambda x: pct(x, 0, False)).map(fora_do_alvo), width="stretch")
        nota("Cobertura do intervalo de 95% calibrado: % dos dias em que o realizado caiu dentro da faixa. "
             "O ideal é ficar perto de 95%; em laranja, o que se afasta mais de 3 pontos.")
    titulo("Fundos que o modelo explica pior")
    pior = (pf.rename("Erro (bps)").to_frame().join(univ.set_index("chave")[["Nome", "Estrategia", "Gestor"]])
            .nlargest(12, "Erro (bps)").rename(columns={"Estrategia": "Estratégia", "Nome": "Fundo"}))
    pior["Fundo"] = pior["Fundo"].map(lambda n: _titulo_fundo(n, 60))
    pior["Gestor"] = pior["Gestor"].astype(str).map(lambda n: _titulo_fundo(n, 40))
    st.dataframe(pior[["Fundo", "Estratégia", "Gestor", "Erro (bps)"]].style.format({"Erro (bps)": num}),
                 hide_index=True, width="stretch", column_config={"Fundo": st.column_config.TextColumn(width="large")})


@st.fragment(run_every=intervalo)
def ao_vivo():
    agora, ts, erro = precos(tuple(px.columns))
    if erro is None:
        quando, vivo = f"Ao vivo, preços das {ts:%H:%M}", True
    else:
        agora, quando, vivo = px.ffill().iloc[-1], f"Sem preço ao vivo, usando o fechamento de {data_br(d_ant)}", False
    agora = agora.reindex(px.columns).fillna(px.ffill().iloc[-1])
    if manual:
        agora = aplicar_manual(agora, manual)
        quando += ", com fatores manuais"
    df = pv.calcular_previa(univ, cot, bet, px, cdi, agora, com_alfa=com_alfa, cal=cal)
    mov = pv.movimento_fatores(px, agora, d_ant)
    v = aplicar_filtros(df)

    barra_topo(quando, vivo)
    hero(df)
    frase_resumo(df, mov)
    fita_fatores(mov)
    titulo("Estratégias hoje", f"Prévia do dia por estratégia, modelo {R(jref)}. A barra mostra onde estão 80% "
                               "dos fundos; o ponto é a mediana.")
    if v.empty:
        st.info("Nenhum fundo com os filtros atuais. Ajuste os filtros na barra lateral.")
        return
    quadro_estrategias(v)

    t1, t2, t3, t4 = st.tabs(["Destaques", "Todos os fundos", "Fundo", "Qualidade do modelo"])
    with t1:
        aba_destaques(df, v)
    with t2:
        aba_fundos(v)
    with t3:
        aba_fundo(v)
    with t4:
        aba_qualidade()


ao_vivo()
