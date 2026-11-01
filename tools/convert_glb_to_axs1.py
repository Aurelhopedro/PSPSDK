#!/usr/bin/env python3
"""
convert_glb_to_axs1.py — RPG Axel Digital
Converte GLB (GLTF binário) para AXS1.

Utilização:
    python3 convert_glb_to_axs1.py <input.glb> <output.axs> [--report <report.md>]

Dependências:
    pip install pygltflib numpy

Formato AXS1 (especificação — deve coincidir com p3d_anim.h):

  [Cabeçalho — 32 bytes]
    magic[4]       "AXS1"
    version        uint32 = 1
    bone_count     uint32
    vertex_count   uint32
    clip_count     uint32
    reserved[3]    uint32×3 (zeros)

  [Ossos — bone_count × 56 bytes]
    name[16]       char×16
    parent_index   int32
    pad[4]         zeros
    bind_pos[3]    float×3
    bind_rot[4]    float×4 (quaternião xyzw)
    pad_end[4]     zeros

  [Vértices — vertex_count × 52 bytes]
    u, v           float×2   → offset 0
    nx, ny, nz     float×3   → offset 8
    px, py, pz     float×3   → offset 20
    bone_idx[4]    uint8×4   → offset 32
    weight[4]      float×4   → offset 36

  [Clips — clip_count vezes:]
    [Cabeçalho de clip — 24 bytes]
      name[16]       char×16
      frame_count    int32
      fps            float
    [Keyframes — frame_count × bone_count × 32 bytes]
      rot[4]         float×4 (xyzw)
      pos[3]         float×3
      pad            float×1
"""

import sys
import os
import struct
import math
import argparse

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from pygltflib import GLTF2
    HAS_PYGLTFLIB = True
except ImportError:
    HAS_PYGLTFLIB = False

# ---------------------------------------------------------------------------
# Constantes (devem coincidir com p3d_anim.h)
# ---------------------------------------------------------------------------
AXS1_MAX_BONES    = 24
AXS1_MAX_CLIPS    = 8
AXS1_MAX_VERTICES = 8192       # limite real do loader PSP
AXS1_VERSION      = 1

AXS1_HEADER_SIZE   = 32
AXS1_BONE_ONDISK   = 56
AXS1_VERTEX_ONDISK = 52
AXS1_CLIP_HDR_SIZE = 24
AXS1_KEY_ONDISK    = 32        # por osso por frame

# Offsets dentro do vértice (52 bytes)
_VTX_UV_OFF     = 0    # 2×float  (8 bytes)
_VTX_NRM_OFF    = 8    # 3×float  (12 bytes)
_VTX_POS_OFF    = 20   # 3×float  (12 bytes)
_VTX_BIDX_OFF   = 32   # 4×uint8  (4 bytes)
_VTX_WGHT_OFF   = 36   # 4×float  (16 bytes)

# Cinco clips obrigatórios (índices fixos no runtime)
CLIP_ORDER = ["IDLE", "WALK", "RUN", "JUMP", "LAND"]

# Aliases de nomes de animação
CLIP_ALIASES = {
    "IDLE":  ["idle", "stand", "standing"],
    "WALK":  ["walk", "walking"],
    "RUN":   ["run", "running"],
    "JUMP":  ["jump", "jumping"],
    "LAND":  ["land", "landing"],
}

# ---------------------------------------------------------------------------
# Quaternião
# ---------------------------------------------------------------------------

def quat_normalize(q):
    x, y, z, w = float(q[0]), float(q[1]), float(q[2]), float(q[3])
    n = math.sqrt(x*x + y*y + z*z + w*w)
    if n < 1e-8:
        return [0.0, 0.0, 0.0, 1.0]
    return [x/n, y/n, z/n, w/n]

def quat_slerp(q0, q1, t):
    """Slerp esférico entre dois quaterniões normalizados."""
    dot = sum(q0[i]*q1[i] for i in range(4))
    if dot < 0.0:
        q1 = [-v for v in q1]
        dot = -dot
    dot = min(1.0, dot)
    if dot > 0.9995:
        result = [q0[i] + t*(q1[i]-q0[i]) for i in range(4)]
        return quat_normalize(result)
    theta0 = math.acos(dot)
    theta = theta0 * t
    sin_theta  = math.sin(theta)
    sin_theta0 = math.sin(theta0)
    s0 = math.cos(theta) - dot * sin_theta / sin_theta0
    s1 = sin_theta / sin_theta0
    return quat_normalize([s0*q0[i] + s1*q1[i] for i in range(4)])

def quat_hermite_cubic(p0, m0, p1, m1, alpha):
    """
    Interpolação Hermite cúbica componente a componente para quaterniões.
    p0, p1: pontos (quaterniões normalizados)
    m0: tangente de saída de p0 (escalada por dt)
    m1: tangente de entrada de p1 (escalada por dt)
    alpha: parâmetro em [0, 1]
    Devolve quaternião normalizado.
    """
    a = alpha
    h00 =  2*a**3 - 3*a**2 + 1
    h10 =    a**3 - 2*a**2 + a
    h01 = -2*a**3 + 3*a**2
    h11 =    a**3 -   a**2
    result = [
        h00*p0[i] + h10*m0[i] + h01*p1[i] + h11*m1[i]
        for i in range(4)
    ]
    return quat_normalize(result)

# ---------------------------------------------------------------------------
# Álgebra de matrizes 4×4 (column-major, como no GLTF)
# ---------------------------------------------------------------------------

def mat4_identity():
    m = [0.0]*16
    m[0] = m[5] = m[10] = m[15] = 1.0
    return m

def mat4_multiply(a, b):
    """Produto de duas matrizes 4×4 column-major."""
    c = [0.0]*16
    for col in range(4):
        for row in range(4):
            s = 0.0
            for k in range(4):
                s += a[row + k*4] * b[k + col*4]
            c[row + col*4] = s
    return c

def mat4_from_trs(t, r, s=None):
    """
    Constrói matriz 4×4 column-major a partir de translation, rotation (xyzw) e scale.
    Se s for None usa [1,1,1].
    """
    if s is None:
        s = [1.0, 1.0, 1.0]
    x, y, z, w = float(r[0]), float(r[1]), float(r[2]), float(r[3])
    # Normalizar
    n = math.sqrt(x*x + y*y + z*z + w*w)
    if n > 1e-8:
        x, y, z, w = x/n, y/n, z/n, w/n

    # Matriz de rotação (linha-major → depois transpomos para column-major)
    sx, sy, sz = float(s[0]), float(s[1]), float(s[2])
    m = [0.0]*16
    m[0]  = (1 - 2*(y*y + z*z)) * sx
    m[1]  = (2*(x*y + z*w))     * sx
    m[2]  = (2*(x*z - y*w))     * sx
    m[4]  = (2*(x*y - z*w))     * sy
    m[5]  = (1 - 2*(x*x + z*z)) * sy
    m[6]  = (2*(y*z + x*w))     * sy
    m[8]  = (2*(x*z + y*w))     * sz
    m[9]  = (2*(y*z - x*w))     * sz
    m[10] = (1 - 2*(x*x + y*y)) * sz
    m[12] = float(t[0])
    m[13] = float(t[1])
    m[14] = float(t[2])
    m[15] = 1.0
    return m

def mat4_inverse(m):
    """Inversa de uma matriz 4×4 column-major (método cofactor/adjugate)."""
    # Expandir para indexação (row, col) = m[row + col*4]
    def e(r, c): return m[r + c*4]

    # Cofactores
    inv = [0.0]*16

    inv[0]  =  e(1,1)*(e(2,2)*e(3,3)-e(2,3)*e(3,2)) - e(1,2)*(e(2,1)*e(3,3)-e(2,3)*e(3,1)) + e(1,3)*(e(2,1)*e(3,2)-e(2,2)*e(3,1))
    inv[4]  = -(e(1,0)*(e(2,2)*e(3,3)-e(2,3)*e(3,2)) - e(1,2)*(e(2,0)*e(3,3)-e(2,3)*e(3,0)) + e(1,3)*(e(2,0)*e(3,2)-e(2,2)*e(3,0)))
    inv[8]  =  e(1,0)*(e(2,1)*e(3,3)-e(2,3)*e(3,1)) - e(1,1)*(e(2,0)*e(3,3)-e(2,3)*e(3,0)) + e(1,3)*(e(2,0)*e(3,1)-e(2,1)*e(3,0))
    inv[12] = -(e(1,0)*(e(2,1)*e(3,2)-e(2,2)*e(3,1)) - e(1,1)*(e(2,0)*e(3,2)-e(2,2)*e(3,0)) + e(1,2)*(e(2,0)*e(3,1)-e(2,1)*e(3,0)))

    inv[1]  = -(e(0,1)*(e(2,2)*e(3,3)-e(2,3)*e(3,2)) - e(0,2)*(e(2,1)*e(3,3)-e(2,3)*e(3,1)) + e(0,3)*(e(2,1)*e(3,2)-e(2,2)*e(3,1)))
    inv[5]  =  e(0,0)*(e(2,2)*e(3,3)-e(2,3)*e(3,2)) - e(0,2)*(e(2,0)*e(3,3)-e(2,3)*e(3,0)) + e(0,3)*(e(2,0)*e(3,2)-e(2,2)*e(3,0))
    inv[9]  = -(e(0,0)*(e(2,1)*e(3,3)-e(2,3)*e(3,1)) - e(0,1)*(e(2,0)*e(3,3)-e(2,3)*e(3,0)) + e(0,3)*(e(2,0)*e(3,1)-e(2,1)*e(3,0)))
    inv[13] =  e(0,0)*(e(2,1)*e(3,2)-e(2,2)*e(3,1)) - e(0,1)*(e(2,0)*e(3,2)-e(2,2)*e(3,0)) + e(0,2)*(e(2,0)*e(3,1)-e(2,1)*e(3,0))

    inv[2]  =  e(0,1)*(e(1,2)*e(3,3)-e(1,3)*e(3,2)) - e(0,2)*(e(1,1)*e(3,3)-e(1,3)*e(3,1)) + e(0,3)*(e(1,1)*e(3,2)-e(1,2)*e(3,1))
    inv[6]  = -(e(0,0)*(e(1,2)*e(3,3)-e(1,3)*e(3,2)) - e(0,2)*(e(1,0)*e(3,3)-e(1,3)*e(3,0)) + e(0,3)*(e(1,0)*e(3,2)-e(1,2)*e(3,0)))
    inv[10] =  e(0,0)*(e(1,1)*e(3,3)-e(1,3)*e(3,1)) - e(0,1)*(e(1,0)*e(3,3)-e(1,3)*e(3,0)) + e(0,3)*(e(1,0)*e(3,1)-e(1,1)*e(3,0))
    inv[14] = -(e(0,0)*(e(1,1)*e(3,2)-e(1,2)*e(3,1)) - e(0,1)*(e(1,0)*e(3,2)-e(1,2)*e(3,0)) + e(0,2)*(e(1,0)*e(3,1)-e(1,1)*e(3,0)))

    inv[3]  = -(e(0,1)*(e(1,2)*e(2,3)-e(1,3)*e(2,2)) - e(0,2)*(e(1,1)*e(2,3)-e(1,3)*e(2,1)) + e(0,3)*(e(1,1)*e(2,2)-e(1,2)*e(2,1)))
    inv[7]  =  e(0,0)*(e(1,2)*e(2,3)-e(1,3)*e(2,2)) - e(0,2)*(e(1,0)*e(2,3)-e(1,3)*e(2,0)) + e(0,3)*(e(1,0)*e(2,2)-e(1,2)*e(2,0))
    inv[11] = -(e(0,0)*(e(1,1)*e(2,3)-e(1,3)*e(2,1)) - e(0,1)*(e(1,0)*e(2,3)-e(1,3)*e(2,0)) + e(0,3)*(e(1,0)*e(2,1)-e(1,1)*e(2,0)))
    inv[15] =  e(0,0)*(e(1,1)*e(2,2)-e(1,2)*e(2,1)) - e(0,1)*(e(1,0)*e(2,2)-e(1,2)*e(2,0)) + e(0,2)*(e(1,0)*e(2,1)-e(1,1)*e(2,0))

    det = e(0,0)*inv[0] + e(0,1)*inv[4] + e(0,2)*inv[8] + e(0,3)*inv[12]
    if abs(det) < 1e-12:
        return mat4_identity()
    inv_det = 1.0 / det
    return [v * inv_det for v in inv]

def mat4_approx_equal(a, b, tol=1e-3):
    """Compara duas matrizes 4×4 component a componente."""
    for i in range(16):
        if abs(a[i] - b[i]) > tol:
            return False, i, a[i], b[i]
    return True, -1, 0.0, 0.0

# ---------------------------------------------------------------------------
# Leitura de accessors GLTF
# ---------------------------------------------------------------------------

def get_accessor_data(gltf, accessor_idx):
    """Devolve array numpy com os dados do accessor."""
    import base64
    acc = gltf.accessors[accessor_idx]
    bv  = gltf.bufferViews[acc.bufferView]
    buf = gltf.buffers[bv.buffer]

    if buf.uri and buf.uri.startswith("data:"):
        _, data = buf.uri.split(",", 1)
        raw = base64.b64decode(data)
    else:
        raw = bytes(gltf.binary_blob())

    bv_offset  = bv.byteOffset  or 0
    acc_offset = acc.byteOffset or 0
    offset = bv_offset + acc_offset
    count  = acc.count

    CTYPES = {
        5120: ('b', 1), 5121: ('B', 1),
        5122: ('h', 2), 5123: ('H', 2),
        5125: ('I', 4), 5126: ('f', 4),
    }
    TYPE_COUNTS = {
        "SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
        "MAT2": 4, "MAT3": 9, "MAT4": 16,
    }
    ctype, csize = CTYPES[acc.componentType]
    ncomp = TYPE_COUNTS[acc.type]
    stride = bv.byteStride if bv.byteStride else csize * ncomp

    result = []
    for i in range(count):
        base = offset + i * stride
        vals = struct.unpack_from(f"{ncomp}{ctype}", raw, base)
        result.append(vals if ncomp > 1 else vals[0])

    return np.array(result, dtype=np.float32)

# ---------------------------------------------------------------------------
# Extrair esqueleto com seleção hierárquica correcta
# ---------------------------------------------------------------------------

def extract_skeleton(gltf):
    """
    Seleciona os ossos realmente utilizados (com peso > 0 em algum vértice),
    preserva antecessores, limita a AXS1_MAX_BONES.

    Devolve (bones, skin_to_axs1) onde:
      bones = lista de dicts {name, parent, bind_pos, bind_rot}
      skin_to_axs1 = {skin_joint_index: axs1_bone_index}
    """
    if not gltf.skins:
        return [], {}

    skin = gltf.skins[0]
    joint_nodes = list(skin.joints)
    n_skin = len(joint_nodes)

    # --- 1. Ossos com peso real ---
    used_skin_joints = set()
    for mesh in gltf.meshes:
        for prim in mesh.primitives:
            ja = getattr(prim.attributes, "JOINTS_0",  None)
            wa = getattr(prim.attributes, "WEIGHTS_0", None)
            if ja is None or wa is None:
                continue
            joints_data  = get_accessor_data(gltf, ja)
            weights_data = get_accessor_data(gltf, wa)
            for vi in range(len(joints_data)):
                for k in range(4):
                    if float(weights_data[vi][k]) > 1e-6:
                        sj = int(joints_data[vi][k])
                        if 0 <= sj < n_skin:
                            used_skin_joints.add(sj)

    if not used_skin_joints:
        used_skin_joints = set(range(min(n_skin, AXS1_MAX_BONES)))

    # --- 2. Expandir para antecessores ---
    def get_skin_parent(si):
        nidx = joint_nodes[si]
        for other_si, other_nidx in enumerate(joint_nodes):
            node = gltf.nodes[other_nidx]
            if node.children and nidx in node.children:
                return other_si
        return -1

    expanded = set(used_skin_joints)
    changed = True
    while changed:
        changed = False
        for si in list(expanded):
            p = get_skin_parent(si)
            if p >= 0 and p not in expanded:
                expanded.add(p)
                changed = True

    if len(expanded) > AXS1_MAX_BONES:
        raise RuntimeError(
            f"ERRO: {len(expanded)} ossos necessários (incluindo antecessores) "
            f"excedem o limite AXS1 de {AXS1_MAX_BONES}."
        )

    # --- 3. Ordem hierárquica (preservar ordem de skin.joints) ---
    ordered_si = [si for si in range(n_skin) if si in expanded]
    skin_to_axs1 = {si: ai for ai, si in enumerate(ordered_si)}

    # --- 4. Construir matrizes globais de bind para validação IBM ---
    # global_bind[si] = matriz 4×4 global desse nó
    global_bind = {}
    for si_ordered in ordered_si:
        node_idx = joint_nodes[si_ordered]
        node = gltf.nodes[node_idx]
        t = list(node.translation) if node.translation else [0.0, 0.0, 0.0]
        r = list(node.rotation)    if node.rotation    else [0.0, 0.0, 0.0, 1.0]
        s = list(node.scale)       if node.scale       else [1.0, 1.0, 1.0]
        local_mat = mat4_from_trs(t, r, s)
        parent_si = get_skin_parent(si_ordered)
        if parent_si >= 0 and parent_si in global_bind:
            global_bind[si_ordered] = mat4_multiply(global_bind[parent_si], local_mat)
        else:
            global_bind[si_ordered] = local_mat

    # --- 5. Validar inverseBindMatrices ---
    ibm_raw = None
    if skin.inverseBindMatrices is not None:
        ibm_data = get_accessor_data(gltf, skin.inverseBindMatrices)
        ibm_raw = ibm_data.reshape(-1, 16)  # n_skin × 16
    else:
        # Especificação GLTF: implicitamente identidade
        ibm_raw = np.tile(np.eye(4, dtype=np.float32).flatten(), (n_skin, 1))

    for si_ordered in ordered_si:
        gbind = global_bind[si_ordered]
        derived_ibm = mat4_inverse(gbind)
        provided_ibm = [float(v) for v in ibm_raw[si_ordered]]

        ok, comp_idx, got, expected_v = mat4_approx_equal(derived_ibm, provided_ibm, tol=1e-2)
        if not ok:
            node_name = gltf.nodes[joint_nodes[si_ordered]].name or f"node_{joint_nodes[si_ordered]}"
            raise RuntimeError(
                f"ERRO: inverseBindMatrix do osso '{node_name}' (skin_joint {si_ordered}) "
                f"é incompatível com a hierarquia local. "
                f"Componente [{comp_idx}]: derivada={got:.6f}, fornecida={expected_v:.6f}. "
                f"O modelo pode ter transformações não-locais (ex: escala não-unitária no pai)."
            )

    # --- 6. Construir lista de ossos AXS1 ---
    bones = []
    for ai, si in enumerate(ordered_si):
        node_idx = joint_nodes[si]
        node = gltf.nodes[node_idx]
        name = (node.name or f"bone_{ai}")[:15]
        bp = [float(v) for v in node.translation] if node.translation else [0.0, 0.0, 0.0]
        br = quat_normalize([float(v) for v in node.rotation]) if node.rotation else [0.0, 0.0, 0.0, 1.0]
        parent_si = get_skin_parent(si)
        parent_axs1 = skin_to_axs1.get(parent_si, -1) if parent_si >= 0 else -1

        bones.append({
            "name":     name,
            "parent":   parent_axs1,
            "bind_pos": bp,
            "bind_rot": br,
        })

    print(f"  Ossos utilizados (com pesos): {len(used_skin_joints)}")
    print(f"  Ossos após expansão hierárquica: {len(expanded)}")
    print(f"  Ossos AXS1 selecionados: {len(bones)}")
    return bones, skin_to_axs1

# ---------------------------------------------------------------------------
# Extrair geometria com mapeamento JOINTS_0 correcto
# ---------------------------------------------------------------------------

def extract_mesh(gltf, skin_to_axs1, max_verts=AXS1_MAX_VERTICES):
    """
    JOINTS_0[k] é índice na lista skin.joints (não node_idx GLTF).
    Mapeamento: sj = JOINTS_0[k] → axs1_bone = skin_to_axs1[sj]
    """
    vertices_out = []
    n_skin = len(gltf.skins[0].joints) if gltf.skins else 0

    for mesh in gltf.meshes:
        for prim in mesh.primitives:
            if prim.attributes.POSITION is None:
                continue

            pos  = get_accessor_data(gltf, prim.attributes.POSITION)
            tc0  = getattr(prim.attributes, "TEXCOORD_0", None)
            uvs  = get_accessor_data(gltf, tc0)  if tc0  is not None else None
            nrms = (get_accessor_data(gltf, prim.attributes.NORMAL)
                    if prim.attributes.NORMAL is not None else None)

            ja = getattr(prim.attributes, "JOINTS_0",  None)
            wa = getattr(prim.attributes, "WEIGHTS_0", None)
            joints_data  = get_accessor_data(gltf, ja) if ja is not None else None
            weights_data = get_accessor_data(gltf, wa) if wa is not None else None

            if prim.indices is not None:
                idx_data = get_accessor_data(gltf, prim.indices).astype(int).flatten()
            else:
                idx_data = np.arange(len(pos), dtype=int)

            for raw_i in idx_data:
                i = int(raw_i)
                if i >= len(pos):
                    continue
                if len(vertices_out) >= max_verts:
                    raise RuntimeError(
                        f"ERRO: modelo excede o limite de {max_verts} vértices do runtime PSP. "
                        f"Não é possível truncar sem corromper a geometria."
                    )

                px_ = float(pos[i][0]);  py_ = float(pos[i][1]);  pz_ = float(pos[i][2])
                u_  = float(uvs[i][0])  if uvs  is not None and i < len(uvs)  else 0.0
                v_  = float(uvs[i][1])  if uvs  is not None and i < len(uvs)  else 0.0
                nx_ = float(nrms[i][0]) if nrms is not None and i < len(nrms) else 0.0
                ny_ = float(nrms[i][1]) if nrms is not None and i < len(nrms) else 1.0
                nz_ = float(nrms[i][2]) if nrms is not None and i < len(nrms) else 0.0

                bi4 = [0, 0, 0, 0]
                wt4 = [1.0, 0.0, 0.0, 0.0]

                if joints_data is not None and weights_data is not None and i < len(joints_data):
                    raw_j = joints_data[i]
                    raw_w = weights_data[i]
                    wsum  = sum(float(raw_w[k]) for k in range(4))

                    for k in range(4):
                        sj = int(raw_j[k])
                        w  = float(raw_w[k])
                        if w < 1e-6:
                            bi4[k] = 0;  wt4[k] = 0.0
                            continue
                        if sj < 0 or sj >= n_skin:
                            raise RuntimeError(
                                f"ERRO: JOINTS_0[{k}]={sj} fora do intervalo [0,{n_skin}) no vértice {i}."
                            )
                        axs1_idx = skin_to_axs1.get(sj, None)
                        if axs1_idx is None:
                            raise RuntimeError(
                                f"ERRO: skin_joint {sj} (vértice {i}) tem peso {w:.4f} "
                                f"mas foi eliminado do esqueleto AXS1."
                            )
                        bi4[k] = axs1_idx & 0xFF
                        wt4[k] = w / wsum if wsum > 1e-6 else (1.0 if k == 0 else 0.0)

                    ws = sum(wt4)
                    wt4 = [w/ws for w in wt4] if ws > 1e-6 else [1.0, 0.0, 0.0, 0.0]

                for val, lbl in [(px_,'px'),(py_,'py'),(pz_,'pz'),
                                 (nx_,'nx'),(ny_,'ny'),(nz_,'nz'),
                                 (u_,'u'),(v_,'v')] + [(w,'w') for w in wt4]:
                    if not math.isfinite(val):
                        raise RuntimeError(f"ERRO: valor não finito '{lbl}' no vértice {i}.")

                vertices_out.append({
                    "u": u_, "v": v_,
                    "nx": nx_, "ny": ny_, "nz": nz_,
                    "px": px_, "py": py_, "pz": pz_,
                    "bone_idx": bi4,
                    "weight":   wt4,
                })

    return vertices_out

# ---------------------------------------------------------------------------
# Interpolação de keyframes GLTF
# ---------------------------------------------------------------------------

def interpolate_vec3(times, values, t, interpolation):
    """
    values shape:
      LINEAR/STEP:   (n, 3)
      CUBICSPLINE:   (n, 3, 3)  — [in_tan, point, out_tan]
    """
    n = len(times)
    if n == 0:
        return [0.0, 0.0, 0.0]
    if t <= float(times[0]):
        v = values[0] if interpolation != "CUBICSPLINE" else values[0][1]
        return [float(v[k]) for k in range(3)]
    if t >= float(times[-1]):
        v = values[-1] if interpolation != "CUBICSPLINE" else values[-1][1]
        return [float(v[k]) for k in range(3)]

    for i in range(n - 1):
        t0, t1 = float(times[i]), float(times[i+1])
        if t0 <= t <= t1:
            dt    = t1 - t0
            alpha = (t - t0) / dt if dt > 1e-9 else 0.0

            if interpolation == "STEP":
                v = values[i]
                return [float(v[k]) for k in range(3)]
            elif interpolation == "CUBICSPLINE":
                p0 = np.array(values[i][1],   dtype=float)
                p1 = np.array(values[i+1][1], dtype=float)
                m0 = np.array(values[i][2],   dtype=float) * dt
                m1 = np.array(values[i+1][0], dtype=float) * dt
                a  = alpha
                h00 =  2*a**3 - 3*a**2 + 1
                h10 =    a**3 - 2*a**2 + a
                h01 = -2*a**3 + 3*a**2
                h11 =    a**3 -   a**2
                result = h00*p0 + h10*m0 + h01*p1 + h11*m1
                return [float(result[k]) for k in range(3)]
            else:  # LINEAR
                v0 = np.array(values[i],   dtype=float)
                v1 = np.array(values[i+1], dtype=float)
                result = v0 + alpha * (v1 - v0)
                return [float(result[k]) for k in range(3)]

    v = values[-1] if interpolation != "CUBICSPLINE" else values[-1][1]
    return [float(v[k]) for k in range(3)]


def interpolate_quat(times, values, t, interpolation):
    """
    LINEAR: slerp entre quaterniões normalizados.
    STEP: reter valor anterior.
    CUBICSPLINE: Hermite cúbico componente a componente, depois normalizar.
      values shape (n, 3, 4): [in_tan, point, out_tan] por keyframe.
    """
    n = len(times)
    if n == 0:
        return [0.0, 0.0, 0.0, 1.0]
    if t <= float(times[0]):
        v = values[0] if interpolation != "CUBICSPLINE" else values[0][1]
        return quat_normalize([float(v[k]) for k in range(4)])
    if t >= float(times[-1]):
        v = values[-1] if interpolation != "CUBICSPLINE" else values[-1][1]
        return quat_normalize([float(v[k]) for k in range(4)])

    for i in range(n - 1):
        t0, t1 = float(times[i]), float(times[i+1])
        if t0 <= t <= t1:
            dt    = t1 - t0
            alpha = (t - t0) / dt if dt > 1e-9 else 0.0

            if interpolation == "STEP":
                v = values[i]
                return quat_normalize([float(v[k]) for k in range(4)])
            elif interpolation == "CUBICSPLINE":
                # Hermite cúbico componente a componente
                p0 = [float(values[i][1][k])   for k in range(4)]
                p1 = [float(values[i+1][1][k]) for k in range(4)]
                m0 = [float(values[i][2][k])   * dt for k in range(4)]  # out_tan * dt
                m1 = [float(values[i+1][0][k]) * dt for k in range(4)]  # in_tan  * dt
                return quat_hermite_cubic(p0, m0, p1, m1, alpha)
            else:  # LINEAR → slerp
                q0 = quat_normalize([float(values[i][k])   for k in range(4)])
                q1 = quat_normalize([float(values[i+1][k]) for k in range(4)])
                return quat_slerp(q0, q1, alpha)

    v = values[-1] if interpolation != "CUBICSPLINE" else values[-1][1]
    return quat_normalize([float(v[k]) for k in range(4)])


def parse_sampler_values(gltf, sampler, n_times, path):
    """
    Lê os valores de saída do sampler.
    CUBICSPLINE: (n, 3, ncomp) — [in_tan, point, out_tan]
    Outro: (n, ncomp)
    """
    interp = (sampler.interpolation or "LINEAR").upper()
    raw    = get_accessor_data(gltf, sampler.output)
    ncomp  = 4 if path == "rotation" else 3

    if interp == "CUBICSPLINE":
        flat = raw.flatten()[:n_times * 3 * ncomp].reshape(n_times, 3, ncomp)
        return flat, interp
    else:
        flat = raw.flatten()[:n_times * ncomp].reshape(n_times, ncomp)
        return flat, interp

# ---------------------------------------------------------------------------
# Extrair animações reais
# ---------------------------------------------------------------------------

def extract_animations(gltf, skin_to_axs1, bone_count, fps_out=30.0):
    """
    Extrai apenas as animações realmente presentes.
    Não cria clips falsos.
    """
    if not gltf.animations:
        return []

    joint_nodes = list(gltf.skins[0].joints) if gltf.skins else []
    axs1_to_node = {ai: joint_nodes[si] for si, ai in skin_to_axs1.items()}
    node_to_axs1 = {joint_nodes[si]: ai for si, ai in skin_to_axs1.items()}

    def canonical_name(anim_name):
        low = anim_name.lower().strip()
        for canon, aliases in CLIP_ALIASES.items():
            for alias in aliases:
                if alias.lower() == low:
                    return canon
        for canon, aliases in CLIP_ALIASES.items():
            for alias in aliases:
                if alias.lower() in low:
                    return canon
        return anim_name[:15]

    clips = []
    seen  = {}

    for anim in gltf.animations:
        anim_name  = anim.name or f"anim_{len(clips)}"
        clip_name  = canonical_name(anim_name)

        if clip_name in seen:
            print(f"  [DUPLICADO] '{anim_name}' → '{clip_name}' — ignorado.")
            continue
        seen[clip_name] = True

        bone_rot   = {}
        bone_pos   = {}
        bone_scale = {}
        all_times  = set()

        for channel in anim.channels:
            target = channel.target
            if target.node is None or target.node not in node_to_axs1:
                continue
            ai = node_to_axs1[target.node]

            sampler = anim.samplers[channel.sampler]
            times   = get_accessor_data(gltf, sampler.input).flatten()
            n_times = len(times)
            for t in times:
                all_times.add(float(t))

            path = target.path
            if path == "rotation":
                bone_rot[ai]   = (times,) + parse_sampler_values(gltf, sampler, n_times, "rotation")
            elif path == "translation":
                bone_pos[ai]   = (times,) + parse_sampler_values(gltf, sampler, n_times, "translation")
            elif path == "scale":
                bone_scale[ai] = (times,) + parse_sampler_values(gltf, sampler, n_times, "scale")

        if not all_times:
            print(f"  [VAZIO] '{anim_name}' — sem keyframes.")
            continue

        # Aviso de escala não-unitária
        for ai, (times_s, vals_s, interp_s) in bone_scale.items():
            for vi in range(len(vals_s)):
                v = vals_s[vi] if interp_s != "CUBICSPLINE" else vals_s[vi][1]
                if any(abs(float(v[k]) - 1.0) > 0.01 for k in range(3)):
                    node_name = gltf.nodes[axs1_to_node.get(ai, 0)].name or f"bone_{ai}"
                    print(f"  [AVISO] '{anim_name}': '{node_name}' tem escala não-unitária "
                          f"(não representável em AXS1 — será ignorada).")
                    break

        sorted_times = sorted(all_times)
        t_start  = sorted_times[0]
        t_end    = sorted_times[-1]
        duration = t_end - t_start

        frame_count = 2 if duration < 1e-6 else max(2, int(round(duration * fps_out)) + 1)
        frame_count = min(frame_count, 512)

        # Poses de bind por osso (para ossos sem canal)
        bind_bones = []
        for bi in range(bone_count):
            nidx = axs1_to_node.get(bi, None)
            if nidx is not None:
                node = gltf.nodes[nidx]
                bp = [float(v) for v in node.translation] if node.translation else [0.0, 0.0, 0.0]
                br = quat_normalize([float(v) for v in node.rotation]) if node.rotation else [0.0, 0.0, 0.0, 1.0]
            else:
                bp = [0.0, 0.0, 0.0]
                br = [0.0, 0.0, 0.0, 1.0]
            bind_bones.append({"pos": bp, "rot": br})

        frames = []
        for fi in range(frame_count):
            alpha = fi / max(frame_count - 1, 1)
            t_q   = t_start + alpha * duration if duration > 1e-6 else t_start
            frame_keys = []
            for bi in range(bone_count):
                if bi in bone_rot:
                    times_r, vals_r, interp_r = bone_rot[bi]
                    rot = interpolate_quat(times_r, vals_r, t_q, interp_r)
                else:
                    rot = bind_bones[bi]["rot"]
                if bi in bone_pos:
                    times_p, vals_p, interp_p = bone_pos[bi]
                    pos = interpolate_vec3(times_p, vals_p, t_q, interp_p)
                else:
                    pos = bind_bones[bi]["pos"]
                frame_keys.append({"rot": rot, "pos": pos})
            frames.append(frame_keys)

        clips.append({
            "name":        clip_name,
            "fps":         fps_out,
            "frame_count": frame_count,
            "frames":      frames,
        })
        print(f"  Clip '{anim_name}' → '{clip_name}': {frame_count} frames @ {fps_out:.0f}fps")

    return clips


def report_missing_clips(clips):
    """Reporta clips em falta. NÃO cria clips falsos."""
    existing = {c["name"].upper() for c in clips}
    missing  = [n for n in CLIP_ORDER if n not in existing]
    if missing:
        print(f"  [AVISO] Clips não encontrados: {missing}")
    return missing


def order_clips(clips):
    """
    Ordena clips na ordem fixa do runtime (IDLE=0, WALK=1, RUN=2, JUMP=3, LAND=4).
    Verifica que todos os cinco estão presentes — aborta se faltar algum.
    """
    existing_names = {c["name"].upper() for c in clips}
    missing = [n for n in CLIP_ORDER if n not in existing_names]
    if missing:
        found = [c["name"] for c in clips]
        raise RuntimeError(
            f"ERRO: clips obrigatórios em falta: {missing}.\n"
            f"Clips encontrados no GLB: {found}.\n"
            f"O runtime usa índices fixos (IDLE=0, WALK=1, RUN=2, JUMP=3, LAND=4). "
            f"Não é possível gerar AXS1 sem todos os cinco."
        )

    ordered = []
    for name in CLIP_ORDER:
        for c in clips:
            if c["name"].upper() == name:
                ordered.append(c)
                break

    # Restantes (fora dos cinco obrigatórios), se houver
    names_taken = {c["name"].upper() for c in ordered}
    for c in clips:
        if c["name"].upper() not in names_taken:
            ordered.append(c)

    if len(ordered) > AXS1_MAX_CLIPS:
        print(f"  [AVISO] {len(ordered)} clips excedem AXS1_MAX_CLIPS={AXS1_MAX_CLIPS}. A truncar.")
        ordered = ordered[:AXS1_MAX_CLIPS]

    return ordered

# ---------------------------------------------------------------------------
# Escrever AXS1
# ---------------------------------------------------------------------------

def write_axs1(path, bones, vertices, clips):
    bone_count   = len(bones)
    vertex_count = len(vertices)
    clip_count   = len(clips)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    with open(path, "wb") as f:
        # Cabeçalho (32 bytes)
        f.write(b"AXS1")
        f.write(struct.pack("<I", AXS1_VERSION))
        f.write(struct.pack("<I", bone_count))
        f.write(struct.pack("<I", vertex_count))
        f.write(struct.pack("<I", clip_count))
        f.write(struct.pack("<III", 0, 0, 0))

        # Ossos (56 bytes cada)
        for b in bones:
            name_b = b["name"].encode("ascii", errors="replace")[:15].ljust(16, b"\x00")
            f.write(name_b)                                               # 16B
            f.write(struct.pack("<i", b["parent"]))                      # 4B
            f.write(b"\x00" * 4)                                         # 4B pad
            f.write(struct.pack("<3f", *[float(v) for v in b["bind_pos"]]))  # 12B
            f.write(struct.pack("<4f", *[float(v) for v in b["bind_rot"]]))  # 16B
            f.write(b"\x00" * 4)                                         # 4B pad_end

        # Vértices (52 bytes cada)
        # offset 0:  u, v         (2×float = 8B)
        # offset 8:  nx, ny, nz   (3×float = 12B)
        # offset 20: px, py, pz   (3×float = 12B)
        # offset 32: bone_idx[4]  (4×uint8 = 4B)
        # offset 36: weight[4]    (4×float = 16B)
        for v in vertices:
            f.write(struct.pack("<2f", v["u"], v["v"]))
            f.write(struct.pack("<3f", v["nx"], v["ny"], v["nz"]))
            f.write(struct.pack("<3f", v["px"], v["py"], v["pz"]))
            f.write(struct.pack("<4B", *[int(b) & 0xFF for b in v["bone_idx"]]))
            f.write(struct.pack("<4f", *[float(w) for w in v["weight"]]))

        # Clips
        for c in clips:
            name_b = c["name"].encode("ascii", errors="replace")[:15].ljust(16, b"\x00")
            f.write(name_b)
            f.write(struct.pack("<i", c["frame_count"]))
            f.write(struct.pack("<f", c["fps"]))
            for frame in c["frames"]:
                for key in frame:
                    f.write(struct.pack("<4f", *[float(v) for v in key["rot"]]))
                    f.write(struct.pack("<3f", *[float(v) for v in key["pos"]]))
                    f.write(struct.pack("<f",  0.0))

    return os.path.getsize(path)

# ---------------------------------------------------------------------------
# Validar AXS1 (robusto a ficheiros truncados)
# ---------------------------------------------------------------------------

def validate_axs1(path, bones, clips):
    """
    Valida a estrutura completa do AXS1.
    Nunca lança struct.error — detecta truncamento e reporta erro descritivo.
    """
    errors = []

    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return [f"Não foi possível ler o ficheiro: {e}"]

    file_size = len(data)

    # --- 1. Cabeçalho mínimo ---
    if file_size < AXS1_HEADER_SIZE:
        return [f"Ficheiro truncado: {file_size} < {AXS1_HEADER_SIZE} bytes (cabeçalho incompleto)"]

    # --- 2. Magic ---
    if data[0:4] != b"AXS1":
        errors.append(f"Magic inválido: {data[0:4]!r} (esperado b'AXS1')")
        return errors

    # --- 3. Contadores ---
    version = struct.unpack_from("<I", data, 4)[0]
    bc      = struct.unpack_from("<I", data, 8)[0]
    vc      = struct.unpack_from("<I", data, 12)[0]
    cc      = struct.unpack_from("<I", data, 16)[0]

    if version != AXS1_VERSION:
        errors.append(f"Versão inválida: {version} (esperado {AXS1_VERSION})")
    if len(bones) > 0 and bc != len(bones):
        errors.append(f"bone_count={bc} != esperado {len(bones)}")
    if vc == 0:
        errors.append("vertex_count é zero")
    if len(clips) > 0 and cc != len(clips):
        errors.append(f"clip_count={cc} != esperado {len(clips)}")
    if bc > AXS1_MAX_BONES:
        errors.append(f"bone_count={bc} excede limite {AXS1_MAX_BONES}")
    if vc > AXS1_MAX_VERTICES:
        errors.append(f"vertex_count={vc} excede limite {AXS1_MAX_VERTICES}")
    if cc > AXS1_MAX_CLIPS:
        errors.append(f"clip_count={cc} excede limite {AXS1_MAX_CLIPS}")

    if errors:
        return errors  # contadores inválidos: não tentar ler secções

    # --- 4. Tamanho esperado total ---
    clip_frames = [c["frame_count"] for c in clips] if clips else []
    expected = AXS1_HEADER_SIZE + bc * AXS1_BONE_ONDISK + vc * AXS1_VERTEX_ONDISK
    for fc in clip_frames:
        expected += AXS1_CLIP_HDR_SIZE + fc * bc * AXS1_KEY_ONDISK

    if file_size != expected:
        errors.append(
            f"Tamanho do ficheiro: {file_size} bytes, esperado {expected} bytes "
            f"(ossos={bc}, vértices={vc}, clips={cc})"
        )
        # Se truncado, não tentar ler além dos bytes disponíveis
        if file_size < expected:
            errors.append("Ficheiro truncado — validação de campos interrompida.")
            return errors

    # --- 5. Validar vértices ---
    off_vtx = AXS1_HEADER_SIZE + bc * AXS1_BONE_ONDISK
    needed_vtx = off_vtx + vc * AXS1_VERTEX_ONDISK
    if file_size < needed_vtx:
        errors.append(f"Ficheiro truncado na secção de vértices: {file_size} < {needed_vtx}")
        return errors

    for vi in range(vc):
        voff = off_vtx + vi * AXS1_VERTEX_ONDISK
        bi4  = struct.unpack_from("<4B", data, voff + _VTX_BIDX_OFF)
        wt4  = struct.unpack_from("<4f", data, voff + _VTX_WGHT_OFF)
        for k in range(4):
            if bi4[k] >= bc:
                errors.append(f"Vértice {vi}: bone_idx[{k}]={bi4[k]} >= bone_count={bc}")
            if not math.isfinite(wt4[k]) or wt4[k] < 0.0:
                errors.append(f"Vértice {vi}: weight[{k}]={wt4[k]} inválido")

    # --- 6. Validar keyframes ---
    off_kf = off_vtx + vc * AXS1_VERTEX_ONDISK
    for ci in range(cc):
        needed_hdr = off_kf + AXS1_CLIP_HDR_SIZE
        if file_size < needed_hdr:
            errors.append(f"Clip {ci}: ficheiro truncado no cabeçalho (offset {off_kf})")
            return errors

        fc    = struct.unpack_from("<i", data, off_kf + 16)[0]
        fps_v = struct.unpack_from("<f", data, off_kf + 20)[0]
        if fc <= 0:
            errors.append(f"Clip {ci}: frame_count={fc} inválido")
        if not math.isfinite(fps_v) or fps_v <= 0:
            errors.append(f"Clip {ci}: fps={fps_v} inválido")

        off_kf += AXS1_CLIP_HDR_SIZE
        needed_keys = off_kf + fc * bc * AXS1_KEY_ONDISK
        if file_size < needed_keys:
            errors.append(f"Clip {ci}: ficheiro truncado nos keyframes "
                          f"(offset {off_kf}, precisa {needed_keys})")
            return errors

        for fi in range(fc):
            for bi in range(bc):
                rot4 = struct.unpack_from("<4f", data, off_kf)
                pos3 = struct.unpack_from("<3f", data, off_kf + 16)
                off_kf += AXS1_KEY_ONDISK
                for k, rv in enumerate(rot4):
                    if not math.isfinite(rv):
                        errors.append(f"Clip {ci} frame {fi} bone {bi}: rot[{k}] não finito")
                for k, pv in enumerate(pos3):
                    if not math.isfinite(pv):
                        errors.append(f"Clip {ci} frame {fi} bone {bi}: pos[{k}] não finito")

    return errors

# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------

def write_report(path, glb_path, bones, vertices, clips, missing_clips,
                 file_size, errors):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Relatório de Conversão AXS1\n\n")
        f.write(f"- **Origem**: `{glb_path}`\n")
        f.write(f"- **Formato**: AXS1 versão {AXS1_VERSION}\n\n")

        f.write("## Dados do modelo\n\n")
        f.write(f"- Vértices: {len(vertices)}\n")
        f.write(f"- Ossos AXS1: {len(bones)}\n")
        f.write(f"- Clips: {len(clips)}\n")
        f.write(f"- Tamanho AXS1: {file_size} bytes ({file_size/1024:.1f} KB)\n\n")

        f.write("## Ossos\n\n")
        f.write("| # | Nome | Parent |\n|---|------|--------|\n")
        for bi, b in enumerate(bones):
            f.write(f"| {bi} | {b['name']} | {b['parent']} |\n")

        f.write("\n## Clips\n\n")
        if clips:
            f.write("| # | Nome | Frames | FPS |\n|---|------|--------|-----|\n")
            for ci, c in enumerate(clips):
                f.write(f"| {ci} | {c['name']} | {c['frame_count']} | {c['fps']:.0f} |\n")
        else:
            f.write("Nenhum clip.\n")

        if missing_clips:
            f.write("\n## Clips em falta\n\n")
            for m in missing_clips:
                f.write(f"- {m} — ausente no GLB\n")

        f.write("\n## Validação\n\n")
        if errors:
            f.write("**ERROS:**\n\n")
            for e in errors:
                f.write(f"- {e}\n")
        else:
            f.write("✅ AXS1 válido.\n")

        f.write(f"\n## Layout binário\n\n```\n"
                f"AXS1_HEADER_SIZE   = {AXS1_HEADER_SIZE}\n"
                f"AXS1_BONE_ONDISK   = {AXS1_BONE_ONDISK}\n"
                f"AXS1_VERTEX_ONDISK = {AXS1_VERTEX_ONDISK}\n"
                f"AXS1_CLIP_HDR_SIZE = {AXS1_CLIP_HDR_SIZE}\n"
                f"AXS1_KEY_ONDISK    = {AXS1_KEY_ONDISK}\n"
                f"_VTX_BIDX_OFF      = {_VTX_BIDX_OFF}\n"
                f"_VTX_WGHT_OFF      = {_VTX_WGHT_OFF}\n"
                f"```\n")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Conversor GLB → AXS1")
    parser.add_argument("input",  help="GLB de entrada")
    parser.add_argument("output", help="AXS1 de saída")
    parser.add_argument("--report", default=None)
    parser.add_argument("--fps",    type=float, default=30.0)
    args = parser.parse_args()

    if not HAS_NUMPY:
        print("ERRO: numpy não instalado."); sys.exit(1)
    if not HAS_PYGLTFLIB:
        print("ERRO: pygltflib não instalado."); sys.exit(1)
    if not os.path.isfile(args.input):
        print(f"ERRO: ficheiro não encontrado: {args.input}"); sys.exit(1)

    print(f"A carregar GLB: {args.input}")
    gltf = GLTF2().load(args.input)

    # 1. Esqueleto
    print("A extrair esqueleto...")
    try:
        bones, skin_to_axs1 = extract_skeleton(gltf)
    except RuntimeError as e:
        print(str(e)); sys.exit(1)

    if not bones:
        print("[AVISO] Sem esqueleto — a criar osso raiz sintético.")
        bones = [{"name": "root", "parent": -1,
                  "bind_pos": [0.0,0.0,0.0], "bind_rot": [0.0,0.0,0.0,1.0]}]
        skin_to_axs1 = {}
    bone_count = len(bones)
    print(f"  {bone_count} osso(s) no AXS1.")

    # 2. Geometria
    print("A extrair geometria...")
    try:
        vertices = extract_mesh(gltf, skin_to_axs1, AXS1_MAX_VERTICES)
    except RuntimeError as e:
        print(str(e)); sys.exit(1)
    if not vertices:
        print("ERRO: sem vértices."); sys.exit(1)
    print(f"  {len(vertices)} vértice(s).")

    # 3. Animações
    print("A extrair animações...")
    try:
        clips = extract_animations(gltf, skin_to_axs1, bone_count, args.fps)
    except RuntimeError as e:
        print(str(e)); sys.exit(1)

    missing = report_missing_clips(clips)

    try:
        clips = order_clips(clips)
    except RuntimeError as e:
        print(str(e)); sys.exit(1)

    print(f"  {len(clips)} clip(s): {[c['name'] for c in clips]}")

    # 4. Escrever
    print(f"A escrever: {args.output}")
    try:
        file_size = write_axs1(args.output, bones, vertices, clips)
    except Exception as e:
        print(f"ERRO ao escrever: {e}"); sys.exit(1)
    print(f"  {file_size} bytes ({file_size/1024:.1f} KB)")

    # 5. Validar
    print("A validar...")
    errors = validate_axs1(args.output, bones, clips)
    if errors:
        print("ERROS DE VALIDAÇÃO:")
        for e in errors:
            print(f"  - {e}")
        if args.report:
            write_report(args.report, args.input, bones, vertices, clips,
                         missing, file_size, errors)
        sys.exit(1)
    print("  Validação: OK")

    # 6. Relatório
    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        write_report(args.report, args.input, bones, vertices, clips,
                     missing, file_size, [])
        print(f"  Relatório: {args.report}")

    print("Conversão concluída com sucesso.")

if __name__ == "__main__":
    main()
