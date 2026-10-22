# BabelKO · 한국어 PDF 번역기

PDFMathTranslate-next의 클라이언트·번역기 인터페이스와 BabelDOC의 문서 분석·배치·조판 엔진을 결합한 별도 Windows 실험판입니다. 기존 PaperTranslator 프로그램과 작업 기록은 그대로 유지합니다.

로컬 Hy-MT2 30B-A3B 초벌과 Qwen 27B 문장별 양방향 대조·재교정을 결합합니다. 두 모델을 동시에 GPU에 올리지 않고 문서 초벌을 저장한 뒤 한 번 전환합니다. Qwen 단일 모델 비교 모드도 유지합니다. API 키 없이 실행하며 PDF 내용은 모델 다운로드 서버로 보내지 않습니다.

## 처음 설치하기 · Windows

Windows 10/11 x64, NVIDIA CUDA 12를 사용할 수 있는 그래픽 드라이버, [Git](https://git-scm.com/downloads/win), [uv](https://docs.astral.sh/uv/getting-started/installation/)가 필요합니다. **24GB VRAM GPU를 권장**합니다. 결합 모드의 모델 파일만 약 35GB이며, 실행 엔진·폰트·OCR·다운로드 여유 공간까지 고려해 Windows 사용자 드라이브에 **45GB 이상**을 확보하세요. CPU 전용 실행과 독립 실행 EXE는 현재 제공하지 않습니다. GPU가 작으면 아래의 Qwen 단일 모델 설치를 사용해도 실행 가능 여부와 속도는 환경에 따라 달라집니다.

Git과 uv가 없다면 PowerShell에서 설치한 뒤 **PowerShell을 새로 열어** 아래 명령을 실행하세요.

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
```

저장소, 고정된 상위 엔진, Python 3.12 환경, OCR·글꼴, 두 번역 모델과 CUDA 실행 엔진을 차례로 설치합니다. 별도로 Python이나 Ollama를 설치할 필요는 없습니다. 첫 설치에는 인터넷이 필요하고 모델 크기만큼 시간이 걸립니다.

```powershell
git clone https://github.com/zzzrichard0101/papertranslator-babelko.git
cd papertranslator-babelko
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\launch.ps1
```

`install.ps1`은 바탕화면에 **BabelKO 한국어 PDF 번역기 (실험판)** 바로가기를 만듭니다. 이후에는 바로가기로 열면 됩니다. 앱에서 PDF를 고르고 **새 번역 시작**을 누르세요. 결과 폴더에 `Original.pdf`, `Korean.pdf`, `Bilingual.pdf`, `Quality.json`이 만들어집니다. `Bilingual.pdf`는 왼쪽 원문·오른쪽 한국어 대조본입니다. 긴 작업은 취소 후 **이 작업 다시 시작**으로 저장된 번역을 재사용할 수 있습니다.

모델은 [Hy-MT2 30B GGUF](https://huggingface.co/tencent/Hy-MT2-30B-A3B-GGUF), [Qwen3.8 27B](https://ollama.com/library/qwen3.8:27b), 실행 엔진은 [llama.cpp b11718 Windows CUDA 12](https://github.com/ggml-org/llama.cpp/releases/tag/b11718)에서 받습니다. 설치기는 다운로드가 끊긴 위치부터 이어받고 파일 크기와 SHA-256을 확인한 뒤 `%LOCALAPPDATA%\PaperTranslatorBabelKO` 아래에 저장합니다. 모델 파일과 PDF는 Git 저장소에 포함되지 않습니다. 이전 PaperTranslator 설치에서 같은 파일이 이미 확인되면 해당 파일을 읽기 전용으로 재사용할 수 있습니다.

**Qwen 단일 모델만 설치**하려면 첫 설치에서 다음 명령을 대신 실행하세요. 모델 다운로드는 약 16.8GB이며, 앱의 번역 방식에서 **Qwen 단일 모델**을 선택해야 합니다. 결합 모드가 필요해지면 나중에 기본 `setup.ps1`을 다시 실행하면 Hy 모델만 추가로 받습니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -ModelMode qwen
```

다운로드가 중단되면 같은 `setup.ps1` 명령을 다시 실행하세요. 설치 확인만 하려면 `.\.venv\Scripts\python.exe scripts\download_models.py --verify-only`를 실행합니다. Qwen만 설치했다면 뒤에 `--mode qwen`을 붙이세요. 설치 오류가 나면 PowerShell에 표시된 파일명과 메시지를 확인하세요. `로컬 엔진 시작 실패`는 작업 폴더의 `engine-*.log`에 상세 원인이 남습니다. 다른 `llama-server.exe`가 이미 실행 중이면 종료한 뒤 다시 시작해야 합니다.

## 명령줄 실행

GUI 없이 번역하려면 결과 폴더를 만든 후 실행합니다.

```powershell
New-Item -ItemType Directory -Force results | Out-Null
.\.venv\Scripts\python.exe scripts\translate.py input.pdf --output results --pages 1-5,9 --ocr auto --mode hybrid
```

결과 폴더는 미리 생성해야 합니다. 쪽 번호는 PDF의 물리 쪽이며 비우면 전체를 처리합니다.
`--mode qwen`은 단일 모델, `auto`는 설치된 두 모델이 있으면 결합 모드를 선택합니다. GUI에서 결합 모드를 사용하려면 두 모델이 모두 필요합니다.

## 현재 동작

- BabelDOC의 배치 인식·문단·수식·스타일 처리와 열/쪽 경계 번역 경로 사용
- 한국어 PDF와 같은 원문 쪽을 왼쪽에 유지한 대조본 생성
- 결합 모드의 원문·번역을 빠짐없이 구간으로 나눠 양방향 대조. 원문 조건절 누락·의미 반전과 번역의 추가 주장 검사. 모델이 반대편 근거 구간 번호를 고르면 프로그램이 실제 문구를 추출해 보존
- 오류가 있으면 필요한 구절부터 자동 수정하고 변경된 결과를 다시 대조. 최대 세 차례 대조 후에도 실패하면 완료로 표시하지 않고 체크포인트와 실패 근거 보존. 단일 모델 비교 모드는 이 의미 대조를 수행하지 않음
- 칼럼·쪽 끝에서 잘린 구절은 실제 입력에 있는 내용만 대조. 주변 문맥을 근거로 없는 뒷문장을 추가하도록 요구하지 않으며, 오래된 검수 버전의 완료 기록도 재검사
- 최종 교정 기록만 원래 번역 전 문서 구조에 다시 적용하여 상위 엔진으로 조판. 초벌/교정 체크포인트와 전체 모델 응답 보존
- 참고문헌 목록은 서지 형식과 구역 경계를 확인해 원문 글자·배치를 보존하고 번역·의미 검수에서 제외. 본문의 인용문은 계속 번역·검수하며, 보존한 구역의 쪽·해시를 품질 보고서에 기록
- OCR에서 첫 저자명이나 줄 순서가 손상된 참고문헌 묶음도 반복되는 저자·연도와 출판 정보로 식별. 문단 검사 실패는 대기열에 저장하고 다른 문단 처리 후 작은 구간 재번역·전체 대조로 자동 복구하며, 미해결 문단이 남으면 완료를 차단
- 검수는 최대 18개 항목·짧은 문단 4개를 묶고 응답 표기를 압축해 중복 입력과 생성량을 절감. 모든 양방향 검사·문단별 근거 검증은 유지하며, 불완전한 구절·복잡한 긴 문단·잘못된 묶음 응답은 기존의 작은 단위 검사로 처리. 기존에 통과한 검수는 재사용하고 확인된 오류는 수정 후 재검사
- 검수 미완료 작업을 먼저 읽으려면 검수 입력의 문장·문맥·주변 원문·수식 뜻이 모두 같으면 기존 양방향 대조 근거를 재사용합니다. 서식 차이도 숫자·수식·태그 검사는 다시 통과해야 합니다. 독립된 완결 문장 일부만 교정한 경우에는 변경 구간, 인접 구간, 기존 오류와 연결된 대조 근거를 다시 검사하고 나머지 근거를 보존합니다. 검수 모델에는 항상 전체 원문과 번역을 보여줍니다. 부정·조건·수량·대명사·문장 경계·원문·문맥이 바뀌거나 의존 관계가 불확실하면 전체 검수를 유지합니다. 속도 이득은 재사용 가능한 구간 수에 따라 달라집니다. 레이아웃 변경으로 복구한 번역 후보도 검수 전 즉시 체크포인트에 저장합니다.

`scripts/export_preview.py --job "작업폴더"`로 별도 확인용 PDF를 내보낼 수 있습니다. 모델 호출 없이 저장된 후보를 사용하고 수식·서식 구조가 안전하지 않으면 원문을 보존합니다. `Korean-preview.pdf`, `Bilingual-preview.pdf`, `Issues.html`, `Preview.json`으로 저장하며 원래 작업의 실패 상태·체크포인트·완료 기준을 바꾸지 않습니다.
- 수식 의미를 교정 힌트로 전달하고, 반복적인 자리표시자 누락은 프로그램이 원래 보호 토큰을 직접 삽입하는 방식으로 재번역
- OCR이 필요 없는 입력은 바이트 그대로 통과. 목차·직접 지정된 페이지 투명도 색공간 보존 및 PDF 중복 리소스 병합
- 수식에 잘못 묶인 글머리표+날짜의 일자와 위첨자 영문 서수 어미를 좁은 문맥 규칙으로 일반 번역 텍스트에 노출
- 색상·글꼴이 달라 같은 문장의 중간 단어가 별도 문단으로 분리된 경우, 원래 좌표와 읽기 순서로 합친 후 상위 엔진의 수식·서식 분석 적용
- 본문 영역 경계에 잘린 짧은 줄 조각도 같은 줄·글자 크기·고유한 인접 영역 근거로 연결. 한국어 문장 속에 그대로 남은 긴 영문 구절도 재번역 대상으로 검사
- 글머리표가 본문과 따로 추출된 목록은 실제 표식과 줄 좌표로 항목을 나눠 번역. 여러 항목이 한 문단으로 합쳐져 원래 위치를 잃는 현상 완화
- 반복되는 표의 선 접점으로 셀 경계가 확인되면, 같은 셀의 줄 단위 조각을 문장으로 복원. 항목 제목·숫자 셀·옆 셀은 구분하고 원문 항목 식별자 보존
- 하이픈으로 잘린 줄 연결, 수식으로 오인된 긴 영문 머리말 복원, 회전 입력의 좌표 정리와 출력 회전 복원
- 선택 쪽의 스캔만 로컬 OCR. 글자가 자모처럼 잘게 깨진 기존 영어 OCR 층도 재인식. 검색용 글꼴 대신 실제 글꼴의 줄을 복원한 입력 사본으로 처리
- 배치 ID·빈 번역·숫자/부호/출현 수·수식과 스타일 자리표시자 검사. 배치 및 단일 문단 fallback에 동일 검사 적용
- 올바른 영어 분수 표현과 한국어 수량 동치 처리. 실패 후보는 제한된 재요청 후 실패 근거 보존
- `1–5 million → 100만–500만` 같은 정확한 수량·범위 변환 허용. 값 변경이나 끝점 누락은 계속 검사
- 퍼센트와 퍼센트포인트는 숫자가 같아도 구분하여 값·부호·출현 수 직접 대조
- 원본 해시·입력 해시·모델 스냅샷·원응답·중간 번역 기록 보존. 취소 후 재시작은 동일 입력 캐시를 활용하고 분석/조판은 다시 수행
- 완료 판단은 실제 BabelDOC 작업의 반환값을 사용. 최종 번역 검사 실패를 완료로 표시하지 않음
- 빈 추적 기록·공백 출력 및 최종 PDF에서 사라진 한국어 본문을 추가 검사. 의미 대조 캐시는 원문·번역·문맥·검사 버전에 묶어 검증하며 오래된 처리 버전은 새 작업 필요
- 자산 준비 후 worker 외부 DNS/연결 차단, 인증된 루프백 모델 서버만 사용

## 검증과 범위

전체 실행 과정의 중복 처리를 함께 줄였습니다. OCR은 완료된 쪽부터 재개하고, 문서 분석 결과도 원본·설정에 묶어 저장합니다. 모델은 실제 요청이 생길 때 로딩하며, 같은 체크포인트 저장과 최종 PDF의 중복 글자 추출을 생략합니다. 초벌 수집과 검수 목록은 캐시 속도 차이로 달라지지 않도록 처리합니다. `performance.json`에서 단계별 시간·요청·토큰을 확인할 수 있습니다. 적용 범위와 채택하지 않은 방법까지 [전체 효율 점검](docs/PERFORMANCE.txt)에 기록했습니다. 실행 중인 작업은 유지하고 새 실행/재개부터 적용합니다.

GUI의 **새 파이프라인 실험** 또는 CLI `--experimental-pipeline`으로 Qwen 동시 검수, 원문 약어 정의 문맥, 문단별 출처와 PDF 글자 위치 검사를 함께 사용할 수 있습니다. 현재는 별도 선택 옵션이며 기존 작업의 설정을 자동 변경하지 않습니다. 구현 범위·검증 방법·제한은 [실험 파이프라인](docs/EXPERIMENTAL-PIPELINE.txt)을 참고하세요.

스캔 복구는 기존 `Input.pdf`와 번역 체크포인트를 보존합니다. 위험한 OCR 행만 별도 로컬 OCR로 대조하고, 양쪽 문맥이 정확히 일치할 때만 `10/to`, `1/I` 같은 인식 혼동을 수정합니다. 지나치게 늘어난 글자 구간은 원본 픽셀에서 복구한 `Layout-input.pdf`로 조판합니다. 수식과 표의 긴 선은 원본으로 보존하며, 문장이 정확히 같은 저장 번역은 후보로 재사용하고 새 문맥에서 검수합니다. 보완 OCR도 쪽별로 저장하므로 재개할 때 완료된 인식을 반복하지 않습니다. 참고문헌 원문 보존 정책과 최종 오류 차단 기준은 유지합니다.

`scripts/export_preview.py --job "작업폴더" --pages "17,100"`으로 저장된 번역만 사용한 일부 쪽 확인본도 만들 수 있습니다. 확인본은 정식 검수 완료본이 아닙니다.

검증 결과는 로컬 `work/`와 `test_vault/`에 기록합니다. 숫자·서식·함수 식별자·서수·문맥 분리·체크포인트·원래 문서 구조 재적용·색상/목차 보존을 회귀 검사합니다. 실제 BabelDOC/OCR/조판 합성 검사는 단일/결합 경로를 각각 실행합니다. 합성 응답 검사는 실제 모델 의미 정확도 평가와 구분합니다. 실제 모델 전체 문서 측정 및 한계는 `DEVELOPMENT.txt`에 기록합니다.

현재는 초기 0.1 실험판입니다. 모든 문서에서 의미 오류·OCR 누락이 없어졌다는 검증은 없습니다. 공개 자료 6종의 지정 11쪽과 직접 만든 6쪽으로 1·2·3칼럼, 표, 수식·알고리즘, 영어 인쇄체 스캔, 가로·회전 페이지를 검사했습니다. 전체 자료의 모든 쪽을 검사한 것은 아닙니다. 색 배경/손글씨/복잡한 도식/병합 표와 장문 장애 복구는 추가 검증이 필요합니다. 스캔 입력은 OCR 글자를 실제 폰트로 재구성하므로 원문의 정확한 글꼴·이미지 조판과 같지 않습니다. 대조본의 원문 면은 원본을 사용합니다.

기존 앱의 무료 API·Obsidian·전체 고급 검수 기능은 아직 이식하지 않았습니다. 모델 교정과 기계 검사 통과는 의미 정확도 인증이 아닙니다. 새 엔진의 모든 문서에 대한 속도·의미 품질 우위를 보증하지 않으며 캐시 사용 시간과 새 번역 시간을 구분합니다.

## 개발 검사

```powershell
uv run pytest -q
uv run python scripts/integration.py
uv run python scripts/integration.py --mode hybrid
uv run python scripts/evaluate_meaning.py
uv run python scripts/evaluate_meaning.py --cases tests/meaning_reserved_cases.json --output test_vault/meaning-reserved
uv run python scripts/evaluate_meaning.py --cases tests/meaning_boundary_cases.json --output test_vault/meaning-boundary
uv run python scripts/accuracy_corpus.py prepare
uv run python scripts/accuracy_corpus.py run
```

다양성 검사는 공개 ACL·JMLR·Adam 논문, NIST 보고서, NASA 스캔, RFC 문서의 지정 쪽과 직접 만든 배치 시험본을 사용합니다. 원문과 결과는 `test_vault/`에만 저장합니다. 의도적으로 오역을 넣은 의미 대조 시험은 정상 번역의 오탐과 오류 번역의 미탐을 함께 기록합니다. 자동 모델 대조 통과를 독립 전문가의 정확도 인증으로 취급하지 않습니다.

두 저장소의 최신 요구 버전은 서로 다릅니다. 전체 상위 WebUI 대신 실제 사용 API에 필요한 의존성만 별도 환경에 고정했으며 `upstream.lock.json`의 커밋과 `uv.lock`을 사용합니다. 한국어 글꼴 별칭과 진행 콜백의 완료 경쟁을 연결부에서 보정합니다. 자세한 구성은 `docs/ARCHITECTURE.txt`에 기록합니다.

AGPL-3.0-only. 상위 프로젝트·가중치·글꼴의 라이선스와 출처는 `NOTICE.txt`, `LICENSE`, `upstream.lock.json`을 확인하세요. 현재 설치는 소스와 별도 가상환경을 이용하며 독립 실행 EXE 배포판은 아닙니다.
