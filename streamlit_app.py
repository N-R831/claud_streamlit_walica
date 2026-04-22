import streamlit as st
import pandas as pd
import requests
from urllib.parse import quote
from datetime import date
 
# ─────────────────────────────────────────
# 設定
# ─────────────────────────────────────────
SHEET_URL      = st.secrets["sheet_url"]
GAS_URL        = st.secrets["gas_url"]
WORKSHEET_NAME = "Walica"
MEMBERS        = ["涼馬", "花帆"]
 
# ─────────────────────────────────────────
# データ読み込み
# ─────────────────────────────────────────
def sheet_id_from_url(url: str) -> str:
    return url.split("/d/")[1].split("/")[0]
 
def build_csv_url(sheet_id: str, sheet_name: str) -> str:
    """
    gviz/tq 方式（シート名をURLエンコード）。
    失敗時のフォールバックとして export 方式も用意。
    """
    encoded = quote(sheet_name)
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/gviz/tq?tqx=out:csv&sheet={encoded}"
    )
 
def build_export_url(sheet_id: str, gid: str = "0") -> str:
    """gid（シートのタブID）を使うexport方式"""
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )
 
@st.cache_data(ttl=30)
def load_data() -> tuple[pd.DataFrame, str]:
    """
    DataFrameとエラーメッセージのタプルを返す。
    エラーなし → ("", df)
    エラーあり → (エラーメッセージ, 空df)
    """
    empty = pd.DataFrame(columns=["date", "member", "kind", "money"])
    sheet_id = sheet_id_from_url(SHEET_URL)
 
    # --- 方式1: gviz/tq（シート名指定）---
    csv_url = build_csv_url(sheet_id, WORKSHEET_NAME)
    try:
        resp = requests.get(csv_url, timeout=10)
        resp.raise_for_status()
 
        from io import StringIO
        df = pd.read_csv(StringIO(resp.text))
 
        # カラム名確認
        if "date" not in df.columns:
            # 方式2: export（gid=0）にフォールバック
            export_url = build_export_url(sheet_id)
            df = pd.read_csv(export_url)
 
        if df.empty or "date" not in df.columns:
            return empty, f"⚠️ 取得できましたがカラムが見つかりません。実際のカラム: {list(df.columns)}"
 
        df["date"]  = pd.to_datetime(df["date"], errors="coerce")
        df["money"] = pd.to_numeric(df["money"], errors="coerce").fillna(0)
        df = df.dropna(subset=["date"])
 
        if df.empty:
            return empty, "⚠️ データを取得しましたが、dateカラムの値がすべて無効です。"
 
        return df, ""
 
    except requests.exceptions.HTTPError as e:
        return empty, f"❌ HTTP エラー: {e}\nURL: {csv_url}"
    except Exception as e:
        return empty, f"❌ 予期しないエラー: {type(e).__name__}: {e}\nURL: {csv_url}"
 
 
def post_row(date_str: str, member: str, kind: str, money: int) -> tuple[bool, str]:
    payload = {"date": date_str, "member": member, "kind": kind, "money": str(money)}
    try:
        res = requests.post(GAS_URL, json=payload, timeout=15)
        res.raise_for_status()
        return True, ""
    except requests.exceptions.Timeout:
        return False, "タイムアウトしました（15秒）"
    except requests.exceptions.HTTPError as e:
        return False, f"HTTP エラー: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
 
 
# ─────────────────────────────────────────
# 割り勘計算
# ─────────────────────────────────────────
def calc_settlement(df: pd.DataFrame):
    totals = {m: 0 for m in MEMBERS}
    for _, row in df.iterrows():
        if row["member"] in totals:
            totals[row["member"]] += row["money"]
 
    grand_total = sum(totals.values())
    fair_share  = grand_total / len(MEMBERS) if MEMBERS else 0
    balances    = {m: totals[m] - fair_share for m in MEMBERS}
 
    settlements = []
    p_list = [[m, -b] for m, b in sorted(balances.items(), key=lambda x: x[1])  if b < 0]
    r_list = [[m,  b] for m, b in sorted(balances.items(), key=lambda x: -x[1]) if b > 0]
 
    p_idx = r_idx = 0
    while p_idx < len(p_list) and r_idx < len(r_list):
        amount = min(p_list[p_idx][1], r_list[r_idx][1])
        if amount > 0.5:
            settlements.append({"from": p_list[p_idx][0], "to": r_list[r_idx][0], "amount": round(amount)})
        p_list[p_idx][1] -= amount
        r_list[r_idx][1] -= amount
        if p_list[p_idx][1] < 0.5: p_idx += 1
        if r_list[r_idx][1] < 0.5: r_idx += 1
 
    return totals, grand_total, fair_share, settlements
 
 
# ─────────────────────────────────────────
# スタイル
# ─────────────────────────────────────────
def apply_style():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@400;700&family=Noto+Sans+JP:wght@300;400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans JP', sans-serif; }
    .stApp { background: linear-gradient(135deg,#fdf6ec,#fce8d5 50%,#f9d9c0); min-height:100vh; }
    .main-title { font-family:'Zen Maru Gothic',sans-serif; font-size:2.4rem; font-weight:700; color:#c0603a; text-align:center; margin-bottom:.2rem; letter-spacing:.05em; }
    .sub-title  { text-align:center; color:#a0826a; font-size:.9rem; margin-bottom:2rem; }
    .card { background:rgba(255,255,255,.75); backdrop-filter:blur(8px); border-radius:20px; padding:1.6rem 2rem; margin-bottom:1.2rem; border:1px solid rgba(192,96,58,.15); box-shadow:0 4px 24px rgba(192,96,58,.08); }
    .section-label { font-family:'Zen Maru Gothic',sans-serif; font-size:1.05rem; color:#c0603a; font-weight:700; margin-bottom:.8rem; }
    .settlement-box { background:linear-gradient(135deg,#fff3ed,#ffe8d6); border:2px solid #f0a882; border-radius:16px; padding:1.2rem 1.6rem; margin:.6rem 0; font-size:1.1rem; color:#7a3520; font-weight:500; }
    .total-box { background:linear-gradient(135deg,#c0603a,#e07a50); border-radius:16px; padding:1rem 1.4rem; color:white; font-weight:700; font-size:1rem; margin:.4rem 0; }
    .balanced-box { background:linear-gradient(135deg,#d4edda,#c3e6cb); border:2px solid #7abf8a; border-radius:16px; padding:1.2rem 1.6rem; color:#3a7a4a; font-weight:600; font-size:1.05rem; }
    div.stButton > button { background:linear-gradient(135deg,#c0603a,#e07a50)!important; color:white!important; border:none!important; border-radius:12px!important; font-family:'Zen Maru Gothic',sans-serif!important; font-size:1rem!important; font-weight:700!important; padding:.6rem 2rem!important; width:100%!important; transition:all .2s ease!important; box-shadow:0 4px 12px rgba(192,96,58,.3)!important; }
    div.stButton > button:hover { transform:translateY(-2px)!important; box-shadow:0 6px 20px rgba(192,96,58,.4)!important; }
    .stTabs [data-baseweb="tab-list"] { gap:8px; background:rgba(255,255,255,.5); border-radius:14px; padding:6px; }
    .stTabs [data-baseweb="tab"] { border-radius:10px!important; font-family:'Zen Maru Gothic',sans-serif!important; font-weight:700!important; color:#a0826a!important; }
    .stTabs [aria-selected="true"] { background:linear-gradient(135deg,#c0603a,#e07a50)!important; color:white!important; }
    .stSelectbox label,.stDateInput label,.stNumberInput label,.stTextInput label { font-weight:600!important; color:#7a3520!important; }
    </style>
    """, unsafe_allow_html=True)
 
 
# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────
def main():
    st.set_page_config(page_title="割り勘アプリ 🍊", page_icon="🍊", layout="centered")
    apply_style()
 
    st.markdown('<div class="main-title">🍊 割り勘アプリ</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">涼馬 & 花帆 の支出管理</div>', unsafe_allow_html=True)
 
    tab_input, tab_result, tab_debug = st.tabs(["📝 支出入力", "📊 集計結果", "🔧 デバッグ"])
 
    # ── タブ1: 入力 ─────────────────────────
    with tab_input:
        st.markdown('<div class="section-label">📅 日付・支払い者</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            selected_date = st.date_input("日付", value=date.today())
        with col2:
            member = st.selectbox("支払い者", MEMBERS)
 
        st.markdown('<div class="section-label">💰 支出内容</div>', unsafe_allow_html=True)
        kind  = st.text_input("名目（例：食費、交通費）")
        money = st.number_input("金額（円）", min_value=0, step=100)
 
        if st.button("✅ 登録する"):
            if not kind.strip():
                st.warning("名目を入力してください。")
            elif money <= 0:
                st.warning("金額を入力してください。")
            else:
                with st.spinner("登録中..."):
                    ok, err = post_row(
                        selected_date.strftime("%Y-%m-%d"),
                        member, kind.strip(), int(money)
                    )
                if ok:
                    st.success(f"✅ 登録しました！　{member} / {kind} / ¥{money:,}")
                    st.cache_data.clear()
                else:
                    st.error(f"登録に失敗しました。\n\n{err}")
 
    # ── タブ2: 集計 ─────────────────────────
    with tab_result:
        df, err_msg = load_data()
 
        if err_msg:
            st.error(err_msg)
            return
 
        if df.empty:
            st.info("まだ支出データがありません。入力タブから登録してください。")
            return
 
        df["year_month"] = df["date"].dt.to_period("M")
        months       = sorted(df["year_month"].unique(), reverse=True)
        month_labels = [str(m) for m in months]
 
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">📆 集計月を選択</div>', unsafe_allow_html=True)
        selected_label = st.selectbox("月を選択", month_labels, index=0, label_visibility="collapsed")
        st.markdown('</div>', unsafe_allow_html=True)
 
        df_month = df[df["year_month"] == pd.Period(selected_label, freq="M")].copy()
        if df_month.empty:
            st.info("選択した月のデータがありません。")
            return
 
        totals, grand_total, fair_share, settlements = calc_settlement(df_month)
 
        # 支払い合計
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">💳 支払い合計</div>', unsafe_allow_html=True)
        cols = st.columns(len(MEMBERS))
        for i, m in enumerate(MEMBERS):
            with cols[i]:
                st.markdown(f'<div class="total-box"><div style="font-size:.85rem;opacity:.85">{m}</div><div style="font-size:1.6rem">¥{totals[m]:,.0f}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div style="text-align:center;color:#a0826a;margin-top:.6rem;font-size:.9rem">合計: <b>¥{grand_total:,.0f}</b> ／ 1人あたりの公平負担: <b>¥{fair_share:,.0f}</b></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
 
        # 精算結果
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">🔄 精算結果</div>', unsafe_allow_html=True)
        if not settlements:
            st.markdown('<div class="balanced-box">✅ 精算不要です！ふたりの支払いはバランスが取れています。</div>', unsafe_allow_html=True)
        else:
            for s in settlements:
                st.markdown(f'<div class="settlement-box">👤 <b>{s["from"]}</b> → <b>{s["to"]}</b> に <span style="font-size:1.3rem;color:#c0603a;margin-left:.3rem"><b>¥{s["amount"]:,}</b></span> を支払う</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
 
        # 明細
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">📋 明細一覧</div>', unsafe_allow_html=True)
        display_df = (
            df_month[["date","member","kind","money"]].copy()
            .assign(date=lambda d: d["date"].dt.strftime("%Y-%m-%d"))
            .rename(columns={"date":"日付","member":"支払い者","kind":"名目","money":"金額（円）"})
            .sort_values("日付", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)
 
 
 
if __name__ == "__main__":
    main()