# Relatório de conversão P3D

- Origem: `assets/characters/protagonist/converted/protagonist.obj`
- Saída: `assets/characters/protagonist/converted/protagonist.p3d`
- Formato: `AXP3`, versão `1`
- Vértices: `42954`
- Triângulos: `14318`
- Posições OBJ: `7231`
- UVs OBJ: `7654`
- Normais OBJ: `7102`
- Stride: `32 bytes`
- Tamanho: `1374544 bytes`

Cada vértice contém 8 float32: U, V, normalX, normalY, normalZ, posiçãoX, posiçãoY, posiçãoZ.

Limitações: formato intermédio personalizado; ainda não existe carregador PSP. Não preserva esqueleto, pesos de ossos, animações nem imagens de textura. UVs ausentes recebem zero e normais ausentes são calculadas por triângulo.
