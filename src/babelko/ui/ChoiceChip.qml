import QtQuick

Rectangle {
    id: chip
    property string label: ""
    property bool selected: false
    property bool available: true
    property bool night: false
    property color accent: "#166C70"
    property real uiScale: 1.0
    signal clicked()

    implicitWidth: name.implicitWidth + 30 * uiScale
    implicitHeight: 35 * uiScale
    radius: height / 2
    color: selected ? accent : night ? "#1E2C39" : "#F4F7F6"
    border.width: selected ? 0 : 1
    border.color: night ? "#3B5160" : "#DCE7E6"
    opacity: available ? 1 : 0.45
    Text {
        id: name
        anchors.centerIn: parent
        text: chip.label
        color: chip.selected ? "white" : chip.night ? "#CEDAE1" : "#3F555C"
        font.pixelSize: 12 * chip.uiScale
        font.weight: chip.selected ? Font.DemiBold : Font.Normal
    }
    MouseArea {
        anchors.fill: parent
        enabled: chip.available
        cursorShape: Qt.PointingHandCursor
        onClicked: chip.clicked()
    }
}
