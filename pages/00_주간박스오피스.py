import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="KOBIS 주간 박스오피스", layout="wide")
st.title("🎬 KOBIS 주간 박스오피스 (52주 누적 조회)")

# -----------------------------
# 1. 인증키 확인 (Streamlit Secrets 사용)
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
# 2. 기준 날짜 선택
# -----------------------------
KST = timezone(timedelta(hours=9))
today_kst = datetime.now(KST).date()

selected_date = st.date_input(
    "기준 날짜를 선택하세요 (이 날짜부터 7일씩 거슬러 올라가며 52주치를 조회합니다)",
    value=today_kst,
    max_value=today_kst
)

run_button = st.button("📥 52주치 데이터 불러오기")

# -----------------------------
# 3. KOBIS 주간 박스오피스 요청 함수
# -----------------------------
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

# -----------------------------
# 4. 52주치 수집 (7일씩 거슬러 올라가며, 집계 기간 중복 방지)
# -----------------------------
if run_button:
    request_count = 0
    success_count = 0
    fail_count = 0
    fail_details = []

    collected_periods = set()   # 이미 수집한 집계 기간(yearWeekTime) 저장
    all_rows = []

    current_date = selected_date
    progress = st.progress(0)
    status_text = st.empty()

    week_index = 0
    max_attempts = 104  # 중복을 건너뛰며 진행할 수 있으므로 충분한 시도 횟수 확보

    while len(collected_periods) < 52 and week_index < max_attempts:
        target_dt_str = current_date.strftime("%Y%m%d")
        status_text.text(f"조회 중... ({target_dt_str}) - 확보된 집계 기간: {len(collected_periods)}/52")

        request_count += 1
        ok, week_list, year_week_time, error_msg = fetch_weekly_box_office(target_dt_str)

        if ok:
            if year_week_time and year_week_time not in collected_periods:
                # 새로운 집계 기간만 채택
                collected_periods.add(year_week_time)
                success_count += 1
                for item in week_list:
                    item["_yearWeekTime"] = year_week_time
                all_rows.extend(week_list)
            elif year_week_time in collected_periods:
                # 이미 확보한 집계 기간과 겹침 → 요청은 성공했지만 새 데이터로 채택하지 않음
                success_count += 1
            else:
                # yearWeekTime 자체를 못 받은 경우
                fail_count += 1
                fail_details.append((target_dt_str, "집계 기간 정보 없음"))
        else:
            fail_count += 1
            fail_details.append((target_dt_str, error_msg))

        progress.progress(min(len(collected_periods) / 52, 1.0))

        current_date = current_date - timedelta(days=7)
        week_index += 1
        time.sleep(0.05)  # 과도한 연속 요청 방지

    status_text.empty()
    progress.empty()

    # -----------------------------
    # 5. 요청/성공/실패 결과 요약
    # -----------------------------
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
        st.stop()

    # -----------------------------
    # 6. 실제 수집된 집계 기간 표시
    # -----------------------------
    st.subheader("🗓️ 실제로 불러온 집계 기간")
    sorted_periods = sorted(collected_periods, reverse=True)
    st.write(f"총 **{len(sorted_periods)}개**의 서로 다른 집계 기간을 수집했습니다.")
    with st.expander("집계 기간 전체 목록 보기"):
        for p in sorted_periods:
            st.write(f"- {p}")

    # -----------------------------
    # 7. 데이터 정리 및 형변환
    # -----------------------------
    fail_convert_count = 0

    def to_int(value):
        global fail_convert_count
        try:
            return int(value)
        except (TypeError, ValueError):
            fail_convert_count += 1
            return None

    def to_date_str(value):
        global fail_convert_count
        if not value:
            fail_convert_count += 1
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            try:
                return datetime.strptime(value, "%Y%m%d").strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                fail_convert_count += 1
                return value

    rows = []
    for item in all_rows:
        rows.append({
            "집계 기간": item.get("_yearWeekTime", ""),
            "영화 코드": item.get("movieCd", ""),
            "영화명": item.get("movieNm", ""),
            "개봉일": to_date_str(item.get("openDt")),
            "순위": to_int(item.get("rank")),
            "주간 관객 수": to_int(item.get("weekAudi")),
            "누적 관객 수": to_int(item.get("audiAcc")),
        })

    df = pd.DataFrame(rows)

    st.caption(f"🔧 계산·날짜 형식으로 바꾸지 못한 값: **{fail_convert_count}개**")

    # -----------------------------
    # 8. 중복 확인 (영화 코드 + 집계 기간 기준)
    # -----------------------------
    dup_mask = df.duplicated(subset=["영화 코드", "집계 기간"], keep=False)
    dup_count = dup_mask.sum()

    if dup_count > 0:
        st.warning(f"⚠️ 영화 코드와 집계 기간이 동일한 중복 자료가 **{dup_count}건** 발견되었습니다.")
        with st.expander("중복 자료 보기"):
            st.dataframe(df[dup_mask], use_container_width=True)
    else:
        st.success("✅ 영화 코드와 집계 기간이 동일한 중복 자료는 없습니다.")

    # -----------------------------
    # 9. 최종 표 출력
    # -----------------------------
    st.subheader("📋 주간 박스오피스 표 (52주 누적)")
    st.dataframe(
        df.sort_values(["집계 기간", "순위"], ascending=[False, True]),
        use_container_width=True
    )

else:
    st.info("기준 날짜를 선택한 뒤 '52주치 데이터 불러오기' 버튼을 눌러주세요.")
