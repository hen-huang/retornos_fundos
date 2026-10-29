"""
Prévia diária de cotas por fatores: fundos Long Only, Long Biased, Long Short e Macro.

Uso (Jupyter/Spyder):
    import previa as pv
    pv.atualizar(); pv.estimar(); pv.backtest(); pv.previa(); pv.consolidado()

Modelo, por fundo e por janela (log-retornos):
    r_fundo - r_CDI = α + Σ βk·xk + ε
    prévia do dia = CDI(1 dia) + Σ βk·xk(hoje),  IC = ± t·σ·√(1 + 1/n + q'Vq)
"""
from __future__ import annotations

import argparse
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Configuração
try:
    DADOS = Path(__file__).resolve().parent / "dados"
except NameError:
    DADOS = Path.cwd() / "dados"
CVM_DIR = DADOS / "cvm"
MESES_HISTORICO = 37             # 36M completos + mês corrente (CVM publica mensais desde 2021)
DOWNLOADS_PARALELOS = 4
PL_MINIMO = 100e6
DIAS_MIN_HISTORICO = 120

FATORES = {
    "IBOV": "^BVSP",
    "SMLL": "SMAL11.SA",
    "USD": "BRL=X",
    "SPX": "^GSPC",
    "IRFM": "IRFM11.SA",
    "IMAB": "IMAB11.SA",
    "IFIX": "XFIX11.SA",
    "NDX": "^IXIC",            # Nasdaq Composite
    "BRENT": "BZ=F",           # petróleo Brent (futuro)
    "OURO": "GC=F",            # ouro (futuro)
    "EEM": "EEM",              # ações emergentes (ETF em USD)
    "TX_UST10": "^TNX",        # Treasury 10 anos (taxa, em % a.a.)
}
# Fatores defasados em 1 dia: capturam marcação em D-1 de ativos no exterior e fechamentos assíncronos.
FATORES_DEFASADOS = ["SPX", "USD"]
FATORES_ESTRATEGIA = {
    "Long Only":   ["IBOV", "SMLL", "SPX", "USD", "IFIX"],
    "Long Biased": ["IBOV", "SMLL", "SPX", "USD", "IFIX"],
    "Long Short":  ["IBOV", "SMLL", "SPX", "USD", "IFIX"],
    "Macro":       ["IBOV", "SPX", "USD", "IRFM", "IMAB", "IFIX"],
    "Hedge Alternative": ["IBOV", "SMLL", "SPX", "USD", "IRFM", "IMAB", "IFIX"],
}
# Fatores adicionais: só entram nos modelos com amostra grande (>= OBS_MIN_ADICIONAIS), contra sobreajuste.
FATORES_ADICIONAIS = {
    "Long Only":   ["NDX", "BRENT", "OURO", "EEM", "SPX_L1", "USD_L1"],
    "Long Biased": ["NDX", "BRENT", "OURO", "EEM", "SPX_L1", "USD_L1"],
    "Long Short":  ["NDX", "BRENT", "EEM", "SPX_L1"],
    "Macro":       ["TX_UST10", "BRENT", "OURO", "EEM", "SPX_L1", "USD_L1"],
    "Hedge Alternative": ["TX_UST10", "BRENT", "OURO", "SPX_L1", "USD_L1"],
}
OBS_MIN_ADICIONAIS = 120           # fatores adicionais só em modelos com >= 120 obs. (6m, 12m, 24m, ew); 0 = em todos
RIDGE_ESCALA = 10                  # ridge efetivo = RIDGE × (1 + RIDGE_ESCALA × fatores / obs.)
# Fundos incluídos sempre, com estratégia própria (ignoram classe, PL mínimo e exclusividade).
FUNDOS_INCLUIR = {
    "35.377.516/0001-34": "Hedge Alternative",   # Master FIM CP
    "06.867.811/0001-70": "Hedge Alternative",   # FICFI Multimercado CP
    "35.372.302/0001-75": "Hedge Alternative",   # W FIC Multi CP
    "42.195.744/0001-59": "Hedge Alternative",   # Prev Multimercado FIC CP
}
APELIDOS = {"35.377.516/0001-34": "Master", "06.867.811/0001-70": "FICFI",
            "35.372.302/0001-75": "W FIC", "42.195.744/0001-59": "Prev FIC"}
ORDEM_ESTRATEGIAS = ["Long Only", "Long Biased", "Long Short", "Macro", "Hedge Alternative"]
# Opcional: dados/fatores_extra.csv com coluna "data" e uma coluna por fator.
# Prefixo TX_ = taxa (variação em p.p.); demais = preço.
EXTRA_CSV = DADOS / "fatores_extra.csv"

# Janelas de estimação em dias úteis. A principal define confiança, ordenação e cota estimada.
JANELAS = {"1m": 21, "2m": 42, "3m": 63, "6m": 126, "12m": 250, "24m": 500}
MIN_OBS = {"1m": 15, "2m": 30, "3m": 40, "6m": 90, "12m": 160, "24m": 320}
MEIA_VIDA_EW = 63                  # modelo "ew": todas as obs., peso exponencial com meia-vida de 63 dias úteis
MIN_OBS_EW = 60
MODELOS = list(JANELAS) + ["ew"]
JANELA_PRINCIPAL = "comb"          # "comb" = combinação das janelas pelo erro recente
CALIB_DIAS = 63                    # dias usados nos pesos da combinação e na calibração do IC
CALIB_MIN = 20
CALIB_ENCOLHE = 20                 # obs. fictícias com fator 1 (encolhe a calibração em amostras curtas)
RIDGE = 2.0
IC_NIVEL = 0.95
RET_MAX_ABS = 0.35
DATAS_EXCLUIR: list[str] = ["2026-10-26"]   # circuit breaker pós-2º turno

CLASSES_LONG_ONLY = {
    "Ações Livre", "Ações Valor/Crescimento", "Ações Índice Ativo", "Ações Small Caps",
    "Ações Dividendos", "Ações Setoriais", "Ações Sustentabilidade/Governança",
    "Previdência Ações Ativo",
}
CLASSES_LS = {"Multimercados L/S - Direcional", "Multimercados L/S - Neutro"}
CLASSES_MACRO = {"Multimercados Macro", "Previdência Multimercados Macro"}

URL_INFORME = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{ym}.zip"
URL_REGISTRO = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
URL_CAD_FI = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv"
URL_CDI = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"
           "?formato=json&dataInicial={ini}&dataFinal={fim}")


# Utilidades
def hoje_br() -> date:
    return pd.Timestamp.now(tz="America/Sao_Paulo").date()


def _log(msg: str) -> None:
    print(f"[{pd.Timestamp.now(tz='America/Sao_Paulo'):%H:%M:%S}] {msg}", flush=True)


def _session():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "previa-cotas/1.0"
    return s


def baixar(url: str, destino: Path, forcar: bool = False, tentativas: int = 3) -> bool:
    zipado = destino.suffix == ".zip"
    if destino.exists() and not forcar and (not zipado or zipfile.is_zipfile(destino)):
        return True
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".part")
    for t in range(tentativas):
        try:
            r = _session().get(url, timeout=300, stream=True)
            if r.status_code == 404:
                return False
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            if zipado and not zipfile.is_zipfile(tmp):
                raise IOError(f"arquivo corrompido: {url}")
            tmp.replace(destino)
            return True
        except Exception:
            tmp.unlink(missing_ok=True)
            if t == tentativas - 1:
                raise
            time.sleep(3 * (t + 1))
    return False


def _meses(n: int, hoje: date | None = None) -> list[str]:
    p = pd.Period(hoje or hoje_br(), "M")
    return [str(p - i).replace("-", "") for i in range(n)][::-1]


def _janelas() -> list[str]:
    return list(MODELOS)


# Cadastro e universo
def _classificar(nome: pd.Series, anbima: pd.Series) -> pd.Series:
    nome = nome.fillna("").str.upper()
    anbima = anbima.fillna("")
    lb = nome.str.contains(r"LONG\s?BIAS", regex=True)
    est = pd.Series(None, index=nome.index, dtype=object)
    est[anbima.isin(CLASSES_LONG_ONLY) & ~lb] = "Long Only"
    est[lb] = "Long Biased"
    est[anbima.isin(CLASSES_LS)] = "Long Short"
    est[anbima.isin(CLASSES_MACRO)] = "Macro"
    return est


def _fmt_cnpj(c) -> str:
    c = "".join(ch for ch in str(c) if ch.isdigit()).zfill(14)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def ler_cadastro() -> pd.DataFrame:
    kw = dict(sep=";", dtype=str, encoding="latin1")
    with zipfile.ZipFile(DADOS / "registro_fundo_classe.zip") as z:
        cl = pd.read_csv(z.open("registro_classe.csv"), **kw)
        fu = pd.read_csv(z.open("registro_fundo.csv"), **kw)
        sb = pd.read_csv(z.open("registro_subclasse.csv"), **kw)
    cl = cl.merge(fu[["ID_Registro_Fundo", "Gestor", "Administrador"]], on="ID_Registro_Fundo", how="left")
    frames = [pd.DataFrame({
        "CNPJ": cl["CNPJ_Classe"].map(_fmt_cnpj),
        "Nome": cl["Denominacao_Social"],
        "Classe_ANBIMA": cl["Classificacao_Anbima"],
        "Gestor": cl["Gestor"],
        "Administrador": cl["Administrador"],
        "Exclusivo": cl["Exclusivo"],
        "Ativo": cl["Situacao"].eq("Em Funcionamento Normal"),
    })]
    if (DADOS / "cad_fi.csv").exists():
        cad = pd.read_csv(DADOS / "cad_fi.csv", **kw)
        frames.append(pd.DataFrame({
            "CNPJ": cad["CNPJ_FUNDO"],
            "Nome": cad["DENOM_SOCIAL"],
            "Classe_ANBIMA": cad["CLASSE_ANBIMA"],
            "Gestor": cad["GESTOR"],
            "Administrador": cad["ADMIN"],
            "Exclusivo": cad["FUNDO_EXCLUSIVO"],
            "Ativo": cad["SIT"].eq("EM FUNCIONAMENTO NORMAL"),
        }))
    cad_all = (pd.concat(frames, ignore_index=True)
               .assign(_ord=lambda d: (~d["Ativo"]).astype(int))
               .sort_values("_ord", kind="stable")
               .drop_duplicates("CNPJ", keep="first")
               .drop(columns="_ord"))
    cad_all["Estrategia"] = _classificar(cad_all["Nome"], cad_all["Classe_ANBIMA"])
    cad_all["Elegivel"] = cad_all["Estrategia"].notna() & cad_all["Ativo"] & cad_all["Exclusivo"].ne("S")
    cad_all.attrs["subclasses"] = sb.drop_duplicates("ID_Subclasse").set_index("ID_Subclasse")["Denominacao_Social"]
    return cad_all.set_index("CNPJ")


def _mapa_fundo_classe() -> dict[str, str]:
    """CNPJ do fundo -> CNPJ da classe, para fundos de classe única que mudaram de CNPJ na RCVM 175.

    Antes da adaptação o informe vinha por fundo (CNPJ_FUNDO); depois, por classe (CNPJ_FUNDO_CLASSE).
    Com o mapa, o histórico antigo emenda no da classe.
    """
    p = DADOS / "registro_fundo_classe.zip"
    if not p.exists():
        return {}
    kw = dict(sep=";", dtype=str, encoding="latin1")
    with zipfile.ZipFile(p) as z:
        cl = pd.read_csv(z.open("registro_classe.csv"), usecols=["ID_Registro_Fundo", "CNPJ_Classe"], **kw)
        fu = pd.read_csv(z.open("registro_fundo.csv"), usecols=["ID_Registro_Fundo", "CNPJ_Fundo"], **kw)
    m = cl.merge(fu, on="ID_Registro_Fundo").dropna()
    m = m[m.groupby("ID_Registro_Fundo")["CNPJ_Classe"].transform("size") == 1]
    f, c = m["CNPJ_Fundo"].map(_fmt_cnpj), m["CNPJ_Classe"].map(_fmt_cnpj)
    return dict(zip(f[f != c], c[f != c]))


def _cnpj_padrao(s: pd.Series) -> pd.Series:
    s = s.str.strip()
    so_digitos = s.str.len() < 18
    if so_digitos.any():
        s = s.where(~so_digitos, s.map(_fmt_cnpj))
    return s


def _ler_informe(zp: Path, alvo: set[str], mapa: dict[str, str]) -> list[pd.DataFrame]:
    cols = {"CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO", "ID_SUBCLASSE", "DT_COMPTC", "VL_QUOTA", "VL_PATRIM_LIQ"}
    out = []
    with zipfile.ZipFile(zp) as z:
        for nm in z.namelist():
            if not nm.lower().endswith(".csv"):
                continue
            df = pd.read_csv(z.open(nm), sep=";", dtype=str, usecols=lambda c: c in cols, encoding="latin1")
            novo = "CNPJ_FUNDO_CLASSE" in df
            cnpj = _cnpj_padrao(df["CNPJ_FUNDO_CLASSE" if novo else "CNPJ_FUNDO"])
            df = df.drop(columns=["CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO"], errors="ignore")
            if not novo and mapa:
                cnpj = cnpj.map(mapa).fillna(cnpj)
            df["CNPJ"] = cnpj
            df["antigo"] = not novo
            out.append(df[cnpj.isin(alvo)])
    return out


def _emendar(d: pd.DataFrame) -> pd.DataFrame:
    """Na troca do formato antigo (fundo) para o novo (classe), reescala o trecho antigo se a cota saltar."""
    mist = d.groupby(["CNPJ", "SUB"])["antigo"].transform("nunique") > 1
    if not mist.any():
        return d
    for (c, s), g in d[mist].groupby(["CNPJ", "SUB"]):
        ant, nov = g[g["antigo"]], g[~g["antigo"]]
        nov = nov[nov["data"] > ant["data"].max()]
        if nov.empty:
            continue
        salto = nov["cota"].iloc[0] / ant["cota"].iloc[-1] - 1
        if abs(salto) > RET_MAX_ABS:
            d.loc[ant.index, "cota"] *= nov["cota"].iloc[0] / ant["cota"].iloc[-1]
    return d


def _emendar_subclasses(d: pd.DataFrame, salto_max: float = 0.03, dias_max: int = 10) -> pd.DataFrame:
    """Leva o histórico da classe sem subclasse (anterior à adaptação) para a subclasse que continua a cota."""
    sem = d[d["SUB"] == ""].groupby("CNPJ").agg(fim=("data", "max"))
    com = d[d["SUB"] != ""].groupby(["CNPJ", "SUB"]).agg(ini=("data", "min")).reset_index()
    com = com[com["CNPJ"].isin(sem.index)]
    if com.empty:
        return d
    ult = d[d["SUB"] == ""].groupby("CNPJ")["cota"].last()
    pri = d[d["SUB"] != ""].groupby(["CNPJ", "SUB"])["cota"].first()
    com = com.join(sem, on="CNPJ")
    com = com[(com["ini"] > com["fim"]) & ((com["ini"] - com["fim"]).dt.days <= dias_max)]
    com["salto"] = (com.set_index(["CNPJ", "SUB"]).index.map(pri).to_numpy() / com["CNPJ"].map(ult) - 1).abs()
    com = com[com["salto"] <= salto_max].sort_values("salto").drop_duplicates("CNPJ")
    if com.empty:
        return d
    alvo = d["CNPJ"].map(com.set_index("CNPJ")["SUB"])
    mover = (d["SUB"] == "") & alvo.notna()
    d.loc[mover, "SUB"] = alvo[mover]
    _log(f"Histórico anterior à adaptação emendado em {len(com)} subclasse(s)")
    return d


def ler_informes(cnpjs: set[str]) -> pd.DataFrame:
    mapa = {f: c for f, c in _mapa_fundo_classe().items() if c in cnpjs}
    out = []
    for zp in sorted(CVM_DIR.glob("inf_diario_fi_*.zip")):
        out += _ler_informe(zp, cnpjs, mapa)
    if not out:
        raise SystemExit("Nenhum informe diário em dados/cvm. Rode pv.atualizar().")
    d = pd.concat(out, ignore_index=True)
    if "ID_SUBCLASSE" not in d:
        d["ID_SUBCLASSE"] = ""
    d = pd.DataFrame({
        "CNPJ": d["CNPJ"],
        "SUB": d["ID_SUBCLASSE"].fillna(""),
        "data": pd.to_datetime(d["DT_COMPTC"]),
        "cota": pd.to_numeric(d["VL_QUOTA"], errors="coerce"),
        "pl": pd.to_numeric(d["VL_PATRIM_LIQ"], errors="coerce"),
        "antigo": d["antigo"].astype(bool),
    })
    d = d[d["cota"] > 0].sort_values(["CNPJ", "SUB", "data", "antigo"], ascending=[True, True, True, False])
    d = d.drop_duplicates(["CNPJ", "SUB", "data"], keep="first").reset_index(drop=True)
    d = _emendar(d)
    d = _emendar_subclasses(d)
    _log(f"Informes: {d['data'].min():%d/%m/%Y} a {d['data'].max():%d/%m/%Y}, "
         f"{d['data'].dt.to_period('M').nunique()} meses")
    return d.drop(columns="antigo").sort_values(["CNPJ", "SUB", "data"], ignore_index=True)


def montar_universo() -> tuple[pd.DataFrame, pd.DataFrame]:
    cad = ler_cadastro()
    forc = [c for c in FUNDOS_INCLUIR if c in cad.index]
    cad.loc[forc, "Estrategia"] = [FUNDOS_INCLUIR[c] for c in forc]
    cad.loc[forc, "Elegivel"] = True
    eleg = cad[cad["Elegivel"]]
    _log(f"Cadastro: {len(cad):,} classes, {len(eleg):,} elegíveis ({len(forc)} incluídos manualmente)")
    cot = ler_informes(set(eleg.index))
    ult = cot.groupby(["CNPJ", "SUB"]).agg(
        data_ult=("data", "max"), pl=("pl", "last"), dias=("data", "nunique")).reset_index()
    fixo = ult["CNPJ"].isin(FUNDOS_INCLUIR)
    ult = ult[(fixo | (ult["pl"] >= PL_MINIMO)) & (ult["dias"] >= DIAS_MIN_HISTORICO)
              & (ult["data_ult"] >= cot["data"].max() - pd.Timedelta(days=7))]
    ult = ult.join(eleg[["Nome", "Estrategia", "Classe_ANBIMA", "Gestor", "Administrador"]], on="CNPJ")
    ult["Subclasse"] = ult["SUB"].map(cad.attrs["subclasses"]).fillna("")
    ult["chave"] = ult["CNPJ"] + "|" + ult["SUB"]
    cot = cot.merge(ult[["CNPJ", "SUB", "chave"]], on=["CNPJ", "SUB"])[["chave", "data", "cota"]]
    _log(f"Universo: {len(ult):,} fundos/subclasses com PL ≥ R$ {PL_MINIMO/1e6:.0f} mi "
         f"({ult['Estrategia'].value_counts().to_dict()})")
    return ult.reset_index(drop=True), cot


# Fatores
def _yf():
    import logging
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    return yf


def baixar_fatores(inicio: pd.Timestamp) -> pd.DataFrame:
    px = _yf().download(list(FATORES.values()), start=(inicio - pd.Timedelta(days=15)).date(),
                        auto_adjust=True, progress=False, threads=True)["Close"]
    px.index = pd.to_datetime(px.index).tz_localize(None).normalize()
    px = px.rename(columns={v: k for k, v in FATORES.items()})[list(FATORES)]
    falt = [c for c in px if px[c].dropna().empty]
    if falt:
        _log(f"Atenção: sem dados no Yahoo para {falt}")
    return px


def baixar_cdi(inicio: pd.Timestamp) -> pd.Series:
    url = URL_CDI.format(ini=inicio.strftime("%d/%m/%Y"), fim=hoje_br().strftime("%d/%m/%Y"))
    r = _session().get(url, timeout=60)
    r.raise_for_status()
    js = pd.DataFrame(r.json())
    return pd.Series(pd.to_numeric(js["valor"]).values,
                     index=pd.to_datetime(js["data"], dayfirst=True), name="CDI")


def carregar_fatores() -> tuple[pd.DataFrame, pd.Series]:
    px = pd.read_parquet(DADOS / "fatores.parquet")
    if EXTRA_CSV.exists():
        ex = pd.read_csv(EXTRA_CSV, sep=None, engine="python", decimal=",")
        ex["data"] = pd.to_datetime(ex["data"], dayfirst=True)
        px = px.join(ex.set_index("data").apply(pd.to_numeric, errors="coerce"), how="outer")
    cdi = pd.read_parquet(DADOS / "cdi.parquet")["CDI"]
    px = px.sort_index()
    for f in FATORES_DEFASADOS:
        if f in px:
            px[f"{f}_L1"] = px[f].ffill().shift(1)
    return px, cdi.sort_index()


def fatores_visiveis(colunas) -> list[str]:
    """Fatores de mercado de verdade (sem as colunas defasadas, que são derivadas)."""
    return [c for c in colunas if not c.endswith("_L1")]


def completar_agora(px: pd.DataFrame, agora: pd.Series, d_ant) -> pd.Series:
    """Nível 'agora' das colunas defasadas = fechamento do fator no último pregão (move = retorno de ontem)."""
    agora = agora.copy()
    for f in FATORES_DEFASADOS:
        if f in px and f"{f}_L1" in px:
            agora[f"{f}_L1"] = px[f].ffill().loc[:d_ant].iloc[-1]
    return agora


def _transformar(niveis: pd.DataFrame) -> pd.DataFrame:
    """Nível cujo diff é o retorno do fator: log(preço), ou a própria taxa para TX_."""
    out = niveis.copy()
    for c in out:
        if not c.startswith("TX_"):
            out[c] = np.log(out[c].where(out[c] > 0))
    return out


# Estimação
def calendario(cot: pd.DataFrame) -> pd.DatetimeIndex:
    n = cot.groupby("data")["chave"].nunique()
    return pd.DatetimeIndex(n[n >= 0.5 * n.max()].index).sort_values()


def _t_quantil(gl, nivel: float | None = None):
    nivel = IC_NIVEL if nivel is None else nivel
    gl = np.maximum(np.asarray(gl, dtype=float), 1.0)
    p = 1 - (1 - nivel) / 2
    try:
        from scipy.stats import t
        return t.ppf(p, gl)
    except ImportError:
        from statistics import NormalDist
        z = NormalDist().inv_cdf(p)
        return z + (z**3 + z) / (4 * gl) + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * gl**2)


def _lam(k: int, n: float) -> float:
    """Ridge adaptativo: mais penalização quando há muitos fatores para poucas observações."""
    return RIDGE * (1 + RIDGE_ESCALA * k / max(n, 1))


def _ridge_somas(N, Neff, Sx, Sy, Syy, Sxx, Sxy, lam):
    """Ridge (X padronizado) a partir de somas ponderadas, vetorizado na 1ª dimensão.
    Retorna α, β, σ², V (var(β) = σ²V), média de X, graus de liberdade e R²."""
    k = Sx.shape[1]
    lam = np.broadcast_to(np.asarray(lam, dtype=float), N.shape)
    mx, my = Sx / N[:, None], Sy / N
    Cxx = Sxx - N[:, None, None] * mx[:, :, None] * mx[:, None, :]
    Cxy = Sxy - N[:, None] * mx * my[:, None]
    sd = np.sqrt(np.clip(np.einsum("tii->ti", Cxx) / N[:, None], 0, None))
    sd[sd == 0] = 1.0
    eye = np.eye(k)
    ZZ = Cxx / (sd[:, :, None] * sd[:, None, :]) + lam[:, None, None] * eye
    b = np.linalg.solve(ZZ, (Cxy / sd)[..., None])[..., 0] / sd
    a = my - (mx * b).sum(1)
    sst = Syy - N * my ** 2
    sse = np.clip(sst - 2 * (b * Cxy).sum(1) + np.einsum("ti,tij,tj->t", b, Cxx, b), 0, None)
    g = Neff - k - 1
    s2 = sse / N * Neff / np.maximum(g, 1)
    V = np.linalg.inv(Cxx + lam[:, None, None] * (sd[:, :, None] ** 2) * eye) * (N / Neff)[:, None, None]
    r2 = np.where(sst > 0, 1 - sse / np.where(sst > 0, sst, 1), np.nan)
    return a, b, s2, V, mx, g, r2


def _ridge(X: np.ndarray, y: np.ndarray, lam: float, w: np.ndarray | None = None):
    """Ridge (opcionalmente ponderado). Retorna α, β, R², erro anual, σ diário, média de X, V e n efetivo."""
    w = np.ones(len(y)) if w is None else np.asarray(w, dtype=float)
    Xw = X * w[:, None]
    N, Neff = np.array([w.sum()]), np.array([w.sum() ** 2 / (w ** 2).sum()])
    a, b, s2, V, mx, g, r2 = _ridge_somas(N, Neff, Xw.sum(0)[None], np.array([(w * y).sum()]),
                                          np.array([(w * y * y).sum()]), (Xw.T @ X)[None], (Xw.T @ y)[None], lam)
    sig = float(np.sqrt(s2[0]))
    return a[0], b[0], r2[0], sig * np.sqrt(252), sig, mx[0], V[0], float(Neff[0])


def _usa_adicionais(modelo: str) -> bool:
    return modelo == "ew" or JANELAS.get(modelo, 0) >= OBS_MIN_ADICIONAIS


def _amostras(univ, cot, px, cdi):
    """Por fundo: fatores usados, datas, retorno r, excesso y, X, cdi e máscara de estimação."""
    cal = calendario(cot)
    cot = cot[cot["data"].isin(cal)]
    L = _transformar(px).reindex(px.index.union(cal)).ffill().reindex(cal)
    C = np.log1p(cdi / 100).reindex(cdi.index.union(cal)).fillna(0).cumsum().reindex(cal).ffill().fillna(0)
    lc = np.log(cot.pivot(index="data", columns="chave", values="cota").reindex(cal))
    Lv, Cv = L.to_numpy(), C.to_numpy()
    excl = cal.isin(pd.to_datetime(DATAS_EXCLUIR))
    fora = [c for c in L.columns if L[c].notna().mean() < 0.8]
    if fora:
        _log(f"Atenção: fatores com pouco histórico, ignorados: {fora}")
    col = {c: i for i, c in enumerate(L.columns) if c not in fora}
    for _, f in univ.iterrows():
        if f["chave"] not in lc:
            continue
        base = [c for c in FATORES_ESTRATEGIA[f["Estrategia"]] if c in col]
        fat = base + [c for c in FATORES_ADICIONAIS.get(f["Estrategia"], []) if c in col and c not in base]
        f = f.copy()
        f["n_base"] = len(base)
        s = lc[f["chave"]].to_numpy()
        ok = np.flatnonzero(~np.isnan(s))
        if len(ok) < 2:
            continue
        r = np.diff(s[ok])
        c = np.diff(Cv[ok])
        X = np.diff(Lv[np.ix_(ok, [col[k] for k in fat])], axis=0)
        fin = np.isfinite(X).all(1)
        est = (np.abs(r) < RET_MAX_ABS) & ~excl[ok[1:]]
        yield f, fat, cal[ok[1:]][fin], r[fin], r[fin] - c[fin], X[fin], c[fin], est[fin]


def _estimar_betas(univ, cot, px, cdi) -> pd.DataFrame:
    linhas = []
    for f, fat, _, _, y, X, _, est in _amostras(univ, cot, px, cdi):
        y, X = y[est], X[est]
        for m in MODELOS:
            cols = slice(None) if _usa_adicionais(m) else slice(0, f["n_base"])
            fm = fat[cols]
            if m == "ew":
                if len(y) < MIN_OBS_EW:
                    continue
                idade = np.arange(len(y))[::-1]
                w = 0.5 ** (idade / MEIA_VIDA_EW)
                neff = w.sum() ** 2 / (w ** 2).sum()
                a, b, r2, te, sig, mx, V, n = _ridge(X[:, cols], y, _lam(len(fm), neff), w)
            else:
                nj = JANELAS[m]
                if len(y) < MIN_OBS[m]:
                    continue
                Xs, ys = X[-nj:, cols], y[-nj:]
                a, b, r2, te, sig, mx, V, n = _ridge(Xs, ys, _lam(len(fm), len(ys)))
            linhas.append({"chave": f["chave"], "janela": m, "n": int(round(n)),
                           "alfa": a, "r2": r2, "te": te, "sig": sig,
                           "fatores": list(fm), "mx": mx.tolist(), "V": V.ravel().tolist(),
                           **{f"b_{c}": v for c, v in zip(fm, b)}})
    bet = pd.DataFrame(linhas)
    _log(f"Estimados {bet['chave'].nunique():,} fundos | R² mediano: "
         + ", ".join(f"{j} {bet.loc[bet.janela == j, 'r2'].median():.2f}" for j in MODELOS))
    return bet


# Backtest
def _previsao_somas(X, valido, N, Neff, Sx, Sy, Syy, Sxx, Sxy, lam):
    T, k = X.shape
    a, vp, gl = np.full(T, np.nan), np.full(T, np.nan), np.full(T, np.nan)
    b = np.full((T, k), np.nan)
    v = valido
    if not v.any():
        return a, b, vp, gl
    lam = np.asarray(lam, dtype=float)
    lam = lam[v] if lam.ndim else lam
    av, bv, s2, V, mx, g, _ = _ridge_somas(N[v], Neff[v], Sx[v], Sy[v], Syy[v], Sxx[v], Sxy[v], lam)
    a[v], b[v], gl[v] = av, bv, g
    q = X[v] - mx
    vp[v] = s2 * (1 + 1 / Neff[v] + np.einsum("ti,tij,tj->t", q, V, q))
    return a, b, vp, gl


def _ridge_rolante(X, y, w, n, lam, min_obs):
    """Ridge fora da amostra: para cada obs. i, ajusta nas n últimas obs. válidas (w) anteriores a i."""
    T, k = X.shape
    w = w.astype(float)
    Xw, yw = X * w[:, None], y * w
    z = lambda a: np.concatenate([np.zeros((1,) + a.shape[1:]), np.cumsum(a, 0)])
    cw, cx, cy, cyy, cxx, cxy = z(w), z(Xw), z(yw), z(yw * y), z(Xw[:, :, None] * X[:, None, :]), z(Xw * y[:, None])
    fim = np.arange(T)
    ini = np.minimum(np.searchsorted(cw, np.maximum(cw[fim] - n, 0), side="left"), fim)
    d = lambda c: c[fim] - c[ini]
    N = d(cw)
    valido = N >= min_obs
    Nn = np.where(N > 0, N, 1.0)
    return _previsao_somas(X, valido, Nn, Nn, d(cx), d(cy), d(cyy), d(cxx), d(cxy), lam)


def _ridge_ew_rolante(X, y, w, meia_vida, lam_fn, min_obs):
    """Ridge com pesos exponenciais fora da amostra: para cada obs. i, usa todas as obs. válidas anteriores,
    com peso 0,5^(idade/meia_vida). Somas recursivas via filtro IIR."""
    from scipy.signal import lfilter
    T, k = X.shape
    w = w.astype(float)
    dl = 0.5 ** (1 / meia_vida)
    filt = lambda z, dd=dl: np.concatenate([np.zeros((1,) + z.shape[1:]), lfilter([1.0], [1.0, -dd], z, axis=0)[:-1]])
    Xw, yw = X * w[:, None], y * w
    N, N2 = filt(w), filt(w, dl ** 2)
    Sx, Sy, Syy = filt(Xw), filt(yw), filt(yw * y)
    Sxx, Sxy = filt(Xw[:, :, None] * X[:, None, :]), filt(Xw * y[:, None])
    cont = np.concatenate([[0], np.cumsum(w)[:-1]])
    Nn = np.where(N > 0, N, 1.0)
    Neff = np.where(N2 > 0, N ** 2 / np.where(N2 > 0, N2, 1), 1.0)
    return _previsao_somas(X, cont >= min_obs, Nn, Neff, Sx, Sy, Syy, Sxx, Sxy, lam_fn(np.maximum(Neff, 1)))


def _rolante(df: pd.DataFrame, func: str, q: float | None = None) -> pd.DataFrame:
    r = df.rolling(CALIB_DIAS, min_periods=CALIB_MIN)
    return (r.quantile(q) if func == "q" else getattr(r, func)()).shift(1)


def _fator_calib(z: pd.DataFrame, anterior: bool = True) -> pd.DataFrame:
    """Fator que leva a cobertura empírica ao IC_NIVEL, encolhido para 1 em amostras curtas."""
    if anterior:
        k, n = _rolante(z, "q", IC_NIVEL), _rolante(z, "count")
    else:
        zz = z.tail(CALIB_DIAS)
        k = pd.DataFrame([zz.quantile(IC_NIVEL).to_numpy()], columns=zz.columns)
        n = pd.DataFrame([zz.count().to_numpy()], columns=zz.columns)
    k = (n * k + CALIB_ENCOLHE) / (n + CALIB_ENCOLHE)
    return k.fillna(1.0).clip(0.75, 3.0)


def _pesos(e2: pd.DataFrame, disp: pd.DataFrame) -> pd.DataFrame:
    w = (1 / e2).where(disp, 0).fillna(0)
    sem = w.sum(axis=1) == 0
    w[sem] = disp[sem].astype(float)
    return w.div(w.sum(axis=1), axis=0)


def _backtest_fundos(univ, cot, px, cdi) -> pd.DataFrame:
    """Prévias fora da amostra por fundo/dia e modelo, combinação ponderada e IC calibrado."""
    jans = list(MODELOS)
    out = []
    for f, fat, dt, r, y, X, c, est in _amostras(univ, cot, px, cdi):
        cols = {"data": dt, "real": r, "cdi": c, "usada_estim": est}
        P, M = {}, {}
        for m in MODELOS:
            sel = slice(None) if _usa_adicionais(m) else slice(0, f["n_base"])
            Xm = X[:, sel]
            km = Xm.shape[1]
            if m == "ew":
                a, b, vp, gl = _ridge_ew_rolante(Xm, y, est, MEIA_VIDA_EW,
                                                 lambda ne, km=km: RIDGE * (1 + RIDGE_ESCALA * km / ne), MIN_OBS_EW)
            else:
                a, b, vp, gl = _ridge_rolante(Xm, y, est, JANELAS[m], _lam(km, JANELAS[m]), MIN_OBS[m])
            P[m] = c + (Xm * b).sum(1)
            M[m] = _t_quantil(np.nan_to_num(gl, nan=1)) * np.sqrt(vp)
            cols[f"prev_{m}_alfa"] = P[m] + a
        P, M = pd.DataFrame(P), pd.DataFrame(M)
        real = pd.Series(r)
        usa = pd.Series(est)
        e2 = P.rsub(real, axis=0).pow(2).where(usa, axis=0)
        w = _pesos(_rolante(e2, "mean"), P.notna())
        P["comb"] = (P[jans].fillna(0) * w).sum(axis=1).where(P[jans].notna().any(axis=1))
        M["comb"] = (M[jans].fillna(0) * w).sum(axis=1).where(P["comb"].notna())
        z = P.rsub(real, axis=0).abs().div(M).where(usa, axis=0)
        k = _fator_calib(z)
        for j in jans + ["comb"]:
            cols[f"prev_{j}"] = P[j].to_numpy()
            cols[f"ic_{j}_teo_min"] = (P[j] - M[j]).to_numpy()
            cols[f"ic_{j}_teo_max"] = (P[j] + M[j]).to_numpy()
            cols[f"ic_{j}_min"] = (P[j] - M[j] * k[j]).to_numpy()
            cols[f"ic_{j}_max"] = (P[j] + M[j] * k[j]).to_numpy()
            cols[f"k_{j}"] = k[j].to_numpy()
        for j in jans:
            cols[f"w_{j}"] = w[j].to_numpy()
        d = pd.DataFrame(cols).assign(chave=f["chave"], Estrategia=f["Estrategia"])
        out.append(d.dropna(subset=["prev_comb"]))
    bt = pd.concat(out, ignore_index=True)
    bt["prev_media"] = bt[[f"prev_{j}" for j in MODELOS]].mean(axis=1)
    return bt


def calibracao(bt: pd.DataFrame) -> pd.DataFrame:
    """Pesos da combinação e fatores do IC para uso ao vivo (usa até o último dia disponível)."""
    jans = list(MODELOS)
    linhas = []
    for ch, g in bt[bt["usada_estim"]].groupby("chave"):
        g = g.tail(CALIB_DIAS)
        P = g[[f"prev_{j}" for j in jans]].set_axis(jans, axis=1)
        e2 = P.rsub(g["real"], axis=0).pow(2).mean().to_frame().T
        w = _pesos(e2, P.notna().any().to_frame().T).iloc[0]
        Mt = pd.DataFrame({j: (g[f"ic_{j}_teo_max"] - g[f"prev_{j}"]) for j in jans + ["comb"]})
        Pc = pd.DataFrame({j: g[f"prev_{j}"] for j in jans + ["comb"]})
        k = _fator_calib(Pc.rsub(g["real"], axis=0).abs().div(Mt), anterior=False).iloc[0]
        linhas.append({"chave": ch, **{f"w_{j}": w[j] for j in jans}, **{f"k_{j}": k[j] for j in jans + ["comb"]}})
    return pd.DataFrame(linhas).set_index("chave")


def resumir_backtest(bt: pd.DataFrame) -> pd.DataFrame:
    """Métricas por estratégia e modelo (erros em bps de retorno diário)."""
    modelos = {j: f"prev_{j}" for j in MODELOS}
    modelos.update({"comb": "prev_comb", "média": "prev_media", "só CDI": "cdi"})
    real = np.expm1(bt["real"])
    linhas = []
    for est, g in [("Todas", bt)] + list(bt.groupby("Estrategia")):
        rr = real.loc[g.index]
        exc = rr - np.expm1(g["cdi"])
        for nome, col in modelos.items():
            ok = g[col].notna()
            e = (rr - np.expm1(g[col]))[ok]
            p_exc = (np.expm1(g[col]) - np.expm1(g["cdi"]))[ok]
            lin = {"Estrategia": est, "Modelo": nome, "obs": int(ok.sum()),
                   "MAE_bps": e.abs().mean() * 1e4, "RMSE_bps": np.sqrt((e ** 2).mean()) * 1e4,
                   "R2_fora_amostra": 1 - (e ** 2).sum() / (exc[ok] ** 2).sum() if (exc[ok] ** 2).sum() > 0 else np.nan,
                   "acerto_sinal": (np.sign(p_exc) == np.sign(exc[ok])).mean() if col != "cdi" else np.nan,
                   "vies_bps": -e.mean() * 1e4, "cobertura_IC": np.nan, "cobertura_IC_teo": np.nan,
                   "largura_IC_bps": np.nan}
            if f"ic_{nome}_min" in g:
                rr_ = g["real"][ok]
                lo, hi = g[f"ic_{nome}_min"][ok], g[f"ic_{nome}_max"][ok]
                lin["cobertura_IC"] = ((rr_ >= lo) & (rr_ <= hi)).mean()
                lin["cobertura_IC_teo"] = ((rr_ >= g[f"ic_{nome}_teo_min"][ok]) & (rr_ <= g[f"ic_{nome}_teo_max"][ok])).mean()
                lin["largura_IC_bps"] = (np.expm1(hi) - np.expm1(lo)).mean() * 1e4
            linhas.append(lin)
    return pd.DataFrame(linhas)


# Prévia
def precos_ao_vivo(colunas: list[str]) -> tuple[pd.Series, pd.Timestamp]:
    tick = [FATORES[c] for c in colunas if c in FATORES]
    df = _yf().download(tick, period="5d", interval="1m", progress=False, threads=True)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(tick[0])
    df = df.rename(columns={v: k for k, v in FATORES.items()}).dropna(how="all")
    if df.empty:
        raise RuntimeError("Yahoo não devolveu cotações (sem internet ou serviço fora)")
    return df.ffill().iloc[-1], df.index[-1]


def fechamento_anterior(px: pd.DataFrame, hoje=None) -> pd.Timestamp:
    hoje = pd.Timestamp(hoje or hoje_br()).normalize()
    idx = px.dropna(how="all").index
    ant = idx[idx < hoje]
    return ant[-1] if len(ant) else idx[-1]


def movimento_fatores(px: pd.DataFrame, agora: pd.Series, d0: pd.Timestamp) -> pd.Series:
    vis = fatores_visiveis(px.columns)
    m = (_transformar(agora.reindex(vis).to_frame().T).iloc[0] - _transformar(px[vis]).ffill().loc[:d0].iloc[-1])
    return pd.Series({c: (np.expm1(v) if not c.startswith("TX_") else v) for c, v in m.items()})


def _meia_largura(b: pd.DataFrame, mov_dia: pd.Series, x_acum: pd.DataFrame, nd: pd.Series):
    """Meia-largura do IC (log). Dia: t·σ·√(1+1/n+q'Vq). Acumulado em nd dias: t·σ·√(nd+nd²/n+q'Vq)."""
    pos = {c: i for i, c in enumerate(x_acum.columns)}
    xd = mov_dia.reindex(x_acum.columns).fillna(0).to_numpy()
    xa = x_acum.fillna(0).to_numpy()
    ndv = nd.to_numpy(dtype=float)
    fats, ns, sigs, Vs, mxs = b["fatores"].to_numpy(), b["n"].to_numpy(), b["sig"].to_numpy(), b["V"].to_numpy(), b["mx"].to_numpy()
    qd, qa, gl = np.full(len(b), np.nan), np.full(len(b), np.nan), np.full(len(b), np.nan)
    for i in range(len(b)):
        fat = fats[i]
        if not isinstance(fat, (list, np.ndarray)) or not np.isfinite(sigs[i]):
            continue
        idx = [pos[f] for f in fat]
        k, n = len(idx), ns[i]
        V = np.asarray(Vs[i], dtype=float).reshape(k, k)
        mx = np.asarray(mxs[i], dtype=float)
        q = xd[idx] - mx
        m = ndv[i]
        u = xa[i, idx] - m * mx
        qd[i] = 1 + 1 / n + q @ V @ q
        qa[i] = m + m * m / n + u @ V @ u
        gl[i] = n - k - 1
    t = np.where(np.isfinite(gl), _t_quantil(np.nan_to_num(gl, nan=1)), np.nan)
    return (pd.Series(t * sigs.astype(float) * np.sqrt(qd), index=b.index),
            pd.Series(t * sigs.astype(float) * np.sqrt(qa), index=b.index))


def calcular_previa(univ, cot, bet, px, cdi, agora: pd.Series, hoje=None, com_alfa: bool = False,
                    cal: pd.DataFrame | None = None) -> pd.DataFrame:
    """Prévia do dia por fundo e janela (e combinada), com IC calibrado; cota estimada encadeada."""
    hoje = pd.Timestamp(hoje or hoje_br())
    L = _transformar(px).ffill()
    agora = completar_agora(px, agora.reindex(px.columns).fillna(px.ffill().iloc[-1]), fechamento_anterior(px, hoje))
    agora_t = _transformar(agora.to_frame().T).iloc[0]
    cdi_dia = np.log1p(cdi.dropna().iloc[-1] / 100)
    base = cot.sort_values("data").groupby("chave").tail(1).set_index("chave")
    df = univ.set_index("chave").join(base.rename(columns={"data": "data_base", "cota": "cota_base"}))

    def mov_desde(d0):
        nivel0 = L.loc[:d0].iloc[-1] if (L.index <= d0).any() else L.iloc[0]
        return (agora_t - nivel0).reindex(L.columns)

    d_ant = fechamento_anterior(px, hoje)
    mov_dia = mov_desde(d_ant)
    movs = {pd.Timestamp(d): mov_desde(pd.Timestamp(d)) for d in df["data_base"].dropna().unique()}
    dias = {d: max(int(np.busday_count(d.date() + pd.Timedelta(days=1), hoje.date() + pd.Timedelta(days=1))), 1)
            for d in movs}
    bcols = [c for c in bet if c.startswith("b_")]
    fcols = [c[2:] for c in bcols]
    x_dia = mov_dia.reindex(fcols).fillna(0).to_numpy()
    x_acum = pd.DataFrame([movs[pd.Timestamp(d)] if pd.notna(d) else pd.Series(dtype=float)
                           for d in df["data_base"]], index=df.index).reindex(columns=fcols)
    nd = df["data_base"].map(dias).fillna(1)
    cal = (cal if cal is not None else pd.DataFrame()).reindex(df.index)
    k_de = lambda j: cal[f"k_{j}"].fillna(1.0) if f"k_{j}" in cal else 1.0
    LD, LA, MD, MA, R2, TE = {}, {}, {}, {}, {}, {}

    for jan in MODELOS:
        b = bet[bet["janela"] == jan].set_index("chave").reindex(df.index)
        bb = b[bcols]
        tem = bb.notna().any(axis=1)
        B = bb.fillna(0).to_numpy()
        alfa = b["alfa"].fillna(0) if com_alfa else 0.0
        log_dia = pd.Series(cdi_dia + B @ x_dia, index=df.index) + alfa
        log_acum = nd * cdi_dia + (B * x_acum.fillna(0).to_numpy()).sum(1) + nd * alfa
        md, ma = _meia_largura(b, mov_dia, x_acum, nd)
        LD[jan], LA[jan] = log_dia.where(tem), log_acum.where(tem)
        MD[jan], MA[jan], R2[jan], TE[jan] = md, ma, b["r2"], b["te"]
        md, ma = md * k_de(jan), ma * k_de(jan)
        df[f"previa_{jan}"] = np.expm1(log_dia).where(tem)
        df[f"previa_{jan}_min"] = np.expm1(log_dia - md).where(tem)
        df[f"previa_{jan}_max"] = np.expm1(log_dia + md).where(tem)
        df[f"cota_est_{jan}"] = (df["cota_base"] * np.exp(log_acum)).where(tem)
        df[f"cota_est_{jan}_min"] = (df["cota_base"] * np.exp(log_acum - ma)).where(tem)
        df[f"cota_est_{jan}_max"] = (df["cota_base"] * np.exp(log_acum + ma)).where(tem)
        df[f"r2_{jan}"] = b["r2"]
        df[f"te_{jan}"] = b["te"]

    LD, LA, MD, MA, R2, TE = (pd.DataFrame(x) for x in (LD, LA, MD, MA, R2, TE))
    if all(f"w_{j}" in cal for j in MODELOS):
        W = pd.DataFrame({j: cal[f"w_{j}"] for j in MODELOS})
    else:
        W = pd.DataFrame(1.0, index=df.index, columns=list(MODELOS))
    W = W.where(LD.notna(), 0).fillna(0)
    W = W.div(W.sum(axis=1).replace(0, np.nan), axis=0)
    soma = lambda X: (X.fillna(0) * W).sum(axis=1).where(W.sum(axis=1) > 0)
    lc, la, mdc, mac = soma(LD), soma(LA), soma(MD) * k_de("comb"), soma(MA) * k_de("comb")
    df["previa_comb"] = np.expm1(lc)
    df["previa_comb_min"], df["previa_comb_max"] = np.expm1(lc - mdc), np.expm1(lc + mdc)
    df["cota_est_comb"] = df["cota_base"] * np.exp(la)
    df["cota_est_comb_min"], df["cota_est_comb_max"] = df["cota_base"] * np.exp(la - mac), df["cota_base"] * np.exp(la + mac)
    df["r2_comb"], df["te_comb"] = soma(R2), soma(TE)
    for j in MODELOS:
        df[f"peso_{j}"] = W[j]
    p = df[[f"previa_{j}" for j in MODELOS]]
    df["amplitude_janelas"] = p.max(axis=1) - p.min(axis=1)
    df["dias_desde_base"] = df["data_base"].map(dias)
    df["ref_dia"] = d_ant
    return df.reset_index()


# Rentabilidade acumulada (cota CVM)
JANELAS_ACUM = ["Dia", "Semana", "Mês", "1M", "3M", "6M", "Ano", "12M", "24M", "36M"]
TOLERANCIA_INICIO = 10   # dias: aceita a primeira cota disponível se ela estiver até 10 dias depois do início ideal


def _alvo(ref: pd.Timestamp, janela: str) -> pd.Timestamp:
    """Data-base da janela: o retorno é medido da última cota até essa data (inclusive) até a cota de ref."""
    if janela == "Semana":
        return ref - pd.Timedelta(days=7)
    if janela == "Mês":
        return ref.replace(day=1) - pd.Timedelta(days=1)
    if janela == "Ano":
        return ref.replace(month=1, day=1) - pd.Timedelta(days=1)
    meses = {"1M": 1, "3M": 3, "6M": 6, "12M": 12, "24M": 24, "36M": 36}[janela]
    return ref - pd.DateOffset(months=meses)


def retornos_acumulados(cot: pd.DataFrame, cdi: pd.Series) -> pd.DataFrame:
    """Por fundo, retorno acumulado pela cota CVM em cada janela de JANELAS_ACUM, CDI do mesmo período,
    % do CDI e a data-base usada. Colunas: r_<janela>, cdi_<janela>, pcdi_<janela>, base_<janela>."""
    c = cot.sort_values(["chave", "data"])
    P = c.pivot(index="data", columns="chave", values="cota").sort_index()
    D = pd.DataFrame(np.where(P.notna(), P.index.values[:, None], np.datetime64("NaT")),
                     index=P.index, columns=P.columns).ffill()
    Pf = P.ffill()
    primeiro = P.apply(lambda s: s.first_valid_index())
    ult = c.groupby("chave").tail(1).set_index("chave")
    ant = c.groupby("chave").nth(-2).set_index("chave")
    cc = np.log1p(cdi.dropna() / 100).cumsum()
    acum_cdi = lambda d0, d1: np.exp(cc.asof(d1) - cc.asof(d0)) - 1 if pd.notna(d0) and pd.notna(d1) else np.nan

    out = pd.DataFrame(index=ult.index)
    out["cota_ult"], out["data_ult"] = ult["cota"], ult["data"]
    out["base_Dia"] = ant["data"].reindex(out.index)
    out["r_Dia"] = ult["cota"] / ant["cota"].reindex(out.index) - 1
    for jan in JANELAS_ACUM[1:]:
        r, bd = pd.Series(np.nan, index=out.index), pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns]")
        for ref, chaves in out.groupby("data_ult").groups.items():
            alvo = _alvo(pd.Timestamp(ref), jan)
            ok_idx = P.index[P.index <= alvo]
            ch = list(chaves)
            if len(ok_idx):
                v0, d0 = Pf.loc[ok_idx[-1], ch], D.loc[ok_idx[-1], ch]
            else:
                v0, d0 = pd.Series(np.nan, index=ch), pd.Series(pd.NaT, index=ch)
            sem = v0.isna()
            if sem.any():   # história começa depois do alvo: aceita se estiver dentro da tolerância
                ini = primeiro[ch][sem]
                perto = (ini - alvo) <= pd.Timedelta(days=TOLERANCIA_INICIO)
                for k in ini[perto].index:
                    v0[k], d0[k] = P.loc[ini[k], k], ini[k]
            r[ch] = out.loc[ch, "cota_ult"] / v0 - 1
            bd[ch] = pd.to_datetime(d0)
        out[f"r_{jan}"], out[f"base_{jan}"] = r, bd
    for jan in JANELAS_ACUM:
        out[f"cdi_{jan}"] = [acum_cdi(b, d) for b, d in zip(out[f"base_{jan}"], out["data_ult"])]
        out[f"pcdi_{jan}"] = out[f"r_{jan}"] / out[f"cdi_{jan}"]
    return out


def com_previa(acum: pd.DataFrame, prev: pd.DataFrame, jan: str = "comb") -> pd.DataFrame:
    """Encadeia ao acumulado CVM o retorno estimado desde a última cota até hoje (cota estimada / última cota)."""
    p = prev.set_index("chave")
    fator = (p[f"cota_est_{jan}"] / p["cota_base"]).reindex(acum.index)
    return pd.DataFrame({f"rp_{k}": (1 + acum[f"r_{k}"]) * fator - 1 for k in JANELAS_ACUM if k != "Dia"},
                        index=acum.index)


# Persistência
def salvar_base(univ, cot):
    univ.to_parquet(DADOS / "universo.parquet", index=False)
    cot.to_parquet(DADOS / "cotas.parquet", index=False)


def carregar_base():
    return (pd.read_parquet(DADOS / "universo.parquet"), pd.read_parquet(DADOS / "cotas.parquet"),
            pd.read_parquet(DADOS / "betas.parquet"))


def carregar_calibracao() -> pd.DataFrame | None:
    p = DADOS / "calibracao.parquet"
    return pd.read_parquet(p) if p.exists() else None


def ordenar_estrategias(presentes) -> list[str]:
    presentes = set(presentes)
    base = ["Todas"] + ORDEM_ESTRATEGIAS
    return [e for e in base if e in presentes] + sorted(presentes - set(base))


def rot(j: str) -> str:
    return {"comb": "combinada", "ew": "EW"}.get(j, j)


def todas_janelas() -> list[str]:
    return ["comb"] + list(MODELOS)


# API
_CACHE: dict = {}
_ARQS = ["universo.parquet", "cotas.parquet", "fatores.parquet", "cdi.parquet", "betas.parquet"]


def _sem_acento(s):
    import unicodedata
    f = lambda t: "".join(c for c in unicodedata.normalize("NFKD", str(t)) if not unicodedata.combining(c)).upper()
    return s.map(f) if isinstance(s, pd.Series) else f(s)


def _contem(serie: pd.Series, texto: str) -> pd.Series:
    return _sem_acento(serie.fillna("")).str.contains(_sem_acento(texto), regex=False)


def _base_ok(precisa_betas: bool = True) -> bool:
    falta = [n for n in _ARQS if not (DADOS / n).exists() and (precisa_betas or n != "betas.parquet")]
    if not falta:
        return True
    passo = "pv.estimar()" if falta == ["betas.parquet"] else "pv.atualizar()"
    print(f"Faltam arquivos em {DADOS}: {', '.join(falta)}. Rode primeiro: {passo}")
    return False


def _dados():
    chave = tuple((DADOS / n).stat().st_mtime for n in _ARQS)
    if _CACHE.get("chave") != chave:
        univ, cot, bet = carregar_base()
        ndias = cot["data"].nunique()
        falta = [j for j in MODELOS if j not in set(bet["janela"]) and MIN_OBS.get(j, MIN_OBS_EW) <= ndias]
        if falta:
            print(f"Betas sem as janelas {falta}. Rode pv.estimar() para recalcular.")
        px, cdi = carregar_fatores()
        cal = carregar_calibracao()
        if cal is None:
            print("Sem calibração: rode pv.estimar() para ativar a combinada e o IC calibrado.")
        _CACHE.update(chave=chave, univ=univ, cot=cot, bet=bet, px=px, cdi=cdi, cal=cal)
    return _CACHE["univ"], _CACHE["cot"], _CACHE["bet"], _CACHE["px"], _CACHE["cdi"]


def _no_jupyter() -> bool:
    try:
        from IPython import get_ipython
        ip = get_ipython()
        return ip is not None and "IPKernelApp" in ip.config
    except ImportError:
        return False


def _mostrar(df: pd.DataFrame, titulo: str | None = None, pct=(), pm=(), porc=(), bps=(), dec=(),
             mi=(), datas=(), cota=()):
    br = lambda v: f"{v:,.0f}".replace(",", ".")
    fmt = {**{c: "{:+.2%}" for c in pct}, **{c: "±{:.2%}" for c in pm}, **{c: "{:.0%}" for c in porc},
           **{c: "{:.1f}" for c in bps}, **{c: "{:.2f}" for c in dec}, **{c: br for c in mi},
           **{c: "{:%d/%m/%Y}" for c in datas}, **{c: "{:.6f}" for c in cota}}
    fmt = {c: f for c, f in fmt.items() if c in df}
    if _no_jupyter():
        from IPython.display import Markdown, display
        if titulo:
            display(Markdown(f"**{titulo}**"))
        sty = df.style.format(fmt, na_rep="–").hide(axis="index")
        cor = [c for c in pct if c in df]
        if cor:
            sty = sty.map(lambda v: "color:#1a7f37" if pd.notna(v) and v > 0 else
                          ("color:#cf222e" if pd.notna(v) and v < 0 else ""), subset=cor)
        display(sty)
        return
    out = df.copy()
    for c, f in fmt.items():
        out[c] = out[c].map(lambda v, f=f: (f(v) if callable(f) else f.format(v)) if pd.notna(v) else "–")
    if titulo:
        print(f"\n{titulo}")
    with pd.option_context("display.max_colwidth", 60, "display.width", 250):
        print(out.to_string(index=False))


def _confianca(r2: pd.Series) -> pd.Series:
    return pd.cut(r2, [-np.inf, 0.4, 0.7, np.inf], labels=["baixa", "média", "alta"]).astype(str).replace("nan", "–")


def _rotulo(r) -> str:
    return r["Nome"] + (f" · {r['Subclasse']}" if r.get("Subclasse") else "")


def atualizar(forcar: bool = False):
    """Baixa CVM (36 meses de informes e cadastro), fatores no Yahoo e CDI no Banco Central."""
    DADOS.mkdir(exist_ok=True)
    meses = _meses(MESES_HISTORICO)
    _log(f"Informes da CVM: {meses[0]} a {meses[-1]} ({len(meses)} meses)")

    def um(i_ym):
        i, ym = i_ym
        try:
            return ym, baixar(URL_INFORME.format(ym=ym), CVM_DIR / f"inf_diario_fi_{ym}.zip",
                              forcar=forcar or i >= len(meses) - 2)
        except Exception as e:
            return ym, e

    falhas = []
    with ThreadPoolExecutor(DOWNLOADS_PARALELOS) as ex:
        for ym, ok in ex.map(um, enumerate(meses)):
            if isinstance(ok, Exception):
                falhas.append(ym)
                _log(f"Informe {ym}: falhou ({ok})")
            else:
                _log(f"Informe {ym}: {'ok' if ok else 'não publicado'}")
    for z in CVM_DIR.glob("inf_diario_fi_*.zip"):
        if z.stem[-6:] not in meses:
            z.unlink()
    if falhas:
        _log(f"Aviso: {len(falhas)} mês(es) sem download ({', '.join(falhas)}). Rode pv.atualizar() de novo.")
    baixar(URL_REGISTRO, DADOS / "registro_fundo_classe.zip", forcar=True)
    baixar(URL_CAD_FI, DADOS / "cad_fi.csv", forcar=True)
    univ, cot = montar_universo()
    salvar_base(univ, cot)
    ini = cot["data"].min()
    baixar_fatores(ini).to_parquet(DADOS / "fatores.parquet")
    baixar_cdi(ini).to_frame().to_parquet(DADOS / "cdi.parquet")
    _log("Base atualizada. Próximo passo: pv.estimar()")


def estimar():
    """Estima os βs de cada fundo em todas as janelas."""
    if not _base_ok(precisa_betas=False):
        return
    univ = pd.read_parquet(DADOS / "universo.parquet")
    cot = pd.read_parquet(DADOS / "cotas.parquet")
    px, cdi = carregar_fatores()
    bet = _estimar_betas(univ, cot, px, cdi)
    bet.to_parquet(DADOS / "betas.parquet", index=False)
    _log("Calibrando pesos da combinada e o IC pelo erro fora da amostra...")
    cal = calibracao(_backtest_fundos(univ, cot, px, cdi))
    cal.to_parquet(DADOS / "calibracao.parquet")
    r = (bet.merge(univ[["chave", "Estrategia"]], on="chave")
         .pivot_table(index="Estrategia", columns="janela", values="r2", aggfunc="median")
         .reindex(columns=_janelas()))
    r.columns = [f"R² {j}" for j in r.columns]
    cw = cal.join(univ.set_index("chave")["Estrategia"]).groupby("Estrategia")
    for j in MODELOS:
        r[f"Peso {j}"] = cw[f"w_{j}"].mean().reindex(r.index) if f"w_{j}" in cal else np.nan
    r["Fator IC"] = cw["k_comb"].median().reindex(r.index)
    r = r.rename_axis("Estratégia").reset_index()
    _mostrar(r, "R² mediano, peso médio de cada janela na combinada e fator de calibração do IC",
             dec=[c for c in r if c.startswith(("R²", "Fator"))], porc=[c for c in r if c.startswith("Peso")])


def previa(estrategia=None, gestor: str | None = None, busca: str | None = None, com_alfa: bool = False,
           so_confiaveis: bool = False, top: int | None = None, retornar: bool = False, mostrar: bool = True):
    """Prévia do dia (retorno só de hoje): combinada e por janela, com IC calibrado da janela principal."""
    if not _base_ok():
        return None
    univ, cot, bet, px, cdi = _dados()
    try:
        agora, ts = precos_ao_vivo(list(px.columns))
        origem = f"preços do Yahoo até {ts:%d/%m %H:%M}"
    except Exception as e:
        agora, origem = px.ffill().iloc[-1], f"sem preço ao vivo ({e}); usando o último fechamento"
    agora = agora.reindex(px.columns).fillna(px.ffill().iloc[-1])
    df = calcular_previa(univ, cot, bet, px, cdi, agora, com_alfa=com_alfa, cal=_CACHE.get("cal"))
    jp, jr = JANELA_PRINCIPAL, rot(JANELA_PRINCIPAL)
    js = todas_janelas()

    if estrategia:
        df = df[df["Estrategia"].isin([estrategia] if isinstance(estrategia, str) else estrategia)]
    if gestor:
        df = df[_contem(df["Gestor"], gestor)]
    if busca:
        df = df[_contem(df["Nome"], busca) | df["CNPJ"].str.contains(busca, regex=False)]
    if so_confiaveis:
        df = df[df[f"r2_{jp}"] >= 0.7]
    if not mostrar:
        return df if retornar else None

    d0 = fechamento_anterior(px)
    mov = movimento_fatores(px, agora, d0)
    print(f"Prévia diária de {hoje_br():%d/%m/%Y} · {origem}")
    print(f"Fatores no dia (desde {d0:%d/%m}): "
          + " | ".join(f"{k} {v:+.2%}" if not k.startswith("TX_") else f"{k} {v:+.2f}pp" for k, v in mov.items()))

    res = df.groupby("Estrategia").agg(Fundos=("chave", "size"),
                                       **{f"Prévia {rot(j)}": (f"previa_{j}", "median") for j in js})
    res[f"± IC {jr}"] = ((df[f"previa_{jp}_max"] - df[f"previa_{jp}_min"]) / 2).groupby(df["Estrategia"]).median()
    res = res.rename_axis("Estratégia").reset_index()
    _mostrar(res, "Mediana por estratégia", pct=[f"Prévia {rot(j)}" for j in js], pm=[f"± IC {jr}"])

    tab = pd.DataFrame({"Fundo": df.apply(_rotulo, axis=1).str.slice(0, 70), "Estratégia": df["Estrategia"],
                        "Gestor": df["Gestor"].str.slice(0, 35), "PL (R$ mi)": df["pl"] / 1e6,
                        "Última cota": df["data_base"]})
    for j in js:
        tab[f"Prévia {rot(j)}"] = df[f"previa_{j}"]
    tab[f"Mín {IC_NIVEL:.0%} {jr}"] = df[f"previa_{jp}_min"]
    tab[f"Máx {IC_NIVEL:.0%} {jr}"] = df[f"previa_{jp}_max"]
    tab["Amplitude janelas"] = df["amplitude_janelas"]
    tab["Confiança"] = _confianca(df[f"r2_{jp}"])
    tab["Cota estimada"] = df[f"cota_est_{jp}"]
    tab["CNPJ"] = df["CNPJ"]
    tab = tab.sort_values(f"Prévia {jr}", ascending=False)
    pcts = [c for c in tab if c.startswith(("Prévia", "Mín", "Máx", "Amplitude"))]
    _mostrar(tab.head(top) if top else tab, f"Fundos ({len(tab)})" + (f", top {top}" if top else ""),
             pct=pcts, mi=["PL (R$ mi)"], datas=["Última cota"], cota=["Cota estimada"])
    print(f"Combinada = média dos modelos {', '.join(MODELOS)} ponderada pelo inverso do erro dos últimos "
          f"{CALIB_DIAS} dias. Mín/Máx = IC {IC_NIVEL:.0%} bicaudal calibrado pelos erros do próprio fundo. "
          f"Confiança = R² ponderado: alta ≥ 0,7, média 0,4–0,7, baixa < 0,4.")
    atras = (df["data_base"] < d0).sum()
    if atras:
        print(f"{atras} fundo(s) com última cota anterior a {d0:%d/%m}: a prévia é só de hoje; "
              "a cota estimada inclui os dias sem cota divulgada.")
    return df if retornar else None


def buscar(texto: str):
    """Procura fundos do universo por parte do nome, gestor ou CNPJ."""
    if not _base_ok():
        return
    univ = _dados()[0]
    r = univ[_contem(univ["Nome"], texto) | _contem(univ["Gestor"], texto)
             | univ["CNPJ"].str.contains(texto, regex=False)].sort_values("pl", ascending=False)
    if r.empty:
        print(f"Nenhum fundo do universo contém '{texto}'.")
        return
    _mostrar(pd.DataFrame({"Fundo": r["Nome"].str.slice(0, 70), "Subclasse": r["Subclasse"], "CNPJ": r["CNPJ"],
                           "Estratégia": r["Estrategia"], "Gestor": r["Gestor"].str.slice(0, 35),
                           "PL (R$ mi)": r["pl"] / 1e6}),
             f"{len(r)} fundo(s) encontrados", mi=["PL (R$ mi)"])


def detalhe(texto: str, dias: int = 63, janela: str | None = None):
    """βs por janela e gráfico real × prévia fora da amostra, com IC."""
    if not _base_ok():
        return
    univ, cot, bet, px, cdi = _dados()
    jan = janela or JANELA_PRINCIPAL
    cand = univ[_contem(univ["Nome"], texto) | univ["CNPJ"].str.contains(texto, regex=False)]
    if cand.empty:
        print(f"Nenhum fundo contém '{texto}'. Use pv.buscar().")
        return
    cand = cand.sort_values("pl", ascending=False)
    f = cand.iloc[0]
    if len(cand) > 1:
        print(f"{len(cand)} fundos contêm '{texto}'; mostrando o de maior PL.")
    print(f"\n{_rotulo(f)}\n{f['CNPJ']} · {f['Estrategia']} ({f['Classe_ANBIMA']}) · {f['Gestor']} · "
          f"PL R$ {f['pl']/1e6:,.0f} mi".replace(",", "."))
    b = bet[bet["chave"] == f["chave"]].set_index("janela").reindex([j for j in MODELOS])
    b = b[b["r2"].notna()]
    if b.empty:
        print("Sem histórico suficiente para estimar.")
        return
    bcols = [c for c in b if c.startswith("b_") and b[c].notna().any()]
    tb = b[bcols].T
    tb.columns = [f"β {j}" for j in tb.columns]
    tb.insert(0, "Fator", [c[2:] for c in bcols])
    _mostrar(tb, "Sensibilidades (β)", dec=[c for c in tb if c.startswith("β")])
    q = pd.DataFrame({"Janela": b.index, "Obs.": b["n"].astype(int).values, "R²": b["r2"].values,
                      "Erro anual": b["te"].values, "Confiança": _confianca(b["r2"]).values})
    _mostrar(q, "Qualidade do ajuste", dec=["R²"], porc=["Erro anual"])

    bt = _backtest_fundos(univ[univ["chave"] == f["chave"]], cot, px, cdi).tail(dias)
    if bt.empty:
        return
    g = bt.set_index("data")
    real, prev = np.expm1(g["real"]) * 100, np.expm1(g[f"prev_{jan}"]) * 100
    lo, hi = np.expm1(g[f"ic_{jan}_min"]) * 100, np.expm1(g[f"ic_{jan}_max"]) * 100
    dentro = ((g["real"] >= g[f"ic_{jan}_min"]) & (g["real"] <= g[f"ic_{jan}_max"])).mean()
    erros = {rot(j): ((np.expm1(g["real"]) - np.expm1(g[f"prev_{j}"])).abs().mean() * 1e4) for j in todas_janelas()}
    pesos = g[[f"w_{j}" for j in MODELOS]].iloc[-1]
    print(f"Últimos {len(g)} dias, fora da amostra. Erro médio (bps): "
          + ", ".join(f"{j} {e:.0f}" for j, e in erros.items())
          + f". Cota real dentro do IC {IC_NIVEL:.0%} ({rot(jan)}) em {dentro:.0%} dos dias. "
          + "Pesos atuais da combinada: " + ", ".join(f"{j} {pesos[f'w_{j}']:.0%}" for j in MODELOS) + ".")
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(1, 2, figsize=(12, 3.8), gridspec_kw={"width_ratios": [2, 1]})
    xi = np.arange(len(g))
    ax[0].bar(xi - 0.2, real, width=0.4, color="#222", label="Real")
    ax[0].bar(xi + 0.2, prev, width=0.4, color="#1f6feb", label=f"Prévia {rot(jan)}")
    ax[0].errorbar(xi + 0.2, prev, yerr=[prev - lo, hi - prev], fmt="none", ecolor="#1f6feb",
                   alpha=.45, lw=1, capsize=1.5, label=f"IC {IC_NIVEL:.0%}")
    passo = max(len(g) // 8, 1)
    ax[0].set_xticks(xi[::passo], [d.strftime("%d/%m") for d in g.index[::passo]])
    ax[0].axhline(0, color="#999", lw=.8)
    ax[0].set_title("Retorno diário (%): real × prévia fora da amostra")
    ax[0].legend()
    ax[0].grid(axis="y", alpha=.3)
    ax[1].scatter(prev, real, s=12, color="#1f6feb")
    lim = np.nanmax(np.abs(np.r_[real.to_numpy(), prev.to_numpy()])) * 1.1
    ax[1].plot([-lim, lim], [-lim, lim], color="#999", lw=1)
    ax[1].set_xlabel(f"Prévia {rot(jan)} (%)")
    ax[1].set_ylabel("Real (%)")
    ax[1].grid(alpha=.3)
    plt.tight_layout()
    plt.show()


def backtest(desde: str | None = None, grafico: bool = True, retornar: bool = False):
    """Prévia fora da amostra × cota real: erro e cobertura do IC por estratégia e janela."""
    if not _base_ok():
        return None
    univ, cot, _, px, cdi = _dados()
    bt = _backtest_fundos(univ, cot, px, cdi)
    if desde:
        bt = bt[bt["data"] >= pd.Timestamp(desde)]
    ok = bt[bt["usada_estim"]]
    print(f"Backtest fora da amostra: {ok['chave'].nunique():,} fundos, {len(ok):,} fundo-dias, "
          f"{ok['data'].min():%d/%m/%Y} a {ok['data'].max():%d/%m/%Y}"
          + (f" (sem {', '.join(DATAS_EXCLUIR)})" if DATAS_EXCLUIR else ""))
    r = resumir_backtest(ok)
    ordem = ordenar_estrategias(set(r["Estrategia"]))
    js = todas_janelas()
    modelos = js + ["média", "só CDI"]
    erro = r.pivot(index="Estrategia", columns="Modelo", values="MAE_bps").reindex(ordem)[modelos]
    melhor = erro[js + ["média"]].idxmin(axis=1).map(rot)
    tab = erro.copy()
    tab.columns = [f"Erro {rot(m)}" for m in modelos]
    tab["Melhor"] = melhor
    tab["Melhora vs CDI"] = 1 - erro["comb"] / erro["só CDI"]
    tab = tab.rename_axis("Estratégia").reset_index()
    _mostrar(tab, "Erro médio absoluto da prévia diária (bps; 1 bp = 0,01%)",
             bps=[c for c in tab if c.startswith("Erro")], porc=["Melhora vs CDI"])

    pv_ = lambda campo: (r[r["Modelo"].isin(js)].pivot(index="Estrategia", columns="Modelo", values=campo)
                         .reindex(ordem)[js].rename(columns=rot))
    t2 = pd.concat([pv_("cobertura_IC_teo").add_prefix("Teórica "), pv_("cobertura_IC").add_prefix("Calibrada "),
                    pv_("largura_IC_bps").add_prefix("Largura "), pv_("acerto_sinal").add_prefix("Sinal ")], axis=1)
    t2 = t2.rename_axis("Estratégia").reset_index()
    _mostrar(t2, f"IC {IC_NIVEL:.0%}: cobertura teórica e calibrada (ideal ≈ {IC_NIVEL:.0%}), "
                 "largura média do calibrado (bps) e acerto de sinal",
             porc=[c for c in t2 if c.startswith(("Teórica", "Calibrada", "Sinal"))],
             bps=[c for c in t2 if c.startswith("Largura")])

    jp = JANELA_PRINCIPAL
    e = (np.expm1(ok["real"]) - np.expm1(ok[f"prev_{jp}"])).abs() * 1e4
    jp = rot(jp)
    pf = (ok.assign(err=e).groupby("chave")["err"].mean().rename(f"Erro {jp} (bps)").reset_index()
          .merge(univ[["chave", "Nome", "Estrategia", "Gestor"]], on="chave"))
    pior = pf.sort_values(f"Erro {jp} (bps)", ascending=False).head(10)
    _mostrar(pd.DataFrame({"Fundo": pior["Nome"].str.slice(0, 60), "Estratégia": pior["Estrategia"],
                           "Gestor": pior["Gestor"].str.slice(0, 30), f"Erro {jp} (bps)": pior[f"Erro {jp} (bps)"]}),
             "10 fundos com maior erro", bps=[f"Erro {jp} (bps)"])

    if grafico:
        try:
            import matplotlib.pyplot as plt
            ax = erro.rename(columns=rot).plot.bar(figsize=(11, 3.8), rot=0, width=.8)
            ax.set_ylabel("Erro médio (bps)")
            ax.set_xlabel("")
            ax.set_title("Erro da prévia diária por estratégia e janela (menor é melhor)")
            ax.grid(axis="y", alpha=.3)
            plt.tight_layout()
            plt.show()
        except ImportError:
            pass
    r.to_csv(DADOS / "backtest_resumo.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
    pf.sort_values(f"Erro {jp} (bps)").to_csv(DADOS / "backtest_por_fundo.csv", sep=";", decimal=",",
                                              index=False, encoding="utf-8-sig")
    print(f"Salvo em {DADOS / 'backtest_resumo.csv'} e backtest_por_fundo.csv")
    return bt if retornar else None


def consolidado(com_backtest: bool = True, com_alfa: bool = False, salvar: str | None = None,
                mostrar: bool = True) -> pd.DataFrame | None:
    """Uma linha por fundo: cadastro, prévias e ICs, cotas estimadas, βs/R² por janela e backtest.
    salvar: ".xlsx" (formatado) ou ".csv"; caminho relativo vai para a pasta dados."""
    if not _base_ok():
        return None
    univ, cot, bet, px, cdi = _dados()
    df = previa(com_alfa=com_alfa, retornar=True, mostrar=False)
    out = pd.DataFrame({
        "Fundo": df["Nome"], "Subclasse": df["Subclasse"], "CNPJ": df["CNPJ"], "ID Subclasse": df["SUB"],
        "Estratégia": df["Estrategia"], "Classe ANBIMA": df["Classe_ANBIMA"], "Gestor": df["Gestor"],
        "Administrador": df["Administrador"], "PL (R$ mi)": df["pl"] / 1e6,
        "Data última cota": df["data_base"], "Última cota": df["cota_base"],
        "Base do dia": df["ref_dia"], "Dias encadeados": df["dias_desde_base"],
    })
    out.index = df["chave"].values
    js = todas_janelas()
    for j in js:
        out[f"Prévia {rot(j)}"] = df[f"previa_{j}"].values
        out[f"Prévia mín {rot(j)}"] = df[f"previa_{j}_min"].values
        out[f"Prévia máx {rot(j)}"] = df[f"previa_{j}_max"].values
    out["Amplitude janelas"] = df["amplitude_janelas"].values
    for j in MODELOS:
        out[f"Peso {j}"] = df[f"peso_{j}"].values
    for j in js:
        out[f"Cota estimada {rot(j)}"] = df[f"cota_est_{j}"].values
        out[f"Cota mín {rot(j)}"] = df[f"cota_est_{j}_min"].values
        out[f"Cota máx {rot(j)}"] = df[f"cota_est_{j}_max"].values
    out["R² combinado"] = df["r2_comb"].values
    out["Confiança"] = _confianca(df[f"r2_{JANELA_PRINCIPAL}"]).values
    acum = retornos_acumulados(cot, cdi)
    acp = com_previa(acum, df)
    for k in JANELAS_ACUM:
        out[f"Retorno {k}"] = acum[f"r_{k}"].reindex(out.index).values
    for k in ("Mês", "Ano", "12M"):
        out[f"CDI {k}"] = acum[f"cdi_{k}"].reindex(out.index).values
        out[f"% CDI {k}"] = acum[f"pcdi_{k}"].reindex(out.index).values
    for k in ("Mês", "Ano", "12M"):
        out[f"Retorno {k} c/ prévia"] = acp[f"rp_{k}"].reindex(out.index).values
    out["Início 12M"] = acum["base_12M"].reindex(out.index).values

    fats = [c for c in FATORES if f"b_{c}" in bet] + [c[2:] for c in bet if c.startswith("b_TX_")]
    extra = {}
    for j in MODELOS:
        b = bet[bet["janela"] == j].set_index("chave").reindex(out.index)
        extra[f"R² {j}"] = b["r2"]
        extra[f"Erro anual {j}"] = b["te"]
        extra[f"α diário {j}"] = b["alfa"]
        extra[f"Obs. {j}"] = b["n"]
        for fz in fats:
            extra[f"β {fz} {j}"] = b[f"b_{fz}"]
    extra = pd.DataFrame(extra, index=out.index)
    extra = extra.drop(columns=[c for c in extra if c.startswith("β") and extra[c].isna().all()])
    out = pd.concat([out, extra], axis=1)

    if com_backtest:
        bt = _backtest_fundos(univ, cot, px, cdi)
        bt = bt[bt["usada_estim"]]
        real = np.expm1(bt["real"])
        agg = {}
        for j in js:
            e = (real - np.expm1(bt[f"prev_{j}"])).abs() * 1e4
            dentro = ((bt["real"] >= bt[f"ic_{j}_min"]) & (bt["real"] <= bt[f"ic_{j}_max"])).where(bt[f"prev_{j}"].notna())
            agg[f"Erro backtest {rot(j)} (bps)"] = e.groupby(bt["chave"]).mean()
            agg[f"Cobertura IC {rot(j)}"] = dentro.groupby(bt["chave"]).mean()
        agg["Erro só CDI (bps)"] = ((real - np.expm1(bt["cdi"])).abs() * 1e4).groupby(bt["chave"]).mean()
        agg["Dias no backtest"] = bt.groupby("chave").size()
        out = out.join(pd.DataFrame(agg))

    out = out.sort_values(["Estratégia", "PL (R$ mi)"], ascending=[True, False]).reset_index(drop=True)
    if salvar:
        caminho = Path(salvar)
        caminho = caminho if caminho.is_absolute() else DADOS / caminho
        if caminho.suffix.lower() == ".xlsx":
            _salvar_excel(out, caminho)
        else:
            out.to_csv(caminho, sep=";", decimal=",", index=False, encoding="utf-8-sig")
        print(f"Consolidado salvo em {caminho}")
    if mostrar:
        print(f"Consolidado: {len(out)} fundos × {out.shape[1]} colunas.")
    return out


def _salvar_excel(df: pd.DataFrame, caminho: Path) -> None:
    def formato(col):
        if col.startswith(("Prévia", "Amplitude", "Erro anual", "Cobertura", "Peso", "Retorno", "CDI ", "% CDI")):
            return "0.00%"
        if col.startswith(("Cota", "Última cota")):
            return "0.000000"
        if col.startswith(("Data", "Base do dia", "Início")):
            return "dd/mm/yyyy"
        if col.startswith(("β", "R²")):
            return "0.000"
        if col.startswith("α"):
            return "0.0000%"
        if "(bps)" in col or col.startswith("PL"):
            return "#,##0.0"
        return None

    with pd.ExcelWriter(caminho, engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="Consolidado", index=False)
        ws = xw.sheets["Consolidado"]
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions
        for j, col in enumerate(df.columns, start=1):
            letra = ws.cell(row=1, column=j).column_letter
            ws.column_dimensions[letra].width = 55 if col == "Fundo" else max(12, min(len(col) + 2, 30))
            fmt = formato(col)
            if fmt:
                for (cel,) in ws.iter_rows(min_row=2, min_col=j, max_col=j):
                    cel.number_format = fmt


def testar_fatores(por_estrategia: int = 60, semente: int = 1):
    """Compara, fora da amostra, onde usar os fatores adicionais. Usa uma amostra de fundos por estratégia."""
    if not _base_ok():
        return None
    univ, cot, _, px, cdi = _dados()
    amostra = pd.concat([g.sample(min(len(g), por_estrategia), random_state=semente)
                         for _, g in univ.groupby("Estrategia")])
    guardado = (OBS_MIN_ADICIONAIS, RIDGE_ESCALA, dict(FATORES_ADICIONAIS))
    cfg = {"Extras em todos os modelos": (0, guardado[1], True),
           "Extras só com >= 120 obs. (padrão)": (120, guardado[1], True),
           "Sem fatores adicionais": (0, guardado[1], False)}
    res = {}
    g = globals()
    try:
        for nome, (omin, escala, extras) in cfg.items():
            g["OBS_MIN_ADICIONAIS"], g["RIDGE_ESCALA"] = omin, escala
            g["FATORES_ADICIONAIS"] = guardado[2] if extras else {}
            bt = _backtest_fundos(amostra, cot, px, cdi)
            r = resumir_backtest(bt[bt["usada_estim"]])
            r = r[r["Estrategia"] == "Todas"].set_index("Modelo")["MAE_bps"]
            res[nome] = r.reindex(MODELOS + ["comb"])
    finally:
        g["OBS_MIN_ADICIONAIS"], g["RIDGE_ESCALA"], g["FATORES_ADICIONAIS"] = guardado
    t = pd.DataFrame(res).T.rename(columns=rot).rename_axis("Configuração").reset_index()
    _mostrar(t, f"Erro médio fora da amostra (bps), {len(amostra)} fundos", bps=[c for c in t if c != "Configuração"])
    print("Menor é melhor. Para mudar, ajuste OBS_MIN_ADICIONAIS no topo do previa.py e rode pv.estimar().")
    return t


def rodar_tudo():
    atualizar()
    estimar()
    backtest()
    previa(top=30)


# Linha de comando
def main(argv=None):
    p = argparse.ArgumentParser(description="Prévia de cotas por fatores. Sem comando, roda tudo.")
    sp = p.add_subparsers(dest="cmd")
    sp.add_parser("tudo")
    sp.add_parser("atualizar").add_argument("--forcar", action="store_true")
    sp.add_parser("estimar")
    v = sp.add_parser("previa")
    v.add_argument("--com-alfa", action="store_true")
    v.add_argument("--top", type=int, default=30)
    v.add_argument("--csv")
    t = sp.add_parser("backtest")
    t.add_argument("--desde")
    c = sp.add_parser("consolidado")
    c.add_argument("--salvar", default="consolidado.xlsx")
    if argv is None and "ipykernel" in sys.argv[0]:
        argv = []
    a, _ = p.parse_known_args(argv)
    if a.cmd in (None, "tudo"):
        rodar_tudo()
    elif a.cmd == "atualizar":
        atualizar(forcar=a.forcar)
    elif a.cmd == "estimar":
        estimar()
    elif a.cmd == "previa":
        df = previa(com_alfa=a.com_alfa, top=a.top, retornar=bool(a.csv))
        if a.csv and df is not None:
            df.to_csv(a.csv, sep=";", decimal=",", index=False, encoding="utf-8-sig")
    elif a.cmd == "backtest":
        backtest(desde=a.desde, grafico=False)
    elif a.cmd == "consolidado":
        consolidado(salvar=a.salvar)


if __name__ == "__main__":
    main()
