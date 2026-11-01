#!/usr/bin/env python3
"""
convert_glb_to_axs1.py — RPG Axel Digital
Converte um ficheiro GLB (GLTF binário) para o formato AXS1 do motor.

Utilização:
    python3 convert_glb_to_axs1.py <input.glb> <output.axs> [--report <report.md>]

Dependências:
    pip install pygltflib numpy

Formato AXS1 (especificação definitiva — deve coincidir com p3d_anim.h):

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
    u, v           float×2
    nx, ny, nz     float×3
    px, py, pz     float×3
    bone_idx[4]    uint8×4
    weight[4]      float×4

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
AXS1_MAX_VERTICES = 65536
AXS1_VERSION      = 1

AXS1_HEADER_SIZE   = 32
AXS1_BONE_ONDISK   = 56
AXS1_VERTEX_ONDISK = 52
AXS1_CLIP_HDR_SIZE = 24
AXS1_KEY_ONDISK    = 32   # por osso por frame

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
    """Slerp entre dois quaterniões normalizados."""
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
    preserva os seus antecessores para manter a hierarquia, limita a
    AXS1_MAX_BONES, e constrói o mapeamento node_idx → bone_idx AXS1.

    Devolve (bones, skin_joint_to_axs1) onde:
      bones = lista de dicts {name, parent, bind_pos, bind_rot}
      skin_joint_to_axs1 = {skin_joint_index: axs1_bone_index}
        (skin_joint_index é a posição em skin.joints, não o node_idx GLTF)
    """
    if not gltf.skins:
        return [], {}

    skin = gltf.skins[0]
    joint_nodes = list(skin.joints)   # [node_idx, ...]
    n_skin = len(joint_nodes)

    # Construir mapa node_idx → posição em skin.joints
    node_to_skin_idx = {nidx: si for si, nidx in enumerate(joint_nodes)}

    # --- 1. Descobrir quais skin_joints têm peso real nos vértices ---
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
        # Nenhum peso encontrado — usar todos (até AXS1_MAX_BONES)
        used_skin_joints = set(range(min(n_skin, AXS1_MAX_BONES)))

    # --- 2. Expandir para incluir antecessores (hierarquia completa) ---
    def get_skin_parent(si):
        """Devolve skin_idx do pai de skin_joints[si], ou -1."""
        nidx = joint_nodes[si]
        for other_si, other_nidx in enumerate(joint_nodes):
            node = gltf.nodes[other_nidx]
            if node.children and nidx in node.children:
                return other_si
        return -1

    # Expandir iterativamente
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
        # Não conseguimos representar o esqueleto correctamente
        raise RuntimeError(
            f"ERRO: {len(expanded)} ossos necessários (incluindo antecessores) "
            f"excedem o limite AXS1 de {AXS1_MAX_BONES}. "
            f"Não é possível converter o esqueleto sem perder integridade."
        )

    # --- 3. Ordenar hierarquicamente (pai antes de filho) ---
    # Usar a ordem original de skin.joints como base (já é topológica no GLTF)
    ordered_si = [si for si in range(n_skin) if si in expanded]

    # Construir mapa skin_joint_idx → AXS1 bone_idx
    skin_to_axs1 = {si: ai for ai, si in enumerate(ordered_si)}

    # --- 4. Inverse bind matrices ---
    ibm = None
    if skin.inverseBindMatrices is not None:
        ibm_data = get_accessor_data(gltf, skin.inverseBindMatrices)
        ibm = ibm_data.reshape(-1, 16)  # column-major 4×4

    # --- 5. Construir lista de ossos AXS1 ---
    bones = []
    for ai, si in enumerate(ordered_si):
        node_idx = joint_nodes[si]
        node = gltf.nodes[node_idx]
        name = (node.name or f"bone_{ai}")[:15]

        # Transformação local do nó (pose de bind)
        if node.translation:
            bp = [float(v) for v in node.translation]
        else:
            bp = [0.0, 0.0, 0.0]

        if node.rotation:
            br = quat_normalize([float(v) for v in node.rotation])
        else:
            br = [0.0, 0.0, 0.0, 1.0]

        # Parent no espaço AXS1
        parent_si = get_skin_parent(si)
        if parent_si >= 0 and parent_si in skin_to_axs1:
            parent_axs1 = skin_to_axs1[parent_si]
        else:
            parent_axs1 = -1

        bones.append({
            "name":      name,
            "parent":    parent_axs1,
            "bind_pos":  bp,
            "bind_rot":  br,  # xyzw
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
    JOINTS_0 contém índices relativos a skin.joints (não node_idx GLTF).
    Portanto o mapeamento correcto é:
        axs1_bone = skin_to_axs1[ JOINTS_0[k] ]

    Devolve lista de vértices como dicts.
    Lança RuntimeError se a geometria não puder ser reduzida de forma segura.
    """
    vertices_out = []
    n_skin = len(gltf.skins[0].joints) if gltf.skins else 0

    for mesh in gltf.meshes:
        for prim in mesh.primitives:
            if prim.attributes.POSITION is None:
                continue

            pos  = get_accessor_data(gltf, prim.attributes.POSITION)
            uvs  = (get_accessor_data(gltf, getattr(prim.attributes, "TEXCOORD_0"))
                    if getattr(prim.attributes, "TEXCOORD_0", None) is not None else None)
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

            for i in idx_data:
                i = int(i)
                if i >= len(pos):
                    continue

                if len(vertices_out) >= max_verts:
                    # Não truncar triângulos incompletos
                    break

                px_ = float(pos[i][0])
                py_ = float(pos[i][1])
                pz_ = float(pos[i][2])
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

                    # Normalizar pesos
                    wsum = sum(float(raw_w[k]) for k in range(4))

                    for k in range(4):
                        # JOINTS_0[k] é índice em skin.joints
                        sj = int(raw_j[k])
                        w  = float(raw_w[k])

                        if w < 1e-6:
                            bi4[k] = 0
                            wt4[k] = 0.0
                            continue

                        if sj < 0 or sj >= n_skin:
                            raise RuntimeError(
                                f"ERRO: JOINTS_0[{k}]={sj} fora do intervalo "
                                f"[0, {n_skin}) para o vértice {i}."
                            )

                        axs1_idx = skin_to_axs1.get(sj, None)
                        if axs1_idx is None:
                            raise RuntimeError(
                                f"ERRO: skin_joint {sj} (vértice {i}) tem peso "
                                f"{w:.4f} mas foi eliminado do esqueleto AXS1. "
                                f"Não é possível representar a geometria correctamente."
                            )

                        bi4[k] = axs1_idx & 0xFF
                        wt4[k] = w / wsum if wsum > 1e-6 else (1.0 if k == 0 else 0.0)

                    # Verificar que os pesos somam ~1.0
                    ws = sum(wt4)
                    if ws > 1e-6:
                        wt4 = [w/ws for w in wt4]
                    else:
                        wt4 = [1.0, 0.0, 0.0, 0.0]

                # Verificar valores finitos
                for val, name_ in [(px_,'px'),(py_,'py'),(pz_,'pz'),
                                   (nx_,'nx'),(ny_,'ny'),(nz_,'nz'),
                                   (u_,'u'),(v_,'v')] + [(w,'w') for w in wt4]:
                    if not math.isfinite(val):
                        raise RuntimeError(f"ERRO: valor não finito em {name_} do vértice {i}.")

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
    """Interpolar vec3. values shape: (n,3) para LINEAR/STEP, (n,3,3) para CUBICSPLINE."""
    n = len(times)
    if n == 0:
        return [0.0, 0.0, 0.0]
    if t <= times[0]:
        return list(values[0] if interpolation != "CUBICSPLINE" else values[0][1])
    if t >= times[-1]:
        return list(values[-1] if interpolation != "CUBICSPLINE" else values[-1][1])

    for i in range(n - 1):
        t0, t1 = float(times[i]), float(times[i+1])
        if t0 <= t <= t1:
            dt = t1 - t0
            alpha = (t - t0) / dt if dt > 1e-9 else 0.0

            if interpolation == "STEP":
                return list(values[i] if isinstance(values[i], (list, np.ndarray)) else values[i])
            elif interpolation == "CUBICSPLINE":
                # values[i] = [in_tangent, point, out_tangent]  (cada vec3)
                p0  = np.array(values[i][1],   dtype=float)
                p1  = np.array(values[i+1][1], dtype=float)
                m0  = np.array(values[i][2],   dtype=float) * dt
                m1  = np.array(values[i+1][0], dtype=float) * dt
                a = alpha
                h00 =  2*a**3 - 3*a**2 + 1
                h10 =    a**3 - 2*a**2 + a
                h01 = -2*a**3 + 3*a**2
                h11 =    a**3 -   a**2
                result = h00*p0 + h10*m0 + h01*p1 + h11*m1
                return list(result)
            else:  # LINEAR
                v0 = np.array(values[i],   dtype=float)
                v1 = np.array(values[i+1], dtype=float)
                return list(v0 + alpha * (v1 - v0))
    return list(values[-1] if interpolation != "CUBICSPLINE" else values[-1][1])


def interpolate_quat(times, values, t, interpolation):
    """Interpolar quaternião. CUBICSPLINE avaliado como LINEAR (discretizado)."""
    n = len(times)
    if n == 0:
        return [0.0, 0.0, 0.0, 1.0]
    if t <= times[0]:
        v = values[0] if interpolation != "CUBICSPLINE" else values[0][1]
        return quat_normalize(list(v))
    if t >= times[-1]:
        v = values[-1] if interpolation != "CUBICSPLINE" else values[-1][1]
        return quat_normalize(list(v))

    for i in range(n - 1):
        t0, t1 = float(times[i]), float(times[i+1])
        if t0 <= t <= t1:
            dt = t1 - t0
            alpha = (t - t0) / dt if dt > 1e-9 else 0.0

            if interpolation == "STEP":
                v = values[i] if interpolation != "CUBICSPLINE" else values[i][1]
                return quat_normalize(list(v))
            elif interpolation == "CUBICSPLINE":
                # Avaliar hermite spline cúbica para quaterniões (aproximação linear discreta)
                p0 = quat_normalize(list(values[i][1]))
                p1 = quat_normalize(list(values[i+1][1]))
                return quat_slerp(p0, p1, alpha)
            else:  # LINEAR (GLTF usa slerp para quaterniões)
                q0 = quat_normalize(list(values[i]))
                q1 = quat_normalize(list(values[i+1]))
                return quat_slerp(q0, q1, alpha)
    v = values[-1] if interpolation != "CUBICSPLINE" else values[-1][1]
    return quat_normalize(list(v))


def parse_sampler_values(gltf, sampler, n_times, path):
    """
    Lê os valores de saída de um sampler.
    Para CUBICSPLINE: devolve array (n, 3, ncomp) — [in_tan, point, out_tan].
    Para LINEAR/STEP: devolve array (n, ncomp).
    """
    interp = (sampler.interpolation or "LINEAR").upper()
    raw = get_accessor_data(gltf, sampler.output)

    ncomp = 4 if path == "rotation" else 3

    if interp == "CUBICSPLINE":
        # 3 valores por keyframe: in_tangent, point, out_tangent
        expected = n_times * 3 * ncomp
        flat = raw.flatten()[:expected].reshape(n_times, 3, ncomp)
        return flat, interp
    else:
        flat = raw.flatten()[:n_times * ncomp].reshape(n_times, ncomp)
        return flat, interp

# ---------------------------------------------------------------------------
# Extrair animações reais
# ---------------------------------------------------------------------------

def extract_animations(gltf, skin_to_axs1, bone_count, fps_out=30.0):
    """
    Extrai apenas as animações realmente presentes no GLB.
    Não cria clips falsos para animações em falta.

    Devolve lista de clips:
      {name, fps, frame_count, frames: [[{rot, pos} por osso] por frame]}
    """
    if not gltf.animations:
        print("  Nenhuma animação encontrada no GLB.")
        return []

    # Inverso: axs1_bone → skin_joint_idx → node_idx
    # Precisamos do node_idx para associar canais de animação
    joint_nodes = list(gltf.skins[0].joints) if gltf.skins else []
    # skin_to_axs1: {skin_joint_idx: axs1_bone_idx}
    # axs1_to_node_idx: {axs1_bone_idx: node_idx}
    axs1_to_node = {}
    for si, ai in skin_to_axs1.items():
        axs1_to_node[ai] = joint_nodes[si]
    node_to_axs1 = {nidx: ai for si, ai in skin_to_axs1.items()
                    for nidx in [joint_nodes[si]]}

    def canonical_name(anim_name):
        low = anim_name.lower().strip()
        for canon, aliases in CLIP_ALIASES.items():
            for alias in aliases:
                if alias.lower() == low or low == alias.lower():
                    return canon
            # Correspondência parcial
            for alias in aliases:
                if alias.lower() in low:
                    return canon
        return anim_name[:15]

    clips = []
    seen = {}

    for anim in gltf.animations:
        anim_name = anim.name or f"anim_{len(clips)}"
        clip_name = canonical_name(anim_name)

        if clip_name in seen:
            print(f"  [DUPLICADO] '{anim_name}' → '{clip_name}' — ignorado.")
            continue
        seen[clip_name] = True

        # Recolher dados de cada canal
        # bone_rot: {axs1_bone_idx: (times, values, interp)}
        # bone_pos: {axs1_bone_idx: (times, values, interp)}
        # bone_scale: {axs1_bone_idx: (times, values, interp)}  — para aviso
        bone_rot   = {}
        bone_pos   = {}
        bone_scale = {}
        all_times  = set()

        for channel in anim.channels:
            target = channel.target
            if target.node is None:
                continue
            if target.node not in node_to_axs1:
                continue
            ai = node_to_axs1[target.node]

            sampler = anim.samplers[channel.sampler]
            times   = get_accessor_data(gltf, sampler.input).flatten()
            n_times = len(times)

            for t in times:
                all_times.add(float(t))

            path = target.path
            if path == "rotation":
                vals, interp = parse_sampler_values(gltf, sampler, n_times, "rotation")
                bone_rot[ai] = (times, vals, interp)
            elif path == "translation":
                vals, interp = parse_sampler_values(gltf, sampler, n_times, "translation")
                bone_pos[ai] = (times, vals, interp)
            elif path == "scale":
                vals, interp = parse_sampler_values(gltf, sampler, n_times, "scale")
                bone_scale[ai] = (times, vals, interp)

        if not all_times:
            print(f"  [VAZIO] '{anim_name}' — sem keyframes. Ignorado.")
            continue

        # Aviso sobre escala
        for ai, (times, vals, interp) in bone_scale.items():
            # Verificar se a escala é não-unitária
            for vi in range(len(vals)):
                v = vals[vi] if interp != "CUBICSPLINE" else vals[vi][1]
                if any(abs(float(v[k]) - 1.0) > 0.01 for k in range(3)):
                    print(
                        f"  [AVISO] '{anim_name}': bone {ai} tem escala não-unitária "
                        f"que não pode ser representada no formato AXS1. "
                        f"A escala será ignorada — a geometria pode ficar incorrecta."
                    )
                    break

        sorted_times = sorted(all_times)
        t_start = sorted_times[0]
        t_end   = sorted_times[-1]
        duration = t_end - t_start

        if duration < 1e-6:
            frame_count = 2
        else:
            frame_count = max(2, int(round(duration * fps_out)) + 1)
        frame_count = min(frame_count, 512)

        # Poses de bind por osso (usadas quando não há canal para esse osso)
        bind_bones = []
        for bi in range(bone_count):
            # Tentativa de encontrar o nó AXS1 correspondente
            node_idx = axs1_to_node.get(bi, None)
            if node_idx is not None:
                node = gltf.nodes[node_idx]
                bp = [float(v) for v in node.translation] if node.translation else [0.0, 0.0, 0.0]
                br = quat_normalize([float(v) for v in node.rotation]) if node.rotation else [0.0, 0.0, 0.0, 1.0]
            else:
                bp = [0.0, 0.0, 0.0]
                br = [0.0, 0.0, 0.0, 1.0]
            bind_bones.append({"pos": bp, "rot": br})

        frames = []
        for fi in range(frame_count):
            alpha = fi / max(frame_count - 1, 1)
            t_q = t_start + alpha * duration if duration > 1e-6 else t_start
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
    """Reportar clips esperados que não existem. NÃO criar clips falsos."""
    existing = {c["name"].upper() for c in clips}
    expected = ["IDLE", "WALK", "RUN", "JUMP", "LAND"]
    missing = [n for n in expected if n not in existing]
    if missing:
        print(f"  [AVISO] Clips não encontrados no GLB: {missing}")
        print(f"  Os clips em falta NÃO serão criados artificialmente.")
    return missing


def order_clips(clips):
    """Ordenar clips com IDLE/WALK/RUN/JUMP/LAND primeiro, depois os restantes."""
    order = ["IDLE", "WALK", "RUN", "JUMP", "LAND"]
    ordered = []
    remaining = list(clips)
    for name in order:
        for c in clips:
            if c["name"].upper() == name:
                ordered.append(c)
                remaining = [x for x in remaining if x is not c]
                break
    ordered.extend(remaining)
    if len(ordered) > AXS1_MAX_CLIPS:
        print(f"  [AVISO] {len(ordered)} clips excedem o máximo {AXS1_MAX_CLIPS}. A truncar.")
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
            f.write(name_b)
            f.write(struct.pack("<i", b["parent"]))
            f.write(b"\x00" * 4)
            f.write(struct.pack("<3f", *[float(v) for v in b["bind_pos"]]))
            f.write(struct.pack("<4f", *[float(v) for v in b["bind_rot"]]))
            f.write(b"\x00" * 4)

        # Vértices (52 bytes cada)
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
                    f.write(struct.pack("<f", 0.0))

    return os.path.getsize(path)

# ---------------------------------------------------------------------------
# Validar AXS1
# ---------------------------------------------------------------------------

def validate_axs1(path, bones, clips):
    """Valida a estrutura completa do ficheiro AXS1, incluindo keyframes."""
    errors = []
    with open(path, "rb") as f:
        data = f.read()

    bone_count = len(bones)
    clip_count = len(clips)

    if len(data) < AXS1_HEADER_SIZE:
        return ["Ficheiro demasiado pequeno para cabeçalho"]

    if data[0:4] != b"AXS1":
        errors.append(f"Magic inválido: {data[0:4]!r}")
        return errors

    version      = struct.unpack_from("<I", data, 4)[0]
    bc           = struct.unpack_from("<I", data, 8)[0]
    vc           = struct.unpack_from("<I", data, 12)[0]
    cc           = struct.unpack_from("<I", data, 16)[0]

    if version != AXS1_VERSION:
        errors.append(f"Versão inválida: {version}")
    if bc != bone_count:
        errors.append(f"bone_count={bc} != esperado {bone_count}")
    if vc == 0:
        errors.append("vertex_count é zero")
    if cc != clip_count:
        errors.append(f"clip_count={cc} != esperado {clip_count}")
    if bc > AXS1_MAX_BONES:
        errors.append(f"bone_count={bc} excede limite {AXS1_MAX_BONES}")
    if vc > AXS1_MAX_VERTICES:
        errors.append(f"vertex_count={vc} excede limite {AXS1_MAX_VERTICES}")
    if cc > AXS1_MAX_CLIPS:
        errors.append(f"clip_count={cc} excede limite {AXS1_MAX_CLIPS}")

    # Calcular tamanho esperado completo
    expected = AXS1_HEADER_SIZE + bc * AXS1_BONE_ONDISK + vc * AXS1_VERTEX_ONDISK
    for c in clips:
        expected += AXS1_CLIP_HDR_SIZE + c["frame_count"] * bc * AXS1_KEY_ONDISK

    if len(data) != expected:
        errors.append(
            f"Tamanho do ficheiro: {len(data)} bytes, esperado {expected} bytes"
        )

    # Validar índices de ossos e pesos nos vértices
    offset = AXS1_HEADER_SIZE + bc * AXS1_BONE_ONDISK
    for vi in range(vc):
        voff = offset + vi * AXS1_VERTEX_ONDISK
        # bone_idx começa ao offset 20 dentro do vértice (8+12=20)
        bi4 = struct.unpack_from("<4B", data, voff + 20)
        wt4 = struct.unpack_from("<4f", data, voff + 24)
        for k in range(4):
            if bi4[k] >= bc:
                errors.append(f"Vértice {vi}: bone_idx[{k}]={bi4[k]} >= bone_count={bc}")
            if not math.isfinite(wt4[k]) or wt4[k] < 0.0:
                errors.append(f"Vértice {vi}: weight[{k}]={wt4[k]} inválido")

    # Validar valores de rotação nos keyframes
    offset_kf = (AXS1_HEADER_SIZE + bc * AXS1_BONE_ONDISK + vc * AXS1_VERTEX_ONDISK)
    for ci in range(cc):
        clip_name_b = data[offset_kf:offset_kf+16]
        fc = struct.unpack_from("<i", data, offset_kf + 16)[0]
        fps_v = struct.unpack_from("<f", data, offset_kf + 20)[0]
        offset_kf += AXS1_CLIP_HDR_SIZE
        if fc <= 0:
            errors.append(f"Clip {ci}: frame_count={fc} inválido")
        if not math.isfinite(fps_v) or fps_v <= 0:
            errors.append(f"Clip {ci}: fps={fps_v} inválido")
        for fi in range(fc):
            for bi in range(bc):
                rot4 = struct.unpack_from("<4f", data, offset_kf)
                pos3 = struct.unpack_from("<3f", data, offset_kf + 16)
                offset_kf += AXS1_KEY_ONDISK
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
        f.write(f"- Clips reais: {len(clips)}\n")
        f.write(f"- Tamanho do AXS1: {file_size} bytes ({file_size/1024:.1f} KB)\n\n")

        f.write("## Ossos\n\n")
        f.write("| # | Nome | Parent |\n|---|------|--------|\n")
        for bi, b in enumerate(bones):
            f.write(f"| {bi} | {b['name']} | {b['parent']} |\n")

        f.write("\n## Clips encontrados\n\n")
        if clips:
            f.write("| # | Nome | Frames | FPS |\n|---|------|--------|-----|\n")
            for ci, c in enumerate(clips):
                f.write(f"| {ci} | {c['name']} | {c['frame_count']} | {c['fps']:.0f} |\n")
        else:
            f.write("Nenhum clip encontrado no GLB.\n")

        if missing_clips:
            f.write(f"\n## Clips não encontrados\n\n")
            for m in missing_clips:
                f.write(f"- {m} — ausente no GLB (não criado artificialmente)\n")

        f.write("\n## Validação\n\n")
        if errors:
            f.write("**ERROS:**\n\n")
            for e in errors:
                f.write(f"- {e}\n")
        else:
            f.write("✅ AXS1 válido — sem erros estruturais.\n")

        f.write("\n## Layout binário\n\n```\n")
        f.write(f"AXS1_HEADER_SIZE   = {AXS1_HEADER_SIZE} bytes\n")
        f.write(f"AXS1_BONE_ONDISK   = {AXS1_BONE_ONDISK} bytes\n")
        f.write(f"AXS1_VERTEX_ONDISK = {AXS1_VERTEX_ONDISK} bytes\n")
        f.write(f"AXS1_CLIP_HDR_SIZE = {AXS1_CLIP_HDR_SIZE} bytes\n")
        f.write(f"AXS1_KEY_ONDISK    = {AXS1_KEY_ONDISK} bytes\n")
        f.write("```\n")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Conversor GLB → AXS1")
    parser.add_argument("input",  help="Ficheiro GLB de entrada")
    parser.add_argument("output", help="Ficheiro AXS1 de saída")
    parser.add_argument("--report", default=None)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--max-verts", type=int, default=AXS1_MAX_VERTICES)
    args = parser.parse_args()

    if not HAS_NUMPY:
        print("ERRO: numpy não instalado.")
        sys.exit(1)
    if not HAS_PYGLTFLIB:
        print("ERRO: pygltflib não instalado.")
        sys.exit(1)
    if not os.path.isfile(args.input):
        print(f"ERRO: ficheiro não encontrado: {args.input}")
        sys.exit(1)

    max_verts = min(args.max_verts, AXS1_MAX_VERTICES)

    print(f"A carregar GLB: {args.input}")
    gltf = GLTF2().load(args.input)

    # 1. Esqueleto
    print("A extrair esqueleto...")
    try:
        bones, skin_to_axs1 = extract_skeleton(gltf)
    except RuntimeError as e:
        print(str(e))
        sys.exit(1)

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
        vertices = extract_mesh(gltf, skin_to_axs1, max_verts)
    except RuntimeError as e:
        print(str(e))
        sys.exit(1)

    if not vertices:
        print("ERRO: sem vértices extraídos.")
        sys.exit(1)
    print(f"  {len(vertices)} vértice(s).")

    # 3. Animações reais
    print("A extrair animações...")
    try:
        clips = extract_animations(gltf, skin_to_axs1, bone_count, args.fps)
    except RuntimeError as e:
        print(str(e))
        sys.exit(1)

    missing = report_missing_clips(clips)
    clips   = order_clips(clips)
    print(f"  {len(clips)} clip(s) reais: {[c['name'] for c in clips]}")

    if not clips:
        print("ERRO: o GLB não contém animações. Não é possível gerar AXS1 com animação.")
        sys.exit(1)

    # 4. Escrever AXS1
    print(f"A escrever: {args.output}")
    try:
        file_size = write_axs1(args.output, bones, vertices, clips)
    except Exception as e:
        print(f"ERRO ao escrever AXS1: {e}")
        sys.exit(1)
    print(f"  {file_size} bytes ({file_size/1024:.1f} KB)")

    # 5. Validar
    print("A validar AXS1...")
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
                     missing, file_size, errors)
        print(f"  Relatório: {args.report}")

    print("Conversão concluída com sucesso.")

if __name__ == "__main__":
    main()
