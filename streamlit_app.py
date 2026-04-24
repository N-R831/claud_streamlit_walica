import streamlit as st
import pandas as pd
import requests
from urllib.parse import quote
from datetime import date
from io import StringIO
 
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
    encoded = quote(sheet_name)
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/gviz/tq?tqx=out:csv&sheet={encoded}"
    )
 
def build_export_url(sheet_id: str, gid: str = "0") -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )
 
@st.cache_data(ttl=30)
def load_data() -> tuple[pd.DataFrame, str]:
    empty = pd.DataFrame(columns=["date", "member", "kind", "money"])
    sheet_id = sheet_id_from_url(SHEET_URL)
    csv_url  = build_csv_url(sheet_id, WORKSHEET_NAME)
    try:
        resp = requests.get(csv_url, timeout=10)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
 
        if "date" not in df.columns:
            export_url = build_export_url(sheet_id)
            df = pd.read_csv(export_url)
 
        if df.empty or "date" not in df.columns:
            return empty, f"⚠️ カラムが見つかりません: {list(df.columns)}"
 
        df["date"]  = pd.to_datetime(df["date"], errors="coerce")
        df["money"] = pd.to_numeric(df["money"], errors="coerce").fillna(0)
        df = df.dropna(subset=["date"])
 
        # スプレッドシート上の行番号（ヘッダー=1行目なのでデータは2行目〜）
        df = df.reset_index(drop=True)
        df["row_num"] = df.index + 2   # GAS側で使う実際の行番号
 
        return df, ""
 
    except requests.exceptions.HTTPError as e:
        return empty, f"❌ HTTP エラー: {e}"
    except Exception as e:
        return empty, f"❌ エラー: {type(e).__name__}: {e}"
 
 
# ─────────────────────────────────────────
# GAS 操作
# ─────────────────────────────────────────
def post_row(date_str: str, member: str, kind: str, money: int) -> tuple[bool, str]:
    payload = {"action": "append", "date": date_str, "member": member, "kind": kind, "money": str(money)}
    try:
        res = requests.post(GAS_URL, json=payload, timeout=15)
        res.raise_for_status()
        return True, ""
    except Exception as e:
        return False, str(e)
 
def update_row(row_num: int, date_str: str, member: str, kind: str, money: int) -> tuple[bool, str]:
    payload = {"action": "update", "row": row_num, "date": date_str, "member": member, "kind": kind, "money": str(money)}
    try:
        res = requests.post(GAS_URL, json=payload, timeout=15)
        res.raise_for_status()
        return True, ""
    except Exception as e:
        return False, str(e)
 
def delete_row(row_num: int) -> tuple[bool, str]:
    payload = {"action": "delete", "row": row_num}
    try:
        res = requests.post(GAS_URL, json=payload, timeout=15)
        res.raise_for_status()
        return True, ""
    except Exception as e:
        return False, str(e)
 
 
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
# 月選択ユーティリティ
# ─────────────────────────────────────────
def select_month(df: pd.DataFrame, key_suffix: str) -> pd.DataFrame:
    df["year_month"] = df["date"].dt.to_period("M")
    months       = sorted(df["year_month"].unique(), reverse=True)
    month_labels = [str(m) for m in months]
 
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">📆 集計月を選択</div>', unsafe_allow_html=True)
    selected_label = st.selectbox(
        "月を選択", month_labels, index=0,
        label_visibility="collapsed", key=f"month_{key_suffix}"
    )
    st.markdown('</div>', unsafe_allow_html=True)
 
    return df[df["year_month"] == pd.Period(selected_label, freq="M")].copy()
 
 
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
    .detail-row { background:rgba(255,255,255,.85); border-radius:14px; padding:1rem 1.2rem; margin:.5rem 0; border:1px solid rgba(192,96,58,.12); box-shadow:0 2px 8px rgba(192,96,58,.06); }
    .detail-member-badge { display:inline-block; background:linear-gradient(135deg,#c0603a,#e07a50); color:white; border-radius:20px; padding:.15rem .75rem; font-size:.85rem; font-weight:700; margin-right:.5rem; }
    .detail-member-badge-2 { display:inline-block; background:linear-gradient(135deg,#7a6abf,#9e8fe0); color:white; border-radius:20px; padding:.15rem .75rem; font-size:.85rem; font-weight:700; margin-right:.5rem; }
    div.stButton > button { background:linear-gradient(135deg,#c0603a,#e07a50)!important; color:white!important; border:none!important; border-radius:12px!important; font-family:'Zen Maru Gothic',sans-serif!important; font-size:1rem!important; font-weight:700!important; padding:.6rem 2rem!important; width:100%!important; transition:all .2s!important; box-shadow:0 4px 12px rgba(192,96,58,.3)!important; }
    div.stButton > button:hover { transform:translateY(-2px)!important; box-shadow:0 6px 20px rgba(192,96,58,.4)!important; }
    .stTabs [data-baseweb="tab-list"] { gap:8px; background:rgba(255,255,255,.5); border-radius:14px; padding:6px; }
    .stTabs [data-baseweb="tab"] { border-radius:10px!important; font-family:'Zen Maru Gothic',sans-serif!important; font-weight:700!important; color:#a0826a!important; }
    .stTabs [aria-selected="true"] { background:linear-gradient(135deg,#c0603a,#e07a50)!important; color:white!important; }
    .stSelectbox label,.stDateInput label,.stNumberInput label,.stTextInput label { font-weight:600!important; color:#7a3520!important; }
    .st-en {color:#A87ED7}
    /* 削除ボタンだけ赤系に上書き */
    button[data-testid*="delete"], .btn-danger > button {
        background:linear-gradient(135deg,#c03a3a,#e05050)!important;
    }
    </style>
    """, unsafe_allow_html=True)
 
 
# ─────────────────────────────────────────
# タブ: 詳細（修正・削除）
# ─────────────────────────────────────────
def render_detail_tab(df: pd.DataFrame):
    if df.empty:
        st.info("まだ支出データがありません。")
        return
 
    df_month = select_month(df, key_suffix="detail")
    if df_month.empty:
        st.info("選択した月のデータがありません。")
        return
 
    # メンバーフィルター
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">👤 表示するメンバー</div>', unsafe_allow_html=True)
    filter_member = st.selectbox(
        "メンバー", ["全員"] + MEMBERS,
        label_visibility="collapsed", key="detail_filter_member"
    )
    st.markdown('</div>', unsafe_allow_html=True)
 
    df_view = df_month if filter_member == "全員" else df_month[df_month["member"] == filter_member]
    df_view = df_view.sort_values("date", ascending=False).reset_index(drop=True)
 
    st.markdown(f'<div class="section-label">📋 明細（{len(df_view)}件）</div>', unsafe_allow_html=True)
 
    # 編集中の行を session_state で管理
    if "editing_row" not in st.session_state:
        st.session_state.editing_row = None
    if "confirm_delete_row" not in st.session_state:
        st.session_state.confirm_delete_row = None
 
    for idx, row in df_view.iterrows():
        row_num  = int(row["row_num"])
        member   = row["member"]
        badge_cls = "detail-member-badge" if member == MEMBERS[0] else "detail-member-badge-2"
 
        with st.container():
            #st.markdown('<div class="detail-row">', unsafe_allow_html=True)
 
            # ── 通常表示 ──────────────────────────
            if st.session_state.editing_row != row_num:
                col_info, col_edit, col_del = st.columns([6, 2, 2])
                with col_info:
                    st.markdown(
                        f'<span class="{badge_cls}">{member}</span>'
                        f'<span style="color:#1E1E1E;font-size:1.1rem;margin-left:.6rem"><b>{row["kind"]}</b></span>'
                        f'<span style="color:#c0603a;font-size:1.1rem;margin-left:.6rem"><b>¥{int(row["money"]):,}</b></span>'
                        f'<span style="color:#a0826a;font-size:.82rem;margin-left:.6rem">{row["date"].strftime("%Y-%m-%d")}</span>',
                        unsafe_allow_html=True
                    )
                with col_edit:
                    if st.button("✏️ 修正", key=f"edit_{row_num}"):
                        st.session_state.editing_row    = row_num
                        st.session_state.confirm_delete_row = None
                        st.rerun()
                with col_del:
                    if st.session_state.confirm_delete_row == row_num:
                        pass  # 下の確認UIを表示
                    else:
                        if st.button("🗑️ 削除", key=f"del_{row_num}"):
                            st.session_state.confirm_delete_row = row_num
                            st.rerun()
 
                # 削除確認
                if st.session_state.confirm_delete_row == row_num:
                    st.warning(f"「{row['kind']} / ¥{int(row['money']):,}」を削除してよいですか？")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ はい、削除する", key=f"confirm_del_{row_num}"):
                            with st.spinner("削除中..."):
                                ok, err = delete_row(row_num)
                            if ok:
                                st.success("削除しました。")
                                st.session_state.confirm_delete_row = None
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(f"削除に失敗: {err}")
                    with c2:
                        if st.button("❌ キャンセル", key=f"cancel_del_{row_num}"):
                            st.session_state.confirm_delete_row = None
                            st.rerun()
 
            # ── 編集フォーム ──────────────────────
            else:
                st.markdown(
                    '<span style="color:#1E1E1E;font-size:1.1rem;margin-left:.6rem">✏️ 編集中</span>',
                    unsafe_allow_html=True
                    )
                e_col1, e_col2 = st.columns(2)
                with e_col1:
                    e_date   = st.date_input("日付",      value=row["date"].date(),    key=f"e_date_{row_num}")
                    e_member = st.selectbox("支払い者",   MEMBERS,
                                            index=MEMBERS.index(member) if member in MEMBERS else 0,
                                            key=f"e_member_{row_num}")
                with e_col2:
                    e_kind   = st.text_input("名目",      value=row["kind"],            key=f"e_kind_{row_num}")
                    e_money  = st.number_input("金額（円）", value=int(row["money"]),
                                               min_value=0, step=100,                  key=f"e_money_{row_num}")
 
                s1, s2 = st.columns(2)
                with s1:
                    if st.button("💾 保存する", key=f"save_{row_num}"):
                        if not e_kind.strip():
                            st.warning("名目を入力してください。")
                        elif e_money <= 0:
                            st.warning("金額を入力してください。")
                        else:
                            with st.spinner("更新中..."):
                                ok, err = update_row(
                                    row_num,
                                    e_date.strftime("%Y-%m-%d"),
                                    e_member, e_kind.strip(), int(e_money)
                                )
                            if ok:
                                st.success("更新しました。")
                                st.session_state.editing_row = None
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(f"更新に失敗: {err}")
                with s2:
                    if st.button("❌ キャンセル", key=f"cancel_edit_{row_num}"):
                        st.session_state.editing_row = None
                        st.rerun()
 
            st.markdown('</div>', unsafe_allow_html=True)
 
 
# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────
def main():
    st.set_page_config(page_title="割り勘アプリ 🍊", page_icon="🍊", layout="centered")
    apply_style()
 
    st.markdown('<div class="main-title">🍊 割り勘アプリ</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">涼馬 & 花帆 の支出管理</div>', unsafe_allow_html=True)
 
    tab_input, tab_result, tab_detail = st.tabs(["📝 支出入力", "📊 集計結果", "📋 詳細・編集"])
 
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
        elif df.empty:
            st.info("まだ支出データがありません。入力タブから登録してください。")
        else:
            df_month = select_month(df, key_suffix="result")
            if df_month.empty:
                st.info("選択した月のデータがありません。")
            else:
                totals, grand_total, fair_share, settlements = calc_settlement(df_month)
 
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown('<div class="section-label">💳 支払い合計</div>', unsafe_allow_html=True)
                cols = st.columns(len(MEMBERS))
                for i, m in enumerate(MEMBERS):
                    with cols[i]:
                        st.markdown(
                            f'<div class="total-box">'
                            f'<div style="font-size:.85rem;opacity:.85">{m}</div>'
                            f'<div style="font-size:1.6rem">¥{totals[m]:,.0f}</div>'
                            f'</div>', unsafe_allow_html=True
                        )
                st.markdown(
                    f'<div style="text-align:center;color:#a0826a;margin-top:.6rem;font-size:.9rem">'
                    f'合計: <b>¥{grand_total:,.0f}</b> ／ 1人あたりの公平負担: <b>¥{fair_share:,.0f}</b>'
                    f'</div>', unsafe_allow_html=True
                )
                st.markdown('</div>', unsafe_allow_html=True)
 
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown('<div class="section-label">🔄 精算結果</div>', unsafe_allow_html=True)
                if not settlements:
                    st.markdown('<div class="balanced-box">✅ 精算不要です！ふたりの支払いはバランスが取れています。</div>', unsafe_allow_html=True)
                else:
                    for s in settlements:
                        st.markdown(
                            f'<div class="settlement-box">👤 <b>{s["from"]}</b> → <b>{s["to"]}</b> に '
                            f'<span style="font-size:1.3rem;color:#c0603a;margin-left:.3rem"><b>¥{s["amount"]:,}</b></span> を支払う</div>',
                            unsafe_allow_html=True
                        )
                st.markdown('</div>', unsafe_allow_html=True)
 
    # ── タブ3: 詳細・編集 ────────────────────
    with tab_detail:
        df, err_msg = load_data()
        if err_msg:
            st.error(err_msg)
        else:
            render_detail_tab(df)
 
 
if __name__ == "__main__":
    main()