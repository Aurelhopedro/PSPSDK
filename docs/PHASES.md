# Plano de Fases — RPG Axel Digital

## FASE 00 — Fundação ✅
- [x] Repositório GitHub criado
- [x] Estrutura de pastas definida
- [x] Makefile configurado
- [x] Programa inicial (`main.c`) funcional
- [x] Documentação técnica criada
- [x] GitHub Actions configurado

**Critério de saída**: EBOOT.PBP compila e exibe texto no ecrã.

---

## FASE 01 — Motor Gráfico ⏳
- [x] Inicialização do sistema GU (`sceGuInit`, display list, `sceGuFinish`, `sceGuSync`)
- [x] Setup do framebuffer e double buffering (VRAM_FB0 / VRAM_FB1)
- [x] Z-buffer configurado (VRAM_DEPTH, `sceGuDepthFunc`, `sceGuEnable(GU_DEPTH_TEST)`)
- [x] Viewport e scissor configurados para 480×272
- [x] Sistema de câmara (`camera.h` / `camera.c`) com posição, alvo e up vector
- [x] Matriz de projeção perspetiva via `sceGumPerspective` (FOV 75°, aspect 480/272)
- [x] Matriz de visualização via `sceGumLookAt`
- [x] Cubo 3D com 36 vértices, 6 faces coloridas (`cube.h` / `cube.c`)
- [x] Rotação contínua nos eixos X, Y, Z via `sceGumRotate`
- [x] Ciclo de renderização: limpar → matrizes → desenhar → swap
- [x] Botão X preservado para sair

**Pendente**:
- [ ] Compilação confirmada via GitHub Actions
- [ ] Teste visual confirmado no PPSSPP

**Critério de saída**: cubo 3D rotativo e colorido visível no PPSSPP.

---

## FASE 02 — Personagem ⏳
- [ ] Mesh provisória do personagem (cubo/cápsula)
- [ ] Movimento nos eixos X/Z com analógico esquerdo
- [ ] Câmara em terceira pessoa (follow cam)
- [ ] Rotação do personagem na direção do movimento
- [ ] Gravidade simples
- [ ] Sistema de animação por keyframes

**Critério de saída**: personagem move-se num plano com câmara a seguir.

---

## FASE 03 — Primeiro Ambiente ⏳
- [ ] Terreno plano com textura
- [ ] Heightmap simples (terreno com relevos)
- [ ] Árvores e vegetação (billboards 2D)
- [ ] Estruturas simples (caixas, paredes)
- [ ] Colisões com o terreno (personagem não cai)
- [ ] Colisões com objetos sólidos
- [ ] Área explorável 100×100 unidades

**Critério de saída**: personagem explora uma pequena zona com colisões funcionais.

---

## FASE 04 — Sistemas de Jogo ⏳
- [ ] NPCs estacionários com caixas de diálogo
- [ ] Sistema de diálogo com escolhas
- [ ] Criaturas com IA simples (patrol/attack)
- [ ] Sistema de combate por turnos
- [ ] Inventário com 20 slots
- [ ] Sistema de experiência e níveis
- [ ] Sistema de missões (aceitar, completar, recompensa)

**Critério de saída**: combate funcional e missão completa jogável.

---

## FASE 05 — Conteúdo ⏳
- [ ] História principal (3 atos)
- [ ] 3 regiões distintas
- [ ] 2 civilizações com designs únicos
- [ ] 10+ personagens com diálogo
- [ ] 5+ tipos de criaturas
- [ ] Sistemas de afinidade (reputação por facção)
- [ ] 10+ missões

**Critério de saída**: demonstração jogável com início, meio e fim.

---

## FASE 06 — Finalização ⏳
- [ ] Profiling de memória e CPU
- [ ] Otimização de draw calls
- [ ] Testes completos no PPSSPP
- [ ] Testes em PSP física (PSP-2000 ou 3000)
- [ ] Correção de incompatibilidades de CFW
- [ ] Geração do EBOOT.PBP final
- [ ] Ícone e background para XMB
- [ ] Versão distribuível

**Critério de saída**: jogo funciona em PSP física sem crashes.
