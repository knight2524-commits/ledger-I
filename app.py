import streamlit as st
import pandas as pd
import io

# 페이지 설정
st.set_page_config(page_title="매입/매출 원장 상세 비교 분석 툴", layout="wide")

# 스타일 설정 (시인성 강화)
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    div[data-testid="stExpander"] { background-color: white; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 매입/매출 원장 상세 비교 분석 툴")

# 1. 파일 업로드 섹션
col_up1, col_up2 = st.columns(2)
with col_up1:
    p_file = st.file_uploader("📥 매입원장 (CSV/Excel) 업로드", type=['csv', 'xlsx'])
with col_up2:
    s_file = st.file_uploader("📤 매출원장 (CSV/Excel) 업로드", type=['csv', 'xlsx'])

if p_file and s_file:
    try:
        # 데이터 로드
        if p_file.name.endswith('.csv'):
            df_p = pd.read_csv(p_file)
        else:
            df_p = pd.read_excel(p_file, engine='openpyxl')
            
        if s_file.name.endswith('.csv'):
            df_s = pd.read_csv(s_file)
        else:
            df_s = pd.read_excel(s_file, engine='openpyxl')

        # 데이터 전처리 (기본적인 컬럼명 공백 제거 등)
        df_p.columns = df_p.columns.str.strip()
        df_s.columns = df_s.columns.str.strip()

        # --- 데이터 처리 옵션 (사이드바) ---
        st.sidebar.header("⚙️ 데이터 처리 옵션")
        
        # 매입장부 미 이월 설정
        p_dates = sorted(df_p['매입일자'].unique())
        exclude_p_dates = st.sidebar.multiselect("📅 매입장부 미 이월 설정", options=p_dates, help="선택한 날짜의 금액은 총 합계에서 제외됩니다.")
        
        # 매출장부 당월 설정
        s_dates = sorted(df_s['매출일자'].unique())
        exclude_s_dates = st.sidebar.multiselect("📅 매출장부 당월 설정", options=s_dates, help="선택한 날짜의 금액은 총 합계에서 제외됩니다.")

        # --- 금액 계산 로직 ---
        # 1. 전체 총액
        total_p_amt = df_p['매입금액'].sum()
        total_s_amt = df_s['매출금액'].sum()

        # 2. 제외 설정된 금액 합계
        ex_p_amt = df_p[df_p['매입일자'].isin(exclude_p_dates)]['매입금액'].sum()
        ex_s_amt = df_s[df_s['매출일자'].isin(exclude_s_dates)]['매출금액'].sum()

        # 3. 최종 조정 금액
        final_p_amt = total_p_amt - ex_p_amt
        final_s_amt = total_s_amt - ex_s_amt

        # --- 상단 지표 (Metrics) 시인성 강화 ---
        st.markdown("### 📌 데이터 요약 및 조정 현황")
        m_col1, m_col2, m_col3 = st.columns(3)

        with m_col1:
            st.metric("📦 매입원장 총액", f"{total_p_amt:,}원")
            st.info(f"**매입장부 미이월 합계:** {ex_p_amt:,}원")
            st.success(f"**최종 매입금액:** {final_p_amt:,}원")

        with m_col2:
            st.metric("💰 매출원장 총액", f"{total_s_amt:,}원")
            st.info(f"**매출장부 당월 합계:** {ex_s_amt:,}원")
            st.success(f"**최종 매출금액:** {final_s_amt:,}원")

        with m_col3:
            diff_raw = total_s_amt - total_p_amt
            diff_final = final_s_amt - final_p_amt
            st.metric("⚖️ 매입/매출 차액 (원천)", f"{diff_raw:,}원", delta=int(diff_raw))
            st.write(f"**조정 후 최종 차액**")
            st.subheader(f"{diff_final:,}원")

        # --- 상세 데이터 분석 및 칼럼명 수정 ---
        # (예시: 비교분석 로직 수행 후 결과 데이터프레임 df_result가 있다고 가정)
        # 여기서는 요청하신 칼럼명 수정(언더바 제거)을 적용합니다.
        
        # 임시 결과 데이터 생성 (실제 비즈니스 로직에 맞게 수정 필요)
        df_result = pd.merge(df_p, df_s, left_on='품목명', right_on='품목명', how='outer') 
        
        # [칼럼명 변경 적용]
        rename_dict = {
            '매입_행번호': '매입행번호',
            '매출_행번호': '매출행번호',
            '매입일자들': '매입일자',
            '매출일자들': '매출일자'
        }
        df_result.rename(columns=rename_dict, inplace=True)
        
        # 언더바(_)가 포함된 다른 행번호 칼럼들도 일괄 제거 (필요시)
        df_result.columns = [col.replace('_행번호', '행번호') for col in df_result.columns]

        # --- 엑셀 다운로드 기능 ---
        st.markdown("---")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_result.to_excel(writer, index=False, sheet_name='비교분석결과')
        
        st.download_button(
            label="📥 분석 결과 엑셀 다운로드",
            data=output.getvalue(),
            file_name="매입매출_비교분석_결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.markdown("#### 🔍 상세 분석 데이터 (미리보기)")
        st.dataframe(df_result, use_container_width=True)

    except Exception as e:
        st.error(f"오류 발생: {e}")
        st.info("엑셀 파일의 칼럼명이 '매입일자', '매입금액', '매출일자', '매출금액'인지 확인해 주세요.")