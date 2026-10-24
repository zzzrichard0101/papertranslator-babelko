import QtQuick

Rectangle {
    id: button
    property string label: ""
    property string symbol: ""
    property bool primary: false
    property bool selected: false
    property bool available: true
    property bool night: false
    property color accent: "#166C70"
    property real uiScale: 1.0
    signal clicked()

    implicitHeight: 44 * uiScale
    implicitWidth: labelText.implicitWidth + (symbol ? 58 : 36)
    radius: 13 * uiScale
    color: primary ? accent : selected ? (night ? "#2E4051" : "#E5F0EF")
           : hover.hovered ? (night ? "#263644" : "#EEF5F4") : "transparent"
    border.width: primary || selected ? 0 : 1
    border.color: night ? "#385061" : "#DCE5E5"
    opacity: available ? 1 : 0.44
    Behavior on color { ColorAnimation { duration: 140 } }

    Row {
        anchors.centerIn: parent
        spacing: 8
        Text {
            visible: button.symbol !== ""
            text: button.symbol
            color: button.primary ? "#FFFFFF" : button.night ? "#D9E5E9" : "#314C54"
            font.family: "Segoe UI Symbol"
            font.pixelSize: 16 * button.uiScale
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            id: labelText
            text: button.label
            color: button.primary ? "#FFFFFF" : button.night ? "#EEF5F7" : "#233B45"
            font.pixelSize: 13 * button.uiScale
            font.weight: button.primary || button.selected ? Font.DemiBold : Font.Medium
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    HoverHandler { id: hover; enabled: button.available }
    MouseArea {
        anchors.fill: parent
        enabled: button.available
        cursorShape: Qt.PointingHandCursor
        onClicked: button.clicked()
    }
}
