import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="장부 오차 검증 툴", layout="wide")
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

# --- 사이드바 처리 옵션 ---
st.sidebar.header("⚙️ 데이터 처리 옵션")

# 1. 매출기준 반품 처리
is_return_zero = st.sidebar.checkbox("매출기준 반품 (-)수량 0표기진행")

# 2. 매입장부 이월 설정
st.sidebar.divider()
st.sidebar.subheader("📅 매입장부 이월 설정")
exclude_buy_amt = st.sidebar.checkbox("선택한 매입 일자 금액 제외하기", key="ex_buy")
buy_dates = st.sidebar.multiselect("체크할 매입 일자 선택", [25, 26, 27, 28, 29, 30, 31])

# 3. 매출장부 당월 설정
st.sidebar.subheader("📅 매출장부 당월 설정")
exclude_sell_amt = st.sidebar.checkbox("선택한 매출 일자 금액 제외하기", key="ex_sell")
sell_dates = st.sidebar.multiselect("체크할 매출 일자 선택", [25, 26, 27, 28, 29, 30, 31])

if buy_file and sell_file:
    try:
        # 데이터 로드
        df_buy = load_data(buy_file)
        df_sell = load_data(sell_file)
        
        # 일자 추출 및 기본 정리
        df_buy['일자_숫자'] = pd.to_datetime(df_buy['매입일자'], errors='coerce').dt.day
        df_sell['일자_숫자'] = pd.to_datetime(df_sell['매출일자'], errors='coerce').dt.day
        df_buy['원본행'] = df_buy.index + 2
        df_sell['원본행'] = df_sell.index + 2

        # --- 매입원장 정제 및 금액 제외 로직 ---
        df_buy_clean = df_buy.dropna(subset=['규격', '합계금액']).copy()
        df_buy_clean['매칭코드'] = df_buy_clean['규격'].apply(extract_code)
        df_buy_clean = df_buy_clean.dropna(subset=['매칭코드'])
        
        df_buy_clean['매입수량'] = pd.to_numeric(df_buy_clean['매입수량'], errors='coerce').fillna(0)
        df_buy_clean['합계금액'] = pd.to_numeric(df_buy_clean['합계금액'], errors='coerce').fillna(0)
        
        if exclude_buy_amt and buy_dates:
            mask_ex = df_buy_clean['일자_숫자'].isin(buy_dates)
            df_buy_clean.loc[mask_ex, '합계금액'] = 0
            df_buy_clean.loc[mask_ex, '매입수량'] = 0

        # 에러 방지용 리스트 강제 변환 (hasattr 체크)
        buy_grouped = df_buy_clean.groupby('매칭코드').agg({
            '상품명': 'first', '매입수량': 'sum', '합계금액': 'sum',
            '일자_숫자': lambda x: list(x) if hasattr(x, '__iter__') else [x],
            '원본행': lambda x: list(x) if hasattr(x, '__iter__') else [x]
        }).reset_index()
        buy_grouped.columns = ['매칭코드', '상품명', '매입원장(수량)', '매입원장(금액)', '매입일자들', '매입_행번호']

        # --- 매출원장 정제 및 금액 제외 로직 ---
        df_sell_clean = df_sell.dropna(subset=['상품코드', '합계']).copy()
        df_sell_clean['상품코드'] = df_sell_clean['상품코드'].astype(str).str.strip()
        df_sell_clean['수량'] = pd.to_numeric(df_sell_clean['수량'], errors='coerce').fillna(0)
        
        if is_return_zero:
            df_sell_clean.loc[df_sell_clean['수량'] < 0, '수량'] = 0
        
        df_sell_clean['합계'] = pd.to_numeric(df_sell_clean['합계'], errors='coerce').fillna(0)
        if exclude_sell_amt and sell_dates:
            mask_ex_s = df_sell_clean['일자_숫자'].isin(sell_dates)
            df_sell_clean.loc[mask_ex_s, '합계'] = 0
            df_sell_clean.loc[mask_ex_s, '수량'] = 0

        sell_grouped = df_sell_clean.groupby('상품코드').agg({
            '품명': 'first', '수량': 'sum', '합계': 'sum',
            '일자_숫자': lambda x: list(x) if hasattr(x, '__iter__') else [x],
            '원본행': lambda x: list(x) if hasattr(x, '__iter__') else [x]
        }).reset_index()
        sell_grouped.columns = ['매칭코드', '품명', '매출원장(수량)', '매출원장(금액)', '매출일자들', '매출_행번호']

        # --- 데이터 병합 및 분석 ---
        merged_df = pd.merge(buy_grouped, sell_grouped, on='매칭코드', how='outer').fillna(0)
        merged_df['수량오차'] = merged_df['매입원장(수량)'] - merged_df['매출원장(수량)']
        merged_df['금액오차'] = merged_df['매입원장(금액)'] - merged_df['매출원장(금액)']

        # 분석 모드별 데이터프레임 정의
        df_all = merged_df[['매칭코드', '상품명', '매입원장(수량)', '매출원장(수량)', '수량오차', '매입원장(금액)', '매출원장(금액)', '금액오차']]
        df_error = df_all[(df_all['수량오차'] != 0) | (df_all['금액오차'] != 0)]
        df_analysis = merged_df[['매칭코드', '상품명', '매입_행번호', '매출_행번호', '수량오차', '금액오차']]
        
        mask_buy = merged_df.apply(lambda r: r['매출원장(수량)'] == 0 and r['매입원장(수량)'] > 0 and any(d in buy_dates for d in r['매입일자들']), axis=1)
        df_buy_unmoved = merged_df[mask_buy][['매칭코드', '상품명', '매입일자들', '매입원장(수량)', '매입_행번호']]
        
        mask_sell = merged_df.apply(lambda r: r['매입원장(수량)'] == 0 and r['매출원장(수량)'] > 0 and any(d in sell_dates for d in r['매출일자들']), axis=1)
        df_sell_current = merged_df[mask_sell][['매칭코드', '품명', '매출일자들', '매출원장(수량)', '매출_행번호']]

        # --- 화면 UI ---
        st.subheader("📋 매입/매출 첨부파일기준")
        view_option = st.selectbox("표시 모드 선택", ["전체", "오차항목", "비교분석", "매입처 미이월", "매출처 당월"])
        
        display_map = {"전체": df_all, "오차항목": df_error, "비교분석": df_analysis, "매입처 미이월": df_buy_unmoved, "매출처 당월": df_sell_current}
        st.dataframe(display_map[view_option], use_container_width=True)

        # --- 총합계 요약 ---
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("매입원장 총수량", f"{merged_df['매입원장(수량)'].sum():,.0f}")
        with c2: st.metric("매입원장 총금액", f"{merged_df['매입원장(금액)'].sum():,.0f}")
        with c3: st.metric("매출원장 총수량", f"{merged_df['매출원장(수량)'].sum():,.0f}")
        with c4: st.metric("매출원장 총금액", f"{merged_df['매출원장(금액)'].sum():,.0f}")

        # --- 시트별 통합 엑셀 다운로드 ---
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_all.to_excel(writer, index=False, sheet_name='1_전체')
            df_error.to_excel(writer, index=False, sheet_name='2_오차항목')
            df_analysis.to_excel(writer, index=False, sheet_name='3_비교분석_행번호')
            df_buy_unmoved.to_excel(writer, index=False, sheet_name='4_매입처_미이월')
            df_sell_current.to_excel(writer, index=False, sheet_name='5_매출처_당월')
        
        st.download_button(label="📥 모든 결과 시트 통합 엑셀 다운로드", data=output.getvalue(), file_name="장부_통합분석_리포트.xlsx")

    except Exception as e:
        st.error(f"오류 발생: {e}")