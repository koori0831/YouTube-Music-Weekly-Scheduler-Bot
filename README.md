# YouTube-Music-Weekly-Scheduler-Bot

요일별(월~금) 유튜브 음악 신청을 관리하는 디스코드 슬래시 명령 봇입니다.

## 주요 기능
- `/신청 제목 요일`: YouTube Music 카테고리(`videoCategoryId=10`) 검색 결과 3개를 버튼으로 보여주고 선택 등록
- `/보기 요일`: 누구나 해당 요일 플레이리스트 현황 조회
- `/플리제한 요일 상태 유저(선택)`: 요일 잠금/해제 및 독점 유저 지정
- `/셔플 요일`: 해당 요일 곡 제목 목록을 랜덤 셔플해 출력
- `/db초기화 확인`: 관리자용 DB 초기화 (`확인`에 `초기화` 입력 필요)
- SQLite 기반 데이터 관리
  - 요일별 플레이리스트
  - 유저 주간 신청 횟수(기본 2곡)
  - 요일 잠금/독점 설정
- 매주 일요일 오전 09:00(KST) 자동 초기화

## 기술 스택
- Python 3.11+
- discord.py
- aiosqlite
- ytmusicapi
- python-dotenv

## 설치
```bash
pip install -r requirements.txt
```

## 환경변수
`.env.example`를 참고해 `.env`를 구성하세요.

- `DISCORD_BOT_TOKEN`: 디스코드 봇 토큰
- `DB_PATH`: SQLite 파일 경로 (기본값 `bot.db`)
- `DISCORD_GUILD_ID`(선택): 길드 단위 슬래시 명령 동기화용

## 실행
```bash
python main.py
```

## 권한 정책
- 관리자 전용 명령: `/플리제한`, `/셔플`
- 관리자 기준: `Administrator` 또는 `Manage Guild`

## 동작 정책 요약
- 운영 요일: 월~금
- 요일당 최대 12곡
- 일반 유저 주간 최대 2곡
- 독점 잠금 요일에서 지정 유저는 주간 2곡 제한 예외
- 잠금+독점 없음 상태는 해당 요일 전체 차단

## 테스트
```bash
pytest -q
```
