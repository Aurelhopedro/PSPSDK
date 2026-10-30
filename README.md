# 🎮 PSP RPG 3D

RPG 3D de exploração e aventura para a **Sony PSP**, desenvolvido em C/C++ com PSPSDK.

---

## 📋 Sobre o Projeto

Um RPG de exploração em mundo aberto construído nativamente para a PSP, sem depender de funcionalidades exclusivas de hardware moderno. Compatível com PSP real e com o emulador PPSSPP.

---

## 🗂️ Estrutura do Projeto

```
PSPSDK/
├── src/
│   ├── main.c              # Ponto de entrada da aplicação
│   ├── graphics/           # Motor gráfico (GU / GE)
│   ├── input/              # Gestão de controlos
│   ├── audio/              # Sistema de som
│   └── game/               # Lógica de jogo
│       ├── player/         # Personagem e movimento
│       ├── world/          # Terreno e ambiente
│       ├── entities/       # NPCs e criaturas
│       ├── combat/         # Sistema de combate
│       ├── inventory/      # Inventário e itens
│       └── quests/         # Sistema de missões
├── assets/
│   ├── models/             # Modelos 3D
│   ├── textures/           # Texturas (TGA/PNG convertidas)
│   ├── audio/              # Sons e música
│   └── fonts/              # Fontes bitmap
├── docs/
│   ├── ARCHITECTURE.md     # Documentação técnica
│   ├── PHASES.md           # Plano de fases
│   └── SETUP.md            # Configuração do ambiente
├── .github/
│   └── workflows/
│       └── build.yml       # GitHub Actions — build automático
├── Makefile                # Build principal
└── README.md               # Este ficheiro
```

---

## 🔧 Requisitos

- PSPSDK / pspdev toolchain
- GCC para MIPS (incluído no pspdev)
- Make
- PPSSPP (para testar sem hardware físico)

---

## 🚀 Como Compilar

```bash
# Instalar pspdev (Linux/macOS)
git clone https://github.com/pspdev/pspdev.git
cd pspdev && ./build.sh

# Configurar variáveis de ambiente
export PSPDEV=/usr/local/pspdev
export PATH=$PATH:$PSPDEV/bin

# Compilar o projeto
make

# Output: build/EBOOT.PBP
```

---

## 📅 Fases de Desenvolvimento

| Fase | Estado | Descrição |
|------|--------|-----------|
| FASE 00 | ✅ Concluída | Fundação — estrutura, Makefile, programa inicial |
| FASE 01 | ⏳ Pendente | Motor Gráfico 3D |
| FASE 02 | ⏳ Pendente | Personagem e Movimento |
| FASE 03 | ⏳ Pendente | Primeiro Ambiente |
| FASE 04 | ⏳ Pendente | Sistemas de Jogo |
| FASE 05 | ⏳ Pendente | Conteúdo e História |
| FASE 06 | ⏳ Pendente | Otimização e Lançamento |

---

## 📄 Licença

MIT License
