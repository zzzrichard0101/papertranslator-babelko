import QtQuick

Item {
    id: cloud
    objectName: "wordCloud2D"
    property var graph: ({ points: [], edges: [] })
    property int selectedIndex: -1
    property real zoom: 1
    signal wordPicked(int index)
    readonly property real factor: Math.min(width / 650, height / 510) * zoom

    Rectangle { anchors.fill: parent; color: "#071523" }
    Canvas {
        id: links
        anchors.fill: parent
        onPaint: {
            const context = getContext("2d")
            context.clearRect(0, 0, width, height)
            const points = cloud.graph.points || []
            const edges = cloud.graph.edges || []
            for (let index = 0; index < edges.length; index++) {
                const edge = edges[index]
                const a = points[edge.a], b = points[edge.b]
                if (!a || !b) continue
                context.strokeStyle = cloud.selectedIndex < 0 ||
                                      edge.a === cloud.selectedIndex || edge.b === cloud.selectedIndex
                                      ? "rgba(126,203,218,0.23)" : "rgba(126,203,218,0.035)"
                context.lineWidth = 1
                context.beginPath()
                context.moveTo(width / 2 + a.x * cloud.factor, height / 2 - a.y * cloud.factor)
                context.lineTo(width / 2 + b.x * cloud.factor, height / 2 - b.y * cloud.factor)
                context.stroke()
            }
        }
        Connections {
            target: cloud
            function onGraphChanged() { links.requestPaint() }
            function onSelectedIndexChanged() { links.requestPaint() }
            function onFactorChanged() { links.requestPaint() }
        }
    }
    Repeater {
        model: cloud.graph.points || []
        delegate: Rectangle {
            id: pointItem
            required property var modelData
            required property int index
            readonly property var point: modelData
            readonly property real diameter: Math.max(5, point.radius * 1.65)
            x: cloud.width / 2 + point.x * cloud.factor - width / 2
            y: cloud.height / 2 - point.y * cloud.factor - height / 2
            width: diameter; height: diameter; radius: diameter / 2
            color: point.color
            opacity: cloud.selectedIndex >= 0 && cloud.selectedIndex !== index ? 0.45 : 0.98
            scale: hover.hovered || cloud.selectedIndex === index ? 1.7 : 1
            Behavior on scale { NumberAnimation { duration: 140 } }
            HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: cloud.wordPicked(pointItem.index) }
            Text {
                visible: hover.hovered
                y: -28; x: width / 2
                text: point.word + " · " + point.count + "회"
                color: "#E8FAF9"; font.pixelSize: 11
            }
        }
    }
    WheelHandler {
        onWheel: (event) => {
            cloud.zoom = Math.max(0.6, Math.min(2.8,
                cloud.zoom + event.angleDelta.y / 900))
            event.accepted = true
        }
    }
}
