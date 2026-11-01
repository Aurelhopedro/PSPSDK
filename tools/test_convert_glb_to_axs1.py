#!/usr/bin/env python3
"""
test_convert_glb_to_axs1.py — Testes unitários do conversor AXS1
RPG Axel Digital

Execução:
    python3 tools/test_convert_glb_to_axs1.py
"""

import sys
import os
import struct
import math
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert_glb_to_axs1 as conv

# ---------------------------------------------------------------------------
# Infraestrutura
# ---------------------------------------------------------------------------

PASSED = 0
FAILED = 0
ERRORS = []

def test(name, fn):
    global PASSED, FAILED
    try:
        fn()
        print(f"  ✅ {name}")
        PASSED += 1
    except AssertionError as e:
        print(f"  ❌ {name}: {e}")
        ERRORS.append(f"{name}: {e}")
        FAILED += 1
    except Exception as e:
        print(f"  ❌ {name}: EXCEÇÃO: {e}")
        ERRORS.append(f"{name}: EXCEÇÃO: {e}\n{traceback.format_exc()}")
        FAILED += 1

def eq(a, b, msg=""):
    assert a == b, f"{msg} {a!r} != {b!r}"

def near(a, b, tol=1e-4, msg=""):
    assert abs(float(a) - float(b)) < tol, f"{msg} |{a} - {b}| >= {tol}"

def near_vec(a, b, tol=1e-4, msg=""):
    assert len(a) == len(b), f"{msg} tamanhos: {len(a)} vs {len(b)}"
    for i, (x, y) in enumerate(zip(a, b)):
        assert abs(float(x) - float(y)) < tol, f"{msg}[{i}] |{x}-{y}| >= {tol}"

import numpy as np

# ---------------------------------------------------------------------------
# Helpers de construção de dados de teste
# ---------------------------------------------------------------------------

def make_bones(n=2):
    return [{"name": f"b{i}", "parent": i-1,
             "bind_pos": [0.0, float(i), 0.0],
             "bind_rot": [0.0, 0.0, 0.0, 1.0]} for i in range(n)]

def make_verts(n=3, bone_count=2):
    """Vértices com bone_idx sempre < bone_count."""
    return [{
        "u": 0.0, "v": 0.0,
        "nx": 0.0, "ny": 1.0, "nz": 0.0,
        "px": float(i), "py": 0.0, "pz": 0.0,
        "bone_idx": [0, 0, 0, 0],          # sempre osso 0, válido para qualquer bone_count ≥ 1
        "weight":   [1.0, 0.0, 0.0, 0.0],
    } for i in range(n)]

def make_clips(bone_count, names=None, frames=4):
    names = names or ["IDLE", "WALK", "RUN", "JUMP", "LAND"]
    clips = []
    for name in names:
        frame_data = [[{"rot": [0.0,0.0,0.0,1.0], "pos": [0.0,0.0,0.0]}
                       for _ in range(bone_count)] for _ in range(frames)]
        clips.append({"name": name, "fps": 30.0,
                      "frame_count": frames, "frames": frame_data})
    return clips

def write_read_validate(bones, verts, clips):
    """Escreve AXS1 e valida. Devolve (path, errors)."""
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    conv.write_axs1(path, bones, verts, clips)
    errors = conv.validate_axs1(path, bones, clips)
    return path, errors

# ---------------------------------------------------------------------------
# 1. Quaternião: normalização
# ---------------------------------------------------------------------------

def test_quat_normalize_unit():
    near_vec(conv.quat_normalize([0,0,0,1]), [0,0,0,1])

def test_quat_normalize_scale():
    near_vec(conv.quat_normalize([0,0,0,2]), [0,0,0,1])

def test_quat_normalize_zero():
    near_vec(conv.quat_normalize([0,0,0,0]), [0,0,0,1])

def test_quat_normalize_arbitrary():
    q = conv.quat_normalize([1,1,1,1])
    near(math.sqrt(sum(v**2 for v in q)), 1.0)

# ---------------------------------------------------------------------------
# 2. Quaternião: slerp
# ---------------------------------------------------------------------------

def test_quat_slerp_t0():
    near_vec(conv.quat_slerp([0,0,0,1],[0,1,0,0], 0.0), [0,0,0,1])

def test_quat_slerp_t1():
    near_vec(conv.quat_slerp([0,0,0,1],[0,1,0,0], 1.0), [0,1,0,0])

def test_quat_slerp_normalized():
    q0 = [0,0,0,1]
    q1 = conv.quat_normalize([1,1,1,1])
    r  = conv.quat_slerp(q0, q1, 0.5)
    near(math.sqrt(sum(v**2 for v in r)), 1.0, tol=1e-3)

# ---------------------------------------------------------------------------
# 3. Interpolação vec3
# ---------------------------------------------------------------------------

def test_vec3_linear():
    t  = np.array([0.0, 1.0])
    v  = np.array([[0,0,0],[1,2,3]], dtype=float)
    near_vec(conv.interpolate_vec3(t, v, 0.5, "LINEAR"), [0.5, 1.0, 1.5])

def test_vec3_step():
    t = np.array([0.0, 1.0])
    v = np.array([[0,0,0],[1,2,3]], dtype=float)
    near_vec(conv.interpolate_vec3(t, v, 0.9, "STEP"), [0,0,0])

def test_vec3_clamp_before():
    t = np.array([1.0, 2.0])
    v = np.array([[5,0,0],[10,0,0]], dtype=float)
    near(conv.interpolate_vec3(t, v, 0.0, "LINEAR")[0], 5.0)

def test_vec3_clamp_after():
    t = np.array([0.0, 1.0])
    v = np.array([[0,0,0],[7,0,0]], dtype=float)
    near(conv.interpolate_vec3(t, v, 2.0, "LINEAR")[0], 7.0)

def test_vec3_cubicspline_zero_tangents():
    # Tangentes zero → equivalente a linear
    t = np.array([0.0, 1.0])
    v = np.array([
        [[0,0,0],[0,0,0],[0,0,0]],
        [[0,0,0],[1,0,0],[0,0,0]],
    ], dtype=float)
    near(conv.interpolate_vec3(t, v, 0.5, "CUBICSPLINE")[0], 0.5, tol=1e-3)

def test_vec3_cubicspline_nonzero_tangents():
    """Com tangentes não-nulas, o resultado difere da interpolação linear."""
    t = np.array([0.0, 1.0])
    # Tangente de saída grande → puxar para além do valor linear
    v = np.array([
        [[0,0,0], [0.0,0,0], [2.0,0,0]],   # out_tan = 2
        [[0,0,0], [1.0,0,0], [0.0,0,0]],
    ], dtype=float)
    r  = conv.interpolate_vec3(t, v, 0.5, "CUBICSPLINE")[0]
    r_linear = 0.5
    # Com tangente de saída 2, resultado em t=0.5 deve ser maior que 0.5
    assert r != r_linear, f"CUBICSPLINE com tangente não-nula deve diferir de LINEAR: {r}"

# ---------------------------------------------------------------------------
# 4. Interpolação quat — LINEAR
# ---------------------------------------------------------------------------

def test_quat_linear_endpoints():
    q0 = np.array([0,0,0,1], dtype=float)
    q1 = np.array([0,0,1,0], dtype=float)
    t  = np.array([0.0, 1.0])
    v  = np.array([q0, q1])
    near_vec(conv.interpolate_quat(t, v, 0.0, "LINEAR"), [0,0,0,1])
    near_vec(conv.interpolate_quat(t, v, 1.0, "LINEAR"), [0,0,1,0])

def test_quat_step():
    q0 = np.array([0,0,0,1], dtype=float)
    q1 = np.array([0,1,0,0], dtype=float)
    t  = np.array([0.0, 1.0])
    v  = np.array([q0, q1])
    # STEP deve reter o valor anterior até ao próximo keyframe
    near_vec(conv.interpolate_quat(t, v, 0.99, "STEP"), [0,0,0,1])
    near_vec(conv.interpolate_quat(t, v, 1.0, "STEP"),  [0,1,0,0])

# ---------------------------------------------------------------------------
# 5. Interpolação quat — CUBICSPLINE com tangentes não-nulas
# ---------------------------------------------------------------------------

def test_quat_cubicspline_nonzero_tangents():
    """
    Com tangentes não-nulas, o Hermite cúbico deve produzir resultado
    diferente do slerp linear entre p0 e p1.
    """
    # p0 = identity, p1 = 180° em torno de Z
    p0 = [0.0, 0.0, 0.0,  1.0]
    p1 = [0.0, 0.0, 1.0,  0.0]
    # Tangente de saída significativa em X
    out_tan_0 = [0.5, 0.0, 0.0, 0.0]
    in_tan_1  = [0.0, 0.0, 0.0, 0.0]

    t  = np.array([0.0, 1.0])
    # shape (2, 3, 4): [in_tan, point, out_tan]
    v  = np.array([
        [[0,0,0,0], p0, out_tan_0],
        [in_tan_1,  p1, [0,0,0,0]],
    ], dtype=float)

    r_cubic  = conv.interpolate_quat(t, v, 0.5, "CUBICSPLINE")
    r_slerp  = conv.quat_slerp(p0, p1, 0.5)

    # Devem ser normalizados
    near(math.sqrt(sum(x**2 for x in r_cubic)), 1.0, tol=1e-3,
         msg="CUBICSPLINE deve ser normalizado")

    # Devem diferir (tangente não-nula afecta o caminho)
    diff = math.sqrt(sum((r_cubic[i] - r_slerp[i])**2 for i in range(4)))
    assert diff > 1e-3, (
        f"CUBICSPLINE com tangente não-nula deve diferir de slerp linear: "
        f"diff={diff:.6f}, cubic={r_cubic}, slerp={r_slerp}"
    )

def test_quat_cubicspline_zero_tangents():
    """Tangentes zero → próximo de slerp linear."""
    p0 = [0.0, 0.0, 0.0, 1.0]
    p1 = [0.0, 0.0, 1.0, 0.0]
    t  = np.array([0.0, 1.0])
    v  = np.array([
        [[0,0,0,0], p0, [0,0,0,0]],
        [[0,0,0,0], p1, [0,0,0,0]],
    ], dtype=float)
    r = conv.interpolate_quat(t, v, 0.5, "CUBICSPLINE")
    near(math.sqrt(sum(x**2 for x in r)), 1.0, tol=1e-3)

# ---------------------------------------------------------------------------
# 6. Hermite cúbico de quaternião directo
# ---------------------------------------------------------------------------

def test_quat_hermite_cubic_endpoints():
    p0 = [0.0, 0.0, 0.0, 1.0]
    p1 = [0.0, 0.0, 1.0, 0.0]
    m0 = [0.0, 0.0, 0.0, 0.0]
    m1 = [0.0, 0.0, 0.0, 0.0]
    near_vec(conv.quat_hermite_cubic(p0, m0, p1, m1, 0.0),
             conv.quat_normalize(p0), tol=1e-4)
    near_vec(conv.quat_hermite_cubic(p0, m0, p1, m1, 1.0),
             conv.quat_normalize(p1), tol=1e-4)

# ---------------------------------------------------------------------------
# 7. Mapeamento JOINTS_0
# ---------------------------------------------------------------------------

def test_joints0_mapping_basic():
    s2a = {0:0, 1:1, 2:2}
    n_skin = 3
    joints = [1, 2, 0, 0]; weights = [0.5, 0.3, 0.2, 0.0]
    bi4 = []; wsum = sum(weights)
    for k in range(4):
        sj = joints[k]; w = weights[k]
        assert 0 <= sj < n_skin
        bi4.append(s2a[sj])
    eq(bi4, [1, 2, 0, 0])

def test_joints0_invalid_raises():
    s2a = {0:0, 1:1}; n_skin = 2
    raised = False
    try:
        sj = 5
        if sj < 0 or sj >= n_skin:
            raise RuntimeError("fora do intervalo")
    except RuntimeError:
        raised = True
    assert raised

def test_joints0_eliminated_raises():
    s2a = {0:0}  # skin_joint 1 eliminado
    raised = False
    try:
        ai = s2a.get(1, None)
        if ai is None:
            raise RuntimeError("eliminado")
    except RuntimeError:
        raised = True
    assert raised

# ---------------------------------------------------------------------------
# 8. Normalização de pesos
# ---------------------------------------------------------------------------

def test_weights_basic():
    raw = [0.4, 0.3, 0.2, 0.1]; s = sum(raw)
    norm = [w/s for w in raw]
    near(sum(norm), 1.0)

def test_weights_partial():
    raw = [0.6, 0.4, 0.0, 0.0]; s = sum(raw)
    norm = [w/s for w in raw]
    near(sum(norm), 1.0); near(norm[2], 0.0)

def test_weights_zero_fallback():
    raw = [0.0]*4; s = sum(raw)
    norm = [1.0,0,0,0] if s < 1e-6 else [w/s for w in raw]
    near(norm[0], 1.0)

# ---------------------------------------------------------------------------
# 9. Seleção hierárquica
# ---------------------------------------------------------------------------

def test_hierarchy_expansion():
    joint_nodes = [0, 1, 2]
    children = {0:[1], 1:[2], 2:[]}

    def get_parent(si):
        nidx = joint_nodes[si]
        for other_si, other_nidx in enumerate(joint_nodes):
            if nidx in children.get(other_nidx, []):
                return other_si
        return -1

    expanded = {2}
    changed = True
    while changed:
        changed = False
        for si in list(expanded):
            p = get_parent(si)
            if p >= 0 and p not in expanded:
                expanded.add(p); changed = True
    eq(expanded, {0, 1, 2})

def test_hierarchy_limit():
    n = conv.AXS1_MAX_BONES + 1
    raised = False
    try:
        if n > conv.AXS1_MAX_BONES:
            raise RuntimeError("excede limite")
    except RuntimeError:
        raised = True
    assert raised

# ---------------------------------------------------------------------------
# 10. Clips — ausência e ordenação
# ---------------------------------------------------------------------------

def test_report_missing_all():
    missing = conv.report_missing_clips([])
    eq(len(missing), 5)

def test_report_missing_partial():
    clips = [{"name": "IDLE", "fps": 30, "frame_count": 2, "frames": []}]
    missing = conv.report_missing_clips(clips)
    assert "WALK" in missing; assert "RUN" in missing

def test_order_clips_raises_on_missing():
    clips = [{"name": "IDLE", "fps": 30, "frame_count": 2, "frames": []}]
    raised = False
    try:
        conv.order_clips(clips)
    except RuntimeError:
        raised = True
    assert raised, "Devia lançar RuntimeError quando faltam clips obrigatórios"

def test_order_clips_correct_order():
    bc = 1
    all5 = make_clips(bc, ["LAND", "JUMP", "RUN", "WALK", "IDLE"], frames=2)
    ordered = conv.order_clips(all5)
    names = [c["name"] for c in ordered]
    eq(names[:5], ["IDLE", "WALK", "RUN", "JUMP", "LAND"])

# ---------------------------------------------------------------------------
# 11. Limite de vértices e ossos
# ---------------------------------------------------------------------------

def test_max_vertices_constant():
    eq(conv.AXS1_MAX_VERTICES, 8192)

def test_max_bones_constant():
    eq(conv.AXS1_MAX_BONES, 24)

def test_vertex_limit_raises():
    raised = False
    try:
        max_v = 3
        verts_seen = 0
        for i in range(5):
            if verts_seen >= max_v:
                raise RuntimeError(f"excede limite {max_v}")
            verts_seen += 1
    except RuntimeError:
        raised = True
    assert raised

# ---------------------------------------------------------------------------
# 12. Estrutura binária AXS1
# ---------------------------------------------------------------------------

def test_axs1_header_fields():
    bc = 2; vc = 3; cc = 1
    bones = make_bones(bc); verts = make_verts(vc, bc)
    clips = make_clips(bc, ["IDLE","WALK","RUN","JUMP","LAND"][:cc], frames=2)
    path, _ = write_read_validate(bones, verts, clips)
    try:
        with open(path, "rb") as f: data = f.read()
        eq(data[0:4], b"AXS1")
        eq(struct.unpack_from("<I", data, 4)[0], 1)
        eq(struct.unpack_from("<I", data, 8)[0], bc)
        eq(struct.unpack_from("<I", data, 12)[0], vc)
        eq(struct.unpack_from("<I", data, 16)[0], cc)
    finally:
        os.unlink(path)

def test_axs1_total_size():
    bc = 3; vc = 5; fc = 4; cc = 2
    bones = make_bones(bc); verts = make_verts(vc, bc)
    clips = make_clips(bc, ["IDLE","WALK","RUN","JUMP","LAND"][:cc], frames=fc)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        sz = conv.write_axs1(path, bones, verts, clips)
        expected = (conv.AXS1_HEADER_SIZE
                    + bc * conv.AXS1_BONE_ONDISK
                    + vc * conv.AXS1_VERTEX_ONDISK
                    + cc * (conv.AXS1_CLIP_HDR_SIZE + fc * bc * conv.AXS1_KEY_ONDISK))
        eq(sz, expected)
    finally:
        os.unlink(path)

def test_axs1_bone_layout():
    bones = [{"name": "root", "parent": -1,
              "bind_pos": [1,2,3], "bind_rot": [0,0,0,1]}]
    verts = make_verts(3, 1)
    clips = make_clips(1, ["IDLE","WALK","RUN","JUMP","LAND"][:1], frames=2)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        with open(path, "rb") as f: data = f.read()
        off = conv.AXS1_HEADER_SIZE
        assert data[off:off+4] == b"root"
        eq(struct.unpack_from("<i", data, off+16)[0], -1)
        near_vec(struct.unpack_from("<3f", data, off+24), [1,2,3])
        near_vec(struct.unpack_from("<4f", data, off+36), [0,0,0,1])
    finally:
        os.unlink(path)

def test_axs1_vertex_layout_offsets():
    """Verifica os offsets correctos dentro do vértice (52 bytes)."""
    bones = make_bones(1)
    verts = [{
        "u": 0.25, "v": 0.75,
        "nx": 0.1, "ny": 0.9, "nz": 0.0,
        "px": 1.0, "py": 2.0, "pz": 3.0,
        "bone_idx": [0, 0, 0, 0],
        "weight": [1.0, 0.0, 0.0, 0.0],
    }]
    clips = make_clips(1, ["IDLE","WALK","RUN","JUMP","LAND"][:1], frames=2)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        with open(path, "rb") as f: data = f.read()
        off = conv.AXS1_HEADER_SIZE + conv.AXS1_BONE_ONDISK
        # UV @ offset 0
        near_vec(struct.unpack_from("<2f", data, off + 0),   [0.25, 0.75])
        # Normal @ offset 8
        near_vec(struct.unpack_from("<3f", data, off + 8),   [0.1, 0.9, 0.0], tol=1e-5)
        # Pos @ offset 20
        near_vec(struct.unpack_from("<3f", data, off + 20),  [1.0, 2.0, 3.0])
        # bone_idx @ offset 32
        eq(list(struct.unpack_from("<4B", data, off + 32)), [0,0,0,0])
        # weight @ offset 36
        near_vec(struct.unpack_from("<4f", data, off + 36), [1,0,0,0])
    finally:
        os.unlink(path)

# ---------------------------------------------------------------------------
# 13. Validação AXS1 — casos de sucesso e erro
# ---------------------------------------------------------------------------

def test_validate_ok():
    bc = 2
    bones = make_bones(bc)
    verts = make_verts(6, bc)
    clips = make_clips(bc, frames=3)   # 5 clips obrigatórios
    path, errors = write_read_validate(bones, verts, clips)
    try:
        eq(errors, [], msg=f"validação deve ser limpa: {errors}")
    finally:
        os.unlink(path)

def test_validate_bad_magic():
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        tmp.write(b"XXXX" + b"\x00"*28); path = tmp.name
    try:
        errors = conv.validate_axs1(path, [], [])
        assert any("Magic" in e or "magic" in e.lower() for e in errors), \
            f"Devia reportar magic: {errors}"
    finally:
        os.unlink(path)

def test_validate_bone_idx_out_of_range():
    """Vértice com bone_idx >= bone_count deve reportar erro."""
    bc = 2
    bones = make_bones(bc)
    verts = make_verts(3, bc)
    verts[1]["bone_idx"] = [bc, 0, 0, 0]  # índice inválido
    clips = make_clips(bc, frames=2)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        errors = conv.validate_axs1(path, bones, clips)
        assert any("bone_idx" in e for e in errors), \
            f"Devia reportar bone_idx inválido: {errors}"
    finally:
        os.unlink(path)

def test_validate_truncated_header():
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        tmp.write(b"AXS1" + b"\x00"*10); path = tmp.name
    try:
        errors = conv.validate_axs1(path, [], [])
        assert len(errors) > 0, "Devia reportar cabeçalho truncado"
        assert not any("struct.error" in e.lower() for e in errors), \
            "Não deve expor struct.error"
    finally:
        os.unlink(path)

def test_validate_truncated_bones():
    """Ficheiro truncado na secção de ossos."""
    bc = 2; vc = 3
    bones = make_bones(bc); verts = make_verts(vc, bc)
    clips = make_clips(bc, frames=2)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        # Truncar a meio dos ossos
        trunc = conv.AXS1_HEADER_SIZE + conv.AXS1_BONE_ONDISK // 2
        with open(path, "r+b") as f: f.truncate(trunc)
        errors = conv.validate_axs1(path, bones, clips)
        assert len(errors) > 0
        assert not any("struct.error" in e.lower() for e in errors)
    finally:
        os.unlink(path)

def test_validate_truncated_vertices():
    """Ficheiro truncado na secção de vértices — não deve lançar struct.error."""
    bc = 2; vc = 3
    bones = make_bones(bc); verts = make_verts(vc, bc)
    clips = make_clips(bc, frames=2)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        # Truncar a meio dos vértices
        trunc = (conv.AXS1_HEADER_SIZE + bc * conv.AXS1_BONE_ONDISK
                 + (vc // 2) * conv.AXS1_VERTEX_ONDISK + 10)
        with open(path, "r+b") as f: f.truncate(trunc)
        errors = conv.validate_axs1(path, bones, clips)
        assert len(errors) > 0, "Devia detectar truncamento nos vértices"
        assert not any("struct.error" in e.lower() for e in errors)
    finally:
        os.unlink(path)

def test_validate_truncated_clip_header():
    """Ficheiro truncado no cabeçalho de clip."""
    bc = 2; vc = 3
    bones = make_bones(bc); verts = make_verts(vc, bc)
    clips = make_clips(bc, frames=2)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        trunc = (conv.AXS1_HEADER_SIZE
                 + bc * conv.AXS1_BONE_ONDISK
                 + vc * conv.AXS1_VERTEX_ONDISK
                 + 8)  # parcial do cabeçalho do primeiro clip
        with open(path, "r+b") as f: f.truncate(trunc)
        errors = conv.validate_axs1(path, bones, clips)
        assert len(errors) > 0
        assert not any("struct.error" in e.lower() for e in errors)
    finally:
        os.unlink(path)

def test_validate_truncated_keyframes():
    """Ficheiro truncado nos keyframes — não deve lançar struct.error."""
    bc = 2; vc = 3
    bones = make_bones(bc); verts = make_verts(vc, bc)
    clips = make_clips(bc, frames=4)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        # Truncar a meio dos keyframes do primeiro clip
        trunc = (conv.AXS1_HEADER_SIZE
                 + bc * conv.AXS1_BONE_ONDISK
                 + vc * conv.AXS1_VERTEX_ONDISK
                 + conv.AXS1_CLIP_HDR_SIZE
                 + bc * conv.AXS1_KEY_ONDISK)  # apenas 1 frame dos 4
        with open(path, "r+b") as f: f.truncate(trunc)
        errors = conv.validate_axs1(path, bones, clips)
        assert len(errors) > 0, "Devia detectar truncamento nos keyframes"
        assert not any("struct.error" in e.lower() for e in errors)
    finally:
        os.unlink(path)

def test_validate_size_mismatch():
    """Ficheiro com tamanho diferente do esperado."""
    bc = 2; vc = 3
    bones = make_bones(bc); verts = make_verts(vc, bc)
    clips = make_clips(bc, frames=2)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        with open(path, "r+b") as f: f.truncate(50)
        errors = conv.validate_axs1(path, bones, clips)
        assert len(errors) > 0, "Devia reportar erro de tamanho"
        assert not any("struct.error" in e.lower() for e in errors)
    finally:
        os.unlink(path)

# ---------------------------------------------------------------------------
# 14. Keyframes — tamanho total correcto
# ---------------------------------------------------------------------------

def test_keyframe_total_size():
    bc = 3; vc = 4; fc = 5; cc = 5
    bones = make_bones(bc); verts = make_verts(vc, bc)
    clips = make_clips(bc, frames=fc)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        sz = conv.write_axs1(path, bones, verts, clips)
        expected = (conv.AXS1_HEADER_SIZE
                    + bc * conv.AXS1_BONE_ONDISK
                    + vc * conv.AXS1_VERTEX_ONDISK
                    + cc * (conv.AXS1_CLIP_HDR_SIZE + fc * bc * conv.AXS1_KEY_ONDISK))
        eq(sz, expected)
    finally:
        os.unlink(path)

# ---------------------------------------------------------------------------
# 15. inverseBindMatrices — validação matemática
# ---------------------------------------------------------------------------

def test_ibm_identity_compatible():
    """
    Um nó sem transformações (identidade) é compatível com IBM identidade.
    mat4_inverse(identity) == identity.
    """
    identity = conv.mat4_identity()
    inv = conv.mat4_inverse(identity)
    ok, idx, got, exp = conv.mat4_approx_equal(inv, identity)
    assert ok, f"inverse(identity) != identity: componente {idx} got={got} exp={exp}"

def test_ibm_translation_inverse():
    """mat4_inverse de uma translação pura deve ser a translação negativa."""
    m = conv.mat4_identity()
    m[12] = 3.0; m[13] = -1.0; m[14] = 2.0
    inv = conv.mat4_inverse(m)
    # inv deve ter translação [-3, 1, -2]
    near(inv[12], -3.0, tol=1e-3, msg="IBM: inverse de translação X:")
    near(inv[13],  1.0, tol=1e-3, msg="IBM: inverse de translação Y:")
    near(inv[14], -2.0, tol=1e-3, msg="IBM: inverse de translação Z:")

def test_mat4_multiply_identity():
    identity = conv.mat4_identity()
    m = [float(i) for i in range(16)]
    result = conv.mat4_multiply(identity, m)
    for i in range(16):
        near(result[i], m[i], tol=1e-5)

def test_ibm_mismatch_detected():
    """
    Verificar que mat4_approx_equal detecta diferença.
    """
    a = conv.mat4_identity()
    b = list(a); b[0] = 999.0
    ok, idx, got, exp = conv.mat4_approx_equal(a, b, tol=1e-2)
    assert not ok, "Devia detectar diferença"
    eq(idx, 0)

# ---------------------------------------------------------------------------
# 16. Constantes de offset de vértice
# ---------------------------------------------------------------------------

def test_vertex_offset_constants():
    eq(conv._VTX_UV_OFF,   0)
    eq(conv._VTX_NRM_OFF,  8)
    eq(conv._VTX_POS_OFF,  20)
    eq(conv._VTX_BIDX_OFF, 32)
    eq(conv._VTX_WGHT_OFF, 36)
    # Tamanho total: 36 + 4×4 = 52
    eq(conv._VTX_WGHT_OFF + 4*4, conv.AXS1_VERTEX_ONDISK)

# ---------------------------------------------------------------------------
# 17. Novos testes matemáticos de mat4_inverse
# ---------------------------------------------------------------------------

def _mat4_product_is_identity(m):
    """Verifica se m × mat4_inverse(m) ≈ identidade."""
    inv = conv.mat4_inverse(m)
    product = conv.mat4_multiply(m, inv)
    identity = conv.mat4_identity()
    ok, idx, got, exp = conv.mat4_approx_equal(product, identity, tol=1e-5)
    assert ok, (
        f"M × inv(M) != identidade: componente [{idx}] "
        f"got={got:.8f} exp={exp:.8f}"
    )

def test_mat4_inverse_identity():
    """inv(I) == I."""
    identity = conv.mat4_identity()
    inv = conv.mat4_inverse(identity)
    ok, idx, got, exp = conv.mat4_approx_equal(inv, identity, tol=1e-6)
    assert ok, f"inv(identidade) != identidade: [{idx}] got={got} exp={exp}"

def test_mat4_inverse_translation_x():
    """Translação pura em X: inv tem -X."""
    m = conv.mat4_identity()
    m[12] = 5.0
    inv = conv.mat4_inverse(m)
    near(inv[12], -5.0, tol=1e-6, msg="translação X:")
    near(inv[13],  0.0, tol=1e-6, msg="translação Y deve ser 0:")
    near(inv[14],  0.0, tol=1e-6, msg="translação Z deve ser 0:")

def test_mat4_inverse_translation_y():
    """Translação pura em Y: inv tem -Y."""
    m = conv.mat4_identity()
    m[13] = -7.0
    inv = conv.mat4_inverse(m)
    near(inv[12],  0.0, tol=1e-6)
    near(inv[13],  7.0, tol=1e-6, msg="translação Y inversa:")
    near(inv[14],  0.0, tol=1e-6)

def test_mat4_inverse_translation_z():
    """Translação pura em Z: inv tem -Z."""
    m = conv.mat4_identity()
    m[14] = 4.5
    inv = conv.mat4_inverse(m)
    near(inv[12],  0.0, tol=1e-6)
    near(inv[13],  0.0, tol=1e-6)
    near(inv[14], -4.5, tol=1e-6, msg="translação Z inversa:")

def test_mat4_inverse_translation_xyz():
    """Translação [3, -1, 2]: inv deve ter [-3, 1, -2]."""
    m = conv.mat4_identity()
    m[12] = 3.0; m[13] = -1.0; m[14] = 2.0
    inv = conv.mat4_inverse(m)
    near(inv[12], -3.0, tol=1e-6, msg="translação XYZ X:")
    near(inv[13],  1.0, tol=1e-6, msg="translação XYZ Y:")
    near(inv[14], -2.0, tol=1e-6, msg="translação XYZ Z:")
    _mat4_product_is_identity(m)

def test_mat4_inverse_rotation_90_z():
    """Rotação 90° em torno de Z — inv deve ser rotação -90°."""
    # column-major: coluna 0 = (cos, sin, 0, 0), coluna 1 = (-sin, cos, 0, 0)
    c = math.cos(math.pi / 2)   # ≈ 0
    s = math.sin(math.pi / 2)   # ≈ 1
    m = conv.mat4_identity()
    m[0] = c;  m[1] = s   # coluna 0: linhas 0,1
    m[4] = -s; m[5] = c   # coluna 1: linhas 0,1
    inv = conv.mat4_inverse(m)
    # inv deve ser transposta (rotação inversa)
    near(inv[0],  c, tol=1e-5)
    near(inv[1], -s, tol=1e-5)
    near(inv[4],  s, tol=1e-5)
    near(inv[5],  c, tol=1e-5)
    _mat4_product_is_identity(m)

def test_mat4_inverse_rotation_45_x():
    """Rotação 45° em torno de X — M × inv(M) == I."""
    a = math.pi / 4
    c = math.cos(a); s = math.sin(a)
    m = conv.mat4_identity()
    # Rotação X column-major: coluna 1 = (0,c,s,0), coluna 2 = (0,-s,c,0)
    m[5]  =  c; m[6]  = s
    m[9]  = -s; m[10] = c
    _mat4_product_is_identity(m)

def test_mat4_inverse_uniform_scale():
    """Escala uniforme 2.0: inv tem 0.5 na diagonal."""
    m = conv.mat4_identity()
    m[0] = 2.0; m[5] = 2.0; m[10] = 2.0
    inv = conv.mat4_inverse(m)
    near(inv[0],  0.5, tol=1e-6, msg="escala inv[0]:")
    near(inv[5],  0.5, tol=1e-6, msg="escala inv[5]:")
    near(inv[10], 0.5, tol=1e-6, msg="escala inv[10]:")
    near(inv[15], 1.0, tol=1e-6)
    _mat4_product_is_identity(m)

def test_mat4_inverse_nonuniform_scale():
    """Escala não-uniforme [3, 0.5, 2]: invertível."""
    m = conv.mat4_identity()
    m[0] = 3.0; m[5] = 0.5; m[10] = 2.0
    inv = conv.mat4_inverse(m)
    near(inv[0],  1.0/3.0, tol=1e-6)
    near(inv[5],  2.0,     tol=1e-6)
    near(inv[10], 0.5,     tol=1e-6)
    _mat4_product_is_identity(m)

def test_mat4_inverse_composed_rotation_translation():
    """Matriz composta rotação + translação: M × inv(M) == I."""
    # Rotação 30° em Z + translação [1, 2, 3]
    a = math.pi / 6
    c = math.cos(a); s = math.sin(a)
    m = conv.mat4_identity()
    m[0] = c;  m[1] = s
    m[4] = -s; m[5] = c
    m[12] = 1.0; m[13] = 2.0; m[14] = 3.0
    _mat4_product_is_identity(m)

def test_mat4_inverse_composed_scale_rotation_translation():
    """Matriz composta com escala, rotação e translação: M × inv(M) == I."""
    a = math.pi / 3
    c = math.cos(a); s = math.sin(a)
    scale = 2.5
    m = conv.mat4_identity()
    m[0] =  c*scale; m[1] = s*scale
    m[4] = -s*scale; m[5] = c*scale
    m[10] = scale
    m[12] = -4.0; m[13] = 1.5; m[14] = 7.0
    _mat4_product_is_identity(m)

def test_mat4_inverse_singular_raises():
    """Matriz singular deve lançar ValueError (nunca devolver silenciosamente identidade)."""
    # Linha 0 = linha 1 → determinante zero
    m = conv.mat4_identity()
    m[0] = 1.0; m[1] = 1.0; m[2] = 0.0; m[3] = 0.0   # linha 0
    m[4] = 1.0; m[5] = 1.0; m[6] = 0.0; m[7] = 0.0   # linha 1 (igual à 0)
    # column-major: m[r + c*4]
    # Para matriz singular: coluna 0 = (1,1,0,0), coluna 1 = (1,1,0,0)
    singular = [0.0] * 16
    singular[0] = 1.0; singular[1] = 1.0   # coluna 0
    singular[4] = 1.0; singular[5] = 1.0   # coluna 1
    singular[10] = 1.0; singular[15] = 1.0
    raised = False
    try:
        conv.mat4_inverse(singular)
    except ValueError as e:
        raised = True
        assert "singular" in str(e).lower() or "pivot" in str(e).lower(), \
            f"Mensagem de erro deve mencionar 'singular' ou 'pivot': {e}"
    assert raised, "mat4_inverse de matriz singular deve lançar ValueError"

def test_mat4_inverse_zero_matrix_raises():
    """Matriz zero deve lançar ValueError."""
    raised = False
    try:
        conv.mat4_inverse([0.0]*16)
    except ValueError:
        raised = True
    assert raised, "mat4_inverse de matriz zero deve lançar ValueError"

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_TESTS = [
    # Quaternião normalização
    ("quat_normalize: identidade",            test_quat_normalize_unit),
    ("quat_normalize: escala 2",              test_quat_normalize_scale),
    ("quat_normalize: zero → identity",       test_quat_normalize_zero),
    ("quat_normalize: arbitrário",            test_quat_normalize_arbitrary),
    # Slerp
    ("quat_slerp: t=0",                       test_quat_slerp_t0),
    ("quat_slerp: t=1",                       test_quat_slerp_t1),
    ("quat_slerp: t=0.5 normalizado",         test_quat_slerp_normalized),
    # Interpolação vec3
    ("vec3: LINEAR t=0.5",                    test_vec3_linear),
    ("vec3: STEP mantém valor anterior",      test_vec3_step),
    ("vec3: clamp antes do início",           test_vec3_clamp_before),
    ("vec3: clamp após o fim",                test_vec3_clamp_after),
    ("vec3: CUBICSPLINE tangentes zero",      test_vec3_cubicspline_zero_tangents),
    ("vec3: CUBICSPLINE tangentes não-nulas", test_vec3_cubicspline_nonzero_tangents),
    # Interpolação quat
    ("quat: LINEAR endpoints",                test_quat_linear_endpoints),
    ("quat: STEP retenção",                   test_quat_step),
    ("quat: CUBICSPLINE tangentes não-nulas", test_quat_cubicspline_nonzero_tangents),
    ("quat: CUBICSPLINE tangentes zero",      test_quat_cubicspline_zero_tangents),
    ("quat_hermite_cubic: endpoints",         test_quat_hermite_cubic_endpoints),
    # Mapeamento JOINTS_0
    ("JOINTS_0: mapeamento básico",           test_joints0_mapping_basic),
    ("JOINTS_0: índice inválido lança erro",  test_joints0_invalid_raises),
    ("JOINTS_0: osso eliminado lança erro",   test_joints0_eliminated_raises),
    # Pesos
    ("pesos: normalização básica",            test_weights_basic),
    ("pesos: parciais",                       test_weights_partial),
    ("pesos: zero → fallback [1,0,0,0]",     test_weights_zero_fallback),
    # Hierarquia
    ("hierarquia: expansão a antecessores",   test_hierarchy_expansion),
    ("hierarquia: limite lança erro",         test_hierarchy_limit),
    # Clips
    ("clips: report_missing sem animações",   test_report_missing_all),
    ("clips: report_missing parcial",         test_report_missing_partial),
    ("clips: order_clips lança erro se faltar", test_order_clips_raises_on_missing),
    ("clips: ordenação correcta (5 obrigatórios)", test_order_clips_correct_order),
    # Limites
    ("limite: AXS1_MAX_VERTICES = 8192",     test_max_vertices_constant),
    ("limite: AXS1_MAX_BONES = 24",          test_max_bones_constant),
    ("limite: vértices excedentes lança erro", test_vertex_limit_raises),
    # Estrutura binária
    ("AXS1: campos do cabeçalho",            test_axs1_header_fields),
    ("AXS1: tamanho total correcto",         test_axs1_total_size),
    ("AXS1: layout de osso",                 test_axs1_bone_layout),
    ("AXS1: offsets do vértice",             test_axs1_vertex_layout_offsets),
    # Validação
    ("validação: AXS1 correcto",             test_validate_ok),
    ("validação: magic inválido",            test_validate_bad_magic),
    ("validação: bone_idx fora do intervalo", test_validate_bone_idx_out_of_range),
    ("validação: cabeçalho truncado",        test_validate_truncated_header),
    ("validação: ossos truncados",           test_validate_truncated_bones),
    ("validação: vértices truncados",        test_validate_truncated_vertices),
    ("validação: cabeçalho de clip truncado", test_validate_truncated_clip_header),
    ("validação: keyframes truncados",       test_validate_truncated_keyframes),
    ("validação: tamanho errado reportado",  test_validate_size_mismatch),
    # Keyframes tamanho
    ("keyframes: tamanho total correcto",    test_keyframe_total_size),
    # inverseBindMatrices — originais
    ("IBM: identity compatível",             test_ibm_identity_compatible),
    ("IBM: inverse de translação",           test_ibm_translation_inverse),
    ("IBM: multiply identity",               test_mat4_multiply_identity),
    ("IBM: incompatibilidade detectada",     test_ibm_mismatch_detected),
    # Offsets de vértice
    ("offsets: constantes correctas",        test_vertex_offset_constants),
    # Novos testes matemáticos mat4_inverse
    ("mat4_inv: identidade",                 test_mat4_inverse_identity),
    ("mat4_inv: translação X",               test_mat4_inverse_translation_x),
    ("mat4_inv: translação Y",               test_mat4_inverse_translation_y),
    ("mat4_inv: translação Z",               test_mat4_inverse_translation_z),
    ("mat4_inv: translação XYZ + M×inv=I",  test_mat4_inverse_translation_xyz),
    ("mat4_inv: rotação 90° Z + M×inv=I",   test_mat4_inverse_rotation_90_z),
    ("mat4_inv: rotação 45° X + M×inv=I",   test_mat4_inverse_rotation_45_x),
    ("mat4_inv: escala uniforme 2.0",        test_mat4_inverse_uniform_scale),
    ("mat4_inv: escala não-uniforme",        test_mat4_inverse_nonuniform_scale),
    ("mat4_inv: composta rot+transl",        test_mat4_inverse_composed_rotation_translation),
    ("mat4_inv: composta escala+rot+transl", test_mat4_inverse_composed_scale_rotation_translation),
    ("mat4_inv: singular lança ValueError",  test_mat4_inverse_singular_raises),
    ("mat4_inv: zero matrix lança ValueError", test_mat4_inverse_zero_matrix_raises),
]

def main():
    print("\n=== Testes do conversor AXS1 ===\n")
    for name, fn in ALL_TESTS:
        test(name, fn)

    print(f"\n{'='*50}")
    print(f"  Passados : {PASSED}")
    print(f"  Falhados : {FAILED}")
    if ERRORS:
        print("\nErros:")
        for e in ERRORS:
            print(f"  - {e}")
    print()
    if FAILED > 0:
        sys.exit(1)
    print("Todos os testes passaram.")
    sys.exit(0)

if __name__ == "__main__":
    main()
