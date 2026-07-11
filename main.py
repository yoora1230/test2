import datetime as dt
import math

import pandas as pd
import streamlit as st


# ---------------------------------------------------------
# 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="방배중 시험 플래너",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded",
)

WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

DEFAULT_SUBJECTS = pd.DataFrame(
    [
        {"과목": "국어", "시험 범위": "", "중요도": 3, "현재 자신감": 3, "목표 점수": 90},
        {"과목": "수학", "시험 범위": "", "중요도": 5, "현재 자신감": 2, "목표 점수": 95},
        {"과목": "영어", "시험 범위": "", "중요도": 4, "현재 자신감": 3, "목표 점수": 95},
        {"과목": "과학", "시험 범위": "", "중요도": 4, "현재 자신감": 3, "목표 점수": 90},
        {"과목": "사회", "시험 범위": "", "중요도": 3, "현재 자신감": 3, "목표 점수": 90},
        {"과목": "역사", "시험 범위": "", "중요도": 3, "현재 자신감": 3, "목표 점수": 90},
    ]
)

PLAN_COLUMNS = [
    "날짜",
    "요일",
    "과목",
    "공부 단계",
    "공부 내용",
    "목표 시간(분)",
    "완료",
    "메모",
]


# ---------------------------------------------------------
# 디자인
# ---------------------------------------------------------
st.markdown(
    """
    <style>
        .stApp {
            background:
                radial-gradient(circle at 10% 0%, rgba(59, 130, 246, 0.10), transparent 26%),
                radial-gradient(circle at 95% 5%, rgba(14, 165, 233, 0.09), transparent 24%);
        }

        .main .block-container {
            max-width: 1280px;
            padding-top: 1.6rem;
            padding-bottom: 3rem;
        }

        .hero {
            padding: 1.7rem 1.8rem;
            border-radius: 24px;
            background: linear-gradient(135deg, #123B73 0%, #176B9B 55%, #1D8BB5 100%);
            color: white;
            box-shadow: 0 14px 35px rgba(18, 59, 115, 0.20);
            margin-bottom: 1.2rem;
        }

        .hero h1 {
            margin: 0;
            font-size: 2.15rem;
            letter-spacing: -0.04em;
        }

        .hero p {
            margin: 0.5rem 0 0 0;
            opacity: 0.92;
            font-size: 1.03rem;
        }

        .tip-box {
            padding: 1rem 1.1rem;
            border-radius: 16px;
            border: 1px solid rgba(59, 130, 246, 0.18);
            background: rgba(239, 246, 255, 0.80);
            margin: 0.5rem 0 1rem 0;
        }

        .small-note {
            color: #64748B;
            font-size: 0.9rem;
        }

        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid rgba(148, 163, 184, 0.22);
            padding: 0.9rem;
            border-radius: 18px;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
        }

        div[data-testid="stDataFrame"] {
            border-radius: 14px;
            overflow: hidden;
        }

        .stButton > button {
            border-radius: 12px;
            font-weight: 700;
        }

        .stDownloadButton > button {
            border-radius: 12px;
            font-weight: 700;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# 상태 관리
# ---------------------------------------------------------
def init_state() -> None:
    if "subjects" not in st.session_state:
        st.session_state.subjects = DEFAULT_SUBJECTS.copy()

    if "plan" not in st.session_state:
        st.session_state.plan = pd.DataFrame(columns=PLAN_COLUMNS)

    if "last_generated" not in st.session_state:
        st.session_state.last_generated = None


init_state()


# ---------------------------------------------------------
# 도우미 함수
# ---------------------------------------------------------
def to_date(value) -> dt.date:
    """문자열, Timestamp, datetime 값을 date로 안전하게 변환합니다."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return pd.to_datetime(value).date()


def clean_subjects(df: pd.DataFrame) -> pd.DataFrame:
    """과목표에서 빈 행과 잘못된 숫자를 정리합니다."""
    result = df.copy()

    required = ["과목", "시험 범위", "중요도", "현재 자신감", "목표 점수"]
    for column in required:
        if column not in result.columns:
            result[column] = ""

    result["과목"] = result["과목"].fillna("").astype(str).str.strip()
    result["시험 범위"] = result["시험 범위"].fillna("").astype(str).str.strip()
    result = result[result["과목"] != ""].copy()

    for column, default, minimum, maximum in [
        ("중요도", 3, 1, 5),
        ("현재 자신감", 3, 1, 5),
        ("목표 점수", 90, 0, 100),
    ]:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(default)
        result[column] = result[column].clip(minimum, maximum).astype(int)

    return result[required].reset_index(drop=True)


def study_weight(row: pd.Series) -> float:
    """
    중요도가 높고 자신감이 낮을수록 더 자주 배정합니다.
    목표 점수가 높으면 가중치를 조금 더 올립니다.
    """
    importance = int(row["중요도"])
    confidence_gap = 6 - int(row["현재 자신감"])
    target_bonus = max(int(row["목표 점수"]) - 80, 0) / 20
    return max(1.0, importance * confidence_gap + target_bonus)


def choose_subject_smooth(
    weights: dict[str, float],
    credits: dict[str, float],
) -> str:
    """같은 과목만 연속으로 나오지 않도록 부드러운 가중 라운드로빈을 사용합니다."""
    total_weight = sum(weights.values())

    for subject, weight in weights.items():
        credits[subject] += weight

    selected = max(credits, key=credits.get)
    credits[selected] -= total_weight
    return selected


def get_stage(progress_ratio: float) -> str:
    if progress_ratio < 0.30:
        return "개념 정리"
    if progress_ratio < 0.68:
        return "문제 풀이"
    if progress_ratio < 0.88:
        return "오답 정리"
    return "최종 복습"


def make_content(subject: str, exam_range: str, stage: str) -> str:
    scope = exam_range if exam_range else "입력한 시험 범위"

    templates = {
        "개념 정리": f"{scope}의 핵심 개념을 교과서·수업 자료로 정리하기",
        "문제 풀이": f"{scope} 관련 기본·응용 문제를 풀고 채점하기",
        "오답 정리": f"{scope}에서 틀린 문제의 원인과 풀이를 오답 노트에 정리하기",
        "최종 복습": f"{scope}의 암기 사항과 자주 틀린 내용을 빠르게 점검하기",
    }
    return templates[stage]


def generate_plan(
    subjects: pd.DataFrame,
    start_date: dt.date,
    exam_date: dt.date,
    weekday_minutes: int,
    weekend_minutes: int,
    selected_weekdays: list[int],
) -> pd.DataFrame:
    """입력한 조건에 맞게 날짜별 학습 계획을 만듭니다."""
    subjects = clean_subjects(subjects)

    if subjects.empty:
        raise ValueError("과목을 한 개 이상 입력해 주세요.")

    if exam_date <= start_date:
        raise ValueError("시험 시작일은 계획 시작일보다 뒤여야 합니다.")

    all_dates = [
        start_date + dt.timedelta(days=i)
        for i in range((exam_date - start_date).days)
    ]
    study_dates = [date for date in all_dates if date.weekday() in selected_weekdays]

    if not study_dates:
        raise ValueError("선택한 공부 요일에 해당하는 날짜가 없습니다.")

    subject_info = subjects.set_index("과목").to_dict(orient="index")
    weights = {
        row["과목"]: study_weight(row)
        for _, row in subjects.iterrows()
    }
    credits = {subject: 0.0 for subject in weights}

    rows = []

    for date_index, current_date in enumerate(study_dates):
        daily_minutes = (
            weekend_minutes if current_date.weekday() >= 5 else weekday_minutes
        )

        if daily_minutes <= 0:
            continue

        if daily_minutes >= 180:
            session_count = 3
        elif daily_minutes >= 80:
            session_count = 2
        else:
            session_count = 1

        base_minutes = daily_minutes // session_count
        extra_minutes = daily_minutes % session_count

        progress_ratio = date_index / max(len(study_dates) - 1, 1)
        stage = get_stage(progress_ratio)

        selected_today = []

        for session_index in range(session_count):
            subject = choose_subject_smooth(weights, credits)

            # 과목 수가 충분하면 같은 날 동일 과목 중복을 줄입니다.
            if len(weights) >= session_count and subject in selected_today:
                alternatives = [
                    name for name in credits
                    if name not in selected_today
                ]
                if alternatives:
                    subject = max(alternatives, key=lambda name: credits[name])
                    credits[subject] -= sum(weights.values())

            selected_today.append(subject)
            exam_range = subject_info[subject]["시험 범위"]
            minutes = base_minutes + (1 if session_index < extra_minutes else 0)

            rows.append(
                {
                    "날짜": current_date.isoformat(),
                    "요일": WEEKDAYS_KO[current_date.weekday()],
                    "과목": subject,
                    "공부 단계": stage,
                    "공부 내용": make_content(subject, exam_range, stage),
                    "목표 시간(분)": minutes,
                    "완료": False,
                    "메모": "",
                }
            )

    return pd.DataFrame(rows, columns=PLAN_COLUMNS)


def normalize_plan(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    for column in PLAN_COLUMNS:
        if column not in result.columns:
            if column == "완료":
                result[column] = False
            elif column == "목표 시간(분)":
                result[column] = 0
            else:
                result[column] = ""

    result["완료"] = result["완료"].fillna(False).astype(bool)
    result["목표 시간(분)"] = (
        pd.to_numeric(result["목표 시간(분)"], errors="coerce")
        .fillna(0)
        .clip(lower=0)
        .astype(int)
    )

    return result[PLAN_COLUMNS].reset_index(drop=True)


def download_csv_button(
    dataframe: pd.DataFrame,
    label: str,
    filename: str,
    key: str,
) -> None:
    csv_data = dataframe.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=label,
        data=csv_data,
        file_name=filename,
        mime="text/csv",
        key=key,
        use_container_width=True,
    )


# ---------------------------------------------------------
# 사이드바
# ---------------------------------------------------------
today = dt.date.today()

with st.sidebar:
    st.header("⚙️ 기본 설정")

    student_name = st.text_input("이름", value="방배중 학생")
    grade = st.selectbox("학년", ["1학년", "2학년", "3학년"], index=0)
    exam_name = st.text_input("시험 이름", value="기말고사")

    default_exam_date = today + dt.timedelta(days=21)
    exam_date = st.date_input(
        "시험 시작일",
        value=default_exam_date,
        min_value=today,
    )

    st.divider()
    st.caption(
        "입력한 내용은 현재 접속 세션에 저장됩니다. "
        "장기간 보관하려면 아래 CSV 다운로드 기능을 이용하세요."
    )


# ---------------------------------------------------------
# 상단 제목
# ---------------------------------------------------------
d_day = (exam_date - today).days
d_day_text = "D-DAY" if d_day == 0 else f"D-{d_day}" if d_day > 0 else f"D+{abs(d_day)}"

st.markdown(
    f"""
    <div class="hero">
        <h1>📘 방배중 시험 플래너</h1>
        <p>{student_name} · {grade} · {exam_name}까지 <b>{d_day_text}</b></p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# 탭 구성
# ---------------------------------------------------------
tab_home, tab_subjects, tab_generator, tab_plan = st.tabs(
    ["🏠 대시보드", "📚 과목·시험 범위", "✨ 자동 계획 만들기", "✅ 나의 계획표"]
)


# ---------------------------------------------------------
# 1. 대시보드
# ---------------------------------------------------------
with tab_home:
    plan = normalize_plan(st.session_state.plan)

    total_tasks = len(plan)
    completed_tasks = int(plan["완료"].sum()) if total_tasks else 0
    completion_rate = completed_tasks / total_tasks if total_tasks else 0
    total_minutes = int(plan["목표 시간(분)"].sum()) if total_tasks else 0
    completed_minutes = (
        int(plan.loc[plan["완료"], "목표 시간(분)"].sum())
        if total_tasks
        else 0
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("시험까지", d_day_text)
    col2.metric("전체 계획", f"{total_tasks}개")
    col3.metric("완료한 계획", f"{completed_tasks}개")
    col4.metric("예상 공부 시간", f"{total_minutes // 60}시간 {total_minutes % 60}분")

    st.subheader("전체 진행률")
    st.progress(completion_rate)
    st.caption(
        f"{completion_rate * 100:.1f}% 완료 · "
        f"완료 시간 {completed_minutes // 60}시간 {completed_minutes % 60}분"
    )

    if plan.empty:
        st.info(
            "아직 계획표가 없습니다. "
            "먼저 **과목·시험 범위**를 입력한 뒤 **자동 계획 만들기**로 이동하세요."
        )
    else:
        left, right = st.columns([1.35, 1])

        with left:
            st.subheader("다가오는 계획")
            plan_dates = pd.to_datetime(plan["날짜"], errors="coerce").dt.date
            upcoming = plan[
                (plan_dates >= today) & (~plan["완료"])
            ].head(8)

            if upcoming.empty:
                st.success("현재 남아 있는 계획이 없습니다. 정말 잘했어요! 🎉")
            else:
                st.dataframe(
                    upcoming[
                        ["날짜", "요일", "과목", "공부 단계", "목표 시간(분)"]
                    ],
                    hide_index=True,
                    use_container_width=True,
                )

        with right:
            st.subheader("과목별 계획 시간")
            subject_minutes = (
                plan.groupby("과목", as_index=False)["목표 시간(분)"]
                .sum()
                .set_index("과목")
            )
            st.bar_chart(subject_minutes)

        st.subheader("오늘의 공부")
        today_rows = plan[
            pd.to_datetime(plan["날짜"], errors="coerce").dt.date == today
        ]

        if today_rows.empty:
            st.write("오늘 배정된 계획이 없습니다.")
        else:
            for _, row in today_rows.iterrows():
                status = "✅" if row["완료"] else "⬜"
                st.markdown(
                    f"**{status} {row['과목']} — {row['공부 단계']}**  \n"
                    f"{row['공부 내용']} · {row['목표 시간(분)']}분"
                )

    st.markdown(
        """
        <div class="tip-box">
            <b>공부 순서 추천</b><br>
            ① 개념을 이해하고 → ② 문제를 풀고 → ③ 틀린 이유를 기록하고
            → ④ 시험 직전에 오답과 암기 내용을 다시 확인하세요.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------
# 2. 과목·시험 범위
# ---------------------------------------------------------
with tab_subjects:
    st.subheader("시험 과목과 범위 입력")
    st.write(
        "과목별 **중요도**가 높고 **현재 자신감**이 낮을수록 자동 계획에 더 자주 배정됩니다."
    )

    edited_subjects = st.data_editor(
        st.session_state.subjects,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "과목": st.column_config.TextColumn(
                "과목",
                help="예: 국어, 수학, 영어",
                required=True,
            ),
            "시험 범위": st.column_config.TextColumn(
                "시험 범위",
                help="예: 교과서 2~4단원, 학습지 1~8쪽",
                width="large",
            ),
            "중요도": st.column_config.NumberColumn(
                "중요도",
                min_value=1,
                max_value=5,
                step=1,
                help="1은 낮음, 5는 매우 높음",
            ),
            "현재 자신감": st.column_config.NumberColumn(
                "현재 자신감",
                min_value=1,
                max_value=5,
                step=1,
                help="1은 매우 어려움, 5는 매우 자신 있음",
            ),
            "목표 점수": st.column_config.NumberColumn(
                "목표 점수",
                min_value=0,
                max_value=100,
                step=1,
            ),
        },
        key="subjects_editor",
    )

    st.session_state.subjects = clean_subjects(edited_subjects)

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "기본 과목으로 되돌리기",
            use_container_width=True,
            key="reset_subjects",
        ):
            st.session_state.subjects = DEFAULT_SUBJECTS.copy()
            st.rerun()

    with col2:
        download_csv_button(
            st.session_state.subjects,
            "과목·범위 CSV 다운로드",
            "방배중_시험과목.csv",
            "download_subjects",
        )

    st.caption(
        "과목 행은 직접 추가하거나 삭제할 수 있습니다. "
        "수행평가 준비 과목도 별도 과목처럼 추가할 수 있습니다."
    )


# ---------------------------------------------------------
# 3. 자동 계획 생성
# ---------------------------------------------------------
with tab_generator:
    st.subheader("나에게 맞는 시험 계획 자동 생성")

    left, right = st.columns(2)

    with left:
        plan_start_date = st.date_input(
            "계획 시작일",
            value=today,
            min_value=today,
            max_value=exam_date,
            key="plan_start_date",
        )
        weekday_minutes = st.slider(
            "평일 하루 공부 가능 시간",
            min_value=30,
            max_value=360,
            value=120,
            step=10,
        )
        weekend_minutes = st.slider(
            "주말 하루 공부 가능 시간",
            min_value=30,
            max_value=480,
            value=180,
            step=10,
        )

    with right:
        st.write("공부할 요일")
        weekday_labels = {
            0: "월",
            1: "화",
            2: "수",
            3: "목",
            4: "금",
            5: "토",
            6: "일",
        }

        selected_weekdays = []
        day_cols = st.columns(4)

        for index, (day_number, day_label) in enumerate(weekday_labels.items()):
            default_checked = True
            checked = day_cols[index % 4].checkbox(
                day_label,
                value=default_checked,
                key=f"study_day_{day_number}",
            )
            if checked:
                selected_weekdays.append(day_number)

        st.info(
            "시험 시작일 전날까지만 계획을 만듭니다. "
            "생성 후 계획표에서 내용과 시간을 자유롭게 수정할 수 있습니다."
        )

    replace_existing = st.checkbox(
        "기존 계획을 지우고 새 계획으로 교체",
        value=True,
    )

    if st.button(
        "✨ 시험 계획표 자동 생성",
        type="primary",
        use_container_width=True,
    ):
        try:
            new_plan = generate_plan(
                st.session_state.subjects,
                to_date(plan_start_date),
                to_date(exam_date),
                weekday_minutes,
                weekend_minutes,
                selected_weekdays,
            )

            if replace_existing or st.session_state.plan.empty:
                st.session_state.plan = new_plan
            else:
                combined = pd.concat(
                    [normalize_plan(st.session_state.plan), new_plan],
                    ignore_index=True,
                )
                st.session_state.plan = normalize_plan(combined)

            st.session_state.last_generated = dt.datetime.now().strftime(
                "%Y-%m-%d %H:%M"
            )
            st.success(
                f"계획 {len(new_plan)}개를 만들었습니다. "
                "이제 '나의 계획표' 탭에서 확인하세요."
            )
        except ValueError as error:
            st.error(str(error))

    if st.session_state.last_generated:
        st.caption(f"최근 생성 시각: {st.session_state.last_generated}")

    subjects_preview = clean_subjects(st.session_state.subjects)
    if not subjects_preview.empty:
        preview = subjects_preview.copy()
        preview["배정 가중치"] = preview.apply(study_weight, axis=1)
        st.subheader("현재 과목별 배정 기준")
        st.dataframe(
            preview[
                ["과목", "중요도", "현재 자신감", "목표 점수", "배정 가중치"]
            ].sort_values("배정 가중치", ascending=False),
            hide_index=True,
            use_container_width=True,
        )


# ---------------------------------------------------------
# 4. 계획표
# ---------------------------------------------------------
with tab_plan:
    st.subheader("나의 시험 계획표")

    if st.session_state.plan.empty:
        st.warning("아직 계획표가 없습니다. 자동 계획을 먼저 생성해 주세요.")
    else:
        filter_col1, filter_col2, filter_col3 = st.columns(3)

        plan_for_filter = normalize_plan(st.session_state.plan)
        subject_options = sorted(plan_for_filter["과목"].dropna().unique().tolist())

        with filter_col1:
            filter_subject = st.multiselect(
                "과목 필터",
                options=subject_options,
                default=[],
            )

        with filter_col2:
            completion_filter = st.selectbox(
                "완료 상태",
                ["전체", "미완료만", "완료만"],
            )

        with filter_col3:
            sort_order = st.selectbox(
                "정렬",
                ["날짜 빠른 순", "날짜 늦은 순"],
            )

        filtered = plan_for_filter.copy()

        if filter_subject:
            filtered = filtered[filtered["과목"].isin(filter_subject)]

        if completion_filter == "미완료만":
            filtered = filtered[~filtered["완료"]]
        elif completion_filter == "완료만":
            filtered = filtered[filtered["완료"]]

        filtered["_sort_date"] = pd.to_datetime(
            filtered["날짜"],
            errors="coerce",
        )
        filtered = filtered.sort_values(
            "_sort_date",
            ascending=(sort_order == "날짜 빠른 순"),
        ).drop(columns="_sort_date")

        st.caption(
            "체크박스로 완료 표시를 하고, 공부 내용·시간·메모를 직접 수정할 수 있습니다."
        )

        edited_plan = st.data_editor(
            filtered,
            hide_index=False,
            use_container_width=True,
            column_config={
                "날짜": st.column_config.TextColumn(
                    "날짜",
                    help="YYYY-MM-DD 형식",
                ),
                "요일": st.column_config.TextColumn("요일"),
                "과목": st.column_config.TextColumn("과목"),
                "공부 단계": st.column_config.SelectboxColumn(
                    "공부 단계",
                    options=["개념 정리", "문제 풀이", "오답 정리", "최종 복습"],
                ),
                "공부 내용": st.column_config.TextColumn(
                    "공부 내용",
                    width="large",
                ),
                "목표 시간(분)": st.column_config.NumberColumn(
                    "목표 시간(분)",
                    min_value=0,
                    max_value=600,
                    step=10,
                ),
                "완료": st.column_config.CheckboxColumn("완료"),
                "메모": st.column_config.TextColumn(
                    "메모",
                    width="medium",
                ),
            },
            key="plan_editor",
        )

        # 필터된 행만 수정한 경우 원본의 같은 인덱스에 반영합니다.
        updated_plan = plan_for_filter.copy()
        for row_index in edited_plan.index:
            if row_index in updated_plan.index:
                for column in PLAN_COLUMNS:
                    updated_plan.at[row_index, column] = edited_plan.at[row_index, column]

        st.session_state.plan = normalize_plan(updated_plan)

        progress = (
            float(st.session_state.plan["완료"].mean())
            if len(st.session_state.plan)
            else 0.0
        )
        st.progress(progress)
        st.caption(f"전체 계획의 {progress * 100:.1f}%를 완료했습니다.")

        action1, action2, action3 = st.columns(3)

        with action1:
            download_csv_button(
                st.session_state.plan,
                "계획표 CSV 다운로드",
                "방배중_시험계획표.csv",
                "download_plan",
            )

        with action2:
            uploaded_file = st.file_uploader(
                "CSV 불러오기",
                type=["csv"],
                label_visibility="collapsed",
                key="upload_plan",
            )
            if uploaded_file is not None:
                try:
                    loaded = pd.read_csv(uploaded_file)
                    st.session_state.plan = normalize_plan(loaded)
                    st.success("계획표를 불러왔습니다.")
                except Exception:
                    st.error("CSV 파일 형식을 확인해 주세요.")

        with action3:
            if st.button(
                "계획표 전체 삭제",
                use_container_width=True,
                key="delete_all_plan",
            ):
                st.session_state.plan = pd.DataFrame(columns=PLAN_COLUMNS)
                st.rerun()

        with st.expander("인쇄용 보기"):
            printable = st.session_state.plan.copy()
            printable["상태"] = printable["완료"].map(
                {True: "완료", False: "미완료"}
            )
            st.dataframe(
                printable[
                    [
                        "날짜",
                        "요일",
                        "과목",
                        "공부 단계",
                        "공부 내용",
                        "목표 시간(분)",
                        "상태",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
            )
