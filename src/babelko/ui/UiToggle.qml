import QtQuick

Rectangle {
    id: control
    property bool checked: false
    property bool available: true
    property bool night: false
    property color accent: "#176F70"
    signal toggled(bool nextValue)

    implicitWidth: 46
    implicitHeight: 27
    radius: height / 2
    color: checked ? accent : night ? "#3E5360" : "#CAD8D8"
    opacity: available ? 1 : 0.45
    Behavior on color { ColorAnimation { duration: 140 } }
    Rectangle {
        width: 21; height: 21; radius: 11
        x: control.checked ? control.width - width - 3 : 3
        y: 3
        color: "#FFFFFF"
        Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    }
    MouseArea {
        anchors.fill: parent
        enabled: control.available
        cursorShape: Qt.PointingHandCursor
        onClicked: control.toggled(!control.checked)
    }
}
