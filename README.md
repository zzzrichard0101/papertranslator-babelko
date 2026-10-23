# BabelKO: 영어 PDF를 한국어 PDF로 번역

BabelKO는 논문과 책의 영어 PDF를 분석해 **한국어 PDF**와 **영한 대조본**을 만드는 Windows용 실험 프로그램입니다. [PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next)의 번역 인터페이스와 [BabelDOC](https://github.com/funstory-ai/BabelDOC)의 문서 분석·조판 엔진을 고정된 버전으로 결합했습니다. 기존 PaperTranslator와는 별도 앱이며 기존 설치나 작업 기록을 변경하지 않습니다.

번역 모델은 사용자의 PC에서 실행됩니다. **API 키나 유료 서비스는 필요하지 않습니다.** 첫 설치 시 프로그램·모델·글꼴 등을 내려받지만, 번역 작업 중 PDF 본문을 외부 서비스로 보내지 않습니다.

> **현재 단계:** 0.1 실험판입니다. 자동 검사에 통과한 PDF도 오역이나 누락이 없다고 보증할 수 없습니다. 중요한 문서는 영한 대조본으로 확인하세요.

## 먼저 알아둘 것

| 항목 | 현재 지원 |
| --- | --- |
| 입력 | 영어 PDF. 선택한 쪽만 번역하거나 전체 번역 가능 |
| 출력 | 한국어 PDF, 원문·번역을 나란히 놓은 대조본, 품질 보고서 |
| 스캔 | 필요한 쪽에 로컬 OCR 적용. 인식 결과는 원본 이미지와 다를 수 있음 |
| 모델 | Hy-MT2 초벌 + Qwen 검수·교정, 또는 Qwen 단일 모델 |
| 보존 | 수식·원본 쪽 대응·참고문헌 목록·확실히 인식한 그림 내부 글자 |
| 환경 | Windows 10/11 x64, NVIDIA CUDA 12 드라이버. 독립 실행 EXE와 CPU 전용 실행은 제공하지 않음 |

결합 모드에는 **24GB VRAM GPU를 권장**합니다. 두 모델 파일만 약 35GB이며, 설치 자산과 작업 공간을 포함해 사용자 드라이브에 **45GB 이상**을 확보하세요. Qwen 단일 모델 설치는 다운로드 약 16.8GB로 더 작지만, GPU가 작은 환경에서의 실행 가능 여부와 속도는 보장하지 않습니다.

## 설치하고 첫 PDF 번역하기

1. [Git](https://git-scm.com/downloads/win)과 [uv](https://docs.astral.sh/uv/getting-started/installation/)를 설치합니다. 설치하지 않았다면 PowerShell에서 아래 명령을 실행하고 **PowerShell을 새로 여세요**.

   ```powershell
   winget install --id Git.Git -e
   winget install --id astral-sh.uv -e
   ```

2. 저장소를 내려받고 설정 스크립트를 실행합니다. 첫 설정에는 인터넷 연결과 모델 다운로드 시간이 필요합니다. 별도로 Python이나 Ollama를 설치할 필요는 없습니다.

   ```powershell
   git clone https://github.com/zzzrichard0101/papertranslator-babelko.git
   cd papertranslator-babelko
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\launch.ps1
   ```

3. 앱에서 PDF를 선택하고 번역 방식과 저장 위치를 확인한 뒤 **새 번역 시작**을 누릅니다. 이후에는 바탕화면의 **BabelKO 한국어 PDF 번역기 (실험판)** 바로가기로 실행할 수 있습니다.

결합 모드 대신 **Qwen 단일 모델만 설치**하려면 2단계에서 아래 설정 명령을 사용하세요. 앱에서도 번역 방식을 **Qwen 단일 모델**로 선택해야 합니다. 나중에 기본 `setup.ps1`을 다시 실행하면 결합 모드용 모델을 추가할 수 있습니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -ModelMode qwen
```

설치기는 다운로드를 재개하고 파일 크기와 SHA-256을 확인합니다. 모델과 작업 데이터는 기본적으로 `%LOCALAPPDATA%\PaperTranslatorBabelKO`에 저장되며 Git 저장소에는 포함되지 않습니다.

### 명령줄로 실행

```powershell
New-Item -ItemType Directory -Force results | Out-Null
.\.venv\Scripts\python.exe scripts\translate.py input.pdf --output results --pages 1-5,9 --ocr auto --mode hybrid
```

`input.pdf`를 실제 PDF 경로로 바꾸고, 경로에 공백이 있으면 따옴표로 묶으세요. `--output` 폴더는 미리 만들어야 합니다. `--pages`는 PDF 파일의 **물리적 쪽 번호**이며 생략하면 전체를 처리합니다. `--mode qwen`은 단일 모델, `--mode auto`는 설치된 모델에 따라 방식을 선택합니다. `--ocr`은 `auto`, `off`, `force` 중에서 고를 수 있습니다.

## 결과물 읽기

| 파일 | 용도 |
| --- | --- |
| `Original.pdf` | 원본 PDF 사본. 대조본의 원문 면에도 이 파일의 쪽을 사용 |
| `Korean.pdf` | 한국어 조판본 |
| `Bilingual.pdf` | 왼쪽 원문, 오른쪽 한국어의 쪽별 대조본 |
| `Quality.json` | 자동 검사 결과, 처리 범위, 미해결 문제와 처리 기록 |
| `FigureLegends.html` | 인식된 그림과 그 아래에 배치한 한국어 범례 |
| `FigureLegends.json` | 그림 범례의 처리·실패 기록. 그림이 없어도 생성 |

품질 검사를 통과하지 못한 경우에도 읽어 볼 PDF가 만들어질 수 있습니다. 앱이 **부분 완료(`partial`)**로 표시하면 `Quality.json`에서 문제를 확인하세요. `partial`은 번역 완료나 의미 정확성 인증이 아닙니다. 취소하거나 실패한 작업은 앱의 **이 작업 다시 시작**으로 저장된 번역을 재사용할 수 있지만, 분석과 조판 일부는 다시 실행될 수 있습니다.

검수가 끝나기 전에 일부 쪽을 확인하려면 `scripts/export_preview.py --job "작업폴더" --pages "17,100"`을 사용할 수 있습니다. 이 확인본은 저장된 번역 후보만 사용하고 모델을 새로 호출하지 않으며, 정식 완료본으로 취급하지 않습니다.

## 번역은 어떻게 진행되나요?

1. **문서 읽기:** BabelDOC가 페이지의 칼럼, 문단, 표, 그림, 수식과 좌표를 분석합니다. 스캔이나 손상된 OCR 층은 필요한 쪽만 로컬 OCR로 보완합니다. 원본 PDF와 입력 파일의 해시를 보존합니다.
2. **번역 대상 결정:** 문장으로 이어지는 조각과 목록·표의 텍스트를 정리합니다. 참고문헌 목록은 원문으로 남기고 본문 인용문은 번역합니다. 신뢰도 높은 그림 경계 안의 글자는 원래 그림에 남겨 두고, 캡션은 본문처럼 번역합니다.
3. **모델 번역:** 결합 모드는 Hy-MT2 30B-A3B로 초벌을 만든 뒤 이를 저장하고 Qwen3.8 27B로 전환합니다. 두 모델을 동시에 GPU에 올리지 않습니다. Qwen 단일 모드는 이 두 단계의 양방향 의미 검수 없이 번역합니다.
4. **검사와 교정:** 프로그램이 번역 항목 누락, 숫자·부호·수량, 수식·서식 자리표시자를 검사합니다. 결합 모드는 원문과 번역을 구간별로 양방향 대조하고 의심되는 구절을 다시 번역·검사합니다. 통과하지 못한 구절은 원문으로 남기고 미해결 사유를 기록합니다.
5. **조판과 출력 검사:** 검사를 통과한 번역을 원래 문서 구조에 적용해 PDF를 만들고, 원문 쪽과 나란히 놓은 대조본을 생성합니다. PDF에서 누락된 문구와 위치 문제를 다시 검사합니다. 초벌·교정 결과와 모델 응답은 로컬 작업 폴더에 저장해 재개와 문제 분석에 사용합니다.

그림 속에서 **설명용 영문 표지**로 판단한 문구는 로컬 모델로 짧게 번역해 `FigureLegends.html`의 **원본 그림 아래 별도 표**에 넣습니다. 숫자 눈금, 수식, 패널 기호는 범례 번역에서 제외합니다. 현재는 그림 내부 글자를 한국어 PDF의 그림 위에 덮어쓰지 않습니다.

중복 작업을 줄이기 위해 완료한 OCR 쪽, 원문·설정에 묶인 문서 분석, 검증된 번역 체크포인트를 재사용합니다. `performance.json`에서 단계별 시간과 모델 요청 수를 확인할 수 있습니다. 속도는 문서 구조, 스캔 상태, 모델·GPU, 캐시 적중 여부에 따라 크게 달라집니다.

## 지금까지의 한계

- **정확도 보증은 없습니다.** 숫자·서식 검사와 모델의 재검수만으로 원문 의미를 완전히 증명할 수 없습니다. 결합 모드의 교정과 검수에도 같은 로컬 Qwen 모델이 관여하므로 독립적인 전문가 검토를 대체하지 않습니다. Qwen 단일 모드는 의미 대조 범위가 더 좁습니다.
- **OCR과 읽기 순서가 틀릴 수 있습니다.** 저해상도 스캔, 손글씨, 복잡한 배경, 다단 구성, 겹친 표·그림에서는 글자를 놓치거나 순서를 잘못 묶을 수 있습니다. OCR 입력의 한국어 조판은 원본 스캔의 글꼴·배치와 같지 않을 수 있습니다.
- **원본과 똑같은 조판은 어렵습니다.** 한국어 문장 길이와 글꼴이 달라 표 셀, 주석, 특수 수식, 회전 페이지에서 위치나 줄바꿈이 달라질 수 있습니다. 대조본은 같은 원문 쪽과 번역 쪽을 대응시키지만 모든 요소의 1:1 위치 일치를 보증하지 않습니다.
- **그림 범례는 제한적입니다.** 그림 경계가 확실히 인식될 때만 내부 글자를 안전하게 보존·분류합니다. 이미지 픽셀에 박힌 글자나 인식되지 않은 도식의 글자를 모두 찾아 번역하지는 못합니다. 범례 실패는 보고서에 남기고 완료 판정을 막습니다.
- **참고문헌 판별도 완전하지 않습니다.** 비정형 서지 목록은 참고문헌으로 식별하지 못하거나 본문과 혼동할 수 있습니다.
- **속도와 지원 환경이 제한됩니다.** 긴 문서의 OCR·모델 검수·PDF 조판은 오래 걸릴 수 있습니다. Windows/NVIDIA 중심의 소스 설치 방식이며 독립 실행 EXE, CPU 전용 실행, 모든 GPU 환경 지원은 제공하지 않습니다. 기존 앱의 무료 API·Obsidian 등 모든 기능도 이식되지 않았습니다.
- **입력 제한이 있습니다.** 500MB를 넘거나 2,000쪽을 넘는 PDF, 암호로 보호된 PDF는 현재 작업을 시작할 수 없습니다.

공개 자료와 합성 PDF로 여러 칼럼, 표, 수식, 인쇄체 스캔, 가로·회전 쪽을 검사했지만 **모든 PDF 형식과 모든 쪽을 검증한 것은 아닙니다**. 테스트에서 모델 응답을 모방한 합성 검사와 실제 모델의 번역 품질 평가는 구분해야 합니다.

## 문제 해결과 개발 문서

- 설치 다운로드가 끊기면 같은 `setup.ps1` 명령을 다시 실행하세요. 모델 확인은 `.\.venv\Scripts\python.exe scripts\download_models.py --verify-only`로 할 수 있습니다. Qwen만 설치했다면 `--mode qwen`을 추가합니다.
- `로컬 엔진 시작 실패`가 뜨면 해당 작업 폴더의 `engine-*.log`를 확인하세요. 다른 `llama-server.exe`가 같은 자원을 사용 중인지도 확인합니다.
- 구현 세부 사항은 [아키텍처](docs/ARCHITECTURE.txt), [성능 점검](docs/PERFORMANCE.txt), [실험 파이프라인](docs/EXPERIMENTAL-PIPELINE.txt), [개발 기록](DEVELOPMENT.txt)에 있습니다. **새 파이프라인 실험**은 결합 모드에서만 선택할 수 있으며 기본 설정은 아닙니다.

개발 검사는 `uv run pytest -q`, `uv run python scripts/integration.py`, `uv run python scripts/integration.py --mode hybrid`로 실행합니다. 실제 모델 의미 평가와 공개 PDF 코퍼스 도구는 `scripts/evaluate_meaning.py`, `scripts/accuracy_corpus.py`에 있습니다. 개발용 원문·결과는 로컬 `test_vault/`에만 저장합니다.

라이선스는 **AGPL-3.0-only**입니다. 상위 프로젝트, 모델 가중치와 글꼴의 라이선스·출처는 [NOTICE.txt](NOTICE.txt), [LICENSE](LICENSE), [upstream.lock.json](upstream.lock.json)을 확인하세요.
