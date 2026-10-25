import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Particles

Item {
    id: atlas
    property var pageData: backend.atlas
    property var selected: backend.atlasSelection
    readonly property bool animated: visible && backend.settings.motion && !backend.job.active
    readonly property color proseColor: "#8EE7DE"
    readonly property color imageColor: "#D7B5FF"
    readonly property color tableColor: "#F2CD88"
    readonly property color warningColor: "#FFAD83"

    function regionColor(region) {
        if (region.status === "source_gap_suspected") return warningColor
        return region.kind === "image" ? imageColor : region.kind === "table" ? tableColor : proseColor
    }
    function statusLabel(status) {
        if (status === "source_gap_suspected") return "원문 누락 의심 · 진단 기록"
        if (status === "source_preserved") return "원본 이미지 영역"
        if (status === "output_created") return "번역 PDF 생성됨 · 의미 검증 아님"
        if (status === "processing") return "처리 중"
        if (status === "outside_selection") return "이번 번역에서 선택하지 않은 쪽"
        return "번역 전 원문"
    }
    function stateColor(status) {
        if (status === "source_gap_suspected") return warningColor
        if (status === "output_created") return "#80E3A7"
        if (status === "processing") return "#FFE092"
        if (status === "outside_selection") return "#6D879A"
        return "#A7C5D0"
    }

    Rectangle {
        anchors.fill: parent
        radius: 26
        gradient: Gradient {
            GradientStop { position: 0; color: "#071622" }
            GradientStop { position: 0.58; color: "#101C34" }
            GradientStop { position: 1; color: "#231932" }
        }
        border.width: 1
        border.color: "#385466"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 22
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                spacing: 3
                Text { text: "DOCUMENT CONSTELLATION"; color: "#8CB9C5"; font.pixelSize: 10; font.letterSpacing: 2.1; font.weight: Font.DemiBold }
                Text { text: "페이지 속 문장과 그림을 탐험하세요"; color: "#EFFBFA"; font.pixelSize: 18; font.weight: Font.Bold }
            }
            Item { Layout.fillWidth: true }
            Text {
                text: pageData.total_pages ? pageData.source_page + " / " + pageData.total_pages + "쪽" : "PDF를 선택하세요"
                color: "#B4D3D9"; font.pixelSize: 13; font.weight: Font.DemiBold
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

                Rectangle {
                    id: paper
                    readonly property real ratio: pageData.aspect || 0.72
                    height: Math.min(stage.height - 18, (stage.width - 18) / ratio)
                    width: height * ratio
                    anchors.centerIn: parent
                    radius: 12
                    color: "#15283B"
                    border.width: 1
                    border.color: "#5A7B88"
                    Image {
                        anchors.fill: parent
                        anchors.margins: 3
                        source: backend.atlasPreview
                        fillMode: Image.PreserveAspectFit
                        opacity: 0.16
                        asynchronous: true
                    }
                }

                ParticleSystem { id: system; running: atlas.animated }
                ImageParticle {
                    system: system; groups: ["text"]
                    source: "qrc:///particleresources/glowdot.png"
                    color: atlas.proseColor; alpha: 0.52
                }
                ImageParticle {
                    system: system; groups: ["image"]
                    source: "qrc:///particleresources/glowdot.png"
                    color: atlas.imageColor; alpha: 0.5
                }
                ImageParticle {
                    system: system; groups: ["table"]
                    source: "qrc:///particleresources/glowdot.png"
                    color: atlas.tableColor; alpha: 0.56
                }
                ImageParticle {
                    system: system; groups: ["suspect"]
                    source: "qrc:///particleresources/glowdot.png"
                    color: atlas.warningColor; alpha: 0.7
                }
                HoverHandler { id: pointer; enabled: atlas.animated }
                Attractor {
                    system: system
                    enabled: atlas.animated && pointer.hovered
                    x: pointer.point.position.x - 65
                    y: pointer.point.position.y - 65
                    width: 130; height: 130
                    pointX: 65; pointY: 65
                    strength: -65
                    proportionalToDistance: Attractor.InverseLinear
                    affectedParameter: Attractor.Velocity
                }

                Repeater {
                    model: pageData.regions || []
                    delegate: Item {
                        id: regionItem
                        required property var modelData
                        required property int index
                        readonly property var region: modelData
                        property real hoverX: 0
                        property real hoverY: 0
                        function displaced(baseX, baseY, horizontal) {
                            if (!regionMouse.containsMouse || !atlas.animated) return horizontal ? baseX : baseY
                            const dx = baseX - hoverX
                            const dy = baseY - hoverY
                            const distance = Math.sqrt(dx * dx + dy * dy)
                            const push = Math.max(0, 1 - distance / 78) * 26
                            return (horizontal ? baseX + dx / Math.max(1, distance) * push
                                               : baseY + dy / Math.max(1, distance) * push)
                        }
                        x: paper.x + region.x * paper.width
                        y: paper.y + region.y * paper.height
                        width: Math.max(5, region.w * paper.width)
                        height: Math.max(5, region.h * paper.height)

                        Rectangle {
                            anchors.fill: parent
                            radius: region.kind === "image" ? 6 : 3
                            color: atlas.regionColor(region)
                            opacity: regionMouse.containsMouse || selected.id === region.id ? 0.22 : 0.075
                            border.width: regionMouse.containsMouse || selected.id === region.id ? 1 : 0
                            border.color: atlas.regionColor(region)
                            Behavior on opacity { NumberAnimation { duration: 180 } }
                        }
                        Rectangle {
                            width: region.status === "source_preserved" ? 0 : 2
                            height: parent.height
                            radius: 1
                            color: atlas.stateColor(region.status)
                            opacity: region.status === "outside_selection" ? 0.28 : 0.9
                        }
                        Emitter {
                            id: emitter
                            system: system
                            anchors.fill: parent
                            group: region.status === "source_gap_suspected" ? "suspect" : region.kind
                            enabled: atlas.animated
                            emitRate: Math.max(2, region.particles / 5)
                            maximumEmitted: region.particles
                            lifeSpan: 5000
                            size: region.kind === "image" ? 5 : 3.6
                            sizeVariation: 1.2
                            velocity: PointDirection { xVariation: 5; yVariation: 5 }
                        }
                        Repeater {
                            model: Math.min(10, Math.max(3, Math.ceil(region.particles / 3)))
                            delegate: Rectangle {
                                required property int index
                                readonly property real homeX: ((index * 0.61803398875 + 0.17) % 1) * regionItem.width
                                readonly property real homeY: ((index * 0.75487766625 + 0.31) % 1) * regionItem.height
                                x: regionItem.displaced(homeX, homeY, true)
                                y: regionItem.displaced(homeX, homeY, false)
                                width: region.kind === "text" ? 2.8 : 3.8
                                height: width
                                radius: width / 2
                                color: atlas.regionColor(region)
                                opacity: regionMouse.containsMouse ? 0.98 : 0.68
                                Behavior on x {
                                    enabled: regionMouse.containsMouse && atlas.animated
                                    SpringAnimation { spring: 3; damping: 0.32 }
                                }
                                Behavior on y {
                                    enabled: regionMouse.containsMouse && atlas.animated
                                    SpringAnimation { spring: 3; damping: 0.32 }
                                }
                            }
                        }
                        MouseArea {
                            id: regionMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onPositionChanged: (mouse) => {
                                regionItem.hoverX = mouse.x
                                regionItem.hoverY = mouse.y
                            }
                            onClicked: {
                                backend.selectAtlasRegion(regionItem.index)
                                if (atlas.animated) emitter.burst(Math.min(26, region.particles))
                            }
                        }
                    }
                }
                Text {
                    anchors.centerIn: parent
                    visible: !pageData.total_pages
                    text: "PDF를 선택하면 문서의 구조가 여기에 나타납니다"
                    color: "#BDCFD7"; font.pixelSize: 13
                }
            }

            Rectangle {
                Layout.preferredWidth: 248
                Layout.fillHeight: true
                radius: 19
                color: "#AA122638"
                border.color: "#365264"
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 17
                    spacing: 10
                    Text { text: "구조 · 상태"; color: "#EAF7F7"; font.pixelSize: 15; font.weight: Font.Bold }
                    Text { text: "한 점의 위치는 원문 PDF의 좌표를 따릅니다."; color: "#A9C7D0"; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#345060" }
                    Text { text: "● 문장 · 문단"; color: atlas.proseColor; font.pixelSize: 11 }
                    Text { text: "● 이미지 영역"; color: atlas.imageColor; font.pixelSize: 11 }
                    Text { text: "● 표 후보 영역"; color: atlas.tableColor; font.pixelSize: 11 }
                    Text { text: "● 원문 누락 의심"; color: atlas.warningColor; font.pixelSize: 11 }
                    Text { text: "│ 초록: 출력 생성 · 금색: 처리 중"; color: "#AFC5C8"; font.pixelSize: 10 }
                    Text {
                        text: pageData.regions ? pageData.regions.length + "개 영역 · 누락 의심 " + pageData.suspect_regions + "개" : ""
                        color: "#B5CCD2"; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#345060" }
                    Text {
                        text: selected.excerpt || "영역에 마우스를 올리고 클릭해보세요."
                        color: "#F1F8FA"; font.pixelSize: 12; wrapMode: Text.Wrap
                        Layout.fillWidth: true; maximumLineCount: 7; elide: Text.ElideRight
                    }
                    Text {
                        text: selected.status ? atlas.statusLabel(selected.status) : ""
                        color: selected.status === "source_gap_suspected" ? atlas.warningColor : "#9ABBC4"
                        font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    Item { Layout.fillHeight: true }
                    UiButton { label: "원문 쪽 열기"; symbol: "↗"; available: pageData.total_pages > 0; Layout.fillWidth: true; night: true; accent: atlas.proseColor; onClicked: backend.openAtlasPage(false) }
                    UiButton { label: "번역 쪽 열기"; symbol: "↗"; available: pageData.translated_available === true; Layout.fillWidth: true; night: true; accent: atlas.proseColor; onClicked: backend.openAtlasPage(true) }
                    Text { text: "이 지도는 진단용입니다. 색상만으로 번역 정확성을 판정하지 않습니다."; color: "#8EABB6"; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            UiButton { label: "‹"; available: pageData.source_page > 1; night: true; accent: atlas.proseColor; onClicked: backend.selectAtlasPage(pageData.source_page - 2) }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 34
                radius: 17
                color: "#1A3446"
                border.color: "#365B69"
                Rectangle {
                    id: pageTrack
                    x: 15; y: 15; width: parent.width - 30; height: 4; radius: 2; color: "#385467"
                    Rectangle {
                        width: pageData.total_pages > 1 ? parent.width * (pageData.source_page - 1) / (pageData.total_pages - 1) : 0
                        height: parent.height; radius: 2; color: atlas.proseColor
                    }
                    Rectangle {
                        x: pageData.total_pages > 1 ? parent.width * (pageData.source_page - 1) / (pageData.total_pages - 1) - 5 : -5
                        y: -4; width: 12; height: 12; radius: 6; color: atlas.proseColor
                    }
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: pageData.total_pages > 1
                    cursorShape: Qt.PointingHandCursor
                    onClicked: (mouse) => backend.selectAtlasPage(
                        Math.min(pageData.total_pages - 1,
                                 Math.max(0, Math.round((mouse.x - 15) / pageTrack.width * (pageData.total_pages - 1)))))
                }
            }
            UiButton { label: "›"; available: pageData.source_page < pageData.total_pages; night: true; accent: atlas.proseColor; onClicked: backend.selectAtlasPage(pageData.source_page) }
        }
    }
}
