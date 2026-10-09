# PC 스캐너 국내 커뮤니티 연동 계약

## 목표 동작

1. 매일 21:00 KST의 기존 GPT 예약작업이 보고서를 생성하고 `reports/YYYY-MM-DD.json`, `.md`를 GitHub에 저장합니다.
2. 위 두 파일의 저장 및 자체 검증 후 `latest.md`, **마지막으로 `latest.json`** 순서로 갱신합니다. `latest.json`은 갱신 완료를 알리는 공개 포인터입니다.
3. 스캐너 → 시황 → 커뮤니티(국내): **프로그램을 21시 이후 실행할 때** 원격 `latest.json`을 조회합니다.
4. **프로그램이 21시 이전부터 켜져 있으면** 21시 이후 5분 간격으로 당일 보고서를 확인합니다. 발행 확인 시 로컬 캐시를 교체하고 화면을 다시 그립니다. 그날 한 번 성공하면 불필요한 반복 다운로드를 하지 않아도 됩니다.
5. **'오늘 새로고침' 버튼**을 누르면 시간과 상관없이 원격 `latest.json`을 다시 조회하며, 필요 시 기존 국내 채널 직접 수집 버튼과 구분합니다.
6. 미발행·조회 실패·유효성 오류·오늘 날짜 불일치면 **기존 데이터를 유지**하고 화면에 상태와 실제 보고서 날짜를 표시합니다. 절대 `00/59`에서 무한 진행하거나 미발행을 성공으로 표시하지 않습니다.

## HTTP

- URL: https://raw.githubusercontent.com/33hankei-afk/radar-telegram-reports/main/latest.json
- 방식: 공개 HTTPS GET, 토큰 불필요. 네트워크 시간 제한 권장 15초. raw 캐시 회피를 위해 `?nocache=<epoch_ns>`를 추가할 수 있습니다.
- 응답이 404라면 보고서 미발행(초기 정상), 200이라도 `date_kst`가 원하는 날과 다르면 '발행 대기'로 표시.
- 검증: `schema=telegram_summaries_v1`, 게시글 `channel/post_id/url` 일치, 중복 없음, KST timestamp, 필수 필드 확인.
- 보관: 임시 파일에 검증된 JSON 작성 → 원자적 교체(os.replace). 데이터 없을 때 지난 파일을 삭제하지 않습니다.

## 인터페이스 사용

참고 코드 `scripts/scanner_feed.py`에서 `refresh_cache(Path(...))`를 호출하면 `updated`, `unchanged`, `not_yet_published` 중 하나와 검증된 보고서를 받습니다. 네트워크 오류는 예외로 전달됩니다.

예시 (Python GUI):

~~~python
from pathlib import Path
from scripts.scanner_feed import refresh_cache

try:
    state, report = refresh_cache(Path('cache/domestic_telegram_latest.json'))
    # state == updated -> UI 모델 갱신
    # state == not_yet_published -> 원격 보고서 발행 대기 표시
except Exception as err:
    # 사용자에게 일시적 연결 오류 알림; 기존 화면/캐시 유지
    pass
~~~

실제 GUI 메인 스레드에서 네트워크 호출하지 말고 작업 스레드로 분리하십시오. 21시 이후 조건/5분 타이머/수동 버튼의 정확한 이벤트 연결은 스캐너 소스에 따라 구현해야 합니다.

## JSON 데이터

최신 보고서 기본 필드는 기존 `telegram_summaries_v1` 호환입니다.

- `entries`: 실제 확인된 게시글만 포함; `channel`, `post_id`, `url`, `views_display`, `published_at_kst`, `title`, `summary_ko` 필수
- `top20_urls`: TOP20 순서대로 실제 게시글의 직접 URL 배열(원문 내용은 `entries`에서 매핑)
- `theme_urls`: 메모리/반도체/AI 관련 확인 글 URL 배열(중복 교차 참조 가능)
- `consensus_up`/`consensus_down`: 상향/하향 리비전 행. 원문 문자열 수치 및 직접 URL 포함. 무확인 값은 임의 계산하거나 채우지 않음
- `coverage`: 총 59개 대상, 전체 확인 수, 부분/실패 목록, 확인된 글 수, 순위 완전성
- `coverage_note`: 검증 실패·읽지 못한 범위의 이유

## 주의사항

이 저장소의 도구를 추가하는 것만으로 이미 실행 중인 PC 스캐너 바이너리가 자동 변경되는 것은 아닙니다. 해당 스캐너의 코드 수정 또는 재배포가 별도로 필요합니다.

공개 링크와 조회수는 **GPT가 실제 확인한 원문**을 기준으로 하고 이 저장소의 유효성 검사는 링크 형식·식별자 일관성만 검증합니다. 게시글 본문 진위나 채널 전수 확인까지 CI가 대신하지 않습니다.
