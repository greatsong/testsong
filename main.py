import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="일별 박스오피스", layout="wide")
st.title("🎬 KOBIS 일별 박스오피스")

# -----------------------------
# 1. 인증키 확인 (Streamlit Community Cloud Secrets 사용)
# -----------------------------
KOBIS_KEY = st.secrets.get("KOBIS_KEY", None)

if not KOBIS_KEY:
    st.error("❌ KOBIS_KEY(인증키)가 설정되어 있지 않습니다.")
    st.markdown("""
    ### 🔑 인증키 등록 방법
    1. [KOBIS 영화관 입장권 통합전산망 오픈API](https://www.kobis.or.kr/kobisopenapi/homepg/main/main.do) 에서 회원가입 후 인증키를 발급받으세요.
    2. Streamlit Community Cloud에 배포한 앱의 **Settings > Secrets** 메뉴로 이동하세요.
    3. 아래와 같은 형식으로 값을 입력하고 저장하세요.

    ```toml
    KOBIS_KEY = "여기에_발급받은_인증키_입력"
    ```

    4. 저장 후 앱을 다시 실행(Reboot)하면 정상적으로 인증키를 불러옵니다.
    """)
    st.stop()

# -----------------------------
# 2. 날짜 선택 (한국 시간 기준 어제를 기본값으로)
# -----------------------------
KST = timezone(timedelta(hours=9))
yesterday_kst = (datetime.now(KST) - timedelta(days=1)).date()

selected_date = st.date_input(
    "조회할 날짜를 선택하세요",
    value=yesterday_kst,
    max_value=yesterday_kst
)

target_date_str = selected_date.strftime("%Y%m%d")

# -----------------------------
# 3. KOBIS API 요청 (공식 안내 요청 주소 및 항목 이름 그대로 사용)
# -----------------------------
REQUEST_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

params = {
    "key": KOBIS_KEY,
    "targetDt": target_date_str
}

movie_list = []
error_message = None

with st.spinner(f"{target_date_str} 박스오피스 정보를 불러오는 중입니다..."):
    try:
        response = requests.get(REQUEST_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        box_office_result = data.get("boxOfficeResult", {})
        daily_box_office_list = box_office_result.get("dailyBoxOfficeList", [])

        movie_list = daily_box_office_list

    except requests.exceptions.Timeout:
        error_message = "⏱️ 10초 동안 응답이 없습니다. KOBIS 서버가 지연되고 있거나 네트워크 연결 상태를 확인해 주세요."
    except requests.exceptions.HTTPError as e:
        error_message = f"⚠️ 서버 응답 오류가 발생했습니다. (HTTP 상태 코드: {e.response.status_code}) 인증키가 유효한지 확인해 주세요."
    except requests.exceptions.RequestException as e:
        error_message = f"⚠️ 네트워크 연결에 문제가 발생했습니다. 인터넷 연결 상태를 확인해 주세요. ({e})"
    except ValueError:
        error_message = "⚠️ 서버로부터 올바른 형식의 데이터를 받지 못했습니다. 잠시 후 다시 시도해 주세요."

if error_message:
    st.error(error_message)
    st.stop()

# -----------------------------
# 4. 조회 결과 요약
# -----------------------------
st.info(f"📅 실제 조회 기간: **{target_date_str}** | 🎞️ 불러온 영화 수: **{len(movie_list)}건**")

if not movie_list:
    st.warning("해당 날짜의 박스오피스 정보를 찾을 수 없습니다. 다른 날짜를 선택해 주세요.")
    st.stop()

# -----------------------------
# 5. 데이터 정리 및 형변환
# -----------------------------
rows = []
fail_count = 0

for item in movie_list:
    def to_int(value):
        global fail_count
        try:
            return int(value)
        except (TypeError, ValueError):
            fail_count += 1
            return 0

    rows.append({
        "순위": item.get("rank", ""),
        "영화명": item.get("movieNm", ""),
        "개봉일": item.get("openDt", ""),
        "당일 관객 수": to_int(item.get("audiCnt")),
        "누적 관객 수": to_int(item.get("audiAcc")),
        "스크린 수": to_int(item.get("scrnCnt")),
        "상영 횟수": to_int(item.get("showCnt")),
    })

df = pd.DataFrame(rows)

st.caption(f"🔧 숫자로 변환하지 못한 값: **{fail_count}개** (0으로 처리됨)")

# -----------------------------
# 6. 표 출력
# -----------------------------
st.subheader("📋 일별 박스오피스 표")
st.dataframe(df, use_container_width=True)

# -----------------------------
# 7. Plotly 가로 막대그래프
# -----------------------------
st.subheader("📊 당일 관객 수 기준 그래프")

df_sorted = df.sort_values("당일 관객 수", ascending=True)

fig = px.bar(
    df_sorted,
    x="당일 관객 수",
    y="영화명",
    orientation="h",
    custom_data=["영화명", "개봉일", "당일 관객 수", "누적 관객 수"],
)

fig.update_traces(
    hovertemplate=(
        "<b>%{customdata[0]}</b><br>"
        "개봉일: %{customdata[1]}<br>"
        "당일 관객 수: %{customdata[2]:,}명<br>"
        "누적 관객 수: %{customdata[3]:,}명"
        "<extra></extra>"
    )
)

fig.update_layout(
    xaxis_title="당일 관객 수",
    yaxis_title="영화명",
    height=600
)

st.plotly_chart(fig, use_container_width=True)
