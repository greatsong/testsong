import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time
import re
from datetime import datetime, timedelta, timezone
from io import StringIO

st.set_page_config(page_title="KOBIS 주간 박스오피스", layout="wide")
st.title("🎬 KOBIS 주간 박스오피스 (52주 누적 조회)")

# =========================================================
# 공통 함수: 데이터 정리 (형변환)
# =========================================================
def clean_dataframe(raw_rows):
    """API 응답 리스트 또는 업로드된 원본 데이터를 표준 컬럼으로 정리"""
    fail_convert_count = 0

    def to_int(value):
        nonlocal fail_convert_count
        try:
            if value is None or value == "":
                fail_convert_count += 1
                return None
            return int(value)
        except (TypeError, ValueError):
            fail_convert_count += 1
            return None

    def to_date_str(value):
        nonlocal fail_convert_count
        if not value or pd.isna(value):
            fail_convert_count += 1
            return None
        value = str(value)
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                continue
        fail_convert_count += 1
        return value

    rows = []
    for item in raw_rows:
        rows.append({
            "집계 기간": item.get("집계 기간") or item.get("_yearWeekTime", ""),
            "영화 코드": item.get("영화 코드") or item.get("movieCd", ""),
            "영화명": item.get("영화명") or item.get("movieNm", ""),
            "개봉일": to_date_str(item.get("개봉일") or item.get("openDt")),
            "순위": to_int(item.get("순위") or item.get("rank")),
            "주간 관객 수": to_int(item.get("주간 관객 수") or item.get("weekAudi")),
            "누적 관객 수": to_int(item.get("누적 관객 수") or item.get("audiAcc")),
        })

    df = pd.DataFrame(rows)
    return df, fail_convert_count


def check_duplicates(df):
    dup_mask = df.duplicated(subset=["영화 코드", "집계 기간"], keep=False)
    dup_count = dup_mask.sum()
    if dup_count > 0:
        st.warning(f"⚠️ 영화 코드와 집계 기간이 동일한 중복 자료가 **{dup_count}건** 발견되었습니다.")
        with st.expander("중복 자료 보기"):
            st.dataframe(df[dup_mask], use_container_width=True)
    else:
        st.success("✅ 영화 코드와 집계 기간이 동일한 중복 자료는 없습니다.")


def show_result_table(df, fail_convert_count, source_label=""):
    st.caption(f"🔧 계산·날짜 형식으로 바꾸지 못한 값: **{fail_convert_count}개**")
    check_duplicates(df)

    st.subheader(f"📋 주간 박스오피스 표 {source_label}")
    st.dataframe(
        df.sort_values(["집계 기간", "순위"], ascending=[False, True]),
        use_container_width=True
    )

    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    st.download_button(
        label="⬇️ CSV 파일로 다운로드",
        data=csv_buffer.getvalue(),
        file_name="kobis_weekly_boxoffice.csv",
        mime="text/csv",
        key=f"download_{source_label}"
    )


# =========================================================
# 공통 함수: 영화별 최근 누적 관객 수 TOP 10 분석
# =========================================================
def show_top10_recent_accumulated(df, source_label):
    st.subheader("🏆 영화별 최근 누적 관객 수 TOP 10")

    df_valid = df.dropna(subset=["영화 코드", "집계 기간"]).copy()

    if df_valid.empty:
        st.info("분석할 데이터가 없습니다.")
        return

    week_count_by_movie = df_valid.groupby("영화 코드")["집계 기간"].nunique().rename("등장 주 수")

    df_valid_sorted = df_valid.sort_values("집계 기간", ascending=False)
    latest_rows = df_valid_sorted.drop_duplicates(subset="영화 코드", keep="first").copy()

    latest_rows = latest_rows.merge(week_count_by_movie, on="영화 코드", how="left")

    latest_rows = latest_rows.dropna(subset=["누적 관객 수"])
    top10 = latest_rows.sort_values("누적 관객 수", ascending=False).head(10).reset_index(drop=True)

    if top10.empty:
        st.info("누적 관객 수 데이터를 찾을 수 없어 순위를 계산할 수 없습니다.")
        return

    st.caption(f"📌 분석에 사용한 자료: **{source_label}**")

    all_periods = sorted(df_valid["집계 기간"].dropna().unique())
    period_start = all_periods[0] if all_periods else "알 수 없음"
    period_end = all_periods[-1] if all_periods else "알 수 없음"
    total_weeks = len(all_periods)

    display_cols = ["영화명", "개봉일", "집계 기간", "누적 관객 수", "등장 주 수"]
    top10_display = top10[display_cols].rename(columns={"집계 기간": "가장 최근 집계 기간"})

    st.dataframe(top10_display, use_container_width=True)

    top10_sorted = top10.sort_values("누적 관객 수", ascending=True)

    fig = px.bar(
        top10_sorted,
        x="누적 관객 수",
        y="영화명",
        orientation="h",
        custom_data=["영화명", "개봉일", "집계 기간", "누적 관객 수", "등장 주 수"],
    )

    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "개봉일: %{customdata[1]}<br>"
            "가장 최근 집계 기간: %{customdata[2]}<br>"
            "누적 관객 수: %{customdata[3]:,}명<br>"
            "등장 주 수: %{customdata[4]}주"
            "<extra></extra>"
        )
    )

    fig.update_layout(
        title=(
            f"영화별 최근 누적 관객 수 TOP 10<br>"
            f"<sub>분석 기간: {period_start} ~ {period_end} | 수집된 주 수: {total_weeks}주 | 자료 출처: {source_label}</sub>"
        ),
        xaxis_title="누적 관객 수",
        yaxis_title="영화명",
        height=600
    )

    st.plotly_chart(fig, use_container_width=True, key=f"top10_chart_{source_label}")


# =========================================================
# 공통 함수: 집계 기간 → 시작 날짜 파싱
# =========================================================
def parse_period_start_date(period_str):
    """
    '2024-01-01~2024-01-07' 또는 '2024-01-01-2024-01-07' 등의 형태에서
    시작 날짜(YYYY-MM-DD)를 추출한다. 실패 시 None 반환.
    """
    if not period_str or pd.isna(period_str):
        return None
    match = re.search(r"(\d{4}-\d{2}-\d{2})", str(period_str))
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


# =========================================================
# 공통 함수: 연속 1위 기간 분석 TOP 10
# =========================================================
def show_top10_longest_first_rank_streak(df, source_label):
    st.subheader("👑 연속 1위 기간이 긴 영화 TOP 10")

    df_valid = df.dropna(subset=["영화 코드", "집계 기간", "순위"]).copy()

    if df_valid.empty:
        st.info("분석할 데이터가 없습니다.")
        return

    # 집계 기간별 시작 날짜 매핑 (같은 집계 기간 문자열은 같은 시작 날짜를 가짐)
    unique_periods = df_valid["집계 기간"].unique()
    period_to_start_date = {p: parse_period_start_date(p) for p in unique_periods}

    df_valid["_시작일"] = df_valid["집계 기간"].map(period_to_start_date)

    # 시작일을 파싱하지 못한 행은 연속성 계산에서 제외
    parse_fail_count = df_valid["_시작일"].isna().sum()
    if parse_fail_count > 0:
        st.caption(f"⚠️ 집계 기간에서 날짜를 인식하지 못해 연속성 계산에서 제외한 자료: **{parse_fail_count}건**")

    df_valid = df_valid.dropna(subset=["_시작일"])

    if df_valid.empty:
        st.info("집계 기간의 날짜를 인식할 수 없어 연속 1위 분석을 진행할 수 없습니다.")
        return

    # 전체 수집된 주(고유 시작일) 목록 - 실제 분석 기간 계산용
    all_start_dates = sorted(df_valid["_시작일"].unique())
    period_start_label = all_start_dates[0].strftime("%Y-%m-%d")
    period_end_label = all_start_dates[-1].strftime("%Y-%m-%d")
    total_weeks = len(all_start_dates)

    # 각 집계 기간(주)에서 순위 1위인 영화만 추출
    first_rank_df = df_valid[df_valid["순위"] == 1].copy()

    if first_rank_df.empty:
        st.info("1위를 차지한 영화 기록을 찾을 수 없습니다.")
        return

    # 시작일 기준 정렬
    first_rank_df = first_rank_df.sort_values("_시작일").reset_index(drop=True)

    # 영화별 전체 1위 횟수
    total_first_rank_count = first_rank_df.groupby("영화 코드").size().rename("전체 1위 횟수")

    # 영화 코드 -> 영화명, 개봉일 매핑 (가장 최근 값 사용)
    info_map = (
        df_valid.sort_values("_시작일", ascending=False)
        .drop_duplicates(subset="영화 코드", keep="first")
        .set_index("영화 코드")[["영화명", "개봉일"]]
    )

    # -----------------------------
    # 영화별 연속 1위 기간(최대 연속 주 수) 계산
    # 수집하지 못한 주가 중간에 있으면 연속으로 보지 않음 -> 시작일 차이가 정확히 7일인 경우만 연속
    # -----------------------------
    max_streak_by_movie = {}

    for movie_cd, group in first_rank_df.groupby("영화 코드"):
        dates = sorted(group["_시작일"].unique())

        if len(dates) == 0:
            max_streak_by_movie[movie_cd] = 0
            continue

        max_streak = 1
        current_streak = 1

        for i in range(1, len(dates)):
            gap_days = (dates[i] - dates[i - 1]).days
            if gap_days == 7:
                current_streak += 1
            else:
                current_streak = 1
            max_streak = max(max_streak, current_streak)

        max_streak_by_movie[movie_cd] = max_streak

    streak_series = pd.Series(max_streak_by_movie, name="가장 긴 연속 1위 기간")

    # 결과 통합
    result_df = pd.concat([total_first_rank_count, streak_series], axis=1).reset_index()
    result_df = result_df.rename(columns={"index": "영화 코드"})
    result_df = result_df.merge(info_map, on="영화 코드", how="left")

    # 정렬: 연속 1위 기간 내림차순 -> 동일하면 전체 1위 횟수 내림차순
    result_df = result_df.sort_values(
        by=["가장 긴 연속 1위 기간", "전체 1위 횟수"],
        ascending=[False, False]
    ).reset_index(drop=True)

    top10_streak = result_df.head(10).copy()

    if top10_streak.empty:
        st.info("연속 1위 데이터를 계산할 수 없습니다.")
        return

    st.caption(f"📌 분석에 사용한 자료: **{source_label}**")

    display_cols = ["영화명", "개봉일", "전체 1위 횟수", "가장 긴 연속 1위 기간"]
    st.dataframe(top10_streak[display_cols], use_container_width=True)

    # -----------------------------
    # Plotly 가로 막대그래프
    # -----------------------------
    top10_streak_sorted = top10_streak.sort_values("가장 긴 연속 1위 기간", ascending=True)

    fig = px.bar(
        top10_streak_sorted,
        x="가장 긴 연속 1위 기간",
        y="영화명",
        orientation="h",
        custom_data=["영화명", "개봉일", "전체 1위 횟수", "가장 긴 연속 1위 기간"],
    )

    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "개봉일: %{customdata[1]}<br>"
            "전체 1위 횟수: %{customdata[2]}회<br>"
            "가장 긴 연속 1위 기간: %{customdata[3]}주"
            "<extra></extra>"
        )
    )

    fig.update_layout(
        title=(
            f"연속 1위 기간이 긴 영화 TOP 10<br>"
            f"<sub>분석 기간: {period_start_label} ~ {period_end_label} | 수집된 주 수: {total_weeks}주 | 자료 출처: {source_label}</sub>"
        ),
        xaxis_title="가장 긴 연속 1위 기간 (주)",
        yaxis_title="영화명",
        height=600
    )

    st.plotly_chart(fig, use_container_width=True, key=f"streak_chart_{source_label}")


# =========================================================
# 1. 인증키 확인 (Streamlit Secrets 사용)
# =========================================================
KOBIS_KEY = st.secrets.get("KOBIS_KEY", None)

tab_api, tab_upload = st.tabs(["🌐 API로 불러오기", "📁 CSV 업로드로 분석"])

# =========================================================
# [탭 1] API로 52주치 데이터 수집
# =========================================================
with tab_api:
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
    else:
        KST = timezone(timedelta(hours=9))
        today_kst = datetime.now(KST).date()

        selected_date = st.date_input(
            "기준 날짜를 선택하세요 (이 날짜부터 7일씩 거슬러 올라가며 52주치를 조회합니다)",
            value=today_kst,
            max_value=today_kst
        )

        run_button = st.button("📥 52주치 데이터 불러오기")

        REQUEST_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchWeeklyBoxOfficeList.json"

        def fetch_weekly_box_office(target_dt_str, week_gb="0"):
            """
            공식 안내: targetDt에 조회하고자 하는 주(week)에 포함된 임의의 날짜(YYYYMMDD)를 넣으면
            KOBIS가 해당 날짜가 속한 주의 집계 기간으로 자동 변환하여 응답한다.
            weekGb: 0(주간, 월~일), 1(주말), 2(주중)
            """
            params = {
                "key": KOBIS_KEY,
                "targetDt": target_dt_str,
                "weekGb": week_gb
            }
            try:
                response = requests.get(REQUEST_URL, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                result = data.get("boxOfficeResult", {})
                week_list = result.get("weeklyBoxOfficeList", [])
                year_week_time = result.get("yearWeekTime", None)
                return True, week_list, year_week_time, None
            except requests.exceptions.Timeout:
                return False, [], None, "10초 동안 응답이 없었습니다."
            except requests.exceptions.HTTPError as e:
                return False, [], None, f"HTTP 오류 ({e.response.status_code})"
            except requests.exceptions.RequestException as e:
                return False, [], None, f"네트워크 오류 ({e})"
            except ValueError:
                return False, [], None, "응답 데이터 형식 오류"

        if run_button:
            request_count = 0
            success_count = 0
            fail_count = 0
            fail_details = []

            collected_periods = set()
            all_rows = []

            current_date = selected_date
            progress = st.progress(0)
            status_text = st.empty()

            week_index = 0
            max_attempts = 104

            while len(collected_periods) < 52 and week_index < max_attempts:
                target_dt_str = current_date.strftime("%Y%m%d")
                status_text.text(f"조회 중... ({target_dt_str}) - 확보된 집계 기간: {len(collected_periods)}/52")

                request_count += 1
                ok, week_list, year_week_time, error_msg = fetch_weekly_box_office(target_dt_str)

                if ok:
                    if year_week_time and year_week_time not in collected_periods:
                        collected_periods.add(year_week_time)
                        success_count += 1
                        for item in week_list:
                            item["_yearWeekTime"] = year_week_time
                        all_rows.extend(week_list)
                    elif year_week_time in collected_periods:
                        success_count += 1
                    else:
                        fail_count += 1
                        fail_details.append((target_dt_str, "집계 기간 정보 없음"))
                else:
                    fail_count += 1
                    fail_details.append((target_dt_str, error_msg))

                progress.progress(min(len(collected_periods) / 52, 1.0))

                current_date = current_date - timedelta(days=7)
                week_index += 1
                time.sleep(0.05)

            status_text.empty()
            progress.empty()

            st.subheader("📊 요청 결과 요약")
            c1, c2, c3 = st.columns(3)
            c1.metric("요청 횟수", f"{request_count}회")
            c2.metric("성공 횟수", f"{success_count}회")
            c3.metric("실패 횟수", f"{fail_count}회")

            if fail_details:
                with st.expander("⚠️ 실패한 요청 상세 보기"):
                    for dt, msg in fail_details:
                        st.write(f"- 기준일 {dt}: {msg}")
                st.info("실패한 주는 데이터를 0으로 채우지 않고 결과에서 제외했습니다.")

            if not all_rows:
                st.warning("불러온 주간 박스오피스 데이터가 없습니다. 날짜를 바꿔 다시 시도해 주세요.")
            else:
                st.subheader("🗓️ 실제로 불러온 집계 기간")
                sorted_periods = sorted(collected_periods, reverse=True)
                st.write(f"총 **{len(sorted_periods)}개**의 서로 다른 집계 기간을 수집했습니다.")
                with st.expander("집계 기간 전체 목록 보기"):
                    for p in sorted_periods:
                        st.write(f"- {p}")

                df, fail_convert_count = clean_dataframe(all_rows)
                show_result_table(df, fail_convert_count, source_label="API 수집 결과")

                st.divider()
                show_top10_recent_accumulated(df, source_label="API로 수집한 자료")

                st.divider()
                show_top10_longest_first_rank_streak(df, source_label="API로 수집한 자료")

# =========================================================
# [탭 2] CSV 업로드로 분석
# =========================================================
with tab_upload:
    st.write("이전에 다운로드한 CSV 파일을 업로드하면 동일한 형식으로 표와 중복 검사, TOP 10 분석을 확인할 수 있습니다.")

    uploaded_file = st.file_uploader("CSV 파일 업로드", type=["csv"])

    if uploaded_file is not None:
        try:
            upload_df_raw = pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"⚠️ CSV 파일을 읽는 중 오류가 발생했습니다: {e}")
            upload_df_raw = None

        if upload_df_raw is not None:
            required_cols = ["집계 기간", "영화 코드", "영화명", "개봉일", "순위", "주간 관객 수", "누적 관객 수"]
            missing_cols = [c for c in required_cols if c not in upload_df_raw.columns]

            if missing_cols:
                st.error(f"⚠️ 다음 필수 컬럼이 없습니다: {', '.join(missing_cols)}")
            else:
                raw_rows = upload_df_raw.to_dict(orient="records")
                df_upload, fail_convert_count_upload = clean_dataframe(raw_rows)

                st.write(f"📄 업로드된 자료 건수: **{len(df_upload)}건**")

                sorted_periods_upload = sorted(df_upload["집계 기간"].dropna().unique(), reverse=True)
                st.subheader("🗓️ 업로드 파일에 포함된 집계 기간")
                st.write(f"총 **{len(sorted_periods_upload)}개**의 서로 다른 집계 기간이 포함되어 있습니다.")
                with st.expander("집계 기간 전체 목록 보기"):
                    for p in sorted_periods_upload:
                        st.write(f"- {p}")

                show_result_table(df_upload, fail_convert_count_upload, source_label="업로드 파일 분석 결과")

                st.divider()
                show_top10_recent_accumulated(df_upload, source_label="업로드한 CSV 파일")

                st.divider()
                show_top10_longest_first_rank_streak(df_upload, source_label="업로드한 CSV 파일")
    else:
        st.info("분석할 CSV 파일을 업로드해 주세요.")
