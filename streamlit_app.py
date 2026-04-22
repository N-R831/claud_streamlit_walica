import streamlit as st
import pandas as pd
import requests
from datetime import date

# ─────────────────────────────────────────
# 設定（★ここだけ書き換える）
# ─────────────────────────────────────────
# スプレッドシートのURL（共有リンク）
SHEET_URL = st.secrets["sheet_url"]          # 例: https://docs.google.com/spreadsheets/d/xxxxx/edit

# GAS Web App の URL
GAS_URL = st.secrets["gas_url"]              # 例: https://script.google.com/macros/s/xxxxx/exec

# スプレッドシートのシート名（タブ名）
WORKSHEET_NAME = "Walica"

MEMBERS = ["涼馬", "花帆"]

# ─────────────────────────────────────────
# データ読み込み（認証不要・公開URLから直接）
# ─────────────────────────────────────────
def sheet_id_from_url(url: str) -> str:
    """スプレッドシートURLからIDを抽出"""
    return url.split("/d/")[1].split("/")[0]

@st.cache_data(ttl=30)  # 30秒キャッシュ（登録後すぐ反映）
def load_data() -> pd.DataFrame:
    sheet_id = sheet_id_from_url(SHEET_URL)
    csv_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/gviz/tq?tqx=out:csv&sheet={WORKSHEET_NAME}"
    )
    try:
        df = pd.read_csv(csv_url)
        if df.empty or "date" not in df.columns:
            return pd.DataFrame(columns=["date", "member", "kind", "money"])
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["money"] = pd.to_numeric(df["money"], errors="coerce").fillna(0)
        return df.dropna(subset=["date"])
    except Exception:
        return pd.DataFrame(columns=["date", "member", "kind", "money"])


def post_row(date_str: str, member: str, kind: str, money: int) -> bool:
    """GAS Web App 経由でスプレッドシートに1行追記"""
    payload = {
        "date": date_str,
        "member": member,
        "kind": kind,
        "money": str(money),
    }
    try:
        res = requests.post(GAS_URL, json=payload, timeout=15)
        return res.status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────
# 割り勘計算
# ─────────────────────────────────────────
def calc_settlement(df: pd.DataFrame):
    totals = {m: 0 for m in MEMBERS}
    for _, row in df.iterrows():
        if row["member"] in totals:
            totals[row["member"]] += row["money"]

    grand_total = sum(totals.values())
    fair_share = grand_total / len(MEMBERS) if MEMBERS else 0
    balances = {m: totals[m] - fair_share for m in MEMBERS}

    settlements = []
    payers   = sorted([(m, b) for m, b in balances.items() if b < 0],  key=lambda x: x[1])
    receivers = sorted([(m, b) for m, b in balances.items() if b > 0], key=lambda x: -x[1])

    p_idx, r_idx = 0, 0
    p_list = [[m, -b] for m, b in payers]
    r_list = [[m, b]  for m, b in receivers]

    while p_idx < len(p_list) and r_idx < len(r_list):
        payer, p_need = p_list[p_idx]
        recv,  r_have = r_list[r_idx]
        amount = min(p_need, r_have)
        if amount > 0.5:
            settlements.append({"from": payer, "to": recv, "amount": round(amount)})
        p_list[p_idx][1] -= amount
        r_list[r_idx][1] -= amount
        if p_list[p_idx][1] < 0.5:
            p_idx += 1
        if r_list[r_idx][1] < 0.5:
            r_idx += 1

    return totals, grand_total, fair_share, settlements


# ─────────────────────────────────────────
# スタイル
# ─────────────────────────────────────────
def apply_style():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@400;500;700&family=Noto+Sans+JP:wght@300;400;700&display=swap');

    html, body, [class*="css"] { font-family: 'Noto Sans JP', sans-serif; }

    .stApp {
        background: linear-gradient(135deg, #fdf6ec 0%, #fce8d5 50%, #f9d9c0 100%);
        min-height: 100vh;
    }
    .main-title {
        font-family: 'Zen Maru Gothic', sans-serif;
        font-size: 2.4rem; font-weight: 700; color: #c0603a;
        text-align: center; margin-bottom: 0.2rem; letter-spacing: 0.05em;
    }
    .sub-title {
        text-align: center; color: #a0826a;
        font-size: 0.9rem; margin-bottom: 2rem;
    }
    .card {
        background: rgba(255,255,255,0.75);
        backdrop-filter: blur(8px);
        border-radius: 20px; padding: 1.6rem 2rem; margin-bottom: 1.2rem;
        border: 1px solid rgba(192,96,58,0.15);
        box-shadow: 0 4px 24px rgba(192,96,58,0.08);
    }
    .section-label {
        font-family: 'Zen Maru Gothic', sans-serif;
        font-size: 1.05rem; color: #c0603a; font-weight: 700;
        margin-bottom: 0.8rem;
    }
    .settlement-box {
        background: linear-gradient(135deg, #fff3ed, #ffe8d6);
        border: 2px solid #f0a882; border-radius: 16px;
        padding: 1.2rem 1.6rem; margin: 0.6rem 0;
        font-size: 1.1rem; color: #7a3520; font-weight: 500;
    }
    .total-box {
        background: linear-gradient(135deg, #c0603a, #e07a50);
        border-radius: 16px; padding: 1rem 1.4rem;
        color: white; font-weight: 700; font-size: 1rem; margin: 0.4rem 0;
    }
    .balanced-box {
        background: linear-gradient(135deg, #d4edda, #c3e6cb);
        border: 2px solid #7abf8a; border-radius: 16px;
        padding: 1.2rem 1.6rem; color: #3a7a4a;
        font-weight: 600; font-size: 1.05rem;
    }
    div.stButton > button {
        background: linear-gradient(135deg, #c0603a, #e07a50) !important;
        color: white !important; border: none !important;
        border-radius: 12px !important;
        font-family: 'Zen Maru Gothic', sans-serif !important;
        font-size: 1rem !important; font-weight: 700 !important;
        padding: 0.6rem 2rem !important; width: 100% !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 12px rgba(192,96,58,0.3) !important;
    }
    div.stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(192,96,58,0.4) !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px; background: rgba(255,255,255,0.5);
        border-radius: 14px; padding: 6px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px !important;
        font-family: 'Zen Maru Gothic', sans-serif !important;
        font-weight: 700 !important; color: #a0826a !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #c0603a, #e07a50) !important;
        color: white !important;
    }
    .stSelectbox label, .stDateInput label,
    .stNumberInput label, .stTextInput label {
        font-weight: 600 !important; color: #7a3520 !important;
    }
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

    tab_input, tab_result = st.tabs(["📝 支出入力", "📊 集計結果"])

    # ── タブ1: 入力 ──────────────────────────
    with tab_input:
        # st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">📅 日付・支払い者</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            selected_date = st.date_input("日付", value=date.today())
        with col2:
            member = st.selectbox("支払い者", MEMBERS)
        st.markdown('</div>', unsafe_allow_html=True)

        # st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">💰 支出内容</div>', unsafe_allow_html=True)
        kind  = st.text_input("名目（例：食費、交通費）")
        money = st.number_input("金額（円）", min_value=0, step=100)
        st.markdown('</div>', unsafe_allow_html=True)

        if st.button("✅ 登録する"):
            if not kind.strip():
                st.warning("名目を入力してください。")
            elif money <= 0:
                st.warning("金額を入力してください。")
            else:
                with st.spinner("登録中..."):
                    ok = post_row(
                        selected_date.strftime("%Y-%m-%d"),
                        member,
                        kind.strip(),
                        int(money),
                    )
                if ok:
                    st.success(f"✅ 登録しました！　{member} / {kind} / ¥{money:,}")
                    st.cache_data.clear()   # キャッシュをクリアして次回読み込みを最新化
                else:
                    st.error("登録に失敗しました。GAS URLや設定を確認してください。")

    # ── タブ2: 集計 ──────────────────────────
    with tab_result:
        df = load_data()

        if df.empty:
            st.info("まだ支出データがありません。入力タブから登録してください。")
            return

        df["year_month"] = df["date"].dt.to_period("M")
        months = sorted(df["year_month"].unique(), reverse=True)
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
                st.markdown(f"""
                <div class="total-box">
                    <div style="font-size:0.85rem;opacity:0.85">{m}</div>
                    <div style="font-size:1.6rem">¥{totals[m]:,.0f}</div>
                </div>""", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="text-align:center;color:#a0826a;margin-top:0.6rem;font-size:0.9rem">
            合計: <b>¥{grand_total:,.0f}</b> ／ 1人あたりの公平負担: <b>¥{fair_share:,.0f}</b>
        </div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # 精算結果
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">🔄 精算結果</div>', unsafe_allow_html=True)
        if not settlements:
            st.markdown("""
            <div class="balanced-box">
                ✅ 精算不要です！ふたりの支払いはバランスが取れています。
            </div>""", unsafe_allow_html=True)
        else:
            for s in settlements:
                st.markdown(f"""
                <div class="settlement-box">
                    👤 <b>{s['from']}</b> → <b>{s['to']}</b> に
                    <span style="font-size:1.3rem;color:#c0603a;margin-left:0.3rem">
                        <b>¥{s['amount']:,}</b>
                    </span> を支払う
                </div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # 明細
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">📋 明細一覧</div>', unsafe_allow_html=True)
        display_df = (
            df_month[["date", "member", "kind", "money"]]
            .copy()
            .assign(date=lambda d: d["date"].dt.strftime("%Y-%m-%d"))
            .rename(columns={"date": "日付", "member": "支払い者", "kind": "名目", "money": "金額（円）"})
            .sort_values("日付", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()