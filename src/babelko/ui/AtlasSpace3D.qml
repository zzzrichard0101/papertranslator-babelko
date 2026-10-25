import QtQuick
import QtQuick3D

Item {
    id: space
    objectName: "wordSpaceScene"
    property var graph: ({ points: [], edges: [], clusters: [] })
    property int selectedIndex: -1
    property real yaw: -16
    property real tilt: -10
    property real cameraDistance: 880
    property int hoveredIndex: -1
    property real hoverX: 0
    property real hoverY: 0
    property int projectionTick: 0
    signal wordPicked(int index)

    function resetView() {
        yaw = -16
        tilt = -10
        cameraDistance = 880
    }

    function nearestWord(x, y, radius) {
        const points = space.graph.points || []
        let nearest = -1
        let distance = radius * radius
        for (let index = 0; index < points.length; index++) {
            const word = points[index]
            const scenePoint = orbitNode.mapPositionToScene(Qt.vector3d(word.x, word.y, word.z))
            const projected = view.mapFrom3DScene(scenePoint)
            if (projected.z <= 0) continue
            const squared = Math.pow(projected.x - x, 2) + Math.pow(projected.y - y, 2)
            if (squared < distance) {
                distance = squared
                nearest = index
            }
        }
        return nearest
    }

    View3D {
        id: view
        objectName: "wordSpaceView"
        anchors.fill: parent
        camera: camera3D
        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: "#071523"
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.Medium
        }
        PerspectiveCamera {
            id: camera3D
            z: space.cameraDistance
            fieldOfView: 48
            clipFar: 2500
        }
        DirectionalLight {
            eulerRotation.x: -25
            eulerRotation.y: -30
            brightness: 1.0
            ambientColor: "#6C98A5"
        }
        Node {
            id: orbitNode
            eulerRotation.x: space.tilt
            eulerRotation.y: space.yaw

            // A halo is centered on each observed co-occurrence community.
            Repeater3D {
                model: space.graph.clusters || []
                delegate: Model {
                    required property var modelData
                    source: "#Sphere"
                    x: modelData.x; y: modelData.y; z: modelData.z
                    scale: Qt.vector3d(modelData.radius / 50,
                                       modelData.radius / 50,
                                       modelData.radius / 50)
                    pickable: false
                    materials: DefaultMaterial {
                        diffuseColor: modelData.color
                        opacity: 0.045
                        lighting: DefaultMaterial.NoLighting
                        cullMode: Material.NoCulling
                    }
                }
            }

            Repeater3D {
                model: space.graph.edges || []
                delegate: Model {
                    required property var modelData
                    readonly property bool adjacent: space.selectedIndex < 0 ||
                                                     modelData.a === space.selectedIndex ||
                                                     modelData.b === space.selectedIndex
                    source: "#Cylinder"
                    x: modelData.x; y: modelData.y; z: modelData.z
                    rotation: Qt.quaternion(modelData.qw, modelData.qx,
                                            modelData.qy, modelData.qz)
                    scale: Qt.vector3d(0.009, modelData.length / 100, 0.009)
                    pickable: false
                    materials: DefaultMaterial {
                        diffuseColor: "#79B7CB"
                        opacity: adjacent ? 0.27 : 0.035
                        lighting: DefaultMaterial.NoLighting
                    }
                }
            }

            Repeater3D {
                model: space.graph.points || []
                delegate: Node {
                    id: wordNode
                    required property var modelData
                    required property int index
                    readonly property var word: modelData
                    x: word.x; y: word.y; z: word.z
                    Model {
                        objectName: "wordParticle3D"
                        property int wordIndex: wordNode.index
                        readonly property bool emphasized: space.selectedIndex === wordNode.index ||
                                                            space.hoveredIndex === wordNode.index
                        source: "#Sphere"
                        scale: Qt.vector3d(word.radius * (emphasized ? 1.4 : 0.85) / 100,
                                           word.radius * (emphasized ? 1.4 : 0.85) / 100,
                                           word.radius * (emphasized ? 1.4 : 0.85) / 100)
                        pickable: true
                        materials: DefaultMaterial {
                            diffuseColor: word.color
                            opacity: space.selectedIndex >= 0 &&
                                     space.selectedIndex < (space.graph.points || []).length &&
                                     !emphasized &&
                                     word.cluster !== space.graph.points[space.selectedIndex].cluster ? 0.35 : 0.98
                            lighting: DefaultMaterial.NoLighting
                        }
                    }
                }
            }
        }
    }

    // Project the most frequent words onto the view so the particles remain readable.
    Timer {
        interval: 160
        repeat: true
        running: space.visible
        onTriggered: space.projectionTick++
    }
    Repeater {
        objectName: "wordLabelRepeater"
        model: Math.min(6, (space.graph.points || []).length)
        delegate: Rectangle {
            objectName: "wordLabel3D"
            z: 2
            property int termIndex: index
            readonly property var term: space.graph.points[termIndex]
            readonly property vector3d projected: {
                space.yaw; space.tilt; space.cameraDistance; space.projectionTick
                return view.mapFrom3DScene(orbitNode.mapPositionToScene(
                    Qt.vector3d(term.x, term.y, term.z)))
            }
            visible: projected.z > 0 && projected.x > 24 && projected.x < view.width - 100 &&
                     projected.y > 32 && projected.y < view.height - 40
            x: projected.x + 8
            y: projected.y - height / 2
            width: label.implicitWidth + 14
            height: 23
            radius: 6
            color: space.selectedIndex === index ? "#D01E4150" : "#B30C2230"
            border.color: space.selectedIndex === index ? "#B7FFEA" : term.color
            border.width: 1
            Text {
                id: label
                anchors.centerIn: parent
                text: term.word
                color: "#F4FFFF"
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: space.wordPicked(index)
            }
        }
    }

    MouseArea {
        id: interaction
        anchors.fill: parent
        hoverEnabled: true
        property real previousX: 0
        property real previousY: 0
        property bool rotated: false
        cursorShape: pressed ? Qt.ClosedHandCursor :
                     space.hoveredIndex >= 0 ? Qt.PointingHandCursor : Qt.OpenHandCursor
        onPressed: (mouse) => {
            previousX = mouse.x; previousY = mouse.y; rotated = false
            space.hoveredIndex = -1
        }
        onPositionChanged: (mouse) => {
            if (!(mouse.buttons & Qt.LeftButton)) {
                space.hoverX = mouse.x
                space.hoverY = mouse.y
                hoverTimer.restart()
                return
            }
            const dx = mouse.x - previousX
            const dy = mouse.y - previousY
            if (Math.abs(dx) + Math.abs(dy) > 1) rotated = true
            space.yaw = Math.max(-80, Math.min(80, space.yaw + dx * 0.3))
            space.tilt = Math.max(-55, Math.min(55, space.tilt + dy * 0.26))
            previousX = mouse.x
            previousY = mouse.y
        }
        onClicked: (mouse) => {
            if (rotated) return
            const hit = view.pick(mouse.x, mouse.y)
            const index = hit.objectHit && hit.objectHit.wordIndex !== undefined
                          ? hit.objectHit.wordIndex : space.nearestWord(mouse.x, mouse.y, 12)
            if (index >= 0) space.wordPicked(index)
        }
        onWheel: (wheel) => {
            space.cameraDistance = Math.max(430, Math.min(1500,
                space.cameraDistance - wheel.angleDelta.y * 0.38))
            wheel.accepted = true
        }
        onExited: space.hoveredIndex = -1
    }
    Timer {
        id: hoverTimer
        interval: 70
        repeat: false
        onTriggered: {
            if (interaction.pressed) return
            const hit = view.pick(space.hoverX, space.hoverY)
            space.hoveredIndex = hit.objectHit && hit.objectHit.wordIndex !== undefined
                                 ? hit.objectHit.wordIndex : space.nearestWord(space.hoverX, space.hoverY, 10)
        }
    }
    Rectangle {
        visible: space.hoveredIndex >= 0 && space.hoveredIndex < (space.graph.points || []).length
        x: Math.min(space.width - width - 10, space.hoverX + 16)
        y: Math.min(space.height - height - 10, space.hoverY + 16)
        width: 190; height: 52; radius: 10
        color: "#EC132C42"
        border.color: "#7AD9D1"
        Column {
            anchors.centerIn: parent
            spacing: 2
            Text {
                text: space.hoveredIndex >= 0 ? space.graph.points[space.hoveredIndex].word : ""
                color: "#F2FFFF"; font.pixelSize: 14; font.weight: Font.Bold
            }
            Text {
                text: space.hoveredIndex >= 0 ? space.graph.points[space.hoveredIndex].count + "회 등장" : ""
                color: "#AACDD2"; font.pixelSize: 10
            }
        }
    }
}
