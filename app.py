import streamlit as st
import pandas as pd
import io

# 페이지 설정
st.set_page_config(page_title="매입/매출 원장 상세 비교 분석 툴", layout="wide")

# 스타일 설정
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 매입/매출 원장 상세 비교 분석 툴")

# 파일 업로드
col_up1, col_up2 = st.columns(2)
with col_up1:
    p_file = st.file_uploader("📥 매입원장 (CSV/Excel) 업로드", type=['csv', 'xlsx'])
with col_up2:
    s_file = st.file_uploader("📤 매출원장 (CSV/Excel) 업로드", type=['csv', 'xlsx'])

def clean_amount(series):
    """금액 데이터에서 콤마나 문자를 제거하고 숫자로 변환"""
    return pd.to_numeric(series.astype(str).str.replace(',', '').str.extract('(\d+)', expand=False), errors='coerce').fillna(0)

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

        # 컬럼명 정리 및 데이터 클리닝
        df_p.columns = df_p.columns.str.strip()
        df_s.columns = df_s.columns.str.strip()

        # [중요] 금액 컬럼 강제 숫자 변환 (오류 방지)
        df_p['매입금액'] = clean_amount(df_p['매입금액'])
        df_s['매출금액'] = clean_amount(df_s['매출금액'])

        # 날짜 컬럼 문자열 통일 (비교 오류 방지)
        df_p['매입일자'] = df_p['매입일자'].astype(str).str.strip()
        df_s['매출일자'] = df_s['매출일자'].astype(str).str.strip()

        # --- 사이드바 설정 ---
        st.sidebar.header("⚙️ 데이터 처리 옵션")
        p_dates = sorted(df_p['매입일자'].unique())
        exclude_p_dates = st.sidebar.multiselect("📅 매입장부 미 이월 설정", options=p_dates)
        
        s_dates = sorted(df_s['매출일자'].unique())
        exclude_s_dates = st.sidebar.multiselect("📅 매출장부 당월 설정", options=s_dates)

        # --- 금액 계산 ---
        total_p_amt = df_p['매입금액'].sum()
        total_s_amt = df_s['매출금액'].sum()

        ex_p_amt = df_p[df_p['매입일자'].isin(exclude_p_dates)]['매입금액'].sum()
        ex_s_amt = df_s[df_s['매출일자'].isin(exclude_s_dates)]['매출금액'].sum()

        final_p_amt = total_p_amt - ex_p_amt
        final_s_amt = total_s_amt - ex_s_amt

        # --- 지표 출력 ---
        st.markdown("### 📌 데이터 요약 및 조정 현황")
        m_col1, m_col2, m_col3 = st.columns(3)

        with m_col1:
            st.metric("📦 매입원장 총액", f"{int(total_p_amt):,}원")
            st.info(f"**매입장부 미이월 합계:** {int(ex_p_amt):,}원")
            st.success(f"**최종 매입금액:** {int(final_p_amt):,}원")

        with m_col2:
            st.metric("💰 매출원장 총액", f"{int(total_s_amt):,}원")
            st.info(f"**매출장부 당월 합계:** {int(ex_s_amt):,}원")
            st.success(f"**최종 매출금액:** {int(final_s_amt):,}원")

        with m_col3:
            diff_final = final_s_amt - final_p_amt
            st.metric("⚖️ 매입/매출 차액 (원천)", f"{int(total_s_amt - total_p_amt):,}원")
            st.write(f"**조정 후 최종 차액**")
            st.subheader(f"{int(diff_final):,}원")

        # --- 결과 테이블 및 다운로드 ---
        # 실제 병합 로직 (필요에 따라 수정)
        df_result = pd.concat([df_p, df_s], axis=1) # 예시용 단순 결합
        
        # 칼럼명 언더바 제거 반영
        df_result.columns = [col.replace('_행번호', '행번호').replace('매입일자들', '매입일자').replace('매출일자들', '매출일자') for col in df_result.columns]

        st.markdown("---")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_result.to_excel(writer, index=False)
        
        st.download_button(label="📥 분석 결과 엑셀 다운로드", data=output.getvalue(), file_name="분석결과.xlsx")
        st.dataframe(df_result, use_container_width=True)

    except Exception as e:
        st.error(f"오류 발생: {e}")