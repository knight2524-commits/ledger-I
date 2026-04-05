import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="장부 오차 검증 툴", layout="wide")

# CSS를 이용한 시인성 강화
st.markdown("""
    <style>
    .report-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #e6e9ef;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 10px;
        text-align: center;
    }
    .main-title { font-size: 24px !important; font-weight: bold; color: #1E1E1E; margin-bottom: 20px; }
    .sub-title { font-size: 18px !important; font-weight: 600; color: #4F4F4F; margin-top: 20px; margin-bottom: 15px; }
    .price-text { font-size: 22px !important; font-weight: 700; color: #007BFF; }
    .diff-text { font-size: 24px !important; font-weight: 800; }
    .card-label { color: #666; font-size: 14px; font-weight: 600; margin-bottom: 8px; }
    .stDataFrame { font-size: 14px !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 매입/매출 원장 상세 비교 분석 툴")

# 파일 업로드 섹션
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

# --- 사이드바 데이터 처리 옵션 ---
st.sidebar.header("⚙️ 데이터 처리 옵션")
is_qty_zero = st.sidebar.checkbox("매출기준 반품 (-)수량만 [0] 표기")
# [수정] 문구 수정
exclude_zero_price = st.sidebar.checkbox("매출기준 [0]원 출고품 제외")
# [추가] 금액차 0원 제외 옵션
exclude_zero_diff_amt = st.sidebar.checkbox("매입, 매출 금액차 [0]원 제외")

fixed_dates = [25, 26, 27, 28, 29, 30, 31]
st.sidebar.divider()

st.sidebar.subheader("📅 매입장부 미 이월 설정")
exclude_buy_amt = st.sidebar.checkbox("선택 일자 금액 제외 (미이월)", key="ex_buy")
buy_dates = st.sidebar.multiselect("체크할 매입 일자 선택", fixed_dates, default=[])

st.sidebar.subheader("📅 매출장부 당월 설정")
exclude_sell_amt = st.sidebar.checkbox("선택 일자 금액 제외 (당월)", key="ex_sell")
sell_dates = st.sidebar.multiselect("체크할 매출 일자 선택", fixed_dates, default=[])

if buy_file and sell_file:
    try:
        df_buy = load_data(buy_file)
        df_sell = load_data(sell_file)
        
        df_buy['일자_숫자'] = pd.to_datetime(df_buy['매입일자'], errors='coerce').dt.day
        df_sell['일자_숫자'] = pd.to_datetime(df_sell['매출일자'], errors='coerce').dt.day
        df_buy['원본행'] = df_buy.index + 2
        df_sell['원본행'] = df_sell.index + 2

        # --- 매입원장 전처리 ---
        df_buy_proc = df_buy.dropna(subset=['규격', '합계금액']).copy()
        df_buy_proc['매칭코드'] = df_buy_proc['규격'].apply(extract_code)
        df_buy_proc = df_buy_proc.dropna(subset=['매칭코드'])
        df_buy_proc['매입수량'] = pd.to_numeric(df_buy_proc['매입수량'], errors='coerce').fillna(0)
        df_buy_proc['합계금액'] = pd.to_numeric(df_buy_proc['합계금액'], errors='coerce').fillna(0)
        
        raw_total_buy_amt = df_buy_proc['합계금액'].sum()
        raw_total_buy_qty = df_buy_proc['매입수량'].sum()

        # --- 매출원장 전처리 ---
        df_sell_proc = df_sell.dropna(subset=['상품코드', '합계']).copy()
        df_sell_proc['상품코드'] = df_sell_proc['상품코드'].astype(str).str.strip()
        df_sell_proc['수량'] = pd.to_numeric(df_sell_proc['수량'], errors='coerce').fillna(0)
        df_sell_proc['합계'] = pd.to_numeric(df_sell_proc['합계'], errors='coerce').fillna(0)

        if is_qty_zero:
            df_sell_proc.loc[df_sell_proc['수량'] < 0, '수량'] = 0

        if exclude_zero_price:
            df_sell_proc = df_sell_proc[df_sell_proc['합계'] != 0]

        raw_total_sell_amt = df_sell_proc['합계'].sum()
        raw_total_sell_qty = df_sell_proc['수량'].sum()

        # --- 그룹화 및 병합 ---
        buy_grouped = df_buy_proc.groupby('매칭코드').agg({
            '상품명': 'first', '매입수량': 'sum', '합계금액': 'sum',
            '일자_숫자': lambda x: sorted(list(set(x))),
            '원본행': lambda x: sorted(list(set(x)))
        }).reset_index()
        
        sell_grouped = df_sell_proc.groupby('상품코드').agg({
            '품명': 'first', '수량': 'sum', '합계': 'sum',
            '일자_숫자': lambda x: sorted(list(set(x))),
            '원본행': lambda x: sorted(list(set(x)))
        }).reset_index()

        merged_df = pd.merge(buy_grouped, sell_grouped, left_on='매칭코드', right_on='상품코드', how='outer').fillna(0)
        
        merged_df['수량오차'] = merged_df['매입수량'] - merged_df['수량']
        merged_df['금액오차'] = merged_df['합계금액'] - merged_df['합계']

        # [추가 로직] 금액차 0원 제외 옵션 적용
        if exclude_zero_diff_amt:
            merged_df = merged_df[merged_df['금액오차'] != 0]

        # 데이터프레임 정리
        df_all = merged_df[['매칭코드', '상품명', '매입수량', '수량', '수량오차', '합계금액', '합계', '금액오차']]
        df_all.columns = ['코드', '품명', '매입수량', '매출수량', '수량오차', '매입금액', '매출금액', '금액오차']
        
        df_error = df_all[(df_all['수량오차'] != 0) | (df_all['금액오차'] != 0)]
        df_analysis = merged_df[['매칭코드', '상품명', '원본행_x', '원본행_y', '수량오차', '금액오차']]
        df_analysis.columns = ['코드', '품명', '매입행번호', '매출행번호', '수량오차', '금액오차']

        # 미이월/당월 필터
        mask_buy_unm = (merged_df['수량'] == 0) & (merged_df['매입수량'] > 0)
        if buy_dates:
            mask_buy_unm &= merged_df['일자_숫자_x'].apply(lambda x: any(d in buy_dates for d in x) if isinstance(x, list) else False)
        df_buy_unmoved = merged_df[mask_buy_unm][['매칭코드', '상품명', '일자_숫자_x', '매입수량', '원본행_x']]
        df_buy_unmoved.columns = ['코드', '품명', '매입일자', '매입수량', '매입행번호']

        mask_sell_cur = (merged_df['매입수량'] == 0) & (merged_df['수량'] > 0)
        if sell_dates:
            mask_sell_cur &= merged_df['일자_숫자_y'].apply(lambda x: any(d in sell_dates for d in x) if isinstance(x, list) else False)
        df_sell_current = merged_df[mask_sell_cur][['매칭코드', '품명', '일자_숫자_y', '수량', '원본행_y']]
        df_sell_current.columns = ['코드', '품명', '매출일자', '매출수량', '매출행번호']

        # --- UI 표시 ---
        st.subheader("📋 데이터 분석 결과")
        view_option = st.selectbox("표시 모드 선택", ["전체", "오차항목", "비교분석", "매입처 미이월", "매출처 당월"])
        display_map = {"전체": df_all, "오차항목": df_error, "비교분석": df_analysis, "매입처 미이월": df_buy_unmoved, "매출처 당월": df_sell_current}
        st.dataframe(display_map[view_option], use_container_width=True)

        # --- 리포트 섹션 ---
        st.divider()
        st.markdown('<p class="main-title">📝 장부 금액 요약 리포트</p>', unsafe_allow_html=True)
        
        # 1. 원본 파일 합계
        st.markdown('<p class="sub-title">1. 원본 파일 합계 (제외 전)</p>', unsafe_allow_html=True)
        rc1, rc2, rc3 = st.columns(3)
        raw_diff = raw_total_buy_amt - raw_total_sell_amt
        r_color = "#007BFF" if raw_diff >= 0 else "#FF4B4B"

        rc1.markdown(f'<div class="report-card"><p class="card-label">📦 매입원장 원천 총액</p><p class="price-text">{raw_total_buy_amt:,.0f}원</p></div>', unsafe_allow_html=True)
        rc2.markdown(f'<div class="report-card"><p class="card-label">💰 매출원장 원천 총액</p><p class="price-text">{raw_total_sell_amt:,.0f}원</p></div>', unsafe_allow_html=True)
        rc3.markdown(f'<div class="report-card"><p class="card-label">⚖️ 원천 차액 (매입-매출)</p><p class="diff-text" style="color:{r_color};">{raw_diff:,.0f}원</p></div>', unsafe_allow_html=True)

        # 2. 최종 금액 카드
        st.markdown('<p class="sub-title">2. 설정 반영 후 최종 금액</p>', unsafe_allow_html=True)
        ex_buy_sum = df_buy_proc[df_buy_proc['일자_숫자'].isin(buy_dates)]['합계금액'].sum() if (exclude_buy_amt and buy_dates) else 0
        ex_sell_sum = df_sell_proc[df_sell_proc['일자_숫자'].isin(sell_dates)]['합계'].sum() if (exclude_sell_amt and sell_dates) else 0
        
        f_buy_total = raw_total_buy_amt - ex_buy_sum
        f_sell_total = raw_total_sell_amt - ex_sell_sum
        f_diff = f_buy_total - f_sell_total
        f_color = "#007BFF" if f_diff >= 0 else "#FF4B4B"

        bc1, bc2, bc3 = st.columns(3)
        bc1.markdown(f'<div class="report-card"><p class="card-label">✅ 최종 매입 금액</p><p style="font-size:13px; color:#E74C3C;">설정 제외: -{ex_buy_sum:,.0f}원</p><p class="price-text">{f_buy_total:,.0f}원</p></div>', unsafe_allow_html=True)
        bc2.markdown(f'<div class="report-card"><p class="card-label">✅ 최종 매출 금액</p><p style="font-size:13px; color:#E74C3C;">설정 제외: -{ex_sell_sum:,.0f}원</p><p class="price-text">{f_sell_total:,.0f}원</p></div>', unsafe_allow_html=True)
        bc3.markdown(f'<div class="report-card"><p class="card-label">⚖️ 최종 결과 차액 (매입-매출)</p><p style="font-size:13px; color:#666;">옵션 반영 완료</p><p class="diff-text" style="color:{f_color};">{f_diff:,.0f}원</p></div>', unsafe_allow_html=True)

        st.divider()
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_all.to_excel(writer, index=False, sheet_name='1_전체')
            df_error.to_excel(writer, index=False, sheet_name='2_오차항목')
            df_analysis.to_excel(writer, index=False, sheet_name='3_비교분석_행번호')
            df_buy_unmoved.to_excel(writer, index=False, sheet_name='4_매입처_미이월')
            df_sell_current.to_excel(writer, index=False, sheet_name='5_매출처_당월')
        
        st.download_button(label="📥 분석 결과 통합 엑셀 다운로드", data=output.getvalue(), file_name="장부_통합분석_리포트.xlsx")

    except Exception as e:
        st.error(f"데이터 처리 중 오류 발생: {e}")
else:
    st.info("파일을 업로드하면 분석 리포트가 생성됩니다.")