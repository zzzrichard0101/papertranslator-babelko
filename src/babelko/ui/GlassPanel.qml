import QtQuick
import QtQuick.Effects

Item {
    id: panel
    property bool night: false
    property bool glass: true
    property int corner: 22
    property Item backdrop: null

    // Capture only the ambient scene. The panel cannot sample itself.
    ShaderEffectSource {
        id: backgroundSample
        anchors.fill: parent
        visible: false
        sourceItem: panel.glass ? panel.backdrop : null
        sourceRect: panel.backdrop
                    ? Qt.rect(panel.mapToItem(panel.backdrop, 0, 0).x,
                              panel.mapToItem(panel.backdrop, 0, 0).y,
                              panel.width, panel.height)
                    : Qt.rect(0, 0, 0, 0)
        textureSize: Qt.size(Math.max(1, Math.ceil(panel.width / 2)),
                             Math.max(1, Math.ceil(panel.height / 2)))
        live: true
    }

    Rectangle {
        id: roundMask
        anchors.fill: parent
        radius: panel.corner
        color: "white"
        visible: false
        layer.enabled: true
    }

    MultiEffect {
        anchors.fill: parent
        visible: panel.glass && panel.backdrop !== null
        source: backgroundSample
        autoPaddingEnabled: false
        blurEnabled: true
        blurMax: 24
        blur: 1.0
        blurMultiplier: 1.5
        maskEnabled: true
        maskSource: roundMask
    }

    Rectangle {
        anchors.fill: parent
        radius: panel.corner
        color: panel.glass ? (panel.night ? "#80202D3B" : "#9CFFFFFF")
                           : (panel.night ? "#202B38" : "#FFFFFF")
        border.width: 1
        border.color: panel.night ? (panel.glass ? "#66B6D1D5" : "#304555")
                                  : (panel.glass ? "#F5FFFFFF" : "#DDE4E6")
        gradient: panel.glass ? frostTint : null
        Gradient {
            id: frostTint
            GradientStop { position: 0; color: panel.night ? "#9A293947" : "#B6FFFFFF" }
            GradientStop { position: 1; color: panel.night ? "#76162331" : "#89F4FAFA" }
        }
    }

    Rectangle {
        x: panel.corner + 3
        y: 1
        width: Math.max(0, panel.width - (panel.corner + 3) * 2)
        height: 1
        visible: panel.glass
        color: panel.night ? "#54FFFFFF" : "#EFFFFFFF"
    }
}
