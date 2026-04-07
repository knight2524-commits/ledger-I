import streamlit as st
import pandas as pd
import re

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

# --- 사이드바 옵션 ---
st.sidebar.header("⚙️ 데이터 처리 옵션")
is_qty_zero = st.sidebar.checkbox("매출기준 반품 (-)수량만 [0] 표기")
exclude_zero_price = st.sidebar.checkbox("매출기준 [0]원 출고품 제외")
exclude_zero_diff_amt = st.sidebar.checkbox("매입, 매출 금액차 [0]원 제외")

buy_fixed_dates = [25, 26, 27, 28, 29, 30, 31]
sell_fixed_dates = [25, 26, 27, 28, 29, 30, 31, 1, 2, 3] # 1, 2, 3일 추가

st.sidebar.divider()
st.sidebar.subheader("📅 매입장부 미 이월 설정")
exclude_buy_amt = st.sidebar.checkbox("선택 일자 금액 제외 (미이월 내역만)", key="ex_buy")
buy_dates = st.sidebar.multiselect("체크할 매입 일자 선택", buy_fixed_dates, default=[])

st.sidebar.subheader("📅 매출장부 당월 설정")
exclude_sell_amt = st.sidebar.checkbox("선택 일자 금액 제외 (당월 내역만)", key="ex_sell")
sell_dates = st.sidebar.multiselect("체크할 매출 일자 선택", sell_fixed_dates, default=[])

if buy_file and sell_file:
    try:
        # 1. 데이터 로드 및 기초 전처리
        df_b_raw = load_data(buy_file)
        df_s_raw = load_data(sell_file)
        
        df_b_raw['일자_숫자'] = pd.to_datetime(df_b_raw['매입일자'], errors='coerce').dt.day
        df_s_raw['일자_숫자'] = pd.to_datetime(df_s_raw['매출일자'], errors='coerce').dt.day
        df_b_raw['원본행'] = df_b_raw.index + 2
        df_s_raw['원본행'] = df_s_raw.index + 2

        # 매입/매출 기본 정제 (코드 추출 및 숫자 변환)
        df_b_raw['매칭코드'] = df_b_raw['규격'].apply(extract_code)
        df_b_clean = df_b_raw.dropna(subset=['매칭코드']).copy()
        df_b_clean['합계금액'] = pd.to_numeric(df_b_clean['합계금액'], errors='coerce').fillna(0)
        
        df_s_clean = df_s_raw.copy()
        df_s_clean['상품코드'] = df_s_clean['상품코드'].astype(str).str.strip()
        df_s_clean['합계'] = pd.to_numeric(df_s_clean['합계'], errors='coerce').fillna(0)
        df_s_clean['수량'] = pd.to_numeric(df_s_clean['수량'], errors='coerce').fillna(0)

        # 2. 미이월 / 당월 대상 판별 (불일치 건 추출)
        b_codes = set(df_b_clean['매칭코드'].unique())
        s_codes = set(df_s_clean['상품코드'].unique())

        # 매입처 미이월 대상: 매출에 없고 + 날짜 조건 맞는 것
        unmoved_raw = df_b_clean[~df_b_clean['매칭코드'].isin(s_codes)].copy()
        df_buy_unmoved_rows = unmoved_raw[unmoved_raw['일자_숫자'].isin(buy_dates)].copy()
        unmoved_sum = df_buy_unmoved_rows['합계금액'].sum() if exclude_buy_amt else 0

        # 매출처 당월 대상: 매입에 없고 + 날짜 조건 맞는 것
        current_raw = df_s_clean[~df_s_clean['상품코드'].isin(b_codes)].copy()
        df_sell_current_rows = current_raw[current_raw['일자_숫자'].isin(sell_dates)].copy()
        current_sum = df_sell_current_rows['합계'].sum() if exclude_sell_amt else 0

        # 3. 최종 계산용 데이터셋 생성 (옵션 체크 시 불일치 건 제외)
        df_b_final = df_b_clean.copy()
        if exclude_buy_amt:
            df_b_final = df_b_final[~df_b_final.index.isin(df_buy_unmoved_rows.index)]

        df_s_final = df_s_clean.copy()
        if exclude_sell_amt:
            df_s_final = df_s_final[~df_s_final.index.isin(df_sell_current_rows.index)]
        
        # 매출 추가 옵션 반영
        if is_qty_zero:
            df_s_final.loc[df_s_final['수량'] < 0, '수량'] = 0
        if exclude_zero_price:
            df_s_final = df_s_final[df_s_final['합계'] != 0]

        # 4. 병합 및 비교 분석 리스트 생성
        b_grp = df_b_final.groupby('매칭코드').agg({'상품명':'first', '매입수량':'sum', '합계금액':'sum', '원본행':lambda x: sorted(list(set(x)))}).reset_index()
        s_grp = df_s_final.groupby('상품코드').agg({'품명':'first', '수량':'sum', '합계':'sum', '원본행':lambda x: sorted(list(set(x)))}).reset_index()

        merged = pd.merge(b_grp, s_grp, left_on='매칭코드', right_on='상품코드', how='outer').fillna(0)
        merged['금액오차'] = merged['합계금액'] - merged['합계']
        merged['수량오차'] = merged['매입수량'] - merged['수량']

        df_all = merged[['매칭코드', '상품명', '원본행_x', '원본행_y', '매입수량', '수량', '수량오차', '합계금액', '합계', '금액오차']].copy()
        df_all.columns = ['코드', '품명', '매입행', '매출행', '매입수량', '매출수량', '수량오차', '매입금액', '매출금액', '금액오차']
        if exclude_zero_diff_amt:
            df_all = df_all[df_all['금액오차'] != 0]

        # 5. UI 출력
        view_option = st.selectbox("표시 모드 선택", ["전체", "오차항목", "비교분석", "매입처 미이월", "매출처 당월"])
        
        # 미이월/당월 탭용 디스플레이 데이터
        df_unmoved_disp = df_buy_unmoved_rows.groupby('매칭코드').agg({'상품명':'first', '원본행':list, '매입수량':'sum', '합계금액':'sum'}).reset_index()
        df_current_disp = df_sell_current_rows.groupby('상품코드').agg({'품명':'first', '원본행':list, '수량':'sum', '합계':'sum'}).reset_index()

        display_map = {
            "전체": df_all,
            "오차항목": df_all[(df_all['금액오차']!=0)|(df_all['수량오차']!=0)],
            "비교분석": df_all[['코드', '품명', '매입행', '매출행', '수량오차', '금액오차']],
            "매입처 미이월": df_unmoved_disp,
            "매출처 당월": df_current_disp
        }
        
        target_df = display_map[view_option]
        if not target_df.empty and '금액오차' in target_df.columns:
            st.markdown(f'<div class="stat-container"><div class="stat-item">📈 (+)합계: {target_df[target_df["금액오차"]>0]["금액오차"].sum():,.0f}원</div><div class="stat-item">📉 (-)합계: {target_df[target_df["금액오차"]<0]["금액오차"].sum():,.0f}원</div><div class="stat-item">⚖️ 모드 합계: {target_df["금액오차"].sum():,.0f}원</div></div>', unsafe_allow_html=True)
        
        st.dataframe(target_df, use_container_width=True)

        # 6. 최종 리포트 카드
        st.divider()
        f_buy_total = df_b_final['합계금액'].sum()
        f_sell_total = df_s_final['합계'].sum()

        c1, c2, c3 = st.columns(3)
        c1.markdown(f'<div class="report-card"><p class="card-label">최종 매입 합계</p><p style="color:red; font-size:12px;">미이월 제외: -{unmoved_sum:,.0f}</p><p class="price-text">{f_buy_total:,.0f}원</p></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="report-card"><p class="card-label">최종 매출 합계</p><p style="color:red; font-size:12px;">당월 제외: -{current_sum:,.0f}</p><p class="price-text">{f_sell_total:,.0f}원</p></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="report-card"><p class="card-label">최종 결과 차액</p><p style="font-size:12px;">&nbsp;</p><p class="diff-text" style="color:{"#007BFF" if (f_buy_total-f_sell_total)>=0 else "#FF4B4B"};">{(f_buy_total-f_sell_total):,.0f}원</p></div>', unsafe_allow_html=True)

    except Exception as e: st.error(f"오류: {e}")
else: st.info("파일을 업로드해주세요.")