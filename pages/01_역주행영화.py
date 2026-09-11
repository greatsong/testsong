import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

DATA_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/kobis_weekly.csv"

st.set_page_config(page_title="역주행 영화 후보 찾기", layout="wide")
st.title("🎬 뒤늦게 관객이 늘어난 영화(역주행 후보) 찾기")

st.info(
    "ℹ️ 이 데이터는 **주간 박스오피스 상위 10편**만 포함하고 있습니다. "
    "따라서 10위 밖으로 밀려난 주는 기록이 존재하지 않습니다."
)

# ----------------------------------------------------------------------
# 1. 데이터 불러오기
# ----------------------------------------------------------------------
@st.cache_data
def load_data(url: str):
    df = pd.read_csv(
        url,
        encoding="utf-8",
        dtype={"영화코드": str},  # 영화코드는 반드시 문자로 취급
    )
    return df


try:
    raw_df = load_data(DATA_URL)
except Exception as e:
    st.error(
        "❌ 데이터를 불러오지 못했습니다.\n\n"
        f"**원인:** {e}\n\n"
        "인터넷 연결 상태나 주소가 올바른지 확인해 주세요. "
        "GitHub 서버가 잠시 응답하지 않을 수도 있습니다."
    )
    st.stop()

# ----------------------------------------------------------------------
# 2. 자료형 변환
# ----------------------------------------------------------------------
df = raw_df.copy()

# 날짜 변환
df["주시작일_변환"] = pd.to_datetime(df["주시작일"], format="%Y%m%d", errors="coerce")
df["개봉일_변환"] = pd.to_datetime(df["개봉일"], format="%Y-%m-%d", errors="coerce")

# 숫자 변환
df["주간관객_변환"] = pd.to_numeric(df["주간관객"], errors="coerce")
df["누적관객_변환"] = pd.to_numeric(df["누적관객"], errors="coerce")
df["순위_변환"] = pd.to_numeric(df["순위"], errors="coerce")

# 변환 실패 개수 집계
fail_counts = {
    "주시작일": df["주시작일_변환"].isna().sum(),
    "개봉일": df["개봉일_변환"].isna().sum(),
    "주간관객": df["주간관객_변환"].isna().sum(),
    "누적관객": df["누적관객_변환"].isna().sum(),
    "순위": df["순위_변환"].isna().sum(),
}

st.subheader("📋 데이터 변환 결과")
fail_msg = ", ".join([f"{k} 변환 실패 {v}건" for k, v in fail_counts.items()])
st.write(f"변환 실패 건수: {fail_msg}")

# 변환에 실패한 행 제거 (핵심 컬럼 기준)
df = df.dropna(subset=["주시작일_변환", "개봉일_변환", "주간관객_변환"]).copy()

# ----------------------------------------------------------------------
# 3. 데이터 개요
# ----------------------------------------------------------------------
st.subheader("📊 데이터 개요")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("시작일", df["주시작일_변환"].min().strftime("%Y-%m-%d"))
col2.metric("마지막 날짜", df["주시작일_변환"].max().strftime("%Y-%m-%d"))
col3.metric("서로 다른 주의 수", df["주시작일_변환"].nunique())
col4.metric("영화 수", df["영화코드"].nunique())
col5.metric("전체 행 수", len(df))

# ----------------------------------------------------------------------
# 4. 개봉일 기준 1주차 계산
# ----------------------------------------------------------------------
# 개봉일이 포함된 주의 월요일을 1주차 시작으로 정의
df["개봉주_월요일"] = df["개봉일_변환"] - pd.to_timedelta(df["개봉일_변환"].dt.weekday, unit="D")

# 주시작일도 해당 주의 월요일이라고 가정하고, 주차 = (주시작일 - 개봉주_월요일)/7 + 1
df["주차"] = ((df["주시작일_변환"] - df["개봉주_월요일"]).dt.days // 7) + 1

# 개봉 이전 기록(주차 < 1)은 제외
df = df[df["주차"] >= 1].copy()

# ----------------------------------------------------------------------
# 5. 영화별 집계 및 필터링
# ----------------------------------------------------------------------
movie_groups = df.groupby("영화코드")

records = []
excluded_no_week12 = 0
excluded_few_records = 0
excluded_zero_or_invalid_start = 0

for code, g in movie_groups:
    movie_name = g["영화명"].iloc[0]
    open_date = g["개봉일_변환"].iloc[0]

    has_week1 = (g["주차"] == 1).any()
    has_week2 = (g["주차"] == 2).any()

    # 조건: 1주차, 2주차 기록 모두 있어야 함
    if not (has_week1 and has_week2):
        excluded_no_week12 += 1
        continue

    # 조건: 첫 8주 안에 기록 4개 이상
    first8 = g[(g["주차"] >= 1) & (g["주차"] <= 8)]
    if len(first8) < 4:
        excluded_few_records += 1
        continue

    week1_val = g.loc[g["주차"] == 1, "주간관객_변환"].max()
    week2_val = g.loc[g["주차"] == 2, "주간관객_변환"].max()

    early_count = max(week1_val, week2_val)

    # 조건: 초반 관객 수가 0이거나 숫자가 아니면 제외
    if pd.isna(early_count) or early_count <= 0:
        excluded_zero_or_invalid_start += 1
        continue

    later = g[(g["주차"] >= 3) & (g["주차"] <= 8)]
    if later.empty:
        continue

    peak_idx = later["주간관객_변환"].idxmax()
    peak_count = later.loc[peak_idx, "주간관객_변환"]
    peak_week = later.loc[peak_idx, "주차"]

    ratio = peak_count / early_count

    records.append(
        {
            "영화코드": code,
            "영화명": movie_name,
            "개봉일": open_date,
            "초반_관객수": early_count,
            "정점_주차": int(peak_week),
            "정점_관객수": peak_count,
            "증가_배율": ratio,
        }
    )

result_df = pd.DataFrame(records)

# 역주행 후보: 이후 최고 관객 수가 초반 관객 수보다 큰 영화만
candidates_df = result_df[result_df["정점_관객수"] > result_df["초반_관객수"]].copy()
candidates_df = candidates_df.sort_values("증가_배율", ascending=False)

# ----------------------------------------------------------------------
# 6. 필터링 결과 안내
# ----------------------------------------------------------------------
st.subheader("🔍 필터링 결과")
st.write(
    f"- 1주차/2주차 기록이 모두 없어 제외된 영화 수: **{excluded_no_week12}**\n"
    f"- 첫 8주 기록이 4개 미만이라 제외된 영화 수: **{excluded_few_records}**\n"
    f"- 초반 관객 수가 0이거나 유효하지 않아 제외된 영화 수: **{excluded_zero_or_invalid_start}**\n"
    f"- 최종 역주행 후보 수: **{len(candidates_df)}**"
)

st.warning(
    "⚠️ 아래 결과는 **역주행을 확정한 것이 아니라**, 정해 둔 조건(1·2주차 대비 3~8주차 최고 관객 수 비교)에 따라 "
    "찾아낸 **후보**일 뿐입니다. 실제 흥행 양상은 다를 수 있습니다."
)

if candidates_df.empty:
    st.error("조건을 만족하는 역주행 후보 영화가 없습니다.")
    st.stop()

# ----------------------------------------------------------------------
# 7. 상위 10편 표 출력
# ----------------------------------------------------------------------
st.subheader("🏆 증가 배율 상위 10편")

top10 = candidates_df.head(10).copy()
top10_display = top10.copy()
top10_display["개봉일"] = top10_display["개봉일"].dt.strftime("%Y-%m-%d")
top10_display["증가_배율"] = top10_display["증가_배율"].round(2)

show_cols = ["영화명", "개봉일", "초반_관객수", "정점_주차", "정점_관객수", "증가_배율"]
st.dataframe(top10_display[show_cols], use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------
# 8. Plotly 가로 막대그래프
# ----------------------------------------------------------------------
st.subheader("📈 증가 배율 그래프 (상위 10편)")

bar_df = top10.sort_values("증가_배율", ascending=True)  # 가로막대는 아래에서 위로 그려지므로 순서 조정

fig_bar = px.bar(
    bar_df,
    x="증가_배율",
    y="영화명",
    orientation="h",
    custom_data=["영화명", "개봉일", "초반_관객수", "정점_주차", "정점_관객수", "증가_배율"],
)

fig_bar.update_traces(
    hovertemplate=(
        "<b>%{customdata[0]}</b><br>"
        "개봉일: %{customdata[1]|%Y-%m-%d}<br>"
        "초반 관객 수: %{customdata[2]:,}<br>"
        "정점 주차: %{customdata[3]}주차<br>"
        "정점 관객 수: %{customdata[4]:,}<br>"
        "증가 배율: %{customdata[5]:.2f}배"
        "<extra></extra>"
    )
)

fig_bar.update_layout(
    xaxis_title="증가 배율(배)",
    yaxis_title="영화명",
    height=500,
)

st.plotly_chart(fig_bar, use_container_width=True)

# ----------------------------------------------------------------------
# 9. 영화 선택 및 개봉 후 20주 추이
# ----------------------------------------------------------------------
st.subheader("🎯 영화 선택 후 개봉 후 20주 관객 추이")

selected_movie_name = st.selectbox(
    "역주행 후보 영화를 선택하세요",
    options=top10["영화명"].tolist(),
)

selected_row = top10[top10["영화명"] == selected_movie_name].iloc[0]
selected_code = selected_row["영화코드"]

movie_data = df[df["영화코드"] == selected_code].copy()
movie_data = movie_data[(movie_data["주차"] >= 1) & (movie_data["주차"] <= 20)]

# 1~20주 전체 뼈대를 만들고 실제 데이터를 병합 (없는 주는 NaN으로 비워둠)
full_weeks = pd.DataFrame({"주차": range(1, 21)})
merged = full_weeks.merge(movie_data, on="주차", how="left")

merged["영화명"] = selected_movie_name
merged["개봉일"] = selected_row["개봉일"]

fig_line = go.Figure()

fig_line.add_trace(
    go.Scatter(
        x=merged["주차"],
        y=merged["주간관객_변환"],
        mode="lines+markers",
        connectgaps=False,  # 기록 없는 구간은 선으로 연결하지 않음
        customdata=np.stack(
            [
                merged["영화명"],
                merged["개봉일"].dt.strftime("%Y-%m-%d") if merged["개봉일"].notna().all() else merged["개봉일"],
                merged["주시작일_변환"].dt.strftime("%Y-%m-%d"),
                merged["순위_변환"],
                merged["주간관객_변환"],
            ],
            axis=-1,
        ),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "주차: %{x}주차<br>"
            "주시작일: %{customdata[2]}<br>"
            "순위: %{customdata[3]}위<br>"
            "주간 관객 수: %{customdata[4]:,}"
            "<extra></extra>"
        ),
    )
)

fig_line.update_layout(
    xaxis_title="개봉 후 주차",
    yaxis_title="주간 관객 수",
    height=500,
)

st.plotly_chart(fig_line, use_container_width=True)

st.caption(
    "※ 기록이 없는 주는 주간 박스오피스 10위 밖으로 밀려나 데이터가 존재하지 않는 경우입니다. "
    "이러한 구간은 0으로 채우지 않고 비워 두었으며, 선 그래프에서도 연결하지 않았습니다."
)
