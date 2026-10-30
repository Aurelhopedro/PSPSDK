# Configuração do Ambiente — PSP RPG 3D

## 1. Instalar pspdev (Toolchain Oficial)

### Linux / macOS
```bash
git clone https://github.com/pspdev/pspdev.git
cd pspdev
./build.sh
```

### Windows (via WSL2)
```bash
# Instalar WSL2 com Ubuntu
wsl --install
# Depois seguir os passos de Linux
```

### Docker (recomendado para CI)
```bash
docker pull pspdev/pspdev:latest
docker run -v $(pwd):/build pspdev/pspdev:latest make
```

---

## 2. Configurar Variáveis de Ambiente

```bash
export PSPDEV=/usr/local/pspdev
export PATH=$PATH:$PSPDEV/bin:$PSPDEV/psp/bin
```

Adicionar ao `~/.bashrc` ou `~/.zshrc` para persistir.

---

## 3. Verificar Instalação

```bash
psp-gcc --version
# Deve mostrar: psp-gcc (GCC) X.X.X
```

---

## 4. Compilar o Projeto

```bash
git clone https://github.com/Aurelhopedro/PSPSDK.git
cd PSPSDK
make
```

Output esperado:
```
psp-gcc -O2 -G0 -Wall -DPSP -c src/main.c -o src/main.o
psp-gcc src/main.o -o psp_rpg.elf [libs...]
mksfo "PSP RPG 3D" PARAM.SFO
pack-pbp EBOOT.PBP PARAM.SFO NULL NULL NULL NULL NULL psp_rpg.elf NULL
```

---

## 5. Testar com PPSSPP

1. Descarregar PPSSPP: https://www.ppsspp.org/
2. Abrir PPSSPP
3. Selecionar `EBOOT.PBP` gerado
4. O jogo deve arrancar

---

## 6. Testar em PSP Real

1. Garantir que a PSP tem Custom Firmware (CFW) instalado
2. Copiar pasta do projeto para:
   ```
   ms0:/PSP/GAME/PSP_RPG/EBOOT.PBP
   ```
3. Ligar a PSP → XMB → Game → Memory Stick

---

## Ferramentas Opcionais

| Ferramenta | Propósito |
|-----------|-----------|
| PPSSPP | Emulador para testes rápidos |
| psp-readelf | Inspecionar binários ELF |
| psp-objdump | Disassembly |
| ProDG (Sony) | Debugger oficial (acesso limitado) |
