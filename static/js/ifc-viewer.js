// static/js/ifc-viewer.js

import * as THREE from "https://unpkg.com/three@0.141.0/build/three.module.js";
import { OrbitControls } from "https://unpkg.com/three@0.141.0/examples/jsm/controls/OrbitControls.js";

class IFCViewer {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.pyodide = null;
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.currentFile = null;

    // Three.js 기본 설정 - Z축을 위로 설정
    THREE.Object3D.DefaultUp = new THREE.Vector3(0, 0, 1);
  }

  async initialize() {
    // 로딩 메시지 표시
    this.showStatus("Pyodide 초기화 중...");

    // Pyodide 초기화
    this.pyodide = await loadPyodide();

    this.showStatus("패키지 매니저 로딩 중...");
    await this.pyodide.loadPackage("micropip");

    const micropip = this.pyodide.pyimport("micropip");
    this.showStatus("IfcOpenShell 로딩 중... (시간이 걸릴 수 있습니다)");

    await micropip.install("IfcOpenShell-0.7.0-py3-none-any.whl");

    console.log(
      await this.pyodide.runPython(`
            import ifcopenshell
            ifcopenshell.version
        `)
    );

    // Three.js 씬 초기화
    this.initScene();

    this.showStatus("");
    return true;
  }

  initScene() {
    // 렌더러 생성
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setSize(
      this.container.clientWidth,
      this.container.clientHeight
    );
    this.renderer.setClearColor(0xf0f0f0, 1);
    this.container.appendChild(this.renderer.domElement);

    // 씬 생성
    this.scene = new THREE.Scene();

    // 조명 설정
    const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight1.position.set(20, 10, 30);
    this.scene.add(directionalLight1);

    const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.6);
    directionalLight2.position.set(-10, 1, -30);
    this.scene.add(directionalLight2);

    this.scene.add(new THREE.AmbientLight(0x404050));

    // 카메라 설정 - Z축이 위를 향하도록 설정
    this.camera = new THREE.PerspectiveCamera(
      45,
      this.container.clientWidth / this.container.clientHeight,
      1,
      10000
    );

    // 카메라의 up 벡터를 Z축으로 명시적 설정
    this.camera.up.set(0, 0, 1);

    // 컨트롤 설정 - 개선된 설정
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;

    // 회전 제한 설정 (더 자연스러운 회전을 위해)
    this.controls.enableZoom = true;
    this.controls.enablePan = true;
    this.controls.enableRotate = true;

    // 회전 속도 조정
    this.controls.rotateSpeed = 0.5;
    this.controls.zoomSpeed = 1.0;
    this.controls.panSpeed = 0.8;

    // 수직 회전 제한 (짐벌락 방지)
    this.controls.minPolarAngle = Math.PI * 0.1; // 18도
    this.controls.maxPolarAngle = Math.PI * 0.9; // 162도

    // 줌 제한
    this.controls.minDistance = 1;
    this.controls.maxDistance = 1000;

    // 윈도우 리사이즈 핸들러
    window.addEventListener("resize", () => this.onWindowResize());

    // 렌더링 루프 시작
    this.animate();
  }

  onWindowResize() {
    this.camera.aspect =
      this.container.clientWidth / this.container.clientHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(
      this.container.clientWidth,
      this.container.clientHeight
    );
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  async loadIFCFile(file) {
    this.showStatus("IFC 파일 처리 중...");

    // 기존 모델 제거
    this.clearScene();

    const content = await file.text();
    const ifcopenshell = this.pyodide.pyimport("ifcopenshell");
    const ifc = ifcopenshell.file.from_string(content);

    this.showStatus("지오메트리 생성 중...");

    const ifcopenshell_geom = this.pyodide.pyimport("ifcopenshell.geom");
    const settings = ifcopenshell_geom.settings();
    settings.set(settings.WELD_VERTICES, false);

    const iterator = ifcopenshell_geom.iterator(settings, ifc);

    if (iterator.initialize()) {
      let lastMeshId = null;
      let geometries = [];

      while (true) {
        const obj = iterator.get();
        const elementType = ifc.by_id(obj.id).is_a();

        // IfcOpeningElement와 IfcSpace 제외
        if (elementType !== "IfcOpeningElement" && elementType !== "IfcSpace") {
          if (lastMeshId !== obj.geometry.id) {
            geometries = this.createGeometries(obj);
            lastMeshId = obj.geometry.id;
          }

          this.addMeshesToScene(geometries, obj);
        }

        if (!iterator.next()) {
          break;
        }
      }
    }

    // 카메라 위치 조정
    this.fitCameraToScene();
    this.showStatus("");

    return true;
  }

  createGeometries(obj) {
    const geometries = [];

    // 재질 생성
    const materials = obj.geometry.materials.toJs().map(
      (mat) =>
        new THREE.MeshLambertMaterial({
          color: new THREE.Color(...mat.diffuse.toJs()),
          opacity: 1.0 - mat.transparency,
          transparent: mat.transparency > 1e-5,
          side: THREE.DoubleSide,
        })
    );

    // 재질 ID 매핑
    const mapping = {};
    obj.geometry.material_ids.toJs().forEach((id, idx) => {
      mapping[id] = mapping[id] || [];
      mapping[id].push(idx);
    });

    // 버텍스 데이터
    const vertices = new Float32Array(obj.geometry.verts.toJs());
    const normals = new Float32Array(obj.geometry.normals.toJs());
    const faces = obj.geometry.faces.toJs();

    // 기본 재질 처리
    let offset = 0;
    if (mapping[-1]) {
      materials.unshift(
        new THREE.MeshLambertMaterial({
          color: new THREE.Color(0.6, 0.6, 0.6),
          side: THREE.DoubleSide,
        })
      );
      offset = 1;
    }

    // 각 재질별로 지오메트리 생성
    materials.forEach((material, materialIndex) => {
      const geometry = new THREE.BufferGeometry();

      const indices = mapping[materialIndex - offset].flatMap((i) => [
        faces[3 * i + 0],
        faces[3 * i + 1],
        faces[3 * i + 2],
      ]);

      geometry.setIndex(indices);
      geometry.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(vertices, 3)
      );
      geometry.setAttribute(
        "normal",
        new THREE.Float32BufferAttribute(normals, 3)
      );

      geometries.push([geometry, material]);
    });

    return geometries;
  }

  addMeshesToScene(geometries, obj) {
    for (const [geometry, material] of geometries) {
      const mesh = new THREE.Mesh(geometry, material);

      // 변환 행렬 적용
      const matrix = new THREE.Matrix4();
      const m = obj.transformation.matrix.data.toJs();
      matrix.set(
        m[0],
        m[1],
        m[2],
        0,
        m[3],
        m[4],
        m[5],
        0,
        m[6],
        m[7],
        m[8],
        0,
        m[9],
        m[10],
        m[11],
        1
      );
      matrix.transpose();

      mesh.matrixAutoUpdate = false;
      mesh.matrix = matrix;

      // 메타데이터 저장
      mesh.userData = {
        ifcId: obj.id,
        ifcType: obj.type,
        globalId: obj.guid,
      };

      this.scene.add(mesh);
    }
  }

  clearScene() {
    while (this.scene.children.length > 3) {
      // 조명 3개는 유지
      const child = this.scene.children[3];
      if (child.geometry) child.geometry.dispose();
      if (child.material) {
        if (Array.isArray(child.material)) {
          child.material.forEach((m) => m.dispose());
        } else {
          child.material.dispose();
        }
      }
      this.scene.remove(child);
    }
  }

  fitCameraToScene() {
    const box = new THREE.Box3();
    box.setFromObject(this.scene);

    if (box.isEmpty()) {
      // 박스가 비어있으면 기본 위치 설정
      this.camera.position.set(10, 10, 10);
      this.controls.target.set(0, 0, 0);
      this.controls.update();
      return;
    }

    const center = new THREE.Vector3();
    box.getCenter(center);

    // 컨트롤 타겟을 중심으로 설정
    this.controls.target.copy(center);

    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);

    // FOV를 라디안으로 변환
    const fov = this.camera.fov * (Math.PI / 180);
    let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));

    cameraZ *= 2.0; // 충분한 여유 공간

    // Z축이 위를 향하는 좌표계에 맞는 카메라 위치 설정
    // 남동쪽에서 약간 위로 바라보는 각도
    const distance = cameraZ;
    const cameraPosition = new THREE.Vector3(
      center.x + distance * 0.7, // X축 (동쪽)
      center.y + distance * 0.7, // Y축 (남쪽)
      center.z + distance * 0.3 // Z축 (위쪽)
    );

    this.camera.position.copy(cameraPosition);

    // 카메라가 중심을 바라보도록 설정
    this.camera.lookAt(center);

    // Near/Far 평면 설정
    this.camera.near = distance / 100;
    this.camera.far = distance * 100;
    this.camera.updateProjectionMatrix();

    // 컨트롤 업데이트
    this.controls.update();

    console.log("Camera fitted to scene:", {
      center: center,
      cameraPosition: cameraPosition,
      distance: distance,
      boxSize: size,
    });
  }

  showStatus(message) {
    const statusEl = document.getElementById("viewer-status");
    if (statusEl) {
      statusEl.textContent = message;
      statusEl.style.display = message ? "block" : "none";
    }
  }

  // 파일 URL로부터 로드
  async loadFromURL(url) {
    try {
      const response = await fetch(url);
      const blob = await response.blob();
      const file = new File([blob], "model.ifc");
      return await this.loadIFCFile(file);
    } catch (error) {
      console.error("IFC 파일 로드 실패:", error);
      this.showStatus("파일 로드 실패");
      return false;
    }
  }
}

// 전역 변수로 뷰어 인스턴스 저장
window.IFCViewer = IFCViewer;
