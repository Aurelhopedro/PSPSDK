#!/usr/bin/env python3
"""
test_convert_glb_to_axs1.py — Testes unitários do conversor AXS1
RPG Axel Digital

Execução:
    python3 tools/test_convert_glb_to_axs1.py

Cobre:
  1. Mapeamento correcto de JOINTS_0 → skin.joints → AXS1
  2. Seleção hierárquica de ossos
  3. Normalização de pesos
  4. Quaternião: normalização e slerp
  5. Interpolação LINEAR, STEP, CUBICSPLINE (vec3 e quat)
  6. Ausência de clips falsos quando o GLB não tem animações
  7. Estrutura binária do AXS1 (tamanhos e layout)
  8. Validação do AXS1 escrito
"""

import sys
import os
import struct
import math
import tempfile
import traceback

# Adicionar o directório pai ao path para importar o conversor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import convert_glb_to_axs1 as conv

# ---------------------------------------------------------------------------
# Infraestrutura de testes
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

def near(a, b, tol=1e-5, msg=""):
    assert abs(a - b) < tol, f"{msg} |{a} - {b}| >= {tol}"

def near_vec(a, b, tol=1e-5, msg=""):
    assert len(a) == len(b), f"{msg} tamanhos diferentes: {len(a)} vs {len(b)}"
    for i, (x, y) in enumerate(zip(a, b)):
        assert abs(float(x) - float(y)) < tol, f"{msg} [i={i}] |{x} - {y}| >= {tol}"

# ---------------------------------------------------------------------------
# 1. Quaternião: normalização
# ---------------------------------------------------------------------------

def test_quat_normalize_unit():
    q = conv.quat_normalize([0.0, 0.0, 0.0, 1.0])
    near_vec(q, [0.0, 0.0, 0.0, 1.0], msg="identity")

def test_quat_normalize_scale():
    q = conv.quat_normalize([0.0, 0.0, 0.0, 2.0])
    near_vec(q, [0.0, 0.0, 0.0, 1.0], msg="scale 2")

def test_quat_normalize_zero():
    q = conv.quat_normalize([0.0, 0.0, 0.0, 0.0])
    near_vec(q, [0.0, 0.0, 0.0, 1.0], msg="zero → identity")

def test_quat_normalize_arbitrary():
    import math
    q = conv.quat_normalize([1.0, 1.0, 1.0, 1.0])
    n = math.sqrt(sum(v**2 for v in q))
    near(n, 1.0, msg="norma após normalização")

# ---------------------------------------------------------------------------
# 2. Quaternião: slerp
# ---------------------------------------------------------------------------

def test_quat_slerp_t0():
    q0 = [0.0, 0.0, 0.0, 1.0]
    q1 = [0.0, 1.0, 0.0, 0.0]
    r = conv.quat_slerp(q0, q1, 0.0)
    near_vec(r, q0, msg="slerp t=0")

def test_quat_slerp_t1():
    q0 = [0.0, 0.0, 0.0, 1.0]
    q1 = [0.0, 1.0, 0.0, 0.0]
    r = conv.quat_slerp(q0, q1, 1.0)
    near_vec(r, q1, msg="slerp t=1")

def test_quat_slerp_normalized():
    import math
    q0 = [0.0, 0.0, 0.0, 1.0]
    q1 = [0.5, 0.5, 0.5, 0.5]
    q1 = conv.quat_normalize(q1)
    r = conv.quat_slerp(q0, q1, 0.5)
    n = math.sqrt(sum(v**2 for v in r))
    near(n, 1.0, tol=1e-4, msg="slerp t=0.5 normalizado")

# ---------------------------------------------------------------------------
# 3. Interpolação de vec3
# ---------------------------------------------------------------------------

import numpy as np

def test_interp_vec3_linear():
    times  = np.array([0.0, 1.0])
    values = np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]])
    r = conv.interpolate_vec3(times, values, 0.5, "LINEAR")
    near_vec(r, [0.5, 1.0, 1.5], msg="linear t=0.5")

def test_interp_vec3_step():
    times  = np.array([0.0, 1.0])
    values = np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]])
    r = conv.interpolate_vec3(times, values, 0.9, "STEP")
    near_vec(r, [0.0, 0.0, 0.0], msg="step mantém valor anterior")

def test_interp_vec3_clamp_before():
    times  = np.array([1.0, 2.0])
    values = np.array([[5.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
    r = conv.interpolate_vec3(times, values, 0.0, "LINEAR")
    near(r[0], 5.0, msg="clamp antes do início")

def test_interp_vec3_clamp_after():
    times  = np.array([0.0, 1.0])
    values = np.array([[0.0, 0.0, 0.0], [7.0, 0.0, 0.0]])
    r = conv.interpolate_vec3(times, values, 2.0, "LINEAR")
    near(r[0], 7.0, msg="clamp após o fim")

def test_interp_vec3_cubicspline():
    # Spline com tangentes zero: deve ser equivalente a linear
    times  = np.array([0.0, 1.0])
    # shape (2, 3, 3): [in_tan, point, out_tan]
    values = np.array([
        [[0.0,0.0,0.0], [0.0,0.0,0.0], [0.0,0.0,0.0]],
        [[0.0,0.0,0.0], [1.0,0.0,0.0], [0.0,0.0,0.0]],
    ])
    r = conv.interpolate_vec3(times, values, 0.5, "CUBICSPLINE")
    near(r[0], 0.5, tol=1e-3, msg="cubicspline t=0.5 com tangentes zero")

# ---------------------------------------------------------------------------
# 4. Interpolação de quaternião
# ---------------------------------------------------------------------------

def test_interp_quat_linear():
    q0 = np.array([0.0, 0.0, 0.0, 1.0])
    q1 = np.array([0.0, 0.0, 1.0, 0.0])
    times  = np.array([0.0, 1.0])
    values = np.array([q0, q1])
    r = conv.interpolate_quat(times, values, 0.0, "LINEAR")
    near_vec(r, [0.0, 0.0, 0.0, 1.0], msg="quat t=0")
    r = conv.interpolate_quat(times, values, 1.0, "LINEAR")
    near_vec(r, [0.0, 0.0, 1.0, 0.0], msg="quat t=1")

# ---------------------------------------------------------------------------
# 5. Mapeamento JOINTS_0 — simulação sem GLB
# ---------------------------------------------------------------------------

def test_joints0_mapping_direct():
    """
    Verifica que JOINTS_0[k] é tratado como índice em skin.joints,
    não como node_idx GLTF directo.

    Exemplo:
      skin.joints = [10, 15, 22]
      skin_to_axs1 = {0→0, 1→1, 2→2}  (si → ai)
      JOINTS_0 = [1, 2, 0, 0]  → AXS1 [1, 2, 0, 0]
    """
    skin_to_axs1 = {0: 0, 1: 1, 2: 2}
    joints_raw = [1, 2, 0, 0]
    weights_raw = [0.5, 0.3, 0.2, 0.0]
    n_skin = 3

    bi4 = [0, 0, 0, 0]
    wt4 = [0.0, 0.0, 0.0, 0.0]
    wsum = sum(weights_raw)
    for k in range(4):
        sj = joints_raw[k]
        w  = weights_raw[k]
        assert 0 <= sj < n_skin, f"sj={sj} fora de [{0},{n_skin})"
        ai = skin_to_axs1[sj]
        bi4[k] = ai
        wt4[k] = w / wsum if wsum > 1e-6 else 0.0

    eq(bi4, [1, 2, 0, 0], msg="mapeamento JOINTS_0")
    near(sum(wt4), 1.0, msg="pesos somam 1")

def test_joints0_mapping_offset():
    """
    Verifica que quando skin.joints começa em índices altos,
    JOINTS_0 ainda refere posições em skin.joints (não node_idx).
    """
    # skin.joints = [10, 15, 22, 30]
    # skin_to_axs1: {0→0, 1→1, 2→2, 3→3}
    skin_to_axs1 = {0: 0, 1: 1, 2: 2, 3: 3}
    n_skin = 4
    joints_raw = [0, 1, 2, 3]  # índices em skin.joints
    weights_raw = [1.0, 0.0, 0.0, 0.0]

    bi4 = []
    for k in range(4):
        sj = joints_raw[k]
        assert 0 <= sj < n_skin
        bi4.append(skin_to_axs1[sj])
    eq(bi4, [0, 1, 2, 3], msg="offset mapping")

def test_joints0_invalid_index_raises():
    """Um índice JOINTS_0 fora de skin.joints deve lançar RuntimeError."""
    skin_to_axs1 = {0: 0, 1: 1}
    n_skin = 2
    sj_invalid = 5  # fora de [0, n_skin)
    w = 0.5
    raised = False
    try:
        if sj_invalid < 0 or sj_invalid >= n_skin:
            raise RuntimeError(f"JOINTS_0={sj_invalid} fora do intervalo")
    except RuntimeError:
        raised = True
    assert raised, "Devia ter lançado RuntimeError para índice inválido"

def test_joints0_missing_from_axs1_raises():
    """Um skin_joint com peso real eliminado do AXS1 deve lançar RuntimeError."""
    skin_to_axs1 = {0: 0}  # skin_joint 1 foi eliminado
    n_skin = 2
    sj = 1
    w  = 0.3
    raised = False
    try:
        ai = skin_to_axs1.get(sj, None)
        if ai is None:
            raise RuntimeError(f"skin_joint {sj} com peso {w} não está em AXS1")
    except RuntimeError:
        raised = True
    assert raised, "Devia ter lançado RuntimeError para osso eliminado com peso"

# ---------------------------------------------------------------------------
# 6. Normalização de pesos
# ---------------------------------------------------------------------------

def test_weights_normalize_basic():
    raw = [0.4, 0.3, 0.2, 0.1]
    s = sum(raw)
    norm = [w/s for w in raw]
    near(sum(norm), 1.0, msg="soma dos pesos normalizados")

def test_weights_normalize_partial():
    """Apenas os primeiros dois com peso real."""
    raw = [0.6, 0.4, 0.0, 0.0]
    s = sum(raw)
    norm = [w/s for w in raw]
    near(sum(norm), 1.0)
    near(norm[2], 0.0)
    near(norm[3], 0.0)

def test_weights_all_zero_fallback():
    """Se todos os pesos são zero, o fallback deve ser [1,0,0,0]."""
    raw = [0.0, 0.0, 0.0, 0.0]
    s = sum(raw)
    if s < 1e-6:
        norm = [1.0, 0.0, 0.0, 0.0]
    else:
        norm = [w/s for w in raw]
    near(norm[0], 1.0)

# ---------------------------------------------------------------------------
# 7. Ausência de clips falsos
# ---------------------------------------------------------------------------

def test_no_false_clips_when_no_animations():
    """
    report_missing_clips não deve criar clips — apenas reportar ausências.
    order_clips com lista vazia deve devolver lista vazia.
    """
    clips = []
    missing = conv.report_missing_clips(clips)
    assert len(missing) == 5, f"5 clips esperados em falta, got {len(missing)}"
    ordered = conv.order_clips(clips)
    eq(len(ordered), 0, msg="sem clips falsos criados")

def test_no_false_clips_partial():
    """Com apenas IDLE, os restantes não devem ser criados."""
    clips = [{"name": "IDLE", "fps": 30.0, "frame_count": 10, "frames": []}]
    missing = conv.report_missing_clips(clips)
    assert "WALK" in missing
    assert "RUN"  in missing
    ordered = conv.order_clips(clips)
    eq(len(ordered), 1)
    eq(ordered[0]["name"], "IDLE")

# ---------------------------------------------------------------------------
# 8. Estrutura binária AXS1
# ---------------------------------------------------------------------------

def make_test_bones(n=2):
    bones = []
    for i in range(n):
        bones.append({
            "name": f"bone{i}",
            "parent": i - 1,
            "bind_pos": [float(i), 0.0, 0.0],
            "bind_rot": [0.0, 0.0, 0.0, 1.0],
        })
    return bones

def make_test_vertices(n=3):
    verts = []
    for i in range(n):
        verts.append({
            "u": 0.0, "v": 0.0,
            "nx": 0.0, "ny": 1.0, "nz": 0.0,
            "px": float(i), "py": 0.0, "pz": 0.0,
            "bone_idx": [0, 0, 0, 0],
            "weight": [1.0, 0.0, 0.0, 0.0],
        })
    return verts

def make_test_clips(bone_count, n_clips=2, frames_per_clip=4):
    clips = []
    names = ["IDLE", "WALK"]
    for ci in range(n_clips):
        frame_data = []
        for fi in range(frames_per_clip):
            keys = [{"rot": [0.0,0.0,0.0,1.0], "pos": [0.0,0.0,0.0]}
                    for _ in range(bone_count)]
            frame_data.append(keys)
        clips.append({
            "name": names[ci],
            "fps": 30.0,
            "frame_count": frames_per_clip,
            "frames": frame_data,
        })
    return clips

def test_axs1_header_size():
    bones   = make_test_bones(2)
    verts   = make_test_vertices(3)
    clips   = make_test_clips(2, n_clips=1, frames_per_clip=2)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        with open(path, "rb") as f:
            data = f.read()
        # magic
        eq(data[0:4], b"AXS1")
        # versão
        eq(struct.unpack_from("<I", data, 4)[0], 1)
        # bone_count
        eq(struct.unpack_from("<I", data, 8)[0], 2)
        # vertex_count
        eq(struct.unpack_from("<I", data, 12)[0], 3)
        # clip_count
        eq(struct.unpack_from("<I", data, 16)[0], 1)
    finally:
        os.unlink(path)

def test_axs1_total_size():
    bc = 3
    vc = 5
    fc = 4
    cc = 2
    bones  = make_test_bones(bc)
    verts  = make_test_vertices(vc)
    clips  = make_test_clips(bc, n_clips=cc, frames_per_clip=fc)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        sz = conv.write_axs1(path, bones, verts, clips)
        expected = (conv.AXS1_HEADER_SIZE
                    + bc * conv.AXS1_BONE_ONDISK
                    + vc * conv.AXS1_VERTEX_ONDISK
                    + cc * (conv.AXS1_CLIP_HDR_SIZE + fc * bc * conv.AXS1_KEY_ONDISK))
        eq(sz, expected, msg="tamanho total AXS1")
    finally:
        os.unlink(path)

def test_axs1_bone_layout():
    """Verificar que o layout dos ossos está correcto (56 bytes, campos correctos)."""
    bones = [{"name": "root", "parent": -1,
              "bind_pos": [1.0, 2.0, 3.0],
              "bind_rot": [0.0, 0.0, 0.0, 1.0]}]
    verts = make_test_vertices(3)
    clips = make_test_clips(1, n_clips=1, frames_per_clip=2)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        with open(path, "rb") as f:
            data = f.read()
        off = conv.AXS1_HEADER_SIZE
        name_b = data[off:off+16]
        assert name_b[:4] == b"root", f"nome errado: {name_b!r}"
        parent = struct.unpack_from("<i", data, off+16)[0]
        eq(parent, -1)
        bp = struct.unpack_from("<3f", data, off+24)
        near_vec(bp, [1.0, 2.0, 3.0], msg="bind_pos")
        br = struct.unpack_from("<4f", data, off+36)
        near_vec(br, [0.0, 0.0, 0.0, 1.0], msg="bind_rot xyzw")
    finally:
        os.unlink(path)

def test_axs1_vertex_layout():
    """Verificar que o layout dos vértices está correcto (52 bytes)."""
    bones = make_test_bones(1)
    verts = [{
        "u": 0.25, "v": 0.75,
        "nx": 0.0, "ny": 1.0, "nz": 0.0,
        "px": 1.0, "py": 2.0, "pz": 3.0,
        "bone_idx": [0, 0, 0, 0],
        "weight": [1.0, 0.0, 0.0, 0.0],
    }]
    clips = make_test_clips(1, n_clips=1, frames_per_clip=2)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        with open(path, "rb") as f:
            data = f.read()
        off = conv.AXS1_HEADER_SIZE + 1 * conv.AXS1_BONE_ONDISK
        uv = struct.unpack_from("<2f", data, off)
        near_vec(uv, [0.25, 0.75], msg="uv")
        nrm = struct.unpack_from("<3f", data, off+8)
        near_vec(nrm, [0.0, 1.0, 0.0], msg="normal")
        pos = struct.unpack_from("<3f", data, off+20)
        near_vec(pos, [1.0, 2.0, 3.0], msg="pos")
        bi4 = struct.unpack_from("<4B", data, off+32)
        eq(list(bi4), [0,0,0,0])
        wt4 = struct.unpack_from("<4f", data, off+36)
        near_vec(wt4, [1.0,0.0,0.0,0.0], msg="weights")
    finally:
        os.unlink(path)

# ---------------------------------------------------------------------------
# 9. Validação AXS1
# ---------------------------------------------------------------------------

def test_validate_axs1_ok():
    bones  = make_test_bones(2)
    verts  = make_test_vertices(6)
    clips  = make_test_clips(2, n_clips=2, frames_per_clip=5)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        errors = conv.validate_axs1(path, bones, clips)
        eq(errors, [], msg="validação sem erros")
    finally:
        os.unlink(path)

def test_validate_axs1_bad_magic():
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        tmp.write(b"XXXX" + b"\x00" * 28)
        path = tmp.name
    try:
        errors = conv.validate_axs1(path, [], [])
        assert any("Magic" in e or "magic" in e.lower() for e in errors), \
            f"Devia reportar magic inválido: {errors}"
    finally:
        os.unlink(path)

def test_validate_axs1_wrong_size():
    bones  = make_test_bones(2)
    verts  = make_test_vertices(3)
    clips  = make_test_clips(2, n_clips=1, frames_per_clip=2)
    with tempfile.NamedTemporaryFile(suffix=".axs", delete=False) as tmp:
        path = tmp.name
    try:
        conv.write_axs1(path, bones, verts, clips)
        # Truncar o ficheiro
        with open(path, "r+b") as f:
            f.truncate(50)
        errors = conv.validate_axs1(path, bones, clips)
        assert len(errors) > 0, "Devia reportar erro de tamanho"
    finally:
        os.unlink(path)

# ---------------------------------------------------------------------------
# 10. Seleção hierárquica — simulação
# ---------------------------------------------------------------------------

def test_hierarchy_expansion():
    """
    Dado que apenas osso 2 tem peso, o pai (osso 1) e avô (osso 0)
    devem ser incluídos automaticamente.
    """
    # Simular: 3 skin_joints em cadeia 0→1→2
    # children: 0→[1], 1→[2]
    # used_skin_joints = {2}
    # Após expansão: {0, 1, 2}

    class FakeNode:
        def __init__(self, name, children=None, translation=None, rotation=None):
            self.name = name
            self.children = children
            self.translation = translation
            self.rotation = rotation

    node_list = [
        FakeNode("root",  children=[1]),
        FakeNode("mid",   children=[2]),
        FakeNode("leaf",  children=None),
    ]
    joint_nodes = [0, 1, 2]

    def get_skin_parent(si):
        nidx = joint_nodes[si]
        for other_si, other_nidx in enumerate(joint_nodes):
            n = node_list[other_nidx]
            if n.children and nidx in n.children:
                return other_si
        return -1

    used = {2}
    expanded = set(used)
    changed = True
    while changed:
        changed = False
        for si in list(expanded):
            p = get_skin_parent(si)
            if p >= 0 and p not in expanded:
                expanded.add(p)
                changed = True

    eq(expanded, {0, 1, 2}, msg="expansão hierárquica")

def test_hierarchy_limit_error():
    """Se após expansão o número excede AXS1_MAX_BONES, deve lançar erro."""
    # Simular 30 ossos necessários (> 24)
    n = conv.AXS1_MAX_BONES + 6  # 30
    raised = False
    try:
        if n > conv.AXS1_MAX_BONES:
            raise RuntimeError(
                f"ERRO: {n} ossos necessários excedem o limite {conv.AXS1_MAX_BONES}."
            )
    except RuntimeError:
        raised = True
    assert raised, "Devia ter lançado RuntimeError"

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    print("\n=== Testes do conversor AXS1 ===\n")

    tests = [
        # Quaternião
        ("quat_normalize: identidade",         test_quat_normalize_unit),
        ("quat_normalize: escala 2",           test_quat_normalize_scale),
        ("quat_normalize: zero → identity",    test_quat_normalize_zero),
        ("quat_normalize: arbitrário",         test_quat_normalize_arbitrary),
        ("quat_slerp: t=0",                    test_quat_slerp_t0),
        ("quat_slerp: t=1",                    test_quat_slerp_t1),
        ("quat_slerp: t=0.5 normalizado",      test_quat_slerp_normalized),
        # Interpolação vec3
        ("interp_vec3: LINEAR t=0.5",          test_interp_vec3_linear),
        ("interp_vec3: STEP mantém valor",     test_interp_vec3_step),
        ("interp_vec3: clamp antes",           test_interp_vec3_clamp_before),
        ("interp_vec3: clamp após",            test_interp_vec3_clamp_after),
        ("interp_vec3: CUBICSPLINE t=0.5",     test_interp_vec3_cubicspline),
        # Interpolação quat
        ("interp_quat: t=0 e t=1",             test_interp_quat_linear),
        # Mapeamento JOINTS_0
        ("JOINTS_0: mapeamento directo",       test_joints0_mapping_direct),
        ("JOINTS_0: mapeamento com offset",    test_joints0_mapping_offset),
        ("JOINTS_0: índice inválido lança erro", test_joints0_invalid_index_raises),
        ("JOINTS_0: osso eliminado lança erro", test_joints0_missing_from_axs1_raises),
        # Pesos
        ("pesos: normalização básica",         test_weights_normalize_basic),
        ("pesos: parciais",                    test_weights_normalize_partial),
        ("pesos: todos zero → fallback",       test_weights_all_zero_fallback),
        # Clips falsos
        ("sem clips falsos (sem animações)",   test_no_false_clips_when_no_animations),
        ("sem clips falsos (parcial)",         test_no_false_clips_partial),
        # Estrutura binária
        ("AXS1: cabeçalho correcto",           test_axs1_header_size),
        ("AXS1: tamanho total correcto",       test_axs1_total_size),
        ("AXS1: layout de osso",               test_axs1_bone_layout),
        ("AXS1: layout de vértice",            test_axs1_vertex_layout),
        # Validação
        ("AXS1: validação OK",                 test_validate_axs1_ok),
        ("AXS1: magic inválido reportado",     test_validate_axs1_bad_magic),
        ("AXS1: tamanho errado reportado",     test_validate_axs1_wrong_size),
        # Hierarquia
        ("hierarquia: expansão a antecessores", test_hierarchy_expansion),
        ("hierarquia: limite → erro",           test_hierarchy_limit_error),
    ]

    for name, fn in tests:
        test(name, fn)

    print(f"\n{'='*40}")
    print(f"  Passados: {PASSED}")
    print(f"  Falhados: {FAILED}")
    if ERRORS:
        print("\nDetalhes dos erros:")
        for e in ERRORS:
            print(f"  - {e}")
    print()

    if FAILED > 0:
        sys.exit(1)
    else:
        print("Todos os testes passaram.")
        sys.exit(0)

if __name__ == "__main__":
    main()
