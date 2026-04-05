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
        try:
            return pd.read_csv(file, encoding='cp949')
        except:
            return pd.read_csv(file, encoding='utf-8')
    else:
        return pd.read_excel(file)

def extract_code(text):
    if pd.isna(text): return None
    match = re.search(r'(\d{3}-\d{4})', str(text))
    return match.group(1) if match else None

if buy_file and sell_file:
    try:
        # 1. 데이터 로드 및 원본 행 번호 보존
        df_buy = load_data(buy_file)
        df_sell = load_data(sell_file)
        
        df_buy['원본행'] = df_buy.index + 2 # 엑셀 행 번호와 맞춤 (헤더 포함)
        df_sell['원본행'] = df_sell.index + 2

        # 2. 매입원장 정제
        df_buy_clean = df_buy.dropna(subset=['규격', '합계금액']).copy()
        df_buy_clean['매칭코드'] = df_buy_clean['규격'].apply(extract_code)
        df_buy_clean = df_buy_clean.dropna(subset=['매칭코드'])
        
        df_buy_clean['매입수량'] = pd.to_numeric(df_buy_clean['매입수량'], errors='coerce').fillna(0)
        df_buy_clean['합계금액'] = pd.to_numeric(df_buy_clean['합계금액'], errors='coerce').fillna(0)
        
        # 비교분석용: 행 번호를 리스트로 수집
        buy_grouped = df_buy_clean.groupby('매칭코드').agg({
            '상품명': 'first',
            '매입수량': 'sum',
            '합계금액': 'sum',
            '원본행': lambda x: list(x)
        }).reset_index()
        buy_grouped.rename(columns={'매입수량': '매입원장(수량)', '합계금액': '매입원장(금액)', '원본행': '매입_행번호'}, inplace=True)

        # 3. 매출원장 정제
        df_sell_clean = df_sell.dropna(subset=['상품코드', '합계']).copy()
        df_sell_clean['상품코드'] = df_sell_clean['상품코드'].astype(str).str.strip()
        df_sell_clean['수량'] = pd.to_numeric(df_sell_clean['수량'], errors='coerce').fillna(0)
        df_sell_clean['합계'] = pd.to_numeric(df_sell_clean['합계'], errors='coerce').fillna(0)
        
        sell_grouped = df_sell_clean.groupby('상품코드').agg({
            '품명': 'first',
            '수량': 'sum',
            '합계': 'sum',
            '원본행': lambda x: list(x)
        }).reset_index()
        sell_grouped.rename(columns={'상품코드': '매칭코드', '수량': '매출원장(수량)', '합계': '매출원장(금액)', '원본행': '매출_행번호'}, inplace=True)

        # 4. 데이터 병합 및 오차 계산
        merged_df = pd.merge(buy_grouped, sell_grouped, on='매칭코드', how='outer').fillna(0)
        merged_df['수량오차'] = merged_df['매입원장(수량)'] - merged_df['매출원장(수량)']
        merged_df['금액오차'] = merged_df['매입원장(금액)'] - merged_df['매출원장(금액)']

        # 5. 상단 옵션 선택 UI
        col_title, col_opt = st.columns([2, 1])
        with col_title:
            st.subheader("📋 매입/매출 첨부파일기준")
        with col_opt:
            view_option = st.selectbox("표시 모드 선택", ["전체", "오차항목", "비교분석"])

        # 데이터 필터링 로직
        if view_option == "전체":
            display_df = merged_df[['매칭코드', '상품명', '매입원장(수량)', '매출원장(수량)', '수량오차', '매입원장(금액)', '매출원장(금액)', '금액오차']]
        elif view_option == "오차항목":
            display_df = merged_df[(merged_df['수량오차'] != 0) | (merged_df['금액오차'] != 0)]
            display_df = display_df[['매칭코드', '상품명', '매입원장(수량)', '매출원장(수량)', '수량오차', '매입원장(금액)', '매출원장(금액)', '금액오차']]
        else: # 비교분석
            display_df = merged_df[['매칭코드', '상품명', '매입_행번호', '매출_행번호', '수량오차', '금액오차']]
            st.info("💡 '비교분석' 모드에서는 각 장부의 몇 번째 행(엑셀 기준) 데이터가 합산되었는지 보여줍니다.")

        st.dataframe(display_df, use_container_width=True)

        # 6. 총합계 섹션 (하단부)
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("매입원장 총수량", f"{merged_df['매입원장(수량)'].sum():,.0f}")
        with c2: st.metric("매입원장 총금액", f"{merged_df['매입원장(금액)'].sum():,.0f}")
        with c3: st.metric("매출원장 총수량", f"{merged_df['매출원장(수량)'].sum():,.0f}")
        with c4: st.metric("매출원장 총금액", f"{merged_df['매출원장(금액)'].sum():,.0f}")

        # 7. 엑셀 다운로드
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            merged_df.to_excel(writer, index=False, sheet_name='데이터분석_전체')
        
        st.download_button(
            label="📥 분석 결과 엑셀 다운로드",
            data=output.getvalue(),
            file_name="장부_상세비교_리포트.xlsx"
        )

    except Exception as e:
        st.error(f"오류 발생: {e}")