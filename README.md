# 국내 텔레그램 커뮤니티 일일 보고서 · Radar

**용도:** GPT 예약작업(한국시간 매일 21:00)이 실제 확인한 공개 텔레그램 게시글의 요약본을 게시하고, PC 스캐너가 공개 파일을 가져오기 위한 전용 저장소입니다.

**중요:** 이 저장소는 보고서의 **전달 경로**입니다. 텔레그램 59개 채널 수집을 GitHub 자체가 실행하거나 검증해 주지는 않습니다. GitHub에 `latest.json`이 없는 동안은 신규 보고서가 아직 배포되지 않은 상태입니다.

## 보고서 파일

| 경로 | 내용 |
| --- | --- |
| `reports/YYYY-MM-DD.json` | KST 해당일 원본 식별자·조회수·요약·구조화 데이터 보관 |
| `reports/YYYY-MM-DD.md` | 한국어 보고서, TOP20/컨센서스/AI·반도체 상세와 눈에 보이는 전체 원문 URL |
| `latest.json` | 가장 최근 **검증 완료** 일일 JSON (스캐너가 읽는 경로) |
| `latest.md` | 가장 최근 일일 Markdown 보고서 |

스캐너 다운로드 URL:

~~~text
https://raw.githubusercontent.com/33hankei-afk/radar-telegram-reports/main/latest.json
~~~

브라우저 보고서 URL: https://github.com/33hankei-afk/radar-telegram-reports/blob/main/latest.md

## 발행 원칙

- 매일 KST 00:00~예약작업 실제 관측 시각까지를 대상으로 합니다. 예약작업은 21:00에 시작하지만 발행시각은 달라질 수 있습니다.
- 대상은 고정 59개 채널과 별도 SEARFin 컨센서스 채널입니다. 59개 중 당일 전체 구간을 확인한 수와 일부/실패 채널을 명시합니다.
- 실제로 확인한 게시글만 기록하고, `channel`, `post_id`, `views_display`, `published_at_kst`, `url`을 **임의 생성·수정하지 않습니다**.
- URL은 실재 게시글의 `https://t.me/채널핸들/게시글번호`를 **전체 문자열이 보이는 클릭 가능한 링크**로 제공합니다.
- TOP20은 확인된 공개 조회수 기준 최대 20개입니다. 전수 확인되지 않은 경우 '확인한 글 기준'이라고 명시합니다.
- 메모리/반도체/AI 관련 당일 확인 글은 TOP20 여부와 무관하게 모두 별도 표기합니다.
- 영업이익 컨센서스 상향·하향 리비전은 별도 표로 표시하며 발표 회차가 다르면 같은 값이라도 원문별 행을 유지합니다.
- 공개 저장소이므로 개인 계정, 로그인 정보, 액세스 토큰, 비공개 데이터는 게시하지 않습니다.

## 데이터 규격

`schema/telegram_summaries_v1.schema.json` 및 `scripts/validate_report.py` 참조. 핵심 호환 필드는 `schema`, `date_kst`, `observed_at_kst`, `entries`, `coverage_note`입니다.

`entries`의 각 원소: `channel`, `post_id`, `url`, `views_display`, `published_at_kst`, `title`, `summary_ko`. 선택적 인덱스 `top20_urls`, `theme_urls`는 **entries에 존재하는 원문 URL**만 참조합니다. `consensus_up`, `consensus_down`은 상향/하향 세부 수치와 같은 URL을 담습니다. 누락·확인 실패 여부는 `coverage`와 `coverage_note`에 기록합니다.

## PC 스캐너 연동

참고용 실행 명령:

~~~bash
python scripts/scanner_feed.py --output domestic_telegram_latest.json
~~~

원격 최신 파일이 아직 없거나 당일 21시 이후에도 이전 날짜라면 **갱신 실패/발행 대기**로 표시하고 과거 파일을 당일 성공으로 표시하지 않습니다. 실제 스캐너 프로그램에 자동 시작/예약 확인/수동 버튼을 연결하려면 프로그램 소스 측 수정이 추가로 필요합니다. 상세: [스캐너 연동 문서](docs/SCANNER_INTEGRATION.md).

## 검증

~~~bash
python scripts/validate_report.py reports/YYYY-MM-DD.json --markdown reports/YYYY-MM-DD.md
~~~

GitHub Actions는 커밋 후 파일 검증을 수행합니다. 검증 통과 전까지 최신 데이터로 신뢰하면 안 됩니다.
