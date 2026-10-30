# Arquitetura Técnica — PSP RPG 3D

## Hardware Alvo

| Componente | Especificação |
|-----------|--------------|
| CPU | MIPS R4000 @ 333 MHz |
| RAM | 32 MB (PSP-1000) / 64 MB (PSP-2000/3000) |
| VRAM | 2 MB (eDRAM embutida na GPU) |
| GPU | PSP GPU (GE — Graphics Engine) |
| Ecrã | 480 × 272 pixels, 16/32 bits por pixel |
| Armazenamento | UMD / Memory Stick |
| Controlos | D-Pad, analógico, 8 botões de ação, triggers L/R |

---

## Sistema de Memória

A PSP tem limitações críticas de memória. Estratégia:

- **Kernel space**: reservado para sistema (alguns MB)
- **User space**: 20–24 MB disponíveis para o jogo
- **VRAM**: 2 MB — texturas e framebuffers
- **Streaming**: carregar/descarregar assets por zona
- **Sem alocação dinâmica excessiva**: usar pools de memória

---

## Pipeline Gráfico

A PSP usa a **GE (Graphics Engine)** através da biblioteca **GU** do PSPSDK:

```
Jogo → Display List → GE (GPU) → Framebuffer → Ecrã
```

- **Display Lists**: comandos pré-compilados enviados à GE
- **Double buffering**: dois framebuffers alternados (draw/display)
- **Formatos de textura**: PSM_8888, PSM_5650, PSM_5551, PSM_4444
- **Modos de rendering**: 2D sprites, 3D transformado, vertex colors

---

## Módulos do PSPSDK Utilizados

| Biblioteca | Propósito |
|-----------|-----------|
| `pspkernel` | Threads, callbacks, módulos |
| `pspdisplay` | VSync, framebuffer |
| `pspge` | Display lists, GPU control |
| `pspgu` | API gráfica de alto nível |
| `pspgum` | Transformações 3D (matrices) |
| `pspctrl` | Leitura de controlos |
| `pspaudio` | Reprodução de som |
| `pspiofilemgr` | Leitura de ficheiros do Memory Stick |

---

## Convenções de Código

- Linguagem: **C99** (compatibilidade máxima)
- Nomenclatura: `snake_case` para funções e variáveis
- Prefixos por módulo: `gfx_`, `input_`, `audio_`, `game_`
- Comentários: Português (PT)
- Máximo de 80 caracteres por linha
- Sem stdlib pesada — usar funções PSP nativas quando possível

---

## Limites de Performance

- **60 FPS** em modo 2D/UI
- **30 FPS** como alvo para cenas 3D
- Máximo de **~2000 polígonos** visíveis por frame (sem LOD)
- Texturas: máximo **512×512** (mas preferir 128×128 ou 256×256)
- **Nenhum float de dupla precisão** — usar `float` sempre
