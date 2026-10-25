import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: atlas
    objectName: "wordNebula"
    property var wordData: backend.wordSpace
    property int selectedIndex: -1
    property bool flatMode: false
    property bool spaceFailed: false
    property string searchMessage: ""
    readonly property bool use3D: backend.supportsSpace && !flatMode && !spaceFailed
    readonly property var selected: selectedIndex >= 0 &&
                                     selectedIndex < (wordData.points || []).length
                                     ? wordData.points[selectedIndex] : ({})

    onWordDataChanged: { selectedIndex = -1; searchMessage = "" }
    function chooseWord(index) {
        if (index < 0 || index >= (wordData.points || []).length) return
        selectedIndex = index
        searchMessage = ""
    }
    function searchWord(query) {
        const needle = query.trim().toLowerCase()
        if (!needle) return
        const points = wordData.points || []
        let partial = -1
        for (let index = 0; index < points.length; index++) {
            if (points[index].word === needle) { chooseWord(index); return }
            if (partial < 0 && points[index].word.indexOf(needle) === 0) partial = index
        }
        if (partial >= 0) chooseWord(partial)
        else searchMessage = "표시된 상위 단어에서 찾지 못했습니다."
    }
    function wordIndex(word) {
        const points = wordData.points || []
        for (let index = 0; index < points.length; index++)
            if (points[index].word === word) return index
        return -1
    }

    Rectangle {
        anchors.fill: parent
        radius: 26
        gradient: Gradient {
            GradientStop { position: 0; color: "#061621" }
            GradientStop { position: 0.65; color: "#0D1E34" }
            GradientStop { position: 1; color: "#211833" }
        }
        border.width: 1; border.color: "#365668"
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 22
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                spacing: 3
                Text { text: "WORD NEBULA  /  LOCAL PDF DATA"; color: "#8DBFCA"; font.pixelSize: 10; font.letterSpacing: 2.0; font.weight: Font.DemiBold }
                Text { text: "이 문서의 단어가 만든 우주"; color: "#F0FAFB"; font.pixelSize: 18; font.weight: Font.Bold }
            }
            Item { Layout.fillWidth: true }
            Text {
                text: wordData.status === "ready" ?
                      wordData.points.length + "개 단어 · " + wordData.analyzed_tokens.toLocaleString() + "회 출현" :
                      wordData.status === "loading" ? "분석 중" : "PDF를 선택하세요"
                color: "#B6D5DB"; font.pixelSize: 12
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14

            Item {
                id: stage
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                Rectangle { anchors.fill: parent; radius: 17; color: "#071523"; border.color: "#26475A" }
                Loader {
                    id: cloudLoader
                    anchors.fill: parent
                    active: atlas.visible && wordData.status === "ready"
                    source: atlas.use3D ? "AtlasSpace3D.qml" : "WordCloud2D.qml"
                    onStatusChanged: {
                        if (status === Loader.Error && atlas.use3D) atlas.spaceFailed = true
                    }
                }
                Binding { target: cloudLoader.item; property: "graph"; value: atlas.wordData; when: cloudLoader.item !== null }
                Binding { target: cloudLoader.item; property: "selectedIndex"; value: atlas.selectedIndex; when: cloudLoader.item !== null }
                Connections {
                    target: cloudLoader.item
                    ignoreUnknownSignals: true
                    function onWordPicked(index) { atlas.chooseWord(index) }
                }

                Column {
                    anchors.left: parent.left; anchors.top: parent.top
                    anchors.margins: 16; spacing: 4
                    Text { text: atlas.use3D ? "◈  CO-OCCURRENCE SPACE" : "◈  WORD FIELD"; color: "#9ED7D5"; font.pixelSize: 10; font.weight: Font.DemiBold; font.letterSpacing: 1.1 }
                    Text { text: "크기  빈도     거리  동시 등장     깊이  문서 흐름"; color: "#779EAB"; font.pixelSize: 10 }
                }
                UiButton {
                    anchors.top: parent.top; anchors.right: parent.right
                    anchors.margins: 10
                    label: atlas.use3D ? "2D 보기" : backend.supportsSpace && !atlas.spaceFailed ? "3D 보기" : "3D 설치 필요"
                    symbol: atlas.use3D ? "▤" : "✧"
                    available: backend.supportsSpace && !atlas.spaceFailed
                    night: true; accent: "#85DBD5"
                    onClicked: atlas.flatMode = !atlas.flatMode
                }
                Text {
                    visible: wordData.status === "ready"
                    anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottomMargin: 16
                    text: atlas.use3D ? "드래그 회전  ·  휠 확대  ·  단어 클릭" : "휠 확대  ·  단어 클릭"
                    color: "#9FC8CF"; font.pixelSize: 11
                }
                Column {
                    visible: wordData.status !== "ready"
                    anchors.centerIn: parent
                    width: Math.min(430, parent.width - 40)
                    spacing: 12
                    BusyIndicator {
                        visible: wordData.status === "loading"
                        running: visible
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        text: wordData.status === "loading" ? "문서의 단어 관계를 읽는 중입니다…" :
                              wordData.status === "failed" ? "단어 분석에 실패했습니다. 다시 읽기를 눌러주세요." :
                              wordData.status === "empty" ? "읽을 수 있는 단어가 없습니다. 스캔본이라면 로컬 OCR 처리 후 다시 읽어주세요." :
                              "PDF를 선택하면 단어들이 이 공간에 나타납니다."
                        color: "#D3E8EB"; font.pixelSize: 14
                    }
                }
            }

            Rectangle {
                Layout.preferredWidth: 266
                Layout.fillHeight: true
                radius: 18
                color: "#C1112839"
                border.color: "#385769"
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 10
                    Text { text: "탐색"; color: "#F1FAFA"; font.pixelSize: 15; font.weight: Font.Bold }
                    Text { text: "단어를 찾거나 입자를 선택하세요"; color: "#A6C7CF"; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    TextField {
                        id: searchField
                        Layout.fillWidth: true
                        enabled: wordData.status === "ready"
                        placeholderText: "단어 검색 ↵"
                        color: "#F2FBFC"; placeholderTextColor: "#7597A6"
                        font.pixelSize: 12
                        background: Rectangle { radius: 9; color: "#1B3445"; border.color: searchField.activeFocus ? "#7BDCD6" : "#38576A" }
                        onAccepted: atlas.searchWord(text)
                    }
                    Text { text: atlas.searchMessage; visible: text.length > 0; color: "#FFBA97"; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#355062" }
                    Text {
                        text: selected.word || "입자를 클릭해보세요"
                        color: selected.color || "#D6EDED"
                        font.pixelSize: selected.word ? 20 : 13
                        font.weight: Font.Bold
                        Layout.fillWidth: true; elide: Text.ElideRight
                    }
                    Text {
                        text: selected.word ? selected.count + "회 등장  ·  " + selected.page_hits + "쪽에서 발견" :
                              "자주 나오는 단어일수록 입자가 큽니다."
                        color: "#B6D0D6"; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    Text {
                        visible: !!selected.word
                        text: selected.first_page === selected.last_page ? selected.first_page + "쪽" :
                              selected.first_page + "–" + selected.last_page + "쪽에 분포"
                        color: "#8CB6BF"; font.pixelSize: 10; Layout.fillWidth: true
                    }
                    Text { text: selected.word ? "함께 등장한 단어" : "많이 등장한 단어"; color: "#A5C7CE"; font.pixelSize: 11; font.weight: Font.DemiBold }
                    Flow {
                        Layout.fillWidth: true
                        width: parent.width
                        spacing: 5
                        Repeater {
                            model: selected.word ? (selected.neighbors || []) : (wordData.points || []).slice(0, 6).map(point => point.word)
                            delegate: UiButton {
                                required property string modelData
                                label: modelData
                                night: true; accent: "#8EDFD9"
                                onClicked: atlas.chooseWord(atlas.wordIndex(modelData))
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#355062" }
                    Text {
                        text: wordData.status === "ready" ?
                              wordData.unique_words.toLocaleString() + "개 고유 단어 중 상위 " + wordData.points.length + "개 표시" : ""
                        color: "#A6C3CA"; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    Text {
                        text: "가까운 거리는 함께 등장한 기록을 나타냅니다. 의미가 같다는 판정은 아닙니다."
                        color: "#8EABB6"; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    UiButton {
                        Layout.fillWidth: true
                        label: "단어 다시 읽기"; symbol: "↻"
                        available: wordData.status !== "loading"
                        night: true; accent: "#8EDFD9"
                        onClicked: backend.reloadWordSpace()
                    }
                }
            }
        }
    }
}
