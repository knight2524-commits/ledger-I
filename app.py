import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="장부 오차 검증 툴", layout="wide")

# CSS 디자인 유지
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

fixed_dates = [25, 26, 27, 28, 29, 30, 31]
st.sidebar.divider()
st.sidebar.subheader("📅 매입장부 미 이월 설정")
exclude_buy_amt = st.sidebar.checkbox("선택 일자 금액 제외 (미이월 내역만)", key="ex_buy")
buy_dates = st.sidebar.multiselect("체크할 매입 일자 선택", fixed_dates, default=[])

st.sidebar.subheader("📅 매출장부 당월 설정")
exclude_sell_amt = st.sidebar.checkbox("선택 일자 금액 제외 (당월 내역만)", key="ex_sell")
sell_dates = st.sidebar.multiselect("체크할 매출 일자 선택", fixed_dates, default=[])

if buy_file and sell_file:
    try:
        # 1. 원본 로드 및 기본 전처리
        df_b_raw = load_data(buy_file)
        df_s_raw = load_data(sell_file)
        
        df_b_raw['일자_숫자'] = pd.to_datetime(df_b_raw['매입일자'], errors='coerce').dt.day
        df_s_raw['일자_숫자'] = pd.to_datetime(df_s_raw['매출일자'], errors='coerce').dt.day
        df_b_raw['원본행'] = df_b_raw.index + 2
        df_s_raw['원본행'] = df_s_raw.index + 2

        # 매입 기본 정제
        df_b_raw['매칭코드'] = df_b_raw['규격'].apply(extract_code)
        df_b_proc = df_b_raw.dropna(subset=['매칭코드']).copy()
        df_b_proc['매입수량'] = pd.to_numeric(df_b_proc['매입수량'], errors='coerce').fillna(0)
        df_b_proc['합계금액'] = pd.to_numeric(df_b_proc['합계금액'], errors='coerce').fillna(0)

        # 매출 기본 정제
        df_s_proc = df_s_raw.copy()
        df_s_proc['상품코드'] = df_s_proc['상품코드'].astype(str).str.strip()
        df_s_proc['수량'] = pd.to_numeric(df_s_proc['수량'], errors='coerce').fillna(0)
        df_s_proc['합계'] = pd.to_numeric(df_s_proc['합계'], errors='coerce').fillna(0)

        if is_qty_zero:
            df_s_proc.loc[df_s_proc['수량'] < 0, '수량'] = 0
        if exclude_zero_price:
            df_s_proc = df_s_proc[df_s_proc['합계'] != 0]

        # 2. 기초 그룹화 (비교분석용)
        b_grouped = df_b_proc.groupby('매칭코드').agg({
            '상품명': 'first', '매입수량': 'sum', '합계금액': 'sum', '원본행': lambda x: sorted(list(set(x))), '일자_숫자': lambda x: list(x)
        }).reset_index()
        
        s_grouped = df_s_proc.groupby('상품코드').agg({
            '품명': 'first', '수량': 'sum', '합계': 'sum', '원본행': lambda x: sorted(list(set(x))), '일자_숫자': lambda x: list(x)
        }).reset_index()

        # 3. 매입처 미이월 & 매출처 당월 내역 추출 (핵심 로직)
        # 매입처 미이월: 매출장부에 코드가 아예 없는 매입건
        unmoved_mask = ~b_grouped['매칭코드'].isin(s_grouped['상품코드'])
        df_buy_unmoved_all = b_grouped[unmoved_mask].copy()
        
        # 필터링: 사이드바에서 선택한 날짜에 포함된 내역만
        def check_date_match(date_list, target_dates):
            return any(d in target_dates for d in date_list) if target_dates else False

        df_buy_unmoved = df_buy_unmoved_all[df_buy_unmoved_all['일자_숫자'].apply(lambda x: check_date_match(x, buy_dates))].copy()
        
        # 매출처 당월: 매입장부에 코드가 아예 없는 매출건
        current_month_mask = ~s_grouped['상품코드'].isin(b_grouped['매칭코드'])
        df_sell_current_all = s_grouped[current_month_mask].copy()
        
        # 필터링: 사이드바에서 선택한 날짜에 포함된 내역만
        df_sell_current = df_sell_current_all[df_sell_current_all['일자_숫자'].apply(lambda x: check_date_match(x, sell_dates))].copy()

        # 4. 병합 및 비교 분석 (전체 리스트)
        merged = pd.merge(b_grouped, s_grouped, left_on='매칭코드', right_on='상품코드', how='outer').fillna(0)
        merged['금액오차'] = merged['합계금액'] - merged['합계']
        merged['수량오차'] = merged['매입수량'] - merged['수량']

        df_all = merged[['매칭코드', '상품명', '원본행_x', '원본행_y', '매입수량', '수량', '수량오차', '합계금액', '합계', '금액오차']].copy()
        df_all.columns = ['코드', '품명', '매입행', '매출행', '매입수량', '매출수량', '수량오차', '매입금액', '매출금액', '금액오차']
        
        if exclude_zero_diff_amt:
            df_all = df_all[df_all['금액오차'] != 0]

        # 5. UI 출력 데이터 매핑
        if not df_buy_unmoved.empty:
            df_buy_unmoved_disp = df_buy_unmoved[['매칭코드', '상품명', '원본행', '매입수량', '합계금액']].copy()
            df_buy_unmoved_disp.columns = ['코드', '품명', '매입행', '매입수량', '매입금액']
            df_buy_unmoved_disp['금액오차'] = df_buy_unmoved_disp['매입금액']
        else:
            df_buy_unmoved_disp = pd.DataFrame(columns=['코드', '품명', '매입행', '매입수량', '매입금액', '금액오차'])

        if not df_sell_current.empty:
            df_sell_current_disp = df_sell_current[['상품코드', '품명', '원본행', '수량', '합계']].copy()
            df_sell_current_disp.columns = ['코드', '품명', '매출행', '매출수량', '매출금액']
            df_sell_current_disp['금액오차'] = -df_sell_current_disp['매출금액']
        else:
            df_sell_current_disp = pd.DataFrame(columns=['코드', '품명', '매출행', '매출수량', '매출금액', '금액오차'])

        view_option = st.selectbox("표시 모드 선택", ["전체", "오차항목", "비교분석", "매입처 미이월", "매출처 당월"])
        display_map = {
            "전체": df_all, 
            "오차항목": df_all[(df_all['금액오차']!=0)|(df_all['수량오차']!=0)], 
            "비교분석": df_all[['코드', '품명', '매입행', '매출행', '수량오차', '금액오차']], 
            "매입처 미이월": df_buy_unmoved_disp, 
            "매출처 당월": df_sell_current_disp
        }
        target_df = display_map[view_option]

        # 집계 바
        if not target_df.empty and '금액오차' in target_df.columns:
            st.markdown(f'<div class="stat-container"><div class="stat-item">📈 (+)합계: {target_df[target_df["금액오차"]>0]["금액오차"].sum():,.0f}원</div><div class="stat-item">📉 (-)합계: {target_df[target_df["금액오차"]<0]["금액오차"].sum():,.0f}원</div><div class="stat-item">⚖️ 모드 합계: {target_df["금액오차"].sum():,.0f}원</div></div>', unsafe_allow_html=True)
        
        st.dataframe(target_df, use_container_width=True)

        # 6. 최종 리포트 카드 (제외 로직 적용)
        st.divider()
        st.markdown('<p class="sub-title">✅ 설정 반영 후 최종 금액</p>', unsafe_allow_html=True)
        
        # 제외할 금액 계산: '미이월'로 분류된 금액과 '당월'로 분류된 금액만 합산
        unmoved_sum = df_buy_unmoved['합계금액'].sum() if exclude_buy_amt else 0
        current_sum = df_sell_current['합계'].sum() if exclude_sell_amt else 0
        
        final_buy_total = df_b_proc['합계금액'].sum() - unmoved_sum
        final_sell_total = df_s_proc['합계'].sum() - current_sum
        final_diff = final_buy_total - final_sell_total

        c1, c2, c3 = st.columns(3)
        c1.markdown(f'<div class="report-card"><p class="card-label">최종 매입 합계</p><p style="color:red; font-size:12px;">미이월 제외: -{unmoved_sum:,.0f}</p><p class="price-text">{final_buy_total:,.0f}원</p></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="report-card"><p class="card-label">최종 매출 합계</p><p style="color:red; font-size:12px;">당월 제외: -{current_sum:,.0f}</p><p class="price-text">{final_sell_total:,.0f}원</p></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="report-card"><p class="card-label">최종 결과 차액</p><p style="font-size:12px;">&nbsp;</p><p class="diff-text" style="color:{"#007BFF" if final_diff>=0 else "#FF4B4B"};">{final_diff:,.0f}원</p></div>', unsafe_allow_html=True)

    except Exception as e: st.error(f"오류: {e}")
else: st.info("파일을 업로드해주세요.")