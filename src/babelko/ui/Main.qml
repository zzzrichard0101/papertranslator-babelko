import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts

ApplicationWindow {
    id: root
    visible: true
    width: 1440
    height: 900
    minimumWidth: 1050
    minimumHeight: 720
    title: "BabelKO · 한국어 PDF 번역기"
    font.family: "Source Han Sans KR"

    property int page: 0
    readonly property bool night: backend.settings.theme === "night"
    readonly property bool glass: backend.settings.glass
    readonly property real uiScale: backend.settings.text_scale
    readonly property bool compact: backend.settings.density === "compact"
    readonly property color ink: night ? "#ECF4F4" : "#193640"
    readonly property color muted: night ? "#9DB1BC" : "#637B83"
    readonly property color faint: night ? "#738C98" : "#8DA0A6"
    readonly property color line: night ? "#344B58" : "#DCE7E6"
    readonly property color accent: backend.settings.accent === "iris" ? "#7163B9"
                                   : backend.settings.accent === "coral" ? "#B96456" : "#176F70"
    readonly property color pageBack: night ? "#0F1925" : "#F0F5F4"

    color: pageBack

    Item {
        id: sceneBackdrop
        anchors.fill: parent
        layer.enabled: root.glass

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0; color: root.night ? "#102433" : "#DCEDEA" }
                GradientStop { position: 0.48; color: root.night ? "#1D293F" : "#F3F2EE" }
                GradientStop { position: 1; color: root.night ? "#132B36" : "#DCE9E9" }
            }
        }
        Item {
            id: ambientShapes
            anchors.fill: parent
            visible: false
            layer.enabled: true
            Rectangle {
                width: 560; height: 560; radius: 280
                x: root.width - 430; y: -255
                color: root.night ? "#268A91" : "#62D7C9"
                NumberAnimation on x {
                    from: root.width - 430; to: root.width - 510
                    duration: 14000; loops: Animation.Infinite
                    easing.type: Easing.InOutSine
                    running: backend.settings.motion && !backend.job.active
                }
            }
            Rectangle {
                width: 470; height: 470; radius: 235
                x: 170; y: root.height - 215
                color: root.night ? "#6B54B0" : "#A899EB"
                NumberAnimation on y {
                    from: root.height - 215; to: root.height - 290
                    duration: 16000; loops: Animation.Infinite
                    easing.type: Easing.InOutSine
                    running: backend.settings.motion && !backend.job.active
                }
            }
            Rectangle {
                width: 410; height: 410; radius: 205
                x: root.width * 0.53; y: root.height * 0.41
                color: root.night ? "#B87370" : "#F5B89F"
            }
        }
        MultiEffect {
            anchors.fill: parent
            source: ambientShapes
            visible: root.glass
            autoPaddingEnabled: false
            blurEnabled: true
            blurMax: 64
            blurMultiplier: 2.5
            blur: 1.0
            opacity: root.night ? 0.45 : 0.48
        }
        Repeater {
            model: 8
            Rectangle {
                x: 24 + index * 190
                y: 0
                width: 1; height: root.height
                color: root.night ? "#11D0F7F4" : "#23FFFFFF"
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 17
        spacing: 17

        GlassPanel {
            Layout.preferredWidth: 224
            Layout.fillHeight: true
            night: root.night
            glass: root.glass; backdrop: sceneBackdrop
            corner: 26

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 69
                    spacing: 11
                    Rectangle {
                        Layout.preferredWidth: 39; Layout.preferredHeight: 39
                        radius: 13
                        color: root.accent
                        Text {
                            anchors.centerIn: parent
                            text: "文"
                            color: "white"
                            font.pixelSize: 22
                            font.weight: Font.DemiBold
                        }
                    }
                    Column {
                        spacing: 2
                        Text { text: "BabelKO"; color: root.ink; font.pixelSize: 19 * root.uiScale; font.weight: Font.Bold }
                        Text { text: "PAPER WORKBENCH"; color: root.faint; font.pixelSize: 9 * root.uiScale; font.letterSpacing: 1.2 }
                    }
                }

                Text {
                    Layout.topMargin: 25
                    Layout.bottomMargin: 13
                    text: "WORKSPACE"
                    color: root.faint
                    font.pixelSize: 10 * root.uiScale
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.8
                }
                UiButton {
                    Layout.fillWidth: true
                    label: "번역 작업실"; symbol: "▤"
                    selected: root.page === 0
                    night: root.night; accent: root.accent; uiScale: root.uiScale
                    onClicked: root.page = 0
                }
                Item { Layout.preferredHeight: 9 }
                UiButton {
                    Layout.fillWidth: true
                    label: "결과 확인"; symbol: "◇"
                    selected: root.page === 1
                    night: root.night; accent: root.accent; uiScale: root.uiScale
                    onClicked: root.page = 1
                }

                Rectangle { Layout.fillWidth: true; Layout.topMargin: 26; height: 1; color: root.line }
                Text {
                    Layout.topMargin: 24
                    text: "CURRENT DOCUMENT"
                    color: root.faint
                    font.pixelSize: 10 * root.uiScale
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.8
                }
                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 13
                    text: backend.job.title || "아직 선택한 문서가 없습니다"
                    color: root.ink
                    font.pixelSize: 13 * root.uiScale
                    font.weight: Font.DemiBold
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }
                Text {
                    Layout.topMargin: 7
                    text: backend.job.sourcePages ? backend.job.sourcePages + "쪽 · 영어 → 한국어" : "PDF를 선택해 시작하세요"
                    color: root.muted
                    font.pixelSize: 11 * root.uiScale
                }
                Item { Layout.fillHeight: true }
                Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
                UiButton {
                    objectName: "settingsNavigation"
                    Layout.fillWidth: true
                    Layout.topMargin: 14
                    label: "화면 설정"; symbol: "≡"
                    selected: root.page === 2
                    night: root.night; accent: root.accent; uiScale: root.uiScale
                    onClicked: root.page = 2
                }
                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 13
                    text: "로컬에서 번역 · 작업 기록 유지"
                    color: root.faint
                    font.pixelSize: 10 * root.uiScale
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 13

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 57
                spacing: 12
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        text: root.page === 2 ? "화면 설정" : root.page === 1 ? "결과 확인" : "번역 작업실"
                        color: root.ink
                        font.pixelSize: 22 * root.uiScale
                        font.weight: Font.Bold
                    }
                    Text {
                        text: root.page === 2 ? "읽는 경험을 취향에 맞게 조정하세요" :
                              root.page === 1 ? "원문과 번역 결과를 이어서 살펴보세요" :
                              "문서를 그대로 읽고, 한국어로 다시 만듭니다"
                        color: root.muted
                        font.pixelSize: 12 * root.uiScale
                    }
                }
                Rectangle {
                    Layout.preferredWidth: statusText.implicitWidth + 33
                    Layout.preferredHeight: 32
                    radius: 16
                    color: root.night ? "#263C42" : "#E2F0EB"
                    Text {
                        id: statusText
                        anchors.centerIn: parent
                        text: backend.job.active ? "●  처리 중" : backend.job.status === "completed" ? "●  완료" : "●  로컬 준비"
                        color: root.accent
                        font.pixelSize: 11 * root.uiScale
                        font.weight: Font.DemiBold
                    }
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: root.page

                Item {
                    RowLayout {
                        anchors.fill: parent
                        spacing: 16
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 13

                            GlassPanel {
                                Layout.fillWidth: true
                                Layout.preferredHeight: root.compact ? 102 : 119
                                night: root.night; glass: root.glass; backdrop: sceneBackdrop
                                Rectangle {
                                    anchors.left: parent.left; anchors.leftMargin: 17
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 54; height: 54; radius: 17
                                    color: root.night ? "#2B4149" : "#E3F0ED"
                                    Text { anchors.centerIn: parent; text: "▤"; color: root.accent; font.pixelSize: 29 }
                                }
                                Column {
                                    anchors.left: parent.left; anchors.leftMargin: 86
                                    anchors.right: chooseButton.left; anchors.rightMargin: 14
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 6
                                    Text {
                                        width: parent.width
                                        text: backend.form.source ? backend.job.title : "PDF를 여기로 가져오세요"
                                        color: root.ink
                                        font.pixelSize: 16 * root.uiScale
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideMiddle
                                    }
                                    Text {
                                        width: parent.width
                                        text: backend.form.source ? backend.form.source : "클릭하거나 파일을 끌어 놓아 시작"
                                        color: root.muted
                                        font.pixelSize: 11 * root.uiScale
                                        elide: Text.ElideMiddle
                                    }
                                }
                                UiButton {
                                    id: chooseButton
                                    anchors.right: parent.right; anchors.rightMargin: 18
                                    anchors.verticalCenter: parent.verticalCenter
                                    label: "PDF 선택"
                                    available: !backend.job.active
                                    night: root.night; accent: root.accent; uiScale: root.uiScale
                                    onClicked: backend.pickSource()
                                }
                                DropArea {
                                    anchors.fill: parent
                                    onDropped: {
                                        if (drop.hasUrls && drop.urls.length > 0)
                                            backend.setSourceUrl(drop.urls[0].toString())
                                    }
                                }
                            }

                            GlassPanel {
                                Layout.fillWidth: true
                                Layout.preferredHeight: root.compact ? 174 : 194
                                night: root.night; glass: root.glass; backdrop: sceneBackdrop
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 18
                                    spacing: 12
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: "작업 설정"; color: root.ink; font.pixelSize: 14 * root.uiScale; font.weight: Font.DemiBold }
                                        Item { Layout.fillWidth: true }
                                        Text { text: "원본을 보존하며 로컬 처리"; color: root.muted; font.pixelSize: 10 * root.uiScale }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 10
                                        Text { text: "쪽 범위"; color: root.muted; font.pixelSize: 12 * root.uiScale; Layout.preferredWidth: 64 }
                                        TextField {
                                            id: pagesField
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 35
                                            text: backend.form.pages
                                            enabled: !backend.job.active
                                            placeholderText: "전체 쪽 · 예: 1-5,9,12-"
                                            color: root.ink
                                            font.pixelSize: 12 * root.uiScale
                                            verticalAlignment: TextInput.AlignVCenter
                                            onEditingFinished: backend.setForm("pages", text)
                                            background: Rectangle { radius: 11; color: root.night ? "#21303D" : "#FFFFFF"; border.color: root.line }
                                        }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        Text { text: "OCR"; color: root.muted; font.pixelSize: 12 * root.uiScale; Layout.preferredWidth: 64 }
                                        ChoiceChip { label: "자동"; selected: backend.form.ocr === "auto"; available: !backend.job.active; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setForm("ocr", "auto") }
                                        ChoiceChip { label: "끔"; selected: backend.form.ocr === "off"; available: !backend.job.active; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setForm("ocr", "off") }
                                        ChoiceChip { label: "강제"; selected: backend.form.ocr === "force"; available: !backend.job.active; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setForm("ocr", "force") }
                                        Item { Layout.fillWidth: true }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        Text { text: "번역"; color: root.muted; font.pixelSize: 12 * root.uiScale; Layout.preferredWidth: 64 }
                                        ChoiceChip { label: "Hy-MT2 + Qwen 검수"; selected: backend.form.mode === "hybrid"; available: !backend.job.active; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setForm("mode", "hybrid") }
                                        ChoiceChip { label: "Qwen 단일"; selected: backend.form.mode === "qwen"; available: !backend.job.active; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setForm("mode", "qwen") }
                                        Item { Layout.fillWidth: true }
                                    }
                                }
                            }

                            GlassPanel {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                night: root.night; glass: root.glass; backdrop: sceneBackdrop
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 18
                                    spacing: 12
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: "문서 미리보기"; color: root.ink; font.pixelSize: 14 * root.uiScale; font.weight: Font.DemiBold }
                                        Item { Layout.fillWidth: true }
                                        Text { text: backend.settings.preview_layout === "spread" ? "원문 · 번역 나란히" : "번역 집중"; color: root.muted; font.pixelSize: 10 * root.uiScale }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        spacing: 13
                                        Rectangle {
                                            visible: backend.settings.preview_layout === "spread" || !backend.koreanPreview
                                            Layout.fillWidth: true; Layout.fillHeight: true
                                            radius: 14
                                            color: root.night ? "#1B2935" : "#EFF4F2"
                                            border.color: root.line
                                            ColumnLayout {
                                                anchors.fill: parent; anchors.margins: 12; spacing: 8
                                                Text { text: "01  ORIGINAL"; color: root.muted; font.pixelSize: 10 * root.uiScale; font.letterSpacing: 1.2 }
                                                Item {
                                                    Layout.fillWidth: true; Layout.fillHeight: true
                                                    Image { anchors.fill: parent; source: backend.sourcePreview; fillMode: Image.PreserveAspectFit; smooth: true; asynchronous: true; visible: backend.sourcePreview !== "" }
                                                    Text { anchors.centerIn: parent; text: "원문 PDF 미리보기"; color: root.faint; font.pixelSize: 12 * root.uiScale; visible: backend.sourcePreview === "" }
                                                }
                                            }
                                        }
                                        Rectangle {
                                            Layout.fillWidth: true; Layout.fillHeight: true
                                            radius: 14
                                            color: root.night ? "#1B2935" : "#EFF4F2"
                                            border.color: root.line
                                            ColumnLayout {
                                                anchors.fill: parent; anchors.margins: 12; spacing: 8
                                                Text { text: "02  KOREAN"; color: root.muted; font.pixelSize: 10 * root.uiScale; font.letterSpacing: 1.2 }
                                                Item {
                                                    Layout.fillWidth: true; Layout.fillHeight: true
                                                    Image { anchors.fill: parent; source: backend.koreanPreview; fillMode: Image.PreserveAspectFit; smooth: true; asynchronous: true; visible: backend.koreanPreview !== "" }
                                                    Column {
                                                        anchors.centerIn: parent
                                                        spacing: 8
                                                        visible: backend.koreanPreview === ""
                                                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "↗"; color: root.accent; font.pixelSize: 29 }
                                                        Text { text: "번역 후 이곳에 나타납니다"; color: root.faint; font.pixelSize: 12 * root.uiScale }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        GlassPanel {
                            Layout.preferredWidth: Math.min(292, root.width * 0.22)
                            Layout.fillHeight: true
                            night: root.night; glass: root.glass; backdrop: sceneBackdrop
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 20
                                spacing: 12
                                Text { text: "TRANSLATION SESSION"; color: root.faint; font.pixelSize: 10 * root.uiScale; font.weight: Font.DemiBold; font.letterSpacing: 1.6 }
                                Text { text: "영어에서 한국어로"; color: root.ink; font.pixelSize: 18 * root.uiScale; font.weight: Font.Bold; wrapMode: Text.Wrap }
                                Text { text: "원문의 구조를 살피고, 번역과 검수를 한곳에서 이어갑니다."; color: root.muted; font.pixelSize: 11 * root.uiScale; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                Rectangle { Layout.fillWidth: true; Layout.topMargin: 12; height: 1; color: root.line }
                                Text { text: "지금 하는 작업"; color: root.faint; font.pixelSize: 11 * root.uiScale }
                                Text { Layout.fillWidth: true; text: backend.job.stageDisplay; color: root.ink; font.pixelSize: 14 * root.uiScale; font.weight: Font.DemiBold; wrapMode: Text.Wrap }
                                Text { Layout.fillWidth: true; visible: backend.job.stepDetail !== ""; text: backend.job.stepDetail; color: root.muted; font.pixelSize: 11 * root.uiScale; wrapMode: Text.Wrap }
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 112
                                    radius: 16
                                    color: root.night ? "#2A3C4A" : "#E8F3F0"
                                    border.width: 1
                                    border.color: root.night ? "#4B6872" : "#CCE4DE"
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 13
                                        spacing: 4
                                        Text { text: backend.job.pageTitle; color: root.muted; font.pixelSize: 10 * root.uiScale; font.weight: Font.DemiBold }
                                        Text { Layout.fillWidth: true; text: backend.job.pageValue; color: root.accent; font.pixelSize: 21 * root.uiScale; font.weight: Font.Bold; elide: Text.ElideRight }
                                        Text { Layout.fillWidth: true; text: backend.job.pageCaption; color: root.muted; font.pixelSize: 10 * root.uiScale; wrapMode: Text.Wrap; maximumLineCount: 2 }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "진행률"; color: root.muted; font.pixelSize: 11 * root.uiScale }
                                    Item { Layout.fillWidth: true }
                                    Text { text: backend.job.progress + "%"; color: root.accent; font.pixelSize: 18 * root.uiScale; font.weight: Font.Bold }
                                }
                                Rectangle {
                                    Layout.fillWidth: true; Layout.preferredHeight: 8; radius: 4
                                    color: root.night ? "#33434B" : "#E3ECEB"
                                    Rectangle {
                                        width: parent.width * backend.job.progress / 100
                                        height: parent.height; radius: 4; color: root.accent
                                        Behavior on width { NumberAnimation { duration: backend.settings.motion ? 300 : 0 } }
                                    }
                                }
                                Text { Layout.fillWidth: true; text: backend.job.details; color: root.muted; font.pixelSize: 11 * root.uiScale; wrapMode: Text.Wrap }
                                Item { Layout.fillHeight: true }
                                UiButton {
                                    Layout.fillWidth: true
                                    label: "새 번역 시작"; symbol: "→"; primary: true
                                    available: !backend.job.active && backend.form.source !== ""
                                    night: root.night; accent: root.accent; uiScale: root.uiScale
                                    onClicked: backend.startTranslation()
                                }
                                UiButton {
                                    Layout.fillWidth: true
                                    label: backend.job.active ? "취소 · 캐시 유지" : "이 작업 다시 시작"
                                    available: backend.job.active || backend.job.canResume
                                    night: root.night; accent: root.accent; uiScale: root.uiScale
                                    onClicked: backend.job.active ? backend.cancelTranslation() : backend.resumeTranslation()
                                }
                                Rectangle { Layout.fillWidth: true; Layout.topMargin: 5; height: 1; color: root.line }
                                Text { text: "저장 위치"; color: root.faint; font.pixelSize: 10 * root.uiScale }
                                Text {
                                    Layout.fillWidth: true
                                    text: backend.form.destination
                                    color: root.muted; font.pixelSize: 10 * root.uiScale
                                    elide: Text.ElideMiddle
                                }
                                UiButton {
                                    Layout.fillWidth: true
                                    label: "폴더 바꾸기"
                                    available: !backend.job.active
                                    night: root.night; accent: root.accent; uiScale: root.uiScale
                                    onClicked: backend.pickDestination()
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Text { text: "추가 검수"; color: root.muted; font.pixelSize: 11 * root.uiScale; Layout.fillWidth: true }
                                    UiToggle { checked: backend.form.experimental; available: backend.form.mode === "hybrid" && !backend.job.active; night: root.night; accent: root.accent; onToggled: (nextValue) => backend.setForm("experimental", nextValue) }
                                }
                            }
                        }
                    }
                }

                Item {
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 14
                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 115
                            night: root.night; glass: root.glass; backdrop: sceneBackdrop
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 22; spacing: 7
                                Text { text: backend.job.title || "작업을 선택하세요"; color: root.ink; font.pixelSize: 18 * root.uiScale; font.weight: Font.Bold; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text { text: backend.job.stage + "  ·  " + backend.job.details; color: root.muted; font.pixelSize: 12 * root.uiScale; Layout.fillWidth: true; elide: Text.ElideRight }
                            }
                        }
                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            night: root.night; glass: root.glass; backdrop: sceneBackdrop
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 24; spacing: 14
                                Text { text: "완성된 파일"; color: root.ink; font.pixelSize: 16 * root.uiScale; font.weight: Font.DemiBold }
                                Text { text: "결과가 생성되면 아래에서 열 수 있습니다. 원문과 번역을 함께 확인하세요."; color: root.muted; font.pixelSize: 12 * root.uiScale; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                Item { Layout.preferredHeight: 10 }
                                UiButton { Layout.fillWidth: true; label: "한국어 PDF 열기"; symbol: "▣"; primary: true; available: backend.job.hasKorean; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.openResult("Korean.pdf") }
                                UiButton { Layout.fillWidth: true; label: "영한 대조본 열기"; symbol: "▤"; available: backend.job.hasBilingual; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.openResult("Bilingual.pdf") }
                                UiButton { Layout.fillWidth: true; label: "그림 범례 열기"; symbol: "◇"; available: backend.job.hasLegends; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.openResult("FigureLegends.html") }
                                UiButton { Layout.fillWidth: true; label: "결과 폴더 열기"; symbol: "↗"; available: backend.job.hasOutput; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.openResult("") }
                                Item { Layout.fillHeight: true }
                                Text { text: "자동 검사 결과는 의미 정확성의 보증이 아닙니다. 중요한 문서는 원문과 대조해 주세요."; color: root.faint; font.pixelSize: 11 * root.uiScale; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            }
                        }
                    }
                }

                Flickable {
                    clip: true
                    contentWidth: width
                    contentHeight: settingsContent.implicitHeight + 18
                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                        width: 6
                        background: Item {}
                        contentItem: Rectangle { radius: 3; color: root.night ? "#526978" : "#BECECD" }
                    }
                    ColumnLayout {
                        id: settingsContent
                        width: parent.width - 12
                        spacing: 14
                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 118
                            night: root.night; glass: root.glass; backdrop: sceneBackdrop
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 22; spacing: 8
                                Text { text: "나에게 맞는 작업 공간"; color: root.ink; font.pixelSize: 19 * root.uiScale; font.weight: Font.Bold }
                                Text { text: "화면 설정은 즉시 적용되고 이 컴퓨터에 저장됩니다. 번역 모델과 결과 PDF는 바뀌지 않습니다."; color: root.muted; font.pixelSize: 12 * root.uiScale; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            }
                        }
                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 170
                            night: root.night; glass: root.glass; backdrop: sceneBackdrop
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 22; spacing: 13
                                Text { text: "테마"; color: root.ink; font.pixelSize: 15 * root.uiScale; font.weight: Font.DemiBold }
                                Text { text: "종이의 차분함 또는 야간 작업실의 깊이"; color: root.muted; font.pixelSize: 11 * root.uiScale }
                                RowLayout { spacing: 12
                                    UiButton { label: "페이퍼"; symbol: "◯"; selected: backend.settings.theme === "paper"; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setSetting("theme", "paper") }
                                    UiButton { objectName: "nightThemeChoice"; label: "나이트"; symbol: "●"; selected: backend.settings.theme === "night"; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setSetting("theme", "night") }
                                }
                            }
                        }
                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 160
                            night: root.night; glass: root.glass; backdrop: sceneBackdrop
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 22; spacing: 13
                                Text { text: "포인트 색상"; color: root.ink; font.pixelSize: 15 * root.uiScale; font.weight: Font.DemiBold }
                                Text { text: "선택과 진행 상태에만 은은하게 사용합니다"; color: root.muted; font.pixelSize: 11 * root.uiScale }
                                RowLayout { spacing: 10
                                    ChoiceChip { label: "딥 틸"; selected: backend.settings.accent === "teal"; night: root.night; accent: "#176F70"; uiScale: root.uiScale; onClicked: backend.setSetting("accent", "teal") }
                                    ChoiceChip { label: "아이리스"; selected: backend.settings.accent === "iris"; night: root.night; accent: "#7163B9"; uiScale: root.uiScale; onClicked: backend.setSetting("accent", "iris") }
                                    ChoiceChip { label: "코랄"; selected: backend.settings.accent === "coral"; night: root.night; accent: "#B96456"; uiScale: root.uiScale; onClicked: backend.setSetting("accent", "coral") }
                                }
                            }
                        }
                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 163
                            night: root.night; glass: root.glass; backdrop: sceneBackdrop
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 22; spacing: 8
                                RowLayout { Layout.fillWidth: true
                                    ColumnLayout { spacing: 3
                                        Text { text: "반투명 패널"; color: root.ink; font.pixelSize: 14 * root.uiScale; font.weight: Font.DemiBold }
                                        Text { text: "도구와 문서 사이에 깊이를 더합니다"; color: root.muted; font.pixelSize: 11 * root.uiScale }
                                    }
                                    Item { Layout.fillWidth: true }
                                    UiToggle { checked: backend.settings.glass; night: root.night; accent: root.accent; onToggled: (nextValue) => backend.setSetting("glass", nextValue) }
                                }
                                Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
                                RowLayout { Layout.fillWidth: true
                                    ColumnLayout { spacing: 3
                                        Text { text: "부드러운 움직임"; color: root.ink; font.pixelSize: 14 * root.uiScale; font.weight: Font.DemiBold }
                                        Text { text: "배경과 상태 전환의 작은 애니메이션"; color: root.muted; font.pixelSize: 11 * root.uiScale }
                                    }
                                    Item { Layout.fillWidth: true }
                                    UiToggle { checked: backend.settings.motion; night: root.night; accent: root.accent; onToggled: (nextValue) => backend.setSetting("motion", nextValue) }
                                }
                            }
                        }
                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 226
                            night: root.night; glass: root.glass; backdrop: sceneBackdrop
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 22; spacing: 12
                                Text { text: "읽기와 배치"; color: root.ink; font.pixelSize: 15 * root.uiScale; font.weight: Font.DemiBold }
                                RowLayout { Layout.fillWidth: true; spacing: 11
                                    Text { text: "미리보기"; color: root.muted; font.pixelSize: 11 * root.uiScale; Layout.preferredWidth: 85 }
                                    ChoiceChip { label: "원문 · 번역"; selected: backend.settings.preview_layout === "spread"; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setSetting("preview_layout", "spread") }
                                    ChoiceChip { label: "번역 집중"; selected: backend.settings.preview_layout === "focus"; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setSetting("preview_layout", "focus") }
                                }
                                RowLayout { Layout.fillWidth: true; spacing: 11
                                    Text { text: "화면 밀도"; color: root.muted; font.pixelSize: 11 * root.uiScale; Layout.preferredWidth: 85 }
                                    ChoiceChip { label: "여유롭게"; selected: backend.settings.density === "comfortable"; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setSetting("density", "comfortable") }
                                    ChoiceChip { label: "촘촘하게"; selected: backend.settings.density === "compact"; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setSetting("density", "compact") }
                                }
                                RowLayout { Layout.fillWidth: true; spacing: 9
                                    Text { text: "글자 크기"; color: root.muted; font.pixelSize: 11 * root.uiScale; Layout.preferredWidth: 85 }
                                    ChoiceChip { label: "90%"; selected: backend.settings.text_scale === 0.9; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setSetting("text_scale", 0.9) }
                                    ChoiceChip { label: "100%"; selected: backend.settings.text_scale === 1.0; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setSetting("text_scale", 1.0) }
                                    ChoiceChip { label: "110%"; selected: backend.settings.text_scale === 1.1; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setSetting("text_scale", 1.1) }
                                    ChoiceChip { label: "120%"; selected: backend.settings.text_scale === 1.2; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.setSetting("text_scale", 1.2) }
                                }
                            }
                        }
                        UiButton { Layout.alignment: Qt.AlignRight; label: "기본값으로 되돌리기"; night: root.night; accent: root.accent; uiScale: root.uiScale; onClicked: backend.resetSettings() }
                    }
                }
            }
        }
    }

    Dialog {
        id: errorDialog
        title: "확인 필요"
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok
        width: Math.min(460, root.width - 60)
        contentItem: Text { text: errorMessage.text; wrapMode: Text.Wrap; color: root.ink; font.pixelSize: 13 * root.uiScale }
        background: Rectangle { radius: 18; color: root.night ? "#243341" : "#FFFFFF"; border.color: root.line }
    }
    Text { id: errorMessage; visible: false }
    Connections {
        target: backend
        function onErrorRaised(message) {
            errorMessage.text = message
            errorDialog.open()
        }
    }
}
