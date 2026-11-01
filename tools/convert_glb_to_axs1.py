#!/usr/bin/env python3
"""
convert_glb_to_axs1.py — RPG Axel Digital
Converte um ficheiro GLB (GLTF binário) para o formato AXS1 do motor.

Utilização:
    python3 convert_glb_to_axs1.py <input.glb> <output.axs> [--report <report.md>]

Dependências (instaladas pelo workflow):
    pip install pygltflib numpy

Formato AXS1 (especificação definitiva — deve coincidir com p3d_anim.h):

  [Cabeçalho — 32 bytes]
    magic[4]       "AXS1"
    version        uint32 = 1
    bone_count     uint32
    vertex_count   uint32
    clip_count     uint32
    reserved[3]    uint32×3 (zeros)

  [Ossos — bone_count × 56 bytes]  (AXS1_BONE_ONDISK = 56)
    name[16]       char×16
    parent_index   int32
    pad[4]         zeros
    bind_pos[3]    float×3
    bind_rot[4]    float×4 (quaternião xyzw)
    pad_end[4]     zeros

  [Vértices — vertex_count × 52 bytes]  (AXS1_VERTEX_ONDISK = 52)
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
import json

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
# Limites (devem coincidir com p3d_anim.h)
# ---------------------------------------------------------------------------
AXS1_MAX_BONES    = 24
AXS1_MAX_CLIPS    = 8
AXS1_MAX_VERTICES = 65536
AXS1_BONE_WEIGHTS = 4
AXS1_VERSION      = 1

AXS1_HEADER_SIZE   = 32
AXS1_BONE_ONDISK   = 56
AXS1_VERTEX_ONDISK = 52
AXS1_CLIP_HDR_SIZE = 24
AXS1_KEY_ONDISK    = 32

# Clips esperados (em ordem de índice)
CLIP_NAMES = ["IDLE", "WALK", "RUN", "JUMP", "LAND"]

# Nomes alternativos nos GLB Quaternius
CLIP_ALIASES = {
    "IDLE":  ["idle", "Idle", "IDLE", "stand", "Stand"],
    "WALK":  ["walk", "Walk", "WALK", "walking", "Walking"],
    "RUN":   ["run", "Run", "RUN", "running", "Running"],
    "JUMP":  ["jump", "Jump", "JUMP", "jumping", "Jumping"],
    "LAND":  ["land", "Land", "LAND", "landing", "Landing"],
}

# ---------------------------------------------------------------------------
# Quaternião utilitário
# ---------------------------------------------------------------------------

def quat_normalize(q):
    x, y, z, w = q
    n = math.sqrt(x*x + y*y + z*z + w*w)
    if n < 1e-8:
        return (0.0, 0.0, 0.0, 1.0)
    return (x/n, y/n, z/n, w/n)

def quat_identity():
    return (0.0, 0.0, 0.0, 1.0)

# ---------------------------------------------------------------------------
# Leitura de dados de buffer GLTF
# ---------------------------------------------------------------------------

def get_accessor_data(gltf, accessor_idx):
    """Devolve um array numpy ou lista de valores do accessor."""
    if not HAS_NUMPY:
        raise RuntimeError("numpy é necessário")
    acc = gltf.accessors[accessor_idx]
    bv  = gltf.bufferViews[acc.bufferView]
    buf = gltf.buffers[bv.buffer]

    # Obter bytes do buffer
    import base64
    if buf.uri and buf.uri.startswith("data:"):
        header, data = buf.uri.split(",", 1)
        raw = base64.b64decode(data)
    else:
        # GLB: buffer 0 está em gltf.binary_blob()
        raw = bytes(gltf.binary_blob())

    offset = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    count  = acc.count

    COMPONENT_TYPES = {
        5120: ('b', 1), 5121: ('B', 1),
        5122: ('h', 2), 5123: ('H', 2),
        5125: ('I', 4), 5126: ('f', 4),
    }
    ctype, csize = COMPONENT_TYPES[acc.componentType]

    TYPE_COUNTS = {
        "SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
        "MAT2": 4,   "MAT3": 9, "MAT4": 16,
    }
    ncomp = TYPE_COUNTS[acc.type]

    stride = bv.byteStride if bv.byteStride else csize * ncomp
    result = []
    for i in range(count):
        base = offset + i * stride
        vals = struct.unpack_from(f"{ncomp}{ctype}", raw, base)
        result.append(vals if ncomp > 1 else vals[0])

    if ncomp == 1:
        return np.array(result)
    return np.array(result)

# ---------------------------------------------------------------------------
# Construir esqueleto a partir do skin GLTF
# ---------------------------------------------------------------------------

def extract_skeleton(gltf):
    """
    Devolve (bones, node_to_bone_idx) onde:
      bones = lista de dicts: {name, parent, bind_pos, bind_rot}
      node_to_bone_idx = {node_idx: bone_idx}
    """
    if not gltf.skins:
        return [], {}

    skin = gltf.skins[0]
    joint_nodes = skin.joints  # lista de índices de nós

    # Limite
    if len(joint_nodes) > AXS1_MAX_BONES:
        print(f"[AVISO] {len(joint_nodes)} ossos excedem o limite {AXS1_MAX_BONES}. A truncar.")
        joint_nodes = joint_nodes[:AXS1_MAX_BONES]

    node_to_bone = {node_idx: bi for bi, node_idx in enumerate(joint_nodes)}

    # Inverse bind matrices (column-major float4×4 per joint)
    ibm = None
    if skin.inverseBindMatrices is not None and HAS_NUMPY:
        ibm_data = get_accessor_data(gltf, skin.inverseBindMatrices)
        ibm = ibm_data.reshape(-1, 16)

    # Construir hierarquia
    bones = []
    for bi, node_idx in enumerate(joint_nodes):
        node = gltf.nodes[node_idx]
        name = (node.name or f"bone_{bi}")[:15]

        # Posição e rotação de bind local
        if node.translation:
            bp = list(node.translation)
        else:
            bp = [0.0, 0.0, 0.0]

        if node.rotation:
            # GLTF rotation: [x, y, z, w]
            br = list(node.rotation)
        else:
            br = [0.0, 0.0, 0.0, 1.0]
        br = list(quat_normalize(br))

        # Parent: procurar qual nó tem este nó como filho
        parent_bone = -1
        for other_node_idx in joint_nodes:
            other_node = gltf.nodes[other_node_idx]
            if other_node.children and node_idx in other_node.children:
                if other_node_idx in node_to_bone:
                    parent_bone = node_to_bone[other_node_idx]
                break

        bones.append({
            "name": name,
            "parent": parent_bone,
            "bind_pos": bp,
            "bind_rot": br,   # xyzw
        })

    return bones, node_to_bone

# ---------------------------------------------------------------------------
# Construir geometria com pesos de ossos
# ---------------------------------------------------------------------------

def extract_mesh(gltf, node_to_bone, max_verts=AXS1_MAX_VERTICES):
    """
    Devolve lista de vértices: cada um é um dict com
    {u, v, nx, ny, nz, px, py, pz, bone_idx[4], weight[4]}
    """
    vertices_out = []

    for mesh in gltf.meshes:
        for prim in mesh.primitives:
            # Posições
            if prim.attributes.POSITION is None:
                continue
            pos = get_accessor_data(gltf, prim.attributes.POSITION)

            # UVs
            uvs = None
            texcoord_attr = getattr(prim.attributes, "TEXCOORD_0", None)
            if texcoord_attr is not None:
                uvs = get_accessor_data(gltf, texcoord_attr)

            # Normais
            nrms = None
            if prim.attributes.NORMAL is not None:
                nrms = get_accessor_data(gltf, prim.attributes.NORMAL)

            # Joints e weights
            joints_acc  = getattr(prim.attributes, "JOINTS_0",  None)
            weights_acc = getattr(prim.attributes, "WEIGHTS_0", None)
            joints  = get_accessor_data(gltf, joints_acc)  if joints_acc  is not None else None
            weights = get_accessor_data(gltf, weights_acc) if weights_acc is not None else None

            # Índices
            if prim.indices is not None:
                idx_data = get_accessor_data(gltf, prim.indices).astype(int)
            else:
                idx_data = list(range(len(pos)))

            n_src = len(pos)

            for i in idx_data:
                if len(vertices_out) >= max_verts:
                    break
                i = int(i)
                if i >= n_src:
                    continue

                px_, py_, pz_ = float(pos[i][0]), float(pos[i][1]), float(pos[i][2])
                u_  = float(uvs[i][0])  if uvs  is not None and i < len(uvs)  else 0.0
                v_  = float(uvs[i][1])  if uvs  is not None and i < len(uvs)  else 0.0
                nx_ = float(nrms[i][0]) if nrms is not None and i < len(nrms) else 0.0
                ny_ = float(nrms[i][1]) if nrms is not None and i < len(nrms) else 1.0
                nz_ = float(nrms[i][2]) if nrms is not None and i < len(nrms) else 0.0

                bi4 = [0, 0, 0, 0]
                wt4 = [1.0, 0.0, 0.0, 0.0]

                if joints is not None and weights is not None and i < len(joints):
                    raw_j = joints[i]
                    raw_w = weights[i]
                    wsum  = sum(float(raw_w[k]) for k in range(4))
                    for k in range(4):
                        gltf_joint = int(raw_j[k])
                        bi4[k] = node_to_bone.get(gltf_joint, 0)
                        wt4[k] = float(raw_w[k]) / wsum if wsum > 1e-6 else (1.0 if k == 0 else 0.0)

                vertices_out.append({
                    "u": u_, "v": v_,
                    "nx": nx_, "ny": ny_, "nz": nz_,
                    "px": px_, "py": py_, "pz": pz_,
                    "bone_idx": bi4,
                    "weight": wt4,
                })

    return vertices_out

# ---------------------------------------------------------------------------
# Extrair animações
# ---------------------------------------------------------------------------

def extract_animations(gltf, node_to_bone, bone_count, fps_out=30.0):
    """
    Devolve lista de clips, cada um:
      {name, fps, frames: [[{rot, pos} para cada osso] para cada frame]}
    """
    if not gltf.animations:
        return []

    clips = []

    # Construir mapa canonical: nome do clip → índice CLIP_NAMES
    def match_clip_name(anim_name):
        low = anim_name.lower()
        for canonical, aliases in CLIP_ALIASES.items():
            for alias in aliases:
                if alias.lower() == low or alias.lower() in low:
                    return canonical
        return None

    # Processar cada animação GLTF
    seen_canonicals = {}
    fallback_idx    = 0

    for anim in gltf.animations:
        anim_name = anim.name or f"anim_{fallback_idx}"
        canonical = match_clip_name(anim_name)

        if canonical is None:
            # Usar como nome direto se couber
            canonical = anim_name[:15]

        if canonical in seen_canonicals:
            continue  # ignorar duplicado
        seen_canonicals[canonical] = True

        # Para cada canal, obter tempo e valores
        # channel → sampler → input (tempo) / output (valores)
        bone_rot_keys  = {}  # bone_idx → {time: rot}
        bone_pos_keys  = {}  # bone_idx → {time: pos}
        all_times      = set()

        for channel in anim.channels:
            target = channel.target
            if target.node is None:
                continue
            if target.node not in node_to_bone:
                continue
            bi = node_to_bone[target.node]

            sampler = anim.samplers[channel.sampler]
            times   = get_accessor_data(gltf, sampler.input)
            values  = get_accessor_data(gltf, sampler.output)

            for t in times:
                all_times.add(float(t))

            if target.path == "rotation":
                if bi not in bone_rot_keys:
                    bone_rot_keys[bi] = {}
                for ti, t in enumerate(times):
                    q = values[ti]
                    bone_rot_keys[bi][float(t)] = list(quat_normalize([
                        float(q[0]), float(q[1]), float(q[2]), float(q[3])
                    ]))

            elif target.path == "translation":
                if bi not in bone_pos_keys:
                    bone_pos_keys[bi] = {}
                for ti, t in enumerate(times):
                    p = values[ti]
                    bone_pos_keys[bi][float(t)] = [
                        float(p[0]), float(p[1]), float(p[2])
                    ]

        if not all_times:
            continue

        sorted_times = sorted(all_times)
        duration     = sorted_times[-1] - sorted_times[0]

        if duration < 1e-6:
            # Animação de pose única: criar 2 frames idênticos
            frame_count = 2
        else:
            frame_count = max(2, int(round(duration * fps_out)) + 1)

        frame_count = min(frame_count, 256)  # limite razoável

        def lerp_values(keys_dict, t_query, default):
            """Interpolar linearmente num dicionário {time: valor}."""
            if not keys_dict:
                return default
            times_k = sorted(keys_dict.keys())
            if t_query <= times_k[0]:
                return keys_dict[times_k[0]]
            if t_query >= times_k[-1]:
                return keys_dict[times_k[-1]]
            for i in range(len(times_k) - 1):
                t0, t1 = times_k[i], times_k[i+1]
                if t0 <= t_query <= t1:
                    alpha = (t_query - t0) / (t1 - t0) if (t1 - t0) > 1e-9 else 0.0
                    v0, v1 = keys_dict[t0], keys_dict[t1]
                    return [v0[j] + alpha * (v1[j] - v0[j]) for j in range(len(v0))]
            return keys_dict[times_k[-1]]

        frames = []
        t_start = sorted_times[0]
        t_end   = sorted_times[-1]

        for fi in range(frame_count):
            alpha = fi / max(frame_count - 1, 1)
            t_q   = t_start + alpha * (t_end - t_start)
            frame_keys = []
            for bi in range(bone_count):
                rot = lerp_values(bone_rot_keys.get(bi, {}), t_q,
                                  [0.0, 0.0, 0.0, 1.0])
                pos = lerp_values(bone_pos_keys.get(bi, {}), t_q,
                                  [0.0, 0.0, 0.0])
                rot = list(quat_normalize(rot))
                frame_keys.append({"rot": rot, "pos": pos})
            frames.append(frame_keys)

        clips.append({
            "name":        canonical[:15],
            "fps":         fps_out,
            "frame_count": frame_count,
            "frames":      frames,
        })

        fallback_idx += 1

    return clips

# ---------------------------------------------------------------------------
# Preencher clips em falta com pose de bind
# ---------------------------------------------------------------------------

def fill_missing_clips(clips, bones, bone_count):
    """
    Garantir que existem clips para IDLE, WALK, RUN, JUMP, LAND.
    Clips em falta são criados com a pose de bind (pose neutra).
    """
    existing_names = {c["name"].upper() for c in clips}

    # Pose de bind: rot=identity, pos=bind_pos do osso
    def make_bind_frame():
        frame = []
        for bi in range(bone_count):
            b = bones[bi]
            frame.append({
                "rot": [0.0, 0.0, 0.0, 1.0],
                "pos": list(b["bind_pos"]),
            })
        return frame

    for cname in CLIP_NAMES:
        if cname not in existing_names:
            f = make_bind_frame()
            clips.append({
                "name":        cname[:15],
                "fps":         30.0,
                "frame_count": 2,
                "frames":      [f, f],
            })
            print(f"[AVISO] Clip '{cname}' não encontrado no GLB. "
                  f"Criado com pose de bind (2 frames).")

    # Garantir ordem correta: IDLE WALK RUN JUMP LAND primeiro
    ordered = []
    for cname in CLIP_NAMES:
        for c in clips:
            if c["name"].upper() == cname:
                ordered.append(c)
                break

    # Adicionar restantes (fora da lista padrão)
    for c in clips:
        if c["name"].upper() not in [n for n in CLIP_NAMES]:
            ordered.append(c)

    # Limitar ao máximo
    return ordered[:AXS1_MAX_CLIPS]

# ---------------------------------------------------------------------------
# Escrever AXS1
# ---------------------------------------------------------------------------

def write_axs1(path, bones, vertices, clips):
    bone_count   = len(bones)
    vertex_count = len(vertices)
    clip_count   = len(clips)

    with open(path, "wb") as f:
        # --- Cabeçalho ---
        f.write(b"AXS1")
        f.write(struct.pack("<I", AXS1_VERSION))
        f.write(struct.pack("<I", bone_count))
        f.write(struct.pack("<I", vertex_count))
        f.write(struct.pack("<I", clip_count))
        f.write(struct.pack("<III", 0, 0, 0))   # reserved[3]
        # Total: 32 bytes

        # --- Ossos (56 bytes cada) ---
        for b in bones:
            name_bytes = b["name"].encode("ascii", errors="replace")[:15].ljust(16, b"\x00")
            f.write(name_bytes)                                  # 16B
            f.write(struct.pack("<i", b["parent"]))             # 4B (int32)
            f.write(struct.pack("<4B", 0, 0, 0, 0))            # 4B pad
            f.write(struct.pack("<3f", *b["bind_pos"]))         # 12B
            f.write(struct.pack("<4f", *b["bind_rot"]))         # 16B (xyzw)
            f.write(struct.pack("<4B", 0, 0, 0, 0))            # 4B pad_end
            # Total: 56B

        # --- Vértices (52 bytes cada) ---
        for v in vertices:
            f.write(struct.pack("<2f", v["u"], v["v"]))                   # 8B
            f.write(struct.pack("<3f", v["nx"], v["ny"], v["nz"]))        # 12B
            f.write(struct.pack("<3f", v["px"], v["py"], v["pz"]))        # 12B
            f.write(struct.pack("<4B", *[b & 0xFF for b in v["bone_idx"]]))  # 4B
            f.write(struct.pack("<4f", *v["weight"]))                     # 16B
            # Total: 52B

        # --- Clips ---
        for c in clips:
            name_bytes = c["name"].encode("ascii", errors="replace")[:15].ljust(16, b"\x00")
            f.write(name_bytes)                                    # 16B
            f.write(struct.pack("<i", c["frame_count"]))          # 4B
            f.write(struct.pack("<f", c["fps"]))                  # 4B
            # Total cabeçalho: 24B

            for frame in c["frames"]:
                for key in frame:
                    f.write(struct.pack("<4f", *key["rot"]))      # 16B
                    f.write(struct.pack("<3f", *key["pos"]))      # 12B
                    f.write(struct.pack("<f",  0.0))              # 4B pad
                    # Total: 32B

    file_size = os.path.getsize(path)
    return file_size

# ---------------------------------------------------------------------------
# Validar AXS1 escrito
# ---------------------------------------------------------------------------

def validate_axs1(path):
    """Relê o ficheiro e verifica a estrutura básica."""
    errors = []
    with open(path, "rb") as f:
        data = f.read()

    if len(data) < AXS1_HEADER_SIZE:
        return ["Ficheiro demasiado pequeno para conter cabeçalho"]

    magic = data[0:4]
    if magic != b"AXS1":
        errors.append(f"Magic inválido: {magic!r}")
        return errors

    version      = struct.unpack_from("<I", data, 4)[0]
    bone_count   = struct.unpack_from("<I", data, 8)[0]
    vertex_count = struct.unpack_from("<I", data, 12)[0]
    clip_count   = struct.unpack_from("<I", data, 16)[0]

    if version != AXS1_VERSION:
        errors.append(f"Versão inválida: {version}")
    if bone_count == 0 or bone_count > AXS1_MAX_BONES:
        errors.append(f"bone_count inválido: {bone_count}")
    if vertex_count == 0:
        errors.append("vertex_count é zero")
    if clip_count == 0 or clip_count > AXS1_MAX_CLIPS:
        errors.append(f"clip_count inválido: {clip_count}")

    expected_min = (AXS1_HEADER_SIZE
                    + bone_count   * AXS1_BONE_ONDISK
                    + vertex_count * AXS1_VERTEX_ONDISK
                    + clip_count   * AXS1_CLIP_HDR_SIZE)
    if len(data) < expected_min:
        errors.append(f"Ficheiro demasiado pequeno: {len(data)} < {expected_min}")

    return errors

# ---------------------------------------------------------------------------
# Gerar relatório
# ---------------------------------------------------------------------------

def write_report(path, glb_path, bones, vertices, clips, file_size, errors):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Relatório de Conversão AXS1\n\n")
        f.write(f"- **Origem**: `{glb_path}`\n")
        f.write(f"- **Licença**: CC0 1.0 Universal (Quaternius Universal Base Characters)\n")
        f.write(f"- **Formato de saída**: AXS1 versão {AXS1_VERSION}\n\n")

        f.write("## Dados do modelo\n\n")
        f.write(f"- Vértices: {len(vertices)}\n")
        f.write(f"- Ossos: {len(bones)}\n")
        f.write(f"- Clips: {len(clips)}\n")
        f.write(f"- Tamanho do ficheiro AXS1: {file_size} bytes "
                f"({file_size/1024:.1f} KB)\n\n")

        f.write("## Ossos\n\n")
        f.write("| # | Nome | Parent |\n|---|------|--------|\n")
        for bi, b in enumerate(bones):
            f.write(f"| {bi} | {b['name']} | {b['parent']} |\n")

        f.write("\n## Clips\n\n")
        f.write("| # | Nome | Frames | FPS |\n|---|------|--------|-----|\n")
        for ci, c in enumerate(clips):
            f.write(f"| {ci} | {c['name']} | {c['frame_count']} | {c['fps']:.0f} |\n")

        f.write("\n## Validação\n\n")
        if errors:
            f.write("**ERROS ENCONTRADOS:**\n\n")
            for e in errors:
                f.write(f"- {e}\n")
        else:
            f.write("✅ Ficheiro AXS1 válido — sem erros estruturais.\n")

        f.write("\n## Layout binário utilizado\n\n")
        f.write("```\n")
        f.write(f"AXS1_BONE_ONDISK   = {AXS1_BONE_ONDISK} bytes\n")
        f.write(f"AXS1_VERTEX_ONDISK = {AXS1_VERTEX_ONDISK} bytes\n")
        f.write(f"AXS1_KEY_ONDISK    = {AXS1_KEY_ONDISK} bytes\n")
        f.write("```\n")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Conversor GLB → AXS1")
    parser.add_argument("input",  help="Ficheiro GLB de entrada")
    parser.add_argument("output", help="Ficheiro AXS1 de saída")
    parser.add_argument("--report", default=None,
                        help="Ficheiro de relatório Markdown (opcional)")
    parser.add_argument("--fps", type=float, default=30.0,
                        help="FPS de saída para as animações (padrão: 30)")
    parser.add_argument("--max-verts", type=int, default=8192,
                        help=f"Máximo de vértices (padrão: 8192, máx: {AXS1_MAX_VERTICES})")
    args = parser.parse_args()

    max_verts = min(args.max_verts, AXS1_MAX_VERTICES)

    if not HAS_NUMPY:
        print("ERRO: numpy não está instalado. Instalar com: pip install numpy")
        sys.exit(1)
    if not HAS_PYGLTFLIB:
        print("ERRO: pygltflib não está instalado. Instalar com: pip install pygltflib")
        sys.exit(1)

    if not os.path.isfile(args.input):
        print(f"ERRO: ficheiro não encontrado: {args.input}")
        sys.exit(1)

    print(f"A carregar GLB: {args.input}")
    gltf = GLTF2().load(args.input)

    # Esqueleto
    print("A extrair esqueleto...")
    bones, node_to_bone = extract_skeleton(gltf)
    if not bones:
        print("[AVISO] Sem esqueleto no GLB. A criar osso raiz sintético.")
        bones = [{
            "name": "root",
            "parent": -1,
            "bind_pos": [0.0, 0.0, 0.0],
            "bind_rot": [0.0, 0.0, 0.0, 1.0],
        }]
        node_to_bone = {}

    bone_count = len(bones)
    print(f"  {bone_count} ossos encontrados.")

    # Geometria
    print("A extrair geometria...")
    vertices = extract_mesh(gltf, node_to_bone, max_verts)
    if not vertices:
        print("ERRO: sem vértices extraídos do GLB.")
        sys.exit(1)
    print(f"  {len(vertices)} vértices extraídos.")

    # Animações
    print("A extrair animações...")
    clips = extract_animations(gltf, node_to_bone, bone_count, args.fps)
    print(f"  {len(clips)} animação(ões) encontradas: "
          f"{[c['name'] for c in clips]}")

    # Preencher clips em falta
    clips = fill_missing_clips(clips, bones, bone_count)
    print(f"  {len(clips)} clips no total após preenchimento.")

    # Escrever AXS1
    print(f"A escrever AXS1: {args.output}")
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    file_size = write_axs1(args.output, bones, vertices, clips)
    print(f"  Tamanho: {file_size} bytes ({file_size/1024:.1f} KB)")

    # Validar
    errors = validate_axs1(args.output)
    if errors:
        print("ERROS DE VALIDAÇÃO:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("  Validação: OK")

    # Relatório
    if args.report:
        write_report(args.report, args.input, bones, vertices, clips,
                     file_size, errors)
        print(f"Relatório: {args.report}")

    print("Conversão concluída.")

if __name__ == "__main__":
    main()
