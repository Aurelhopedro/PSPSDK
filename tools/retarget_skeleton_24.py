#!/usr/bin/env python3
"""
retarget_skeleton_24.py — RPG Axel Digital
Reduz o esqueleto Quaternius Universal Base Characters (63 ossos) para
exactamente 24 ossos compatíveis com o limite AXS1_MAX_BONES do runtime PSP.

Estratégia:
  1. Definir os 24 ossos alvo por nome canónico (Quaternius naming).
  2. Para cada osso eliminado, transferir os seus pesos para o pai
     conservado mais próximo na hierarquia.
  3. Re-normalizar pesos por vértice.
  4. Recalcular inverseBindMatrices para o novo esqueleto.
  5. Gravar GLB novo com skin, mesh e animações actualizados.

Utilização:
    python3 tools/retarget_skeleton_24.py <input.glb> <output.glb>

Dependências:
    pip install pygltflib numpy
"""

import sys
import os
import struct
import math
import copy
import base64
import argparse

try:
    import numpy as np
except ImportError:
    print("ERRO: numpy não instalado."); sys.exit(1)

try:
    from pygltflib import GLTF2, BufferView, Accessor, Buffer
    from pygltflib.utils import ImageFormat
except ImportError:
    print("ERRO: pygltflib não instalado."); sys.exit(1)

# ---------------------------------------------------------------------------
# Ossos alvo — 24 ossos para animação humana básica na PSP
# Os nomes correspondem ao esqueleto Quaternius Universal Base Characters.
# Cada entrada: (nome_canónico_axs1, [variantes_de_nome_quaternius])
# ---------------------------------------------------------------------------

TARGET_BONES_DEF = [
    # Raiz e coluna
    ("Root",       ["Root", "root", "ROOT"]),
    ("Hips",       ["Hips", "hips", "Pelvis", "pelvis"]),
    ("Spine",      ["Spine", "spine", "Spine1", "spine1", "Spine_01"]),
    ("Chest",      ["Chest", "chest", "Spine2", "spine2", "Spine_02",
                    "Spine3", "spine3", "Spine_03"]),
    ("Neck",       ["Neck", "neck", "Neck1", "neck1", "Neck_01"]),
    ("Head",       ["Head", "head"]),
    # Braço esquerdo
    ("ShoulderL",  ["LeftShoulder", "Shoulder.L", "shoulder_l",
                    "Clavicle_L", "clavicle_l", "ClavicleLeft",
                    "UpperArm.L"]),
    ("UpperArmL",  ["LeftArm", "UpperArm.L", "upper_arm_l",
                    "UpperArm_L", "Arm_L"]),
    ("LowerArmL",  ["LeftForeArm", "LowerArm.L", "lower_arm_l",
                    "ForeArm_L", "forearm_l", "Elbow.L"]),
    ("HandL",      ["LeftHand", "Hand.L", "hand_l", "Hand_L"]),
    # Braço direito
    ("ShoulderR",  ["RightShoulder", "Shoulder.R", "shoulder_r",
                    "Clavicle_R", "clavicle_r", "ClavicleRight",
                    "UpperArm.R"]),
    ("UpperArmR",  ["RightArm", "UpperArm.R", "upper_arm_r",
                    "UpperArm_R", "Arm_R"]),
    ("LowerArmR",  ["RightForeArm", "LowerArm.R", "lower_arm_r",
                    "ForeArm_R", "forearm_r", "Elbow.R"]),
    ("HandR",      ["RightHand", "Hand.R", "hand_r", "Hand_R"]),
    # Perna esquerda
    ("UpperLegL",  ["LeftUpLeg", "UpperLeg.L", "upper_leg_l",
                    "Thigh_L", "thigh_l", "UpperLeg_L"]),
    ("LowerLegL",  ["LeftLeg", "LowerLeg.L", "lower_leg_l",
                    "Shin_L", "shin_l", "LowerLeg_L", "Knee.L"]),
    ("FootL",      ["LeftFoot", "Foot.L", "foot_l", "Foot_L"]),
    ("ToeL",       ["LeftToeBase", "Toe.L", "toe_l", "Toe_L",
                    "ToeBase_L", "Ball.L"]),
    # Perna direita
    ("UpperLegR",  ["RightUpLeg", "UpperLeg.R", "upper_leg_r",
                    "Thigh_R", "thigh_r", "UpperLeg_R"]),
    ("LowerLegR",  ["RightLeg", "LowerLeg.R", "lower_leg_r",
                    "Shin_R", "shin_r", "LowerLeg_R", "Knee.R"]),
    ("FootR",      ["RightFoot", "Foot.R", "foot_r", "Foot_R"]),
    ("ToeR",       ["RightToeBase", "Toe.R", "toe_r", "Toe_R",
                    "ToeBase_R", "Ball.R"]),
    # Dois slots extras — usados para ombros/clavículas se não mapeados acima,
    # ou para spine adicional se o modelo não tiver clavículas separadas
    ("SpineUpper", ["Spine4", "spine4", "Spine_04", "Chest2",
                    "chest2", "UpperChest", "upper_chest"]),
    ("SpineLower", ["SpineLower", "spine_lower", "Spine0", "spine0",
                    "Spine_00", "HipSpine", "Pelvis2"]),
]

# Hierarquia alvo (índices na lista TARGET_BONES_DEF acima)
# parent_axs1[i] = índice do pai de TARGET_BONES_DEF[i], ou -1 para raiz
TARGET_PARENT = {
    "Root":       -1,
    "Hips":       "Root",
    "Spine":      "Hips",
    "SpineLower": "Hips",
    "Chest":      "Spine",
    "SpineUpper": "Chest",
    "Neck":       "Chest",
    "Head":       "Neck",
    "ShoulderL":  "Chest",
    "UpperArmL":  "ShoulderL",
    "LowerArmL":  "UpperArmL",
    "HandL":      "LowerArmL",
    "ShoulderR":  "Chest",
    "UpperArmR":  "ShoulderR",
    "LowerArmR":  "UpperArmR",
    "HandR":      "LowerArmR",
    "UpperLegL":  "Hips",
    "LowerLegL":  "UpperLegL",
    "FootL":      "LowerLegL",
    "ToeL":       "FootL",
    "UpperLegR":  "Hips",
    "LowerLegR":  "UpperLegR",
    "FootR":      "LowerLegR",
    "ToeR":       "FootR",
}

# ---------------------------------------------------------------------------
# Auxiliares de leitura/escrita de accessors
# ---------------------------------------------------------------------------

COMPONENT_TYPES = {
    5120: ('b', 1, np.int8),
    5121: ('B', 1, np.uint8),
    5122: ('h', 2, np.int16),
    5123: ('H', 2, np.uint16),
    5125: ('I', 4, np.uint32),
    5126: ('f', 4, np.float32),
}
TYPE_COUNTS = {
    "SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
    "MAT2": 4, "MAT3": 9, "MAT4": 16,
}


def read_accessor(gltf, raw_bin, accessor_idx):
    """Lê um accessor e devolve numpy array shape (count, ncomp) ou (count,) para SCALAR."""
    acc = gltf.accessors[accessor_idx]
    bv  = gltf.bufferViews[acc.bufferView]

    bv_offset  = bv.byteOffset  or 0
    acc_offset = acc.byteOffset or 0
    offset = bv_offset + acc_offset
    count  = acc.count

    _, csize, np_type = COMPONENT_TYPES[acc.componentType]
    ncomp = TYPE_COUNTS[acc.type]
    stride = bv.byteStride if bv.byteStride else csize * ncomp

    result = np.zeros((count, ncomp), dtype=np_type)
    for i in range(count):
        base = offset + i * stride
        vals = struct.unpack_from(f"{ncomp}{'bBhHIf'[list(COMPONENT_TYPES.keys()).index(acc.componentType)]}", raw_bin, base)
        result[i] = vals

    if ncomp == 1:
        return result.reshape(-1)
    return result


def read_accessor_float(gltf, raw_bin, accessor_idx):
    """Lê accessor e converte para float32."""
    acc = gltf.accessors[accessor_idx]
    bv  = gltf.bufferViews[acc.bufferView]

    bv_offset  = bv.byteOffset  or 0
    acc_offset = acc.byteOffset or 0
    offset = bv_offset + acc_offset
    count  = acc.count

    ctype_char, csize, _ = COMPONENT_TYPES[acc.componentType]
    ncomp  = TYPE_COUNTS[acc.type]
    stride = bv.byteStride if bv.byteStride else csize * ncomp

    result = []
    for i in range(count):
        base = offset + i * stride
        vals = struct.unpack_from(f"{ncomp}{ctype_char}", raw_bin, base)
        result.append(vals)
    arr = np.array(result, dtype=np.float32)
    if ncomp == 1:
        return arr.reshape(-1)
    return arr


def get_raw_bin(gltf):
    """Devolve os bytes binários do buffer 0."""
    buf = gltf.buffers[0]
    if buf.uri and buf.uri.startswith("data:"):
        _, data = buf.uri.split(",", 1)
        return bytearray(base64.b64decode(data))
    return bytearray(gltf.binary_blob())


# ---------------------------------------------------------------------------
# Identificação dos ossos Quaternius no GLB
# ---------------------------------------------------------------------------

def build_name_to_node(gltf):
    """Devolve {node_name: node_index}."""
    return {(node.name or f"_node_{i}"): i for i, node in enumerate(gltf.nodes)}


def match_target_bones(gltf, joint_nodes):
    """
    Para cada osso alvo em TARGET_BONES_DEF, encontra o node_index no GLB.
    Devolve:
      target_node[canonical_name] = node_index  (ou None se não encontrado)
    """
    name_to_node = build_name_to_node(gltf)
    target_node = {}

    for canonical, variants in TARGET_BONES_DEF:
        found = None
        for v in variants:
            if v in name_to_node:
                found = name_to_node[v]
                break
        # Tentativa case-insensitive se não encontrado
        if found is None:
            low = {k.lower(): v for k, v in name_to_node.items()}
            for v in variants:
                if v.lower() in low:
                    found = low[v.lower()]
                    break
        target_node[canonical] = found

    return target_node


def build_skin_hierarchy(gltf, joint_nodes):
    """
    Devolve:
      skin_parent[si] = si do pai dentro da skin (ou -1 se raiz)
      node_to_si[node_idx] = si
    """
    node_to_si = {nidx: si for si, nidx in enumerate(joint_nodes)}
    skin_parent = {}
    for si, nidx in enumerate(joint_nodes):
        parent_si = -1
        for other_si, other_nidx in enumerate(joint_nodes):
            node = gltf.nodes[other_nidx]
            if node.children and nidx in node.children:
                parent_si = other_si
                break
        skin_parent[si] = parent_si
    return skin_parent, node_to_si


def find_kept_ancestor(si, skin_parent, kept_si_set):
    """
    Sobe na hierarquia a partir de si até encontrar um antecessor em kept_si_set.
    Devolve o si do antecessor mais próximo, ou None se não existir.
    """
    current = skin_parent.get(si, -1)
    while current != -1:
        if current in kept_si_set:
            return current
        current = skin_parent.get(current, -1)
    return None


# ---------------------------------------------------------------------------
# Operações de matriz column-major
# ---------------------------------------------------------------------------

def mat4_identity():
    m = np.eye(4, dtype=np.float64)
    return m


def mat4_from_trs_np(t, r, s):
    """Constrói matriz 4×4 column-major (como array numpy 4×4 column-major)."""
    x, y, z, w = float(r[0]), float(r[1]), float(r[2]), float(r[3])
    n = math.sqrt(x*x + y*y + z*z + w*w)
    if n > 1e-8:
        x, y, z, w = x/n, y/n, z/n, w/n
    sx, sy, sz = float(s[0]), float(s[1]), float(s[2])

    # Construir em row-major depois transpor para column-major
    R = np.array([
        [(1-2*(y*y+z*z))*sx, (2*(x*y-z*w))*sy,   (2*(x*z+y*w))*sz,   float(t[0])],
        [(2*(x*y+z*w))*sx,   (1-2*(x*x+z*z))*sy, (2*(y*z-x*w))*sz,   float(t[1])],
        [(2*(x*z-y*w))*sx,   (2*(y*z+x*w))*sy,   (1-2*(x*x+y*y))*sz, float(t[2])],
        [0.0,                 0.0,                 0.0,                 1.0],
    ], dtype=np.float64)
    return R


def global_transform(gltf, node_idx, raw_bin=None):
    """
    Calcula a transformação global de node_idx acumulando a hierarquia.
    Retorna numpy 4×4 (row-major, compatível com @ de numpy).
    """
    chain = []
    current = node_idx
    # Construir mapa filho→pai para todos os nós
    parent_map = {}
    for i, node in enumerate(gltf.nodes):
        if node.children:
            for child in node.children:
                parent_map[child] = i

    while current is not None:
        chain.append(current)
        current = parent_map.get(current, None)

    chain.reverse()
    M = np.eye(4, dtype=np.float64)
    for nidx in chain:
        node = gltf.nodes[nidx]
        t = list(node.translation) if node.translation else [0.0, 0.0, 0.0]
        r = list(node.rotation)    if node.rotation    else [0.0, 0.0, 0.0, 1.0]
        s = list(node.scale)       if node.scale       else [1.0, 1.0, 1.0]
        M = M @ mat4_from_trs_np(t, r, s)
    return M


# ---------------------------------------------------------------------------
# Retargeting principal
# ---------------------------------------------------------------------------

def retarget(input_path, output_path):
    print(f"A carregar: {input_path}")
    gltf = GLTF2().load(input_path)
    raw_bin = get_raw_bin(gltf)

    if not gltf.skins:
        print("ERRO: GLB sem skin — nada a fazer.")
        sys.exit(1)

    skin = gltf.skins[0]
    joint_nodes = list(skin.joints)
    n_original  = len(joint_nodes)
    print(f"  Esqueleto original: {n_original} ossos")

    # Listar nomes para diagnóstico
    print("  Ossos no GLB:")
    for si, nidx in enumerate(joint_nodes):
        name = gltf.nodes[nidx].name or f"_node_{nidx}"
        print(f"    [{si:2d}] {name}")

    # --- 1. Mapear ossos alvo ---
    target_node = match_target_bones(gltf, joint_nodes)
    skin_parent, node_to_si = build_skin_hierarchy(gltf, joint_nodes)

    print("\n  Mapeamento alvo → GLB:")
    kept_node_idxs = []   # node_index de cada osso alvo encontrado, pela ordem TARGET_BONES_DEF
    kept_canonicals = []  # nome canónico correspondente

    for canonical, _ in TARGET_BONES_DEF:
        nidx = target_node.get(canonical)
        if nidx is not None and nidx in node_to_si:
            kept_node_idxs.append(nidx)
            kept_canonicals.append(canonical)
            print(f"    {canonical:14s} → {gltf.nodes[nidx].name} (node {nidx})")
        else:
            print(f"    {canonical:14s} → NÃO ENCONTRADO (será omitido)")

    n_kept = len(kept_node_idxs)
    print(f"\n  Ossos mantidos: {n_kept} / 24")

    if n_kept == 0:
        print("ERRO: nenhum osso alvo encontrado — verificar nomes no GLB.")
        sys.exit(1)

    if n_kept > 24:
        print(f"ERRO: {n_kept} ossos mapeados excedem o limite de 24.")
        sys.exit(1)

    # --- 2. Construir mapeamento old_si → new_si ---
    # kept_si_set: conjunto dos si originais que ficam
    kept_si_set = {node_to_si[nidx] for nidx in kept_node_idxs if nidx in node_to_si}

    # old_si_to_new[old_si] = new_si  (para os ossos mantidos)
    old_si_to_new = {}
    for new_si, nidx in enumerate(kept_node_idxs):
        old_si = node_to_si[nidx]
        old_si_to_new[old_si] = new_si

    # Para ossos eliminados: old_si → new_si do antecessor conservado mais próximo
    redirect = {}  # old_si → new_si efectivo
    for old_si in range(n_original):
        if old_si in old_si_to_new:
            redirect[old_si] = old_si_to_new[old_si]
        else:
            ancestor_si = find_kept_ancestor(old_si, skin_parent, kept_si_set)
            if ancestor_si is not None:
                redirect[old_si] = old_si_to_new[ancestor_si]
            else:
                # Cair no osso 0 (raiz)
                redirect[old_si] = 0

    # --- 3. Reescrever JOINTS_0 e WEIGHTS_0 para todos os meshes ---
    print("\n  A reescrever pesos dos vértices...")

    # Precisamos de reconstruir o buffer completo com os novos dados.
    # Estratégia: ler todos os accessors relevantes, modificar, reescrever o GLB.

    # Recolher todos os pares (JOINTS_0, WEIGHTS_0) que precisam de ser reescritos
    # e os seus novos valores.
    new_joints_map = {}   # accessor_idx_joints → novo array uint8 (count, 4)
    new_weights_map = {}  # accessor_idx_weights → novo array float32 (count, 4)

    for mesh in gltf.meshes:
        for prim in mesh.primitives:
            ja = getattr(prim.attributes, "JOINTS_0",  None)
            wa = getattr(prim.attributes, "WEIGHTS_0", None)
            if ja is None or wa is None:
                continue

            joints_raw  = read_accessor_float(gltf, raw_bin, ja).astype(np.int32)
            weights_raw = read_accessor_float(gltf, raw_bin, wa)
            count = len(joints_raw)

            new_joints  = np.zeros((count, 4), dtype=np.uint8)
            new_weights = np.zeros((count, 4), dtype=np.float32)

            for vi in range(count):
                # Acumular pesos por new_si
                accum = {}
                for k in range(4):
                    old_si = int(joints_raw[vi][k])
                    w      = float(weights_raw[vi][k])
                    if w < 1e-7:
                        continue
                    if old_si < 0 or old_si >= n_original:
                        continue
                    new_si = redirect.get(old_si, 0)
                    accum[new_si] = accum.get(new_si, 0.0) + w

                # Ordenar por peso descendente, manter top-4
                sorted_items = sorted(accum.items(), key=lambda x: -x[1])[:4]
                total = sum(w for _, w in sorted_items)

                for k, (new_si, w) in enumerate(sorted_items):
                    new_joints[vi][k]  = new_si & 0xFF
                    new_weights[vi][k] = w / total if total > 1e-7 else (1.0 if k == 0 else 0.0)

                # Se não há pesos, ligar ao osso 0
                if not sorted_items:
                    new_joints[vi][0]  = 0
                    new_weights[vi][0] = 1.0

            new_joints_map[ja]  = new_joints
            new_weights_map[wa] = new_weights

    # --- 4. Calcular nova skin: joint_nodes e inverseBindMatrices ---
    new_joint_nodes = kept_node_idxs  # node_index de cada osso novo

    # IBM: inverse da transformação global de bind de cada osso
    new_ibms = []
    for new_si, nidx in enumerate(new_joint_nodes):
        G = global_transform(gltf, nidx, raw_bin)
        try:
            IBM = np.linalg.inv(G)
        except np.linalg.LinAlgError:
            print(f"  [AVISO] IBM singular para '{gltf.nodes[nidx].name}' — a usar identidade.")
            IBM = np.eye(4, dtype=np.float64)
        new_ibms.append(IBM)

    # --- 5. Actualizar animações ---
    # Remover canais que referenciam ossos eliminados (não nos new_joint_nodes)
    kept_node_set = set(new_joint_nodes)
    print(f"\n  A filtrar animações...")

    for anim in gltf.animations:
        kept_channels = []
        for channel in anim.channels:
            if channel.target.node is None:
                continue
            if channel.target.node in kept_node_set:
                kept_channels.append(channel)
        removed = len(anim.channels) - len(kept_channels)
        if removed:
            print(f"    '{anim.name}': removidos {removed} canais de ossos eliminados")
        anim.channels = kept_channels

    # --- 6. Reconstruir o buffer GLB ---
    # Vamos construir um novo buffer com os dados modificados.
    # Para simplicidade: extrair todos os bufferViews existentes,
    # substituir os que foram modificados, e reembalar.

    print("\n  A reconstruir buffer GLB...")

    # Converter IBM para flat column-major float32 (como GLTF espera)
    # IBM_gltf[i] = flat 16 floats column-major = IBM[i].T.flatten() (numpy é row-major)
    ibm_flat = np.zeros((n_kept, 16), dtype=np.float32)
    for i, IBM in enumerate(new_ibms):
        # GLTF MAT4 é column-major: elemento (r,c) → offset r + c*4
        # numpy array IBM[r,c], para column-major flat: IBM.T.flatten()
        ibm_flat[i] = IBM.T.flatten().astype(np.float32)

    # Reconstruir o GLB com pygltflib
    # A abordagem mais segura: modificar gltf in-place e chamar gltf.save()

    # 6a. Actualizar a skin
    skin.joints = new_joint_nodes

    # 6b. Escrever novos accessors para IBM, JOINTS_0, WEIGHTS_0
    # Para isso, precisamos de adicionar novos bufferViews e accessors,
    # e actualizar o buffer.

    # Recolher dados novos para incluir no buffer
    new_buffer_parts = []   # lista de (bytes, accessor_idx_to_update, bv_idx_novo)

    def pack_float32_array(arr):
        """Converte numpy array para bytes little-endian float32."""
        return arr.astype(np.float32).tobytes()

    def pack_uint8_array(arr):
        return arr.astype(np.uint8).tobytes()

    # Começar com o binário original para preservar texturas e geometria
    # mas vamos reconstruir completamente o buffer dados os dados modificados.

    # Usar a abordagem de converter para GLB com buffer inlinado:
    # 1. Reembalar todos os bufferViews existentes (exceto os modificados)
    # 2. Adicionar os novos

    # Mapeamento: accessor_idx → novo bufferView + dados
    # Para os accessors que não modificamos, mantemos o byteOffset/byteLength existente.
    # Para os que modificamos, substituímos.

    new_bin = bytearray()
    new_bv_offsets = {}  # bv_idx → novo byteOffset em new_bin

    # Identificar bufferViews que precisam de ser substituídos
    modified_bv = set()
    for acc_idx in list(new_joints_map.keys()) + list(new_weights_map.keys()):
        acc = gltf.accessors[acc_idx]
        if acc.bufferView is not None:
            modified_bv.add(acc.bufferView)

    # IBM accessor e bufferView (criar novos)
    ibm_bytes  = ibm_flat.tobytes()
    ibm_bv_idx = len(gltf.bufferViews)
    ibm_acc_idx = len(gltf.accessors)

    # Copiar bufferViews não modificados
    for bv_idx, bv in enumerate(gltf.bufferViews):
        if bv_idx in modified_bv:
            new_bv_offsets[bv_idx] = None  # será substituído
            continue
        # Copiar dados originais
        start = bv.byteOffset or 0
        length = bv.byteLength
        chunk = raw_bin[start:start+length]
        # Alinhar a 4 bytes
        while len(new_bin) % 4 != 0:
            new_bin += b'\x00'
        new_bv_offsets[bv_idx] = len(new_bin)
        new_bin += chunk

    # Escrever bufferViews modificados (joints e weights)
    new_acc_bv = {}  # accessor_idx → novo bv_idx efectivo
    for acc_idx, new_data in list(new_joints_map.items()) + \
                             [(k, v) for k, v in new_weights_map.items()]:
        is_joints  = acc_idx in new_joints_map
        is_weights = acc_idx in new_weights_map
        if is_joints:
            data_bytes = pack_uint8_array(new_joints_map[acc_idx])
        else:
            data_bytes = pack_float32_array(new_weights_map[acc_idx])

        while len(new_bin) % 4 != 0:
            new_bin += b'\x00'
        new_offset = len(new_bin)
        new_bin += data_bytes

        # Criar novo bufferView
        from pygltflib import BufferView as BV
        new_bv = BV()
        new_bv.buffer = 0
        new_bv.byteOffset = new_offset
        new_bv.byteLength = len(data_bytes)
        new_bv.byteStride = None
        new_bv.target = 34963  # ELEMENT_ARRAY_BUFFER para joints/weights

        gltf.bufferViews.append(new_bv)
        new_bv_local_idx = len(gltf.bufferViews) - 1
        new_acc_bv[acc_idx] = new_bv_local_idx

    # Escrever IBM bufferView
    while len(new_bin) % 4 != 0:
        new_bin += b'\x00'
    ibm_offset = len(new_bin)
    new_bin += ibm_bytes

    from pygltflib import BufferView as BV, Accessor as AC
    ibm_bv = BV()
    ibm_bv.buffer      = 0
    ibm_bv.byteOffset  = ibm_offset
    ibm_bv.byteLength  = len(ibm_bytes)
    ibm_bv.byteStride  = None
    ibm_bv.target      = None
    gltf.bufferViews.append(ibm_bv)
    ibm_bv_real_idx = len(gltf.bufferViews) - 1

    # Actualizar byteOffsets dos bufferViews não modificados
    for bv_idx, bv in enumerate(gltf.bufferViews):
        if bv_idx in new_bv_offsets and new_bv_offsets[bv_idx] is not None:
            bv.byteOffset = new_bv_offsets[bv_idx]
            bv.buffer = 0

    # Actualizar accessors modificados
    for acc_idx in list(new_joints_map.keys()):
        acc = gltf.accessors[acc_idx]
        data = new_joints_map[acc_idx]
        acc.bufferView  = new_acc_bv[acc_idx]
        acc.byteOffset  = 0
        acc.count       = len(data)
        acc.type        = "VEC4"
        acc.componentType = 5121  # UNSIGNED_BYTE
        acc.normalized  = False
        acc.min = None; acc.max = None

    for acc_idx in list(new_weights_map.keys()):
        acc = gltf.accessors[acc_idx]
        data = new_weights_map[acc_idx]
        acc.bufferView  = new_acc_bv[acc_idx]
        acc.byteOffset  = 0
        acc.count       = len(data)
        acc.type        = "VEC4"
        acc.componentType = 5126  # FLOAT
        acc.normalized  = False
        acc.min = None; acc.max = None

    # Criar accessor IBM
    ibm_acc = AC()
    ibm_acc.bufferView    = ibm_bv_real_idx
    ibm_acc.byteOffset    = 0
    ibm_acc.count         = n_kept
    ibm_acc.type          = "MAT4"
    ibm_acc.componentType = 5126  # FLOAT
    ibm_acc.normalized    = False
    gltf.accessors.append(ibm_acc)
    ibm_acc_real_idx = len(gltf.accessors) - 1

    # Actualizar skin para apontar para o novo IBM accessor
    skin.inverseBindMatrices = ibm_acc_real_idx

    # Actualizar tamanho do buffer
    gltf.buffers[0].byteLength = len(new_bin)
    gltf.buffers[0].uri = None  # GLB inlinado

    # Guardar como GLB com o novo binário
    gltf.set_binary_blob(bytes(new_bin))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    gltf.save(output_path)

    out_size = os.path.getsize(output_path)
    print(f"\n  GLB retargetado: {output_path} ({out_size/1024:.1f} KB)")
    print(f"  Ossos: {n_original} → {n_kept}")
    print("\n  Esqueleto final:")
    for new_si, (canonical, nidx) in enumerate(zip(kept_canonicals, new_joint_nodes)):
        parent_name = TARGET_PARENT.get(canonical, -1)
        print(f"    [{new_si:2d}] {canonical:14s} ← {gltf.nodes[nidx].name}")

    return n_kept


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Retargeting de esqueleto Quaternius 63 → 24 ossos para AXS1/PSP"
    )
    parser.add_argument("input",  help="GLB de entrada (63 ossos)")
    parser.add_argument("output", help="GLB de saída (≤ 24 ossos)")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"ERRO: ficheiro não encontrado: {args.input}")
        sys.exit(1)

    n_kept = retarget(args.input, args.output)

    if n_kept > 24:
        print(f"ERRO: resultado tem {n_kept} ossos — excede o limite de 24.")
        sys.exit(1)

    print(f"\nRetargeting concluído: {n_kept} ossos.")


if __name__ == "__main__":
    main()
