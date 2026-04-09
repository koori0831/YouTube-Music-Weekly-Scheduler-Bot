from __future__ import annotations

DAY_CHOICES: list[str] = ["월", "화", "수", "목", "금"]

MAX_SONGS_PER_DAY = 12
FRIDAY_MAX_SONGS_PER_DAY = 15
MAX_WEEKLY_SONGS_PER_USER = 2
MAX_SONG_DURATION_SECONDS = 4 * 60 + 30

LOCKED_MESSAGE = "이 요일 플레이리스트는 현재 잠겨 있습니다."
EXCLUSIVE_ONLY_MESSAGE = "상점 사용 플리입니다."
PAST_DAY_MESSAGE = "이미 지난 요일입니다."
DAY_FULL_MESSAGE = "해당 요일 플레이리스트가 가득 찼습니다."
WEEKLY_LIMIT_MESSAGE = "주간 신청 가능 횟수(2곡)를 모두 사용했습니다."
NO_RESULTS_MESSAGE = "조건에 맞는 음악 검색 결과를 찾지 못했습니다."
UNAUTHORIZED_BUTTON_MESSAGE = "요청자만 선택할 수 있습니다."
REGISTER_SUCCESS_MESSAGE = "곡이 플레이리스트에 등록되었습니다."
LONG_SONG_MESSAGE = "곡이 너무 길어요! 4분 30초 이내의 곡만 신청 가능합니다."

RESET_META_KEY = "last_weekly_reset_date"


def get_max_songs_for_day(day: str) -> int:
    if day == "금":
        return FRIDAY_MAX_SONGS_PER_DAY
    return MAX_SONGS_PER_DAY
