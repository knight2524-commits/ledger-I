import streamlit as st
import pandas as pd
import re
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="장부 오차 검증 툴", layout="wide")

# CSS 디자인
st.markdown("""
    <style>
    .report-card { background-color: #ffffff; padding: 20px; border-radius: 10px; border: 1px solid #e6e9ef; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 10px; text-align: center; }
    .price-text { font-size: 22px !important; font-weight: 700; color: #007BFF; }
    .diff-text { font-size: 24px !important; font-weight: 800; }
    .stat-container { background: linear-gradient(90deg, #f0f4f8 0%, #ffffff 100%); padding: 15px 25px; border-radius: 8px; border: 2px solid #007BFF; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 매입/매출 원장 상세 비교 분석 툴")

col1, col2 = st.columns(2)
with col1:
    buy_file = st.file_uploader("📥 매입원장 (CSV/Excel) 업로드", type=['csv', 'xlsx'])
with col2:
    sell_file = st.file_uploader("📤 매출원장 (CSV/Excel) 업로드", type=['csv', 'xlsx'])

def load_data(file):
    if file.name.endswith('.csv'):
        try: return pd.read_csv(file, encoding='cp949')
        except: return pd.read_csv(file, encoding='utf-8')
    else: return pd.read_excel(file)

def extract_code(text):
    if pd.isna(text): return None
    match = re.search(r'(\d{3}-\d{4})', str(text))
    return match.group(1) if match else None

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='검증결과')
    return output.getvalue()

# --- 사이드바 옵션 ---
st.sidebar.header("⚙️ 데이터 처리 옵션")
is_qty_zero = st.sidebar.checkbox("매출기준 반품 (-)수량만 [0] 표기")
exclude_zero_price = st.sidebar.checkbox("매출기준 [0]원 출고품 제외")
exclude_zero_diff_amt = st.sidebar.checkbox("매입, 매출 금액차 [0]원 제외")

fixed_dates = [25, 26, 27, 28, 29, 30, 31]

st.sidebar.divider()
st.sidebar.subheader("📅 매입장부 미 이월 설정")
exclude_buy_amt = st.sidebar.checkbox("선택 일자 금액 제외 (미이월)", key="ex_buy")
buy_dates = st.sidebar.multiselect("체크할 매입 일자 선택", fixed_dates, default=[], key="buy_date_sel")

st.sidebar.subheader("📅 매출장부 이월 설정")
exclude_sell_amt = st.sidebar.checkbox("선택 일자 금액 제외 (이월)", key="ex_sell")
sell_dates = st.sidebar.multiselect("체크할 매출 일자 선택", fixed_dates, default=[], key="sell_date_sel")

st.sidebar.subheader("🔍 당월/이월 검증")
check_validation = st.sidebar.checkbox("당월/이월 검증 활성화", key="ex_val")
val_dates = st.sidebar.multiselect("검증할 매입 일자 선택 (25~31일)", fixed_dates, default=fixed_dates, key="val_date_sel")

if buy_file and sell_file:
    try:
        # 1. 데이터 로드
        df_buy = load_data(buy_file)
        df_sell = load_data(sell_file)
        
        df_buy['일자_숫자'] = pd.to_datetime(df_buy['매입일자'], errors='coerce').dt.day
        df_sell['일자_숫자'] = pd.to_datetime(df_sell['매출일자'], errors='coerce').dt.day
        df_buy['원본행'] = df_buy.index + 2
        df_sell['원본행'] = df_sell.index + 2

        # 2. 전처리
        df_buy_proc = df_buy.dropna(subset=['규격', '합계금액']).copy()
        df_buy_proc['매칭코드'] = df_buy_proc['규격'].apply(extract_code)
        df_buy_proc = df_buy_proc.dropna(subset=['매칭코드'])
        df_buy_proc['매입수량'] = pd.to_numeric(df_buy_proc['매입수량'], errors='coerce').fillna(0)
        df_buy_proc['합계금액'] = pd.to_numeric(df_buy_proc['합계금액'], errors='coerce').fillna(0)

        df_sell_proc = df_sell.dropna(subset=['상품코드', '합계']).copy()
        df_sell_proc['상품코드'] = df_sell_proc['상품코드'].astype(str).str.strip()
        df_sell_proc['수량'] = pd.to_numeric(df_sell_proc['수량'], errors='coerce').fillna(0)
        df_sell_proc['합계'] = pd.to_numeric(df_sell_proc['합계'], errors='coerce').fillna(0)

        if is_qty_zero:
            df_sell_proc.loc[df_sell_proc['수량'] < 0, '수량'] = 0
        if exclude_zero_price:
            df_sell_proc = df_sell_proc[df_sell_proc['합계'] != 0]

        # 3. 그룹화
        buy_grouped = df_buy_proc.groupby('매칭코드').agg({
            '상품명': 'first', '매입수량': 'sum', '합계금액': 'sum',
            '일자_숫자': lambda x: sorted(list(set(x))),
            '원본행': lambda x: sorted(list(set(x.dropna().astype(int))))
        }).reset_index()
        
        sell_grouped = df_sell_proc.groupby('상품코드').agg({
            '품명': 'first', '수량': 'sum', '합계': 'sum',
            '일자_숫자': lambda x: sorted(list(set(x))),
            '원본행': lambda x: sorted(list(set(x.dropna().astype(int))))
        }).reset_index()

        # 4. 병합
        merged = pd.merge(buy_grouped, sell_grouped, left_on='매칭코드', right_on='상품코드', how='outer').fillna(0)
        
        # 5. 로직 정의
        mask_buy_only = (merged['수량'] == 0) & (merged['매입수량'] > 0)
        if buy_dates:
            mask_buy_only &= merged['일자_숫자_x'].apply(lambda x: any(d in buy_dates for d in x) if isinstance(x, list) else False)
        df_buy_unmoved = merged[mask_buy_only][['매칭코드', '상품명', '원본행_x', '매입수량', '합계금액']].copy()
        df_buy_unmoved.columns = ['코드', '품명', '매입행', '매입수량', '매입금액']
        df_buy_unmoved['금액오차'] = df_buy_unmoved['매입금액']

        mask_sell_only = (merged['매입수량'] == 0) & (merged['수량'] > 0)
        if sell_dates:
            mask_sell_only &= merged['일자_숫자_y'].apply(lambda x: any(d in sell_dates for d in x) if isinstance(x, list) else False)
        df_sell_carryover = merged[mask_sell_only][['매칭코드', '품명', '원본행_y', '수량', '합계']].copy()
        df_sell_carryover.columns = ['코드', '품명', '매출행', '매출수량', '매출금액']
        df_sell_carryover['금액오차'] = -df_sell_carryover['매출금액']

        mask_val = (merged['매입수량'] > 0) & (merged['수량'] == 0)
        if val_dates:
            mask_val &= merged['일자_숫자_x'].apply(lambda x: any(d in val_dates for d in x) if isinstance(x, list) else False)
        df_validation = merged[mask_val][['매칭코드', '상품명', '원본행_x', '매입수량', '합계금액']].copy()
        df_validation.columns = ['코드', '품명', '매입행', '매입수량', '매입금액']
        df_validation['금액오차'] = df_validation['매입금액']

        # 6. 전체 결과 정리
        merged['수량오차'] = merged['매입수량'] - merged['수량']
        merged['금액오차'] = merged['합계금액'] - merged['합계']
        df_all = merged[['매칭코드', '상품명', '원본행_x', '원본행_y', '매입수량', '수량', '수량오차', '합계금액', '합계', '금액오차']]
        df_all.columns = ['코드', '품명', '매입행', '매출행', '매입수량', '매출수량', '수량오차', '매입금액', '매출금액', '금액오차']
        if exclude_zero_diff_amt:
            df_all = df_all[df_all['금액오차'] != 0]

        # 7. UI 출력 및 엑셀 내보내기 버튼
        view_option = st.selectbox("표시 모드 선택", ["전체", "오차항목", "비교분석", "매입처 미이월", "매출처 이월", "당월/이월 검증"])
        display_map = {
            "전체": df_all, "오차항목": df_all[(df_all['금액오차']!=0)|(df_all['수량오차']!=0)], 
            "비교분석": df_all[['코드', '품명', '매입행', '매출행', '수량오차', '금액오차']], 
            "매입처 미이월": df_buy_unmoved, "매출처 이월": df_sell_carryover, "당월/이월 검증": df_validation
        }
        target_df = display_map[view_option]

        # 엑셀 내보내기 버튼 배치
        excel_data = to_excel(target_df)
        st.download_button(
            label=f"📥 {view_option} 데이터 엑셀로 내보내기",
            data=excel_data,
            file_name=f"검증결과_{view_option}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if not target_df.empty:
            p_sum = target_df[target_df['금액오차'] > 0]['금액오차'].sum()
            m_sum = target_df[target_df['금액오차'] < 0]['금액오차'].sum()
            st.markdown(f'<div class="stat-container"><div class="stat-item">📈 (+)합계: {p_sum:,.0f}원</div><div class="stat-item">📉 (-)합계: {m_sum:,.0f}원</div><div class="stat-item">⚖️ 총 오차: {target_df["금액오차"].sum():,.0f}원</div></div>', unsafe_allow_html=True)
        
        st.dataframe(target_df, use_container_width=True)

        # 8. 리포트 카드
        st.divider()
        ex_buy_sum = df_buy_unmoved['매입금액'].sum() if exclude_buy_amt else 0
        ex_sell_sum = df_sell_carryover['매출금액'].sum() if exclude_sell_amt else 0
        
        f_buy_total = df_buy_proc['합계금액'].sum() - ex_buy_sum
        f_sell_total = df_sell_proc['합계'].sum() - ex_sell_sum

        c1, c2, c3 = st.columns(3)
        c1.markdown(f'<div class="report-card"><p class="card-label">최종 매입 합계</p><p style="color:red; font-size:12px;">제외: -{ex_buy_sum:,.0f}</p><p class="price-text">{f_buy_total:,.0f}원</p></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="report-card"><p class="card-label">최종 매출 합계</p><p style="color:red; font-size:12px;">제외: -{ex_sell_sum:,.0f}</p><p class="price-text">{f_sell_total:,.0f}원</p></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="report-card"><p class="card-label">결과 차액</p><p style="font-size:12px;">&nbsp;</p><p class="diff-text" style="color:{"#007BFF" if (f_buy_total-f_sell_total)>=0 else "#FF4B4B"};">{(f_buy_total-f_sell_total):,.0f}원</p></div>', unsafe_allow_html=True)

    except Exception as e: st.error(f"오류: {e}")
else: st.info("파일을 업로드해주세요.")
